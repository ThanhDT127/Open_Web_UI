"""
Dashboard login endpoint for cookie-based authentication.
"""

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from config import ADMIN_KEY
from utils.jwt_auth import create_session_token


async def dashboard_login(request: Request):
    """
    Login endpoint for dashboard.
    
    POST /v1/_mw/dashboard/login
    Body: {"admin_key": "..."}
    
    Response:
        - 200: Sets mw_admin_session cookie (HttpOnly, SameSite=Lax, 4h expiry)
        - 403: Invalid admin key
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"error": "Invalid JSON"},
            status_code=400
        )
    
    admin_key = body.get("admin_key", "")
    
    if not admin_key:
        return JSONResponse(
            {"error": "Missing admin_key"},
            status_code=400
        )
    
    # Verify admin key
    if admin_key != ADMIN_KEY:
        return JSONResponse(
            {"error": "Invalid admin key"},
            status_code=403
        )
    
    # Create session token
    token = create_session_token(admin_key, expiry_hours=4)
    
    # Create response with cookie
    response = JSONResponse({
        "ok": True,
        "message": "Login successful",
        "expires_in_hours": 4
    })
    
    import os
    cookie_secure = os.getenv("MW_COOKIE_SECURE", "True").lower() in ("true", "1")

    # Set cookie (HttpOnly for security, SameSite=Lax for SSE)
    response.set_cookie(
        key="mw_admin_session",
        value=token,
        max_age=4 * 3600,  # 4 hours in seconds
        httponly=True,
        samesite="lax",  # Important: allows cookie in SSE requests
        secure=cookie_secure,  # Configurable for localhost HTTP testing
        path="/"
    )
    
    return response


async def dashboard_logout(request: Request):
    """
    Logout endpoint for dashboard.
    
    POST /v1/_mw/dashboard/logout
    
    Response:
        - 200: Clears mw_admin_session cookie
    """
    response = JSONResponse({
        "ok": True,
        "message": "Logout successful"
    })
    
    # Clear cookie
    response.delete_cookie(
        key="mw_admin_session",
        path="/"
    )
    
    return response
