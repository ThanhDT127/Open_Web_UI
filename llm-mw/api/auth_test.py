"""
Auth diagnostic endpoint for testing subkey validity.
Allows admins/users to quickly verify their Bearer token works.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from core.auth import find_user, hash_subkey
from config import logger
from utils.client_ip import client_address


async def auth_test(request: Request):
    """
    Test authentication with a Bearer token.
    Returns user info if valid, or descriptive error if not.
    
    GET /v1/_mw/auth-test
    Headers: Authorization: Bearer <subkey>
    
    Success (200):
        {"status": "ok", "user_id": "...", "active": true, "allowed_models": [...], "quota_status": {...}}
    
    Errors:
        401: {"detail": "Missing sub-key", "error_code": "MISSING_SUBKEY"}
        401: {"detail": "Invalid sub-key", "error_code": "INVALID_SUBKEY"}
        403: {"detail": "User account is deactivated", "error_code": "USER_INACTIVE"}
    """
    client_ip = client_address(request) or "unknown"
    
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        logger.warning(
            "auth_test_fail reason=missing_token client_ip=%s",
            client_ip,
        )
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing sub-key", "error_code": "MISSING_SUBKEY"},
        )
    
    subkey = auth.split(" ", 1)[1].strip()
    user = find_user(subkey)
    
    if not user:
        hashed_prefix = hash_subkey(subkey)[:8]
        logger.warning(
            "auth_test_fail reason=invalid_subkey hash_prefix=%s client_ip=%s",
            hashed_prefix, client_ip,
        )
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid sub-key", "error_code": "INVALID_SUBKEY"},
        )
    
    if not user.get("active", True):
        logger.warning(
            "auth_test_fail reason=user_inactive user_id=%s client_ip=%s",
            user.get("user_id"), client_ip,
        )
        return JSONResponse(
            status_code=403,
            content={
                "detail": "User account is deactivated",
                "error_code": "USER_INACTIVE",
                "user_id": user.get("user_id"),
            },
        )
    
    # Build quota status summary
    quota = user.get("quota", {})
    quota_status = {
        "period": quota.get("period", "none"),
        "limit_tokens": quota.get("limit_tokens", 0),
        "used_tokens": quota.get("used_tokens", 0),
        "limit_cost_usd": quota.get("limit_cost_usd", 0.0),
        "used_cost_usd": quota.get("used_cost_usd", 0.0),
    }
    
    logger.info(
        "auth_test_ok user_id=%s client_ip=%s",
        user.get("user_id"), client_ip,
    )
    
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "user_id": user.get("user_id"),
            "active": user.get("active", True),
            "allowed_models": user.get("allowed_models", ["*"]),
            "quota_status": quota_status,
        },
    )
