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
