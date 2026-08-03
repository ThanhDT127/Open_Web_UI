"""
Adoption endpoint (Phase 4) — User/Account adoption metrics for an internal tool.

Touches two data domains that must not be confused:
  - ACTIVITY (mw_audit_log, window-scoped): reused from compute_usage_summary.
  - ROSTER  (mw_users, whole-table snapshot): queried directly here.

Design: openspec/changes/dashboard-adoption/design.md. compute_usage_summary is
reused, never modified — the DAU/WAU series comes from its own grouped (day,user)
query (D2) so the shared aggregation stays untouched.
"""

import datetime as dt
from typing import Dict, Any, Optional, List
from fastapi import Request

from config import logger
from api.summary_v2 import _resolve_range, compute_usage_summary, _db_available


# Dormant threshold: an account whose last activity is older than this is "stopped".
# One month — long enough that a genuinely-abandoned account, not an occasional user,
# lands in the list. Configurable here without redeploying logic (design D5).
DORMANT_THRESHOLD_DAYS = 30

# Trailing window for WAU (weekly active users), in days.
WAU_WINDOW_DAYS = 7


def _roster_rows() -> List[Dict[str, Any]]:
    """Provisioned accounts (soft-delete keeps the row; deleted_at IS NULL = current).

    Operational deletion is soft, so this is the honest "currently provisioned" set
    (see memory: middleware-soft-delete-only). DB-only; [] if unavailable.
    """
    if not _db_available():
        return []
    try:
        from core.db import db_conn
        rows = []
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT user_id, created_at, active, quota "
                "FROM mw_users WHERE deleted_at IS NULL"
            )
            for r in cur.fetchall():
                rows.append({
                    "user_id": r[0],
                    "created_at": r[1],
                    "active": bool(r[2]) if r[2] is not None else True,
                    "quota": r[3] if isinstance(r[3], dict) else {},
                })
            cur.close()
        return rows
    except Exception:
        logger.error("adoption: roster query failed", exc_info=True)
        return []


def _new_accounts_in_period(cutoff, end_time) -> int:
    """Count accounts provisioned within [cutoff, end_time].

    NOT filtered by deleted_at/active (D4b): a provisioning event that happened in the
    period must keep counting for that period, so later soft-deletes cannot erode past
    comparison windows. Hard purge (legal erasure) is non-operational and out of scope.
    """
    if not _db_available():
        return 0
    try:
        from core.db import db_conn
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT count(*) FROM mw_users WHERE created_at >= %s AND created_at <= %s",
                (cutoff, end_time),
            )
            n = cur.fetchone()[0]
            cur.close()
        return n or 0
    except Exception:
        logger.error("adoption: new-accounts query failed", exc_info=True)
        return 0


def _last_seen_per_user() -> Dict[str, dt.datetime]:
    """user_id -> most recent activity timestamp, whole audit history.

    Immutable audit (survives user deletion), so this is the deletion-proof "last seen".
    """
    if not _db_available():
        return {}
    try:
        from core.db import db_conn
        out: Dict[str, dt.datetime] = {}
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, max(ts) FROM mw_audit_log GROUP BY user_id")
            for uid, last in cur.fetchall():
                if uid:
                    out[uid] = last
            cur.close()
        return out
    except Exception:
        logger.error("adoption: last-seen query failed", exc_info=True)
        return {}


def _daily_user_pairs(start, end) -> Dict[dt.date, set]:
    """Distinct (day, user) pairs over [start, end] -> {date: set(user_id)}.

    Day boundaries pinned to Vietnam time (UTC+7) so a working day is not split across
    UTC midnight (design D4/1.1b). SQL dedupes to (day,user) pairs, keeping the payload
    small even on long ranges. Feeds both DAU and WAU without touching the shared
    aggregation function (D2).
    """
    if not _db_available():
        return {}
    try:
        from core.db import db_conn
        day_sets: Dict[dt.date, set] = {}
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS d, user_id "
                "FROM mw_audit_log WHERE ts >= %s AND ts <= %s "
                "GROUP BY d, user_id",
                (start, end),
            )
            for d, uid in cur.fetchall():
                if d is None or not uid:
                    continue
                day_sets.setdefault(d, set()).add(uid)
            cur.close()
        return day_sets
    except Exception:
        logger.error("adoption: daily-pairs query failed", exc_info=True)
        return {}


def _build_activity_series(cutoff, end_time) -> List[Dict[str, Any]]:
    """DAU + WAU per day for [cutoff, end_time], at day resolution.

    DAU = distinct users that day. WAU = size of the union of the trailing 7 daily
    sets (NOT a sum of DAU — a user active on multiple days is one person). Range
    shorter than a day yields no series (D4).
    """
    if (end_time - cutoff).total_seconds() < 86400:
        return []

    # Extend the left edge so the first visible day still has a full 7-day trail.
    query_start = cutoff - dt.timedelta(days=WAU_WINDOW_DAYS - 1)
    day_sets = _daily_user_pairs(query_start, end_time)
    if not day_sets:
        return []

    start_date = cutoff.date()
    end_date = end_time.date()
    series: List[Dict[str, Any]] = []
    d = start_date
    while d <= end_date:
        dau = len(day_sets.get(d, ()))
        wau_union: set = set()
        for k in range(WAU_WINDOW_DAYS):
            wau_union |= day_sets.get(d - dt.timedelta(days=k), set())
        series.append({"date": d.isoformat(), "dau": dau, "wau": len(wau_union)})
        d += dt.timedelta(days=1)
    return series


