"""
OAuth 2.0 Click-to-Connect API endpoints.
Handles initiation and callbacks for Google Workspace, GitHub, and Office 365 integrations.
"""

import os
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
import requests
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse
import logging

from utils.crypto import encrypt
from core.db import db_conn

logger = logging.getLogger("llm_mw")
router = APIRouter(prefix="/_mw/oauth", tags=["OAuth Integrations"])

# Supported providers configuration
PROVIDERS = {
    "google_gmail": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly",
        "client_id_env": "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET"
    },
    "google_drive": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": "https://www.googleapis.com/auth/drive.readonly",
        "client_id_env": "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET"
    },
    "github": {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scopes": "repo read:user",
        "client_id_env": "GITHUB_CLIENT_ID",
        "client_secret_env": "GITHUB_CLIENT_SECRET"
    },
    "office365": {
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scopes": "https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/Mail.Read",
        "client_id_env": "OFFICE365_CLIENT_ID",
        "client_secret_env": "OFFICE365_CLIENT_SECRET"
    }
}


@router.get("/connect")
def connect(
    provider: str,
    subkey: str = None,
    openwebui_user_id: str = None,
    request: Request = None
):
    """
    Start the OAuth flow. Redirects user to provider login.
    """
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported OAuth provider")

    prov_cfg = PROVIDERS[provider]
    client_id = os.getenv(prov_cfg["client_id_env"]) or "mock-client-id"
    
    # Public callback URL
    public_url = os.getenv("MW_PUBLIC_URL", "https://localhost:3000").rstrip("/")
    redirect_uri = f"{public_url}/v1/_mw/oauth/callback"

    # State parameter contains provider and user's identification upon return
    if openwebui_user_id:
        state = urllib.parse.quote(f"{provider}:ow_user_id:{openwebui_user_id}")
    elif subkey:
        state = urllib.parse.quote(f"{provider}:subkey:{subkey}")
    else:
        raise HTTPException(status_code=400, detail="Either subkey or openwebui_user_id must be provided")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": prov_cfg["scopes"],
        "state": state
    }

    # Add offline access for Google/Office365 to obtain refresh_token
    if "google" in provider:
        params.update({
            "access_type": "offline",
            "prompt": "consent"
        })
    elif provider == "office365":
        params.update({
            "access_type": "offline"
        })

    auth_url = prov_cfg["auth_url"] + "?" + urllib.parse.urlencode(params)
    logger.info("Initiated OAuth flow for %s, redirecting user...", provider)
    return RedirectResponse(auth_url)


@router.get("/callback")
def callback(
    code: str = None,
    state: str = None,
    error: str = None
):
    """
    Receive authorization code, exchange it for tokens, encrypt, and save to DB.
    """
    if error:
        logger.error("OAuth callback received error: %s", error)
        return HTMLResponse(content=f"<h3>OAuth Error</h3><p>{error}</p>", status_code=400)

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing authorization code or state")

    try:
        decoded_state = urllib.parse.unquote(state)
        parts = decoded_state.split(":", 2)
        provider = parts[0]
        id_type = parts[1]
        id_val = parts[2]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Invalid provider in state")

    # Resolve user subkey hash
    if id_type == "subkey":
        user_id_hash = hashlib.sha256(id_val.encode("utf-8")).hexdigest()
    elif id_type == "ow_user_id":
        # Look up subkey_hash from mw_users by openwebui_user_id
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT subkey_hash FROM mw_users WHERE openwebui_user_id = %s LIMIT 1",
                (id_val,)
            )
            res = cur.fetchone()
            cur.close()
        if not res or not res[0]:
            return HTMLResponse(
                content="<h3>OAuth Error</h3><p>Không tìm thấy tài khoản người dùng tương ứng trong hệ thống Middleware.</p>",
                status_code=404
            )
        user_id_hash = res[0]
    else:
        raise HTTPException(status_code=400, detail="Invalid identity type in state")

    prov_cfg = PROVIDERS[provider]
    client_id = os.getenv(prov_cfg["client_id_env"]) or "mock-client-id"
    client_secret = os.getenv(prov_cfg["client_secret_env"]) or "mock-client-secret"

    public_url = os.getenv("MW_PUBLIC_URL", "https://localhost:3000").rstrip("/")
    redirect_uri = f"{public_url}/v1/_mw/oauth/callback"

    # Mock exchange for testing/local development if mock credentials are used
    if client_id == "mock-client-id":
        access_token = f"mock-access-token-{provider}-{int(time.time())}"
        refresh_token = f"mock-refresh-token-{provider}"
        expires_in = 3600
    else:
        # Standard Token Exchange
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }
        headers = {"Accept": "application/json"}
        
        try:
            res = requests.post(prov_cfg["token_url"], data=data, headers=headers, timeout=10)
            res.raise_for_status()
            res_data = res.json()
        except Exception as e:
            logger.error("Token exchange failed for provider %s: %s", provider, e)
            return HTMLResponse(content=f"<h3>Token Exchange Failed</h3><p>{e}</p>", status_code=500)

        access_token = res_data.get("access_token")
        refresh_token = res_data.get("refresh_token")
        expires_in = res_data.get("expires_in", 3600)

    if not access_token:
        return HTMLResponse(content="<h3>OAuth Error</h3><p>No access token returned by provider</p>", status_code=400)

    # Encrypt tokens using crypto utils
    enc_access = encrypt(access_token)
    enc_refresh = encrypt(refresh_token) if refresh_token else None
    
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    # Save to PostgreSQL database
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO mw_user_integrations (user_id_hash, provider, access_token, refresh_token, expires_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT (user_id_hash, provider)
            DO UPDATE SET 
                access_token = EXCLUDED.access_token,
                refresh_token = COALESCE(EXCLUDED.refresh_token, mw_user_integrations.refresh_token),
                expires_at = EXCLUDED.expires_at,
                updated_at = now()
            """,
            (user_id_hash, provider, enc_access, enc_refresh, expires_at)
        )
        conn.commit()

    logger.info("Successfully connected account for provider: %s", provider)

    # Success Page HTML
    success_html = """
    <html>
        <head>
            <title>Kết Nối Thành Công</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; text-align: center; padding-top: 100px; }
                .card { background: #1e293b; border-radius: 12px; max-width: 400px; margin: 0 auto; padding: 40px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3); border: 1px solid #334155; }
                h2 { color: #10b981; margin-top: 0; }
                button { background: #6366f1; border: none; color: white; padding: 10px 20px; border-radius: 6px; font-weight: bold; cursor: pointer; margin-top: 20px; transition: background 0.2s; }
                button:hover { background: #4f46e5; }
            </style>
        </head>
        <body>
            <div class="card">
                <h2>✓ Kết Nối Thành Công!</h2>
                <p>Tài khoản của bạn đã được liên kết bảo mật thành công.</p>
                <p>Bạn có thể đóng cửa sổ này và quay lại khung chat.</p>
                <button onclick="window.close()">Đóng Cửa Sổ</button>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=success_html)


# Import hashlib locally in case it wasn't imported
import hashlib
