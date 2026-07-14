"""
API endpoint for retrieving clean, decrypted OAuth tokens for user integrations.
Handles automatic token refreshing.
"""

import os
from datetime import datetime, timezone, timedelta
import requests
from fastapi import APIRouter, Request, HTTPException, Depends
import logging

from config import OPENWEBUI_SERVICE_KEY
from utils.crypto import decrypt, encrypt
from core.auth import require_user
from core.db import db_conn
from api.oauth import PROVIDERS

logger = logging.getLogger("llm_mw")
router = APIRouter(prefix="/_mw/integrations", tags=["User Integrations"])


def _refresh_oauth_token(provider: str, refresh_token: str) -> dict:
    """
    Call OAuth provider to refresh the access token.
    """
    prov_cfg = PROVIDERS[provider]
    client_id = os.getenv(prov_cfg["client_id_env"]) or "mock-client-id"
    client_secret = os.getenv(prov_cfg["client_secret_env"]) or "mock-client-secret"

    if client_id == "mock-client-id":
        # Mock refresh response for dev/test
        return {
            "access_token": f"mock-refreshed-token-{provider}",
            "expires_in": 3600
        }

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    # Microsoft identity platform yêu cầu `scope` khi đổi refresh_token; access token mới
    # chỉ có đúng các scope gửi kèm, nên phải gửi lại toàn bộ scopes của provider.
    if prov_cfg.get("refresh_send_scope"):
        data["scope"] = prov_cfg["scopes"]
    headers = {"Accept": "application/json"}

    res = requests.post(prov_cfg["token_url"], data=data, headers=headers, timeout=10)
    res.raise_for_status()
    return res.json()


@router.get("/get_token")
def get_token(
    provider: str,
    request: Request,
    openwebui_user_id: str = None
):
    """
    Retrieve decrypted OAuth token for the authenticated user.
    Refreshes the token automatically if expired.
    """
    # Authenticate user via bearer token (subkey)
    user = require_user(request)

    # Custom tool chạy trong Open WebUI gọi bằng service key kèm openwebui_user_id để lấy
    # token CỦA CHÍNH user đó. Cho phép nhánh này theo service key thay vì theo role: tài
    # khoản dịch vụ trong users.json không mang role 'admin', nên nếu chỉ xét role thì mọi
    # tool sẽ đọc token dưới hash của tài khoản dịch vụ — tức dùng chung một danh tính.
    auth_header = request.headers.get("Authorization", "")
    bearer = auth_header.split(" ", 1)[1].strip() if auth_header.startswith("Bearer ") else ""
    is_service_caller = bool(OPENWEBUI_SERVICE_KEY) and bearer == OPENWEBUI_SERVICE_KEY

    if openwebui_user_id and (is_service_caller or user.get("role") == "admin"):
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT subkey_hash FROM mw_users WHERE openwebui_user_id = %s LIMIT 1",
                (openwebui_user_id,)
            )
            res = cur.fetchone()
            cur.close()
        if not res or not res[0]:
            raise HTTPException(status_code=444, detail="Mapped middleware user not found")
        user_id_hash = res[0]
    else:
        user_id_hash = user.get("subkey_hash")

    if not user_id_hash:
        raise HTTPException(status_code=401, detail="User subkey hash missing")

    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    # Fetch token details from PostgreSQL
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT access_token, refresh_token, expires_at 
            FROM mw_user_integrations 
            WHERE user_id_hash = %s AND provider = %s
            """,
            (user_id_hash, provider)
        )
        row = cur.fetchone()
        cur.close()

    if not row:
        raise HTTPException(
            status_code=404, 
            detail=f"No active connection found for provider '{provider}'"
        )

    enc_access, enc_refresh, expires_at = row
    
    # Check if token is expired (or expires in less than 5 minutes)
    now = datetime.now(timezone.utc)
    if expires_at and expires_at <= now + timedelta(minutes=5):
        if not enc_refresh:
            raise HTTPException(
                status_code=401, 
                detail="Access token expired and no refresh token available. Re-connection required."
            )
        
        try:
            # Decrypt refresh token
            refresh_token = decrypt(enc_refresh)
            logger.info("Access token for %s expired. Attempting token refresh...", provider)
            
            # Call provider to refresh
            refresh_res = _refresh_oauth_token(provider, refresh_token)
            
            new_access_token = refresh_res["access_token"]
            new_refresh_token = refresh_res.get("refresh_token") # some providers return new refresh token
            expires_in = refresh_res.get("expires_in", 3600)
            
            # Encrypt and save back to DB
            enc_new_access = encrypt(new_access_token)
            enc_new_refresh = encrypt(new_refresh_token) if new_refresh_token else enc_refresh
            new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE mw_user_integrations 
                    SET access_token = %s, refresh_token = %s, expires_at = %s, updated_at = now()
                    WHERE user_id_hash = %s AND provider = %s
                    """,
                    (enc_new_access, enc_new_refresh, new_expires_at, user_id_hash, provider)
                )
                conn.commit()
                cur.close()
                
            logger.info("Successfully refreshed access token for %s", provider)
            return {"access_token": new_access_token}
            
        except Exception as e:
            logger.error("Failed to auto-refresh token for %s: %s", provider, e)
            raise HTTPException(
                status_code=401,
                detail=f"Token refresh failed: {e}. Please reconnect your account."
            )

    # Token is valid, decrypt and return
    try:
        access_token = decrypt(enc_access)
        return {"access_token": access_token}
    except Exception as e:
        logger.error("Failed to decrypt access token: %s", e)
        raise HTTPException(status_code=500, detail="Token decryption failed")
