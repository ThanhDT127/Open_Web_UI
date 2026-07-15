"""
Admin endpoints for user management and usage reconciliation.
"""

import json
from fastapi import Request, HTTPException

from config import ADMIN_KEY
from core.auth import clear_user_quota_usage, load_users, get_user_by_id, update_user_quota
from core.cost import load_prices, calc_cost_usd
from services.litellm import find_usage_in_log


def get_usage(request: Request):
    """
    Admin endpoint to view user usage statistics.
    Scrubs sensitive data (subkey, subkey_hash) for security.
    """
    if request.headers.get("X-Admin-Key", "") != ADMIN_KEY:
        raise HTTPException(403, "Invalid admin key")
    
    users = load_users()
    # Scrub sensitive fields before returning
    scrubbed = []
    for user in users:
        safe_user = {k: v for k, v in user.items() if k not in ("subkey", "subkey_hash")}
        scrubbed.append(safe_user)
    return scrubbed


async def reset_quota(request: Request):
    """
    Admin endpoint to reset quota for specific user or all users.
    """
    if request.headers.get("X-Admin-Key", "") != ADMIN_KEY:
        raise HTTPException(403, "Invalid admin key")
    
    body = await request.json()
    target_user = body.get("user_id")
    user_ids = [target_user] if target_user else [u.get("user_id") for u in load_users()]
    reset_count = sum(1 for user_id in user_ids if user_id and clear_user_quota_usage(user_id))
    return {"ok": True, "reset_count": reset_count}


async def reconcile_usage(request: Request):
    """
    Admin endpoint to manually reconcile usage from LiteLLM logs.
    Searches LiteLLM log for request_id and updates user usage accordingly.
    Idempotent: Returns early if already reconciled.
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    body = await request.json()
    request_id = body.get("request_id")
    user_id = body.get("user_id")
    if not request_id or not user_id:
        raise HTTPException(400, "Missing request_id or user_id")
    
    # Check if already reconciled (idempotent)
    import os
    from config import AUDIT_LOG_FILE
    if os.path.exists(AUDIT_LOG_FILE):
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        if entry.get("rid") == request_id and entry.get("status") == "reconciled":
                            return {
                                "ok": True,
                                "message": "Already reconciled",
                                "request_id": request_id,
                                "reconciled_at": entry.get("ts")
                            }
                    except Exception:
                        continue

    usage = find_usage_in_log(request_id)
    if not usage:
        raise HTTPException(404, f"No usage found in LiteLLM log for request_id={request_id}")

    model = usage.get("model") or body.get("model") or ""
    prompt_tokens = int(usage.get("prompt_tokens", 0))
    completion_tokens = int(usage.get("completion_tokens", 0))
    total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))
    logged_cost = usage.get("response_cost")
    try:
        logged_cost_f = float(logged_cost) if logged_cost is not None else 0.0
    except Exception:
        logged_cost_f = 0.0
    
    prices = load_prices()
    cost_usd = logged_cost_f if logged_cost_f > 0 else calc_cost_usd(model, prompt_tokens, completion_tokens, prices)

    # O(1) lookup + atomic update instead of load-all → modify → save-all
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(404, f"user_id={user_id} not found")

    update_user_quota(
        user_id,
        add_tokens=total_tokens,
        add_cost_usd=cost_usd,
    )

    from core.cost import remove_pending
    from utils.logging import write_audit_line
    from datetime import datetime, timezone
    
    remove_pending(request_id)
    
    # Write reconciled audit line
    write_audit_line({
        "ts": datetime.now(timezone.utc).isoformat(),
        "rid": request_id,
        "user_id": user_id,
        "endpoint": "/v1/chat/completions",
        "model": model,
        "status": "reconciled",
        "status_code": 200,
        "latency_ms": None,
        "tokens_in": prompt_tokens,
        "tokens_out": completion_tokens,
        "tokens_total": total_tokens,
        "cost_usd": cost_usd,
        "image_count": None,
        "tts_chars": None,
        "stt_seconds": None,
        "video_count": None,
        "error_type": None,
        "error_message": None
    })

    return {
        "ok": True,
        "request_id": request_id,
        "user_id": user_id,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": round(cost_usd, 6),
    }


def list_pending(request: Request):
    """
    Get a list of active pending requests with metadata.
    """
    from utils.auth_guard import require_admin_or_session
    from core.db import db_conn
    
    require_admin_or_session(request)
    
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT p.request_id, p.user_id, p.ts, a.model, a.endpoint
                FROM mw_pending p
                LEFT JOIN (
                    SELECT DISTINCT ON (rid) rid, model, endpoint
                    FROM mw_audit_log
                    WHERE status = 'pending'
                    ORDER BY rid, ts DESC
                ) a ON p.request_id = a.rid
                ORDER BY p.ts DESC
            """)
            rows = cur.fetchall()
            cur.close()
        
        pending_list = []
        for rid, uid, ts, model, endpoint in rows:
            pending_list.append({
                "request_id": rid,
                "user_id": uid,
                "started_at": ts,  # unix timestamp
                "model": model or "unknown",
                "endpoint": endpoint or "unknown"
            })
        return pending_list
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch pending requests: {str(e)}")


