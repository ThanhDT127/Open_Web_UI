"""
Quota management and enforcement for user limits.
"""

import datetime as dt
from typing import Dict, Any
from zoneinfo import ZoneInfo
from fastapi import HTTPException

from core.auth import get_user_by_id, reset_user_quota_period, update_user_quota


def period_anchor_ms(period: str, tz: str, now: dt.datetime = None) -> int:
    """
    Calculate period start timestamp in milliseconds.
    
    Args:
        period: "weekly" or "monthly"
        tz: Timezone name (e.g., "Asia/Ho_Chi_Minh")
        
    Returns:
        Timestamp in milliseconds
    """
    zone = ZoneInfo(tz) if tz else ZoneInfo("UTC")
    now = now.astimezone(zone) if now else dt.datetime.now(zone)
    if period == "weekly":
        start = now - dt.timedelta(days=now.weekday())
        start = dt.datetime(start.year, start.month, start.day, tzinfo=zone)
    else:
        start = dt.datetime(now.year, now.month, 1, tzinfo=zone)
    return int(start.timestamp() * 1000)


def maybe_reset_quota(user: Dict[str, Any]):
    """
    Reset period-based quota tracking when period boundary crossed.
    IMPORTANT: Only resets quota["used_*"], NOT user["used_*"] (lifetime data).
    
    Args:
        user: User dictionary (modified in-place)
    """
    quota = user.setdefault("quota", {})
    period = quota.get("period", "monthly")
    tz = quota.get("timezone", "UTC")
    current_anchor = period_anchor_ms(period, tz)
    if int(quota.get("period_start", 0)) < current_anchor:
        quota["period_start"] = current_anchor
        # Reset period metrics only
        quota["used_tokens"] = 0
        quota["used_cost_usd"] = 0.0
        quota["used_image_requests"] = 0
        # Reset alert tracking for the new period
        user["alerts_sent"] = {}
        # DO NOT reset user["used_*"] - those are lifetime counters


def get_current_quota_user(user_id: str) -> Dict[str, Any]:
    """Return one committed user record after applying any required period reset."""
    user = get_user_by_id(user_id)
    if not user:
        return None
    quota = user.get("quota", {})
    anchor = period_anchor_ms(
        quota.get("period", "monthly"),
        quota.get("timezone", "UTC"),
    )
    return reset_user_quota_period(user_id, anchor)


def get_quota_reset_info(user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate quota period info for user-facing messages.

    Returns:
        Dict with keys: period_label (str), days_until_reset (int)
    """
    quota = user.get("quota", {})
    period = quota.get("period", "monthly")
    tz_str = quota.get("timezone", "UTC")
    zone = ZoneInfo(tz_str) if tz_str else ZoneInfo("UTC")
    now = dt.datetime.now(zone)

    if period == "weekly":
        period_label = "tuần"
        # Next Monday
        days_until = 7 - now.weekday()
        if days_until == 0:
            days_until = 7
    else:
        period_label = "tháng"
        # First day of next month
        if now.month == 12:
            next_start = dt.datetime(now.year + 1, 1, 1, tzinfo=zone)
        else:
            next_start = dt.datetime(now.year, now.month + 1, 1, tzinfo=zone)
        days_until = (next_start - now).days
        if days_until < 1:
            days_until = 1

    return {
        "period_label": period_label,
        "days_until_reset": days_until,
    }


def enforce_and_bump_quota(
    user_id: str,
    *,
    apply: bool = True,
    add_image_requests: int = 0,
    add_stt_requests: int = 0,
    add_tokens: int = 0,
    add_cost_usd: float = 0.0,
):
    """
    Enforce quota limits and update usage counters.
    
    Uses O(1) get_user_by_id() instead of loading all users.
    Uses atomic update_user_quota() instead of save_users() for all.
    
    Args:
        user_id: User identifier
        apply: Whether to actually increment counters
        add_image_requests: Image requests to add
        add_stt_requests: Speech-to-text requests to add
        add_tokens: Tokens to add
        add_cost_usd: Cost to add
        
    Raises:
        HTTPException: 403 if quota exceeded, 404 if user not found
    """
    # O(1) lookup instead of load_users() + loop
    stored_user = get_current_quota_user(user_id)
    if not stored_user:
        raise HTTPException(404, f"user_id={user_id} not found")

    quota = stored_user.setdefault("quota", {})

    def _enforce_limit(limit_key: str, used_key: str, add_value: float, label: str):
        """Check if adding value would exceed limit"""
        limit_val = float(quota.get(limit_key, 0) or 0)
        if limit_val <= 0:
            return
        used_val = float(quota.get(used_key, 0) or 0)
        if used_val + add_value > limit_val + 1e-9:
            percent = round((used_val + add_value) / limit_val * 100, 1)
            if "cost" in limit_key.lower():
                detail_msg = f"⚠️ Bạn đã hết quota tháng này (đã dùng ${used_val + add_value:.2f}/${limit_val:.2f}). Vui lòng liên hệ admin để được nâng hạn mức."
            else:
                detail_msg = f"⚠️ Bạn đã hết quota {label} tháng này ({used_val + add_value:.0f}/{limit_val:.0f}). Vui lòng liên hệ admin để được nâng hạn mức."
            raise HTTPException(
                403,
                detail={
                    "detail": detail_msg,
                    "error_code": "QUOTA_EXCEEDED",
                    "quota_info": {"type": label.lower(), "used": round(used_val + add_value, 4), "limit": round(limit_val, 2), "percent": percent}
                },
            )

    # Enforce limits (read-only check, no lock needed)
    if add_image_requests:
        _enforce_limit("limit_image_requests", "used_image_requests", float(add_image_requests), "Image requests")
    if add_stt_requests:
        _enforce_limit("limit_stt_requests", "used_stt_requests", float(add_stt_requests), "STT requests")
    if add_tokens:
        _enforce_limit("limit_tokens", "used_tokens", float(add_tokens), "Token")
    if add_cost_usd:
        _enforce_limit("limit_cost_usd", "used_cost_usd", float(add_cost_usd), "Cost USD")

    if not apply:
        return

    # O(1) atomic update instead of save_users() for all
    update_user_quota(
        user_id,
        add_tokens=add_tokens,
        add_cost_usd=add_cost_usd,
        add_image_requests=add_image_requests,
        add_stt_requests=add_stt_requests,
    )

