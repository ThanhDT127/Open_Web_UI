"""
Access log summary and stream endpoints for HTTP access monitoring.
Primary: queries mw_request_log DB table. Fallback: reads middleware.requests.log file.
"""

import os
import json
import datetime as dt
from typing import Dict, Any, Optional, List
from collections import defaultdict
from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse
import asyncio

from config import MW_DETAIL_LOG_FILE, LOG_DIR


def _db_available() -> bool:
    try:
        from core.db import _pool
        return _pool is not None
    except Exception:
        return False


def get_access_summary(
    request: Request,
    minutes: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    source: Optional[str] = None,
):
    """
    Access log summary: Aggregate from mw_request_log DB or middleware.requests.log file.
    """
    from utils.auth_guard import require_admin_or_session
    from api.summary_v2 import _resolve_range
    require_admin_or_session(request)

    # Shared resolver — this file used to carry the fifth copy of it. The private copy
    # and the shared one disagreed on malformed input, silently. `minutes=60` is passed
    # explicitly so the historical default window is preserved.
    cutoff, end_time, _bucket = _resolve_range(
        minutes=60 if minutes is None else minutes, start=start, end=end
    )

    if source is not None and source not in ("db", "file"):
        raise HTTPException(400, "source must be 'db' or 'file'")

    # The file store is still reachable, but only when it is *asked for*. It covers
    # different rows and different retention than the DB, so falling back to it on a DB
    # error made this tab quietly disagree with every other tab on the same window.
    if source == "file":
        return _access_summary_file(cutoff, end_time)

    if not _db_available():
        # No DB configured at all. That is a deployment fact, not a failure being hidden.
        return _access_summary_file(cutoff, end_time)

    # DB configured: a read failure is an outage. Let it raise so the tab can say so.
    return _access_summary_db(cutoff, end_time)


# The service's own liveness probe. Its failures are the container examining itself,
# not a user meeting an error, and they outnumber real faults roughly 7:1.
HEALTH_PROBE_PATH = "/health"


def _new_acc() -> Dict[str, Any]:
    return {
        "by_path": defaultdict(int),
        "by_path_errors": defaultdict(int),
        "by_status": defaultdict(int),
        "by_method": defaultdict(int),
        "latencies": [],
        "requests_total": 0,
        "error_count": 0,
        # Four disjoint groups covering every status >= 400. Each maps to one repair
        # action: call someone / review an access decision / raise a limit / ignore.
        "failures": 0,        # 5xx, excluding the liveness probe
        "denied": 0,          # 401, 403
        "throttled": 0,       # 429
        "other_client": 0,    # remaining 4xx
        "health_probe_failures": 0,  # 5xx on the liveness probe
        # Rejected sign-ins at the dashboard door specifically. Staff sign-ins are routed
        # by nginx to Open WebUI and never reach this service, so this figure cannot
        # carry that signal — which is why its label must keep the word "dashboard".
        "failed_dashboard_logins": 0,
    }


DASHBOARD_LOGIN_PATH = "/v1/_mw/dashboard/login"


def _add_record(acc: Dict[str, Any], path, status, method, ms) -> None:
    """Fold one outbound record into the accumulator. Single place where a status is
    classified, so the DB path and the file path cannot drift apart."""
    acc["requests_total"] += 1
    path = path or "unknown"
    acc["by_path"][path] += 1
    acc["by_status"][status] += 1
    acc["by_method"][method or "unknown"] += 1

    # `if ms:` dropped both the records missing a duration AND the genuinely fastest
    # ones (ms == 0), quietly shrinking the percentile's sample.
    if ms is not None:
        acc["latencies"].append(ms)

    if not isinstance(status, int) or status < 400:
        return

    acc["error_count"] += 1
    acc["by_path_errors"][path] += 1

    if path == DASHBOARD_LOGIN_PATH:
        acc["failed_dashboard_logins"] += 1

    if status >= 500:
        if path == HEALTH_PROBE_PATH:
            acc["health_probe_failures"] += 1
        else:
            acc["failures"] += 1
    elif status in (401, 403):
        acc["denied"] += 1
    elif status == 429:
        acc["throttled"] += 1
    else:
        acc["other_client"] += 1