async def force_remove_pending(request_id: str, request: Request):
    """
    Force clear a pending request from DB and file backup without reconciliation.
    """
    from utils.auth_guard import require_admin_or_session
    from core.cost import remove_pending
    
    require_admin_or_session(request)
    
    try:
        remove_pending(request_id)
        return {"ok": True, "message": f"Pending request {request_id} force cleared"}
    except Exception as e:
        raise HTTPException(500, f"Failed to force clear pending request: {str(e)}")


def get_active_users_count() -> int:
    """
    Count unique user IDs active right now (in mw_pending or active in last 5 mins).
    """
    from core.db import db_conn, _pool
    db_available = _pool is not None

    metrics = {"active_users": 0, "pending_count": 0}

    if db_available:
        try:
            with db_conn() as conn:
                cur = conn.cursor()

                # Active users
                cur.execute("""
                    WITH active_pending AS (
                        SELECT DISTINCT user_id FROM mw_pending
                    ),
                    active_recent AS (
                        SELECT DISTINCT user_id FROM mw_audit_log
                        WHERE ts >= now() - interval '5 minutes' AND status IN ('ok', 'reconciled')
                    )
                    SELECT count(DISTINCT user_id) FROM (
                        SELECT user_id FROM active_pending
                        UNION
                        SELECT user_id FROM active_recent
                    ) combined;
                """)
                metrics["active_users"] = cur.fetchone()[0] or 0

                # Pending count
                cur.execute("SELECT count(*) FROM mw_pending")
                metrics["pending_count"] = cur.fetchone()[0] or 0

                cur.close()
            return count or 0
        except Exception as e:
            print(f"[SSE Live Metrics] DB query failed, falling back to files: {e}")

    # Fallback to files
    import os
    import csv
    import json
    import datetime as dt
    from config import PENDING_CSV, AUDIT_LOG_FILE

    active_users = set()
    pending_count = 0

    # 1. Read pending.csv
    if os.path.exists(PENDING_CSV):
        try:
            with open(PENDING_CSV, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                rows = list(reader)[1:]
                for row in rows:
                    if len(row) >= 2:
                        active_users.add(row[1])  # user_id
        except Exception as e:
            print(f"[SSE Live Metrics] Fallback failed to read pending.csv: {e}")

    # 2. Read audit.jsonl (last 5 minutes)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)
    if os.path.exists(AUDIT_LOG_FILE):
        try:
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        ts_str = entry.get("ts", "")
                        if ts_str:
                            entry_time = dt.datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                            if entry_time < cutoff:
                                break
                            if entry.get("status") in ["ok", "reconciled"]:
                                active_users.add(entry.get("user_id", "unknown"))
                    except Exception:
                        continue
        except Exception as e:
            print(f"[SSE Live Metrics] Fallback failed to read audit.jsonl: {e}")

    metrics["active_users"] = len(active_users)
    metrics["pending_count"] = pending_count
    return metrics


async def active_users_generator(request: Request):
async def active_users_generator(request: Request):
    """
    SSE Generator yielding live metrics (active users + pending count) periodically.
    """
    import asyncio
    import json

    last_metrics = None

    while True:
        if await request.is_disconnected():
            break

        try:
            current_count = get_active_users_count()
            if current_count != last_count:
                last_count = current_count
                yield f"event: active_users\ndata: {json.dumps({'active_users': current_count})}\n\n"
            else:
                yield ": ping\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        await asyncio.sleep(5)


async def stream_active_users(request: Request):
async def stream_active_users(request: Request):
    """
    SSE endpoint streaming real-time active users.
    SSE endpoint streaming real-time active users.
    """
    from fastapi.responses import StreamingResponse
    from utils.auth_guard import require_admin_or_session
    
    require_admin_or_session(request)
    
    return StreamingResponse(
        active_users_generator(request),
        active_users_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )


