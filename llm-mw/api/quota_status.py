"""
Quota status API endpoint.
Lightweight endpoint for Open WebUI Filter to query user quota usage.
"""

from fastapi import Request, Query, HTTPException
from fastapi.responses import JSONResponse

from core.alerting import get_user_quota_status, load_alert_config, save_alert_config
from config import ADMIN_KEY, logger


async def get_quota_status(request: Request, user_id: str = Query(None, description="User ID to check")):
    """Return self quota, or arbitrary user quota for authenticated admins."""
    from core.auth import require_user
    from utils.auth_guard import require_admin_or_session

    try:
        require_admin_or_session(request)
        if not user_id:
            raise HTTPException(400, "Admin lookup requires user_id")
        return JSONResponse(content=get_user_quota_status(user_id))
    except HTTPException as admin_error:
        if admin_error.status_code != 403:
            raise

    user = require_user(request)
    own_user_id = user.get("user_id")
    if user_id and user_id != own_user_id:
        raise HTTPException(403, "Users may only retrieve their own quota")
    return JSONResponse(content=get_user_quota_status(own_user_id))


async def get_alert_config(request: Request):
    """
    GET /v1/_mw/admin/alerts/config
    
    Return current alert configuration (admin only).
    """
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {ADMIN_KEY}":
        return JSONResponse(status_code=403, content={"error": "Admin key required"})
    
    config = load_alert_config()
    # Mask SMTP password env var name but show it exists
    if "smtp" in config:
        smtp = config["smtp"]
        smtp["password_configured"] = bool(
            smtp.get("password_env") and 
            __import__("os").environ.get(smtp.get("password_env", ""), "")
        )
    return JSONResponse(content=config)


async def update_alert_config(request: Request):
    """
    PUT /v1/_mw/admin/alerts/config
    
    Update alert configuration (admin only).
    Accepts partial updates — merges with existing config.
    """
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {ADMIN_KEY}":
        return JSONResponse(status_code=403, content={"error": "Admin key required"})
    
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})
    
    config = load_alert_config()
    
    # Deep merge updates
    for key, value in body.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key].update(value)
        else:
            config[key] = value
    
    save_alert_config(config)
    logger.info("alert_config_updated by admin")
    return JSONResponse(content={"status": "updated", "config": config})


async def test_alert_email(request: Request):
    """
    POST /v1/_mw/admin/alerts/test-email
    
    Send a test alert email to verify SMTP configuration (admin only).
    """
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {ADMIN_KEY}":
        return JSONResponse(status_code=403, content={"error": "Admin key required"})
    
    from core.alerting import _smtp_send
    
    config = load_alert_config()
    smtp_cfg = config.get("smtp", {})
    
    if not smtp_cfg.get("enabled"):
        return JSONResponse(status_code=400, content={"error": "SMTP is disabled in alert_config.json"})
    
    admin_emails = config.get("admin_alerts", {}).get("emails", [])
    if not admin_emails:
        return JSONResponse(status_code=400, content={"error": "No admin emails configured"})
    
    try:
        _smtp_send(
            smtp_cfg, admin_emails,
            subject="🧪 LLM Gateway — Test Alert Email",
            body=(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "🧪 Test Alert Email\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Nếu bạn nhận được email này, SMTP đã được cấu hình đúng!\n\n"
                f"Thời gian: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )
        )
        return JSONResponse(content={"status": "sent", "to": admin_emails})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"SMTP send failed: {str(e)}"})
