"""
OAuth 2.0 Click-to-Connect API endpoints.
Handles initiation and callbacks for Google Workspace, GitHub, and Office 365 integrations.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
import requests
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse
import logging

from config import MW_SECRET, WEBUI_SECRET_KEY
from utils.crypto import encrypt
from core.db import db_conn

logger = logging.getLogger("llm_mw")
router = APIRouter(prefix="/_mw/oauth", tags=["OAuth Integrations"])

# Thời hạn tối đa của tham số state (chống replay link connect cũ)
STATE_TTL_SECONDS = 600  # 10 phút

# Cookie mang nonce ràng luồng OAuth vào đúng trình duyệt đã khởi tạo (double-submit).
# Path hẹp trong /v1/_mw/oauth để không lộ ra request khác.
NONCE_COOKIE = "mw_oauth_nonce"
NONCE_COOKIE_PATH = "/v1/_mw/oauth"

# Tenant Azure AD/Entra ID. Mặc định `common` (multi-tenant); đặt OFFICE365_TENANT_ID
# về tenant công ty để chỉ chấp nhận tài khoản nội bộ (design.md Open Questions).
OFFICE365_TENANT = os.getenv("OFFICE365_TENANT_ID") or "common"

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
        "auth_url": f"https://login.microsoftonline.com/{OFFICE365_TENANT}/oauth2/v2.0/authorize",
        "token_url": f"https://login.microsoftonline.com/{OFFICE365_TENANT}/oauth2/v2.0/token",
        # Delegated scopes (least privilege): mail, lịch, SharePoint đọc, gửi tin Teams.
        # `offline_access` là cách Microsoft cấp refresh_token (không dùng access_type=offline như Google).
        "scopes": " ".join([
            "https://graph.microsoft.com/Mail.Send",
            "https://graph.microsoft.com/Mail.Read",
            "https://graph.microsoft.com/Calendars.ReadWrite",
            "https://graph.microsoft.com/Sites.Read.All",
            "https://graph.microsoft.com/ChannelMessage.Send",
            "offline_access",
        ]),
        # Microsoft yêu cầu gửi kèm `scope` khi đổi refresh_token lấy access_token mới
        "refresh_send_scope": True,
        "client_id_env": "OFFICE365_CLIENT_ID",
        "client_secret_env": "OFFICE365_CLIENT_SECRET"
    }
}


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def sign_state(provider: str, nonce: str) -> str:
    """
    Tạo token state ký HMAC-SHA256 bằng MW_SECRET. Chỉ mang provider + nonce + hạn 10 phút.

    CỐ Ý KHÔNG chứa danh tính user: danh tính được suy ra tại callback từ phiên đăng nhập
    Open WebUI của chính trình duyệt hoàn tất luồng (xem resolve_openwebui_session). Nhét
    user_id vào state rồi tin nó ở callback chính là lỗ hổng CSRF token-binding cũ — kẻ xấu
    xin một state ký hợp lệ cho id của mình rồi lừa nạn nhân consent. `nonce` khớp với cookie
    double-submit để ràng luồng vào đúng trình duyệt đã khởi tạo.
    """
    payload = {
        "provider": provider,
        "nonce": nonce,
        "exp": int(time.time()) + STATE_TTL_SECONDS,
    }
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    sig = hmac.new(
        MW_SECRET.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{payload_b64}.{sig}"


def resolve_openwebui_session(request: Request) -> str:
    """
    Trả về openwebui_user_id của trình duyệt gọi tới, suy từ cookie phiên `token` của
    Open WebUI (JWT HS256 ký bằng WEBUI_SECRET_KEY). Trả "" nếu thiếu/sai chữ ký/hết hạn.

    Cùng origin :3000 (nginx) + cookie Path=/ + SameSite=Lax nên trình duyệt gửi kèm cookie
    này cả trên redirect GET từ provider về callback. Ta luôn xác minh bằng HMAC-SHA256 và
    bỏ qua `alg` trong header ⇒ miễn nhiễm alg-confusion (alg=none vẫn phải có chữ ký hợp lệ).
    """
    if request is None or not WEBUI_SECRET_KEY:
        return ""
    token = request.cookies.get("token")
    if not token:
        return ""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        return ""
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(WEBUI_SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        got = _b64url_decode(sig_b64)
    except Exception:
        return ""
    if not hmac.compare_digest(expected, got):
        return ""
    try:
        claims = json.loads(_b64url_decode(payload_b64))
    except Exception:
        return ""
    exp = claims.get("exp")
    if exp is not None:
        try:
            if int(exp) < int(time.time()):
                return ""
        except (TypeError, ValueError):
            return ""
    uid = claims.get("id")
    return uid if isinstance(uid, str) and uid else ""


def verify_state(state: str) -> dict:
    """
    Xác minh chữ ký và thời hạn của state; trả về payload nếu hợp lệ.
    Ném HTTPException 400 khi state sai định dạng, sai chữ ký hoặc hết hạn.
    """
    try:
        payload_b64, sig = state.split(".", 1)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    expected_sig = hmac.new(
        MW_SECRET.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise HTTPException(status_code=400, detail="Invalid state signature")

    try:
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid state payload")

    if not isinstance(payload.get("exp"), int) or payload["exp"] < int(time.time()):
        raise HTTPException(status_code=400, detail="State expired")

    return payload


@router.get("/connect")
def connect(
    provider: str,
    request: Request = None,
):
    """
    Start the OAuth flow. Redirects user to provider login.

    Danh tính KHÔNG nhận qua query param nữa: user phải đang đăng nhập Open WebUI trong chính
    trình duyệt này (kiểm cookie phiên). Ta đặt cookie nonce ràng luồng vào trình duyệt này rồi
    redirect. Token sẽ gắn vào user của phiên tại callback, không phải id do client cung cấp.
    """
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported OAuth provider")

    ow_user_id = resolve_openwebui_session(request)
    if not ow_user_id:
        raise HTTPException(
            status_code=401,
            detail="Bạn cần đăng nhập Open WebUI trong trình duyệt này trước khi kết nối tài khoản.",
        )

    prov_cfg = PROVIDERS[provider]
    client_id = os.getenv(prov_cfg["client_id_env"]) or "mock-client-id"

    # Public callback URL
    public_url = os.getenv("MW_PUBLIC_URL", "https://localhost:3000").rstrip("/")
    redirect_uri = f"{public_url}/v1/_mw/oauth/callback"

    # nonce ràng luồng vào trình duyệt này (double-submit): vừa nằm trong state ký, vừa trong cookie
    nonce = secrets.token_urlsafe(24)
    state = sign_state(provider, nonce)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": prov_cfg["scopes"],
        "state": state,
    }

    # Google cần access_type=offline để trả refresh_token; Microsoft dùng scope `offline_access`
    if "google" in provider:
        params.update({
            "access_type": "offline",
            "prompt": "consent"
        })

    auth_url = prov_cfg["auth_url"] + "?" + urllib.parse.urlencode(params)
    logger.info("Initiated OAuth flow for %s (user=%s), redirecting...", provider, ow_user_id)
    resp = RedirectResponse(auth_url)
    resp.set_cookie(
        NONCE_COOKIE,
        nonce,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path=NONCE_COOKIE_PATH,
    )
    return resp


@router.get("/callback")
def callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
):
    """
    Receive authorization code, exchange it for tokens, encrypt, and save to DB.

    Chống CSRF token-binding: (1) state phải ký hợp lệ + còn hạn; (2) nonce trong state phải
    khớp cookie double-submit của chính trình duyệt này; (3) token gắn vào user suy ra TỪ PHIÊN
    Open WebUI của trình duyệt này — không tin bất kỳ id nào do client cung cấp.
    """
    if error:
        logger.error("OAuth callback received error: %s", error)
        return HTMLResponse(content=f"<h3>OAuth Error</h3><p>{error}</p>", status_code=400)

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing authorization code or state")

    # (1) Xác minh chữ ký + hạn của state trước khi trao đổi code
    payload = verify_state(state)
    provider = payload.get("provider")
    nonce = payload.get("nonce")

    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Invalid provider in state")

    # (2) nonce trong state phải khớp cookie đặt lúc /connect (ràng đúng trình duyệt, chống replay)
    cookie_nonce = request.cookies.get(NONCE_COOKIE)
    if not nonce or not cookie_nonce or not hmac.compare_digest(str(nonce), str(cookie_nonce)):
        raise HTTPException(status_code=400, detail="Invalid or missing session binding")

    # (3) Danh tính lấy từ phiên Open WebUI của trình duyệt hoàn tất luồng
    ow_user_id = resolve_openwebui_session(request)
    if not ow_user_id:
        return HTMLResponse(
            content=(
                "<h3>OAuth Error</h3><p>Bạn cần đăng nhập Open WebUI trong trình duyệt này "
                "rồi kết nối lại.</p>"
            ),
            status_code=400,
        )

    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT subkey_hash FROM mw_users WHERE openwebui_user_id = %s LIMIT 1",
            (ow_user_id,),
        )
        res = cur.fetchone()
        cur.close()
    if not res or not res[0]:
        return HTMLResponse(
            content="<h3>OAuth Error</h3><p>Không tìm thấy tài khoản người dùng tương ứng trong hệ thống Middleware.</p>",
            status_code=404,
        )
    user_id_hash = res[0]

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
        # GitHub OAuth App trả token không hết hạn: không có expires_in, cũng không có
        # refresh_token. Nếu mặc định 3600 thì sau 1 giờ get_token coi là hết hạn, không
        # có refresh token để gia hạn → bắt user kết nối lại dù token vẫn dùng được.
        # expires_in rỗng ⇒ lưu expires_at = NULL ⇒ token không bao giờ bị coi là hết hạn.
        expires_in = res_data.get("expires_in")

    if not access_token:
        return HTMLResponse(content="<h3>OAuth Error</h3><p>No access token returned by provider</p>", status_code=400)

    # Encrypt tokens using crypto utils
    enc_access = encrypt(access_token)
    enc_refresh = encrypt(refresh_token) if refresh_token else None
    
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=int(expires_in)) if expires_in else None
    )

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
    resp = HTMLResponse(content=success_html)
    # Tiêu thụ nonce (single-use): callback lặp lại cùng state sẽ không còn cookie khớp ⇒ 400
    resp.delete_cookie(NONCE_COOKIE, path=NONCE_COOKIE_PATH)
    return resp