def _dormant_accounts(roster: List[Dict[str, Any]], last_seen: Dict[str, dt.datetime],
                      now_utc: dt.datetime) -> Dict[str, Any]:
    """Never-used + stopped accounts from the current roster (D5).

    Whole-roster snapshot, not window-scoped — declared compare:false in the registry.
    """
    threshold = now_utc - dt.timedelta(days=DORMANT_THRESHOLD_DAYS)
    never, stopped = [], []
    for u in roster:
        uid = u["user_id"]
        seen = last_seen.get(uid)
        created = u.get("created_at")
        if seen is None:
            # Never used: measure silence from provisioning date.
            base = created or now_utc
            days_silent = max(0, (now_utc - base).days)
            never.append({
                "user_id": uid,
                "created_at": created.isoformat() if created else None,
                "last_seen": None,
                "days_silent": days_silent,
                "active": u.get("active", True),
            })
        elif seen < threshold:
            days_silent = max(0, (now_utc - seen).days)
            stopped.append({
                "user_id": uid,
                "created_at": created.isoformat() if created else None,
                "last_seen": seen.isoformat(),
                "days_silent": days_silent,
                "active": u.get("active", True),
            })

    rows = never + stopped
    rows.sort(key=lambda x: x["days_silent"], reverse=True)
    return {
        "threshold_days": DORMANT_THRESHOLD_DAYS,
        "never_used_count": len(never),
        "stopped_count": len(stopped),
        "dormant_count": len(rows),
        "accounts": rows,
    }


def _quota_histogram(roster: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-account quota utilization buckets, same formula as get_user_quota_status (D6).

    Bulk read (no per-user call — get_current_quota_user has period-reset side effects).
    Non-positive limit -> its own 'unlimited' bucket, never forced into 0-25 (which would
    inflate the low band with accounts that simply have no cap).
    """
    buckets = {"0-25": 0, "25-50": 0, "50-75": 0, "75-90": 0, ">90": 0, "unlimited": 0}
    for u in roster:
        quota = u.get("quota") or {}
        try:
            limit = float(quota.get("limit_cost_usd", 0) or 0)
            used = float(quota.get("used_cost_usd", 0) or 0)
        except (TypeError, ValueError):
            limit, used = 0.0, 0.0
        if limit <= 0:
            buckets["unlimited"] += 1
            continue
        pct = used / limit * 100
        if pct < 25:
            buckets["0-25"] += 1
        elif pct < 50:
            buckets["25-50"] += 1
        elif pct < 75:
            buckets["50-75"] += 1
        elif pct < 90:
            buckets["75-90"] += 1
        else:
            buckets[">90"] += 1
    return buckets


def compute_adoption(cutoff, end_time, bucket_size: str) -> Dict[str, Any]:
    """Assemble the adoption payload. Pure — no Request, no auth, no HTTP.

    Reuses compute_usage_summary for the activity domain (adoption numerator, cost,
    Pareto) and queries mw_users for the roster domain.
    """
    summary = compute_usage_summary(cutoff, end_time, bucket_size)
    if "error" in summary:
        return {"error": summary["error"]}

    totals = summary.get("totals", {})
    breakdown_by_user = summary.get("breakdown_by_user", [])
    cost_total = float(totals.get("cost_total_usd", 0) or 0)

    # Activity domain (raw — includes users since deleted, honouring audit immutability).
    active_user_ids = {u["user_id"] for u in breakdown_by_user}
    active_users = len(active_user_ids)

    # Roster domain (current, soft-delete aware).
    roster = _roster_rows()
    roster_ids = {u["user_id"] for u in roster}
    provisioned = len(roster_ids)

    # Adoption rate: intersect so the numerator can never contain non-provisioned users
    # (D3) — otherwise deleted-but-historically-active users push the rate over 100%.
    active_provisioned = len(active_user_ids & roster_ids)
    adoption_rate = (active_provisioned / provisioned * 100) if provisioned > 0 else 0.0

    # Cost per REAL active user (raw denominator — incurred cost is real even for users
    # since deleted; D8), distinct from the roster-intersected adoption numerator.
    cost_per_active_user = (cost_total / active_users) if active_users > 0 else 0.0

    now_utc = dt.datetime.now(tz=dt.timezone.utc)
    last_seen = _last_seen_per_user()

    return {
        "time_range": {
            "start": cutoff.isoformat(),
            "end": end_time.isoformat(),
            "bucket_size": bucket_size,
        },
        "roster": {
            "provisioned": provisioned,
            "new_accounts_in_period": _new_accounts_in_period(cutoff, end_time),
        },
        "adoption": {
            "active_users": active_users,
            "active_provisioned": active_provisioned,
            "provisioned": provisioned,
            "adoption_rate_percent": round(adoption_rate, 1),
            "cost_per_active_user": round(cost_per_active_user, 6),
        },
        "activity_series": _build_activity_series(cutoff, end_time),
        "dormant": _dormant_accounts(roster, last_seen, now_utc),
        "quota_histogram": _quota_histogram(roster),
        # Pareto: reuse only — cost concentration already computed server-side.
        "pareto": {
            "top10_pct_cost_share": totals.get("top10_pct_cost_share"),
            "breakdown_by_user": breakdown_by_user,
        },
    }


def get_adoption(
    request: Request,
    minutes: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    bucket: str = "auto",
):
    """Admin endpoint: adoption metrics for a time range. Mirrors get_summary_v2's auth
    and range resolution; reuses the same audit aggregation underneath."""
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    cutoff, end_time, bucket_size = _resolve_range(minutes, start, end, bucket)
    return compute_adoption(cutoff, end_time, bucket_size)