def _access_summary_db(cutoff, end_time):
    """Aggregate access stats from mw_request_log table."""
    from core.db import db_conn

    acc = _new_acc()

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT payload FROM mw_request_log
            WHERE ts >= %s AND ts <= %s
        """, (cutoff, end_time))
        rows = cur.fetchall()
        cur.close()

    for (payload,) in rows:
        if not isinstance(payload, dict):
            continue
        if payload.get("event") != "outbound":
            continue
        _add_record(acc, payload.get("path"), payload.get("status", 500),
                    payload.get("method"), payload.get("ms"))

    return _format_access_result(cutoff, end_time, acc, "database")


def _access_summary_file(cutoff, end_time):
    """Fallback: aggregate from middleware.requests.log files."""
    if not os.path.exists(MW_DETAIL_LOG_FILE):
        return {"error": "middleware.requests.log not found", "data": []}

    acc = _new_acc()

    try:
        for log_file in _get_access_log_files():
            if not os.path.exists(log_file):
                continue
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        event_type = entry.get("event")
                        if event_type not in ("inbound", "outbound"):
                            continue
                        ts_str = entry.get("ts", "")
                        if not ts_str:
                            continue
                        entry_time = dt.datetime.fromisoformat(ts_str)
                        if entry_time < cutoff or entry_time > end_time:
                            continue
                        if event_type == "outbound":
                            _add_record(acc, entry.get("path"), entry.get("status", 500),
                                        entry.get("method"), entry.get("ms"))
                    except Exception:
                        continue
    except Exception as e:
        return {"error": str(e)}

    return _format_access_result(cutoff, end_time, acc, "file")


def _format_access_result(cutoff, end_time, acc, source):
    """Format access summary results."""
    requests_total = acc["requests_total"]
    latencies = acc["latencies"]
    by_path = acc["by_path"]
    by_path_errors = acc["by_path_errors"]

    def _rate(n: int) -> float:
        return round(n / requests_total * 100, 2) if requests_total > 0 else 0.0

    # breakdown_by_path is cut to the 20 busiest paths, so the per-path error counts on
    # their own cannot reconcile with error_count. Carry the remainder rather than let a
    # reader conclude the difference is unaccounted for. (Same [:20] trap Phase 1 and
    # Phase 4 hit with top10_pct_cost_share.)
    _top_paths = sorted(by_path.items(), key=lambda x: x[1], reverse=True)[:20]
    _top_path_names = {p for p, _ in _top_paths}
    _errors_outside_top = sum(n for p, n in by_path_errors.items() if p not in _top_path_names)

    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    p95_latency = None
    if latencies:
        latencies.sort()
        idx = min(int(len(latencies) * 0.95), len(latencies) - 1)
        p95_latency = latencies[idx]

    return {
        "time_range": {"start": cutoff.isoformat(), "end": end_time.isoformat()},
        "totals": {
            "requests_total": requests_total,
            "error_count": acc["error_count"],
            "error_rate_percent": _rate(acc["error_count"]),
            # Three groups, three repair actions. `other_client_errors` and
            # `health_probe_failures` are carried so the five add up to `error_count`
            # exactly — no row counted twice, none dropped.
            "failures": acc["failures"],
            "failure_rate_percent": _rate(acc["failures"]),
            "denied": acc["denied"],
            "denied_rate_percent": _rate(acc["denied"]),
            "throttled": acc["throttled"],
            "throttled_rate_percent": _rate(acc["throttled"]),
            "other_client_errors": acc["other_client"],
            "health_probe_failures": acc["health_probe_failures"],
            "failed_dashboard_logins": acc["failed_dashboard_logins"],
            "avg_latency_ms": round(avg_latency, 2),
            # `if p95_latency` turned a genuine 0 ms percentile into "no data".
            "p95_latency_ms": round(p95_latency, 2) if p95_latency is not None else None,
            # Records without a duration never reach the percentile, so its sample base
            # is smaller than requests_total. Disclose it rather than imply full coverage.
            "latency_sample_count": len(latencies),
            "errors_outside_top_paths": _errors_outside_top,
        },
        "breakdown_by_path": [
            {
                "path": p,
                "count": c,
                "errors": by_path_errors.get(p, 0),
                "error_rate_percent": round(by_path_errors.get(p, 0) / c * 100, 2) if c else 0.0,
            }
            for p, c in _top_paths
        ],
        "breakdown_by_status": [{"status": s, "count": c} for s, c in sorted(acc["by_status"].items(), key=lambda x: x[1], reverse=True)],
        "breakdown_by_method": [{"method": m, "count": c} for m, c in sorted(acc["by_method"].items(), key=lambda x: x[1], reverse=True)],
        "source": source,
    }


async def stream_access(request: Request):
    """
    SSE Stream for access log. Uses DB polling if available, file tailing otherwise.
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    if _db_available():
        gen = _db_access_generator(request)
    else:
        gen = _file_access_generator(request)

    return StreamingResponse(
        gen, media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


async def _db_access_generator(request: Request):
    """Poll mw_request_log table for new access events."""
    from core.db import db_conn

    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, payload FROM mw_request_log ORDER BY id DESC LIMIT 50")
            rows = cur.fetchall()
            cur.close()

        last_id = 0
        for r in reversed(rows):
            last_id = max(last_id, r[0])
            yield f"event: access\ndata: {json.dumps(r[1], ensure_ascii=False)}\n\n"
    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        return

    while True:
        if await request.is_disconnected():
            break
        try:
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id, payload FROM mw_request_log WHERE id > %s ORDER BY id ASC", (last_id,))
                new_rows = cur.fetchall()
                cur.close()
            for r in new_rows:
                last_id = max(last_id, r[0])
                yield f"event: access\ndata: {json.dumps(r[1], ensure_ascii=False)}\n\n"
        except Exception:
            pass
        yield ": keepalive\n\n"
        await asyncio.sleep(2)


async def _file_access_generator(request: Request):
    """Fallback: tail middleware.requests.log."""
    if not os.path.exists(MW_DETAIL_LOG_FILE):
        yield f"event: error\ndata: {json.dumps({'error': 'middleware.requests.log not found'})}\n\n"
        return

    try:
        with open(MW_DETAIL_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines[-50:]:
                if line.strip():
                    yield f"event: access\ndata: {line.strip()}\n\n"
    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    last_size = os.path.getsize(MW_DETAIL_LOG_FILE)
    while True:
        if await request.is_disconnected():
            break
        try:
            current_size = os.path.getsize(MW_DETAIL_LOG_FILE)
            if current_size < last_size:
                last_size = 0
                with open(MW_DETAIL_LOG_FILE, "r", encoding="utf-8") as f:
                    for line in f.readlines():
                        if line.strip():
                            yield f"event: access\ndata: {line.strip()}\n\n"
                last_size = current_size
            elif current_size > last_size:
                with open(MW_DETAIL_LOG_FILE, "r", encoding="utf-8") as f:
                    f.seek(last_size)
                    for line in f.readlines():
                        if line.strip():
                            yield f"event: access\ndata: {line.strip()}\n\n"
                last_size = current_size
        except FileNotFoundError:
            yield f"event: error\ndata: {json.dumps({'error': 'file not found'})}\n\n"
            break
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
            break
        yield ": keepalive\n\n"
        await asyncio.sleep(2)


def _get_access_log_files() -> List[str]:
    """Get list of access log files (main + rotated)."""
    files = [MW_DETAIL_LOG_FILE]
    for i in range(1, 11):
        rotated = f"{MW_DETAIL_LOG_FILE}.{i}"
        if os.path.exists(rotated):
            files.append(rotated)
    files.sort(key=lambda f: os.path.getmtime(f) if os.path.exists(f) else 0, reverse=True)
    return files[:10]
