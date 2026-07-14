"""
Unit tests cho OAuth session-binding trong api/oauth.py
(OpenSpec: department-plugin-access, D4 — chống CSRF token-binding).

Bao gồm: state ký/exp (sign_state/verify_state) và xác minh cookie phiên Open WebUI
(resolve_openwebui_session). Chạy trong container: `python test_oauth_state.py`.
"""

import sys
import os
import base64
import hashlib
import hmac
import json
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi import HTTPException

import api.oauth as oauth
from api.oauth import sign_state, verify_state, resolve_openwebui_session, STATE_TTL_SECONDS
from config import MW_SECRET


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_payload(state: str) -> dict:
    payload_b64 = state.split(".", 1)[0]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))


def _forge_state(payload: dict, secret: str = MW_SECRET) -> str:
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def _expect_400(state):
    try:
        verify_state(state)
        assert False, "verify_state phải từ chối state không hợp lệ"
    except HTTPException as e:
        assert e.status_code == 400


class _Req:
    """Request giả chỉ mang cookies (đủ cho resolve_openwebui_session)."""
    def __init__(self, cookies):
        self.cookies = cookies


def _make_owui_jwt(secret: str, claims: dict) -> str:
    """Tạo JWT HS256 giống PyJWT của Open WebUI (header.payload.signature)."""
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps(claims, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode("utf-8"), f"{header}.{payload}".encode("ascii"), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(sig)}"


# ── state ký / exp ────────────────────────────────────────────────

def test_valid_state_roundtrip():
    state = sign_state("google_gmail", "nonce-abc123")
    payload = verify_state(state)
    assert payload["provider"] == "google_gmail"
    assert payload["nonce"] == "nonce-abc123"
    assert payload["exp"] > int(time.time())
    assert payload["exp"] <= int(time.time()) + STATE_TTL_SECONDS
    # KHÔNG được mang danh tính user trong state (đó là lỗ hổng cũ)
    assert "id_val" not in payload and "openwebui_user_id" not in payload


def test_expired_state_rejected():
    payload = _decode_payload(sign_state("office365", "n1"))
    payload["exp"] = int(time.time()) - 1
    _expect_400(_forge_state(payload))


def test_wrong_signature_rejected():
    payload = _decode_payload(sign_state("office365", "n1"))
    _expect_400(_forge_state(payload, secret="attacker-secret"))
    state = sign_state("office365", "n1")
    payload_b64, sig = state.split(".", 1)
    bad_sig = ("0" if sig[0] != "0" else "1") + sig[1:]
    _expect_400(f"{payload_b64}.{bad_sig}")


def test_tampered_payload_rejected():
    state = sign_state("google_gmail", "n1")
    _, sig = state.split(".", 1)
    tampered = _decode_payload(state)
    tampered["provider"] = "office365"
    tampered_b64 = _b64url(json.dumps(tampered, separators=(",", ":")).encode())
    _expect_400(f"{tampered_b64}.{sig}")


def test_malformed_state_rejected():
    for bad in ["", "khong-co-dau-cham", "a.b", "%%%.###", "abc"]:
        _expect_400(bad)


# ── xác minh cookie phiên Open WebUI ──────────────────────────────

def test_session_valid_returns_id():
    secret = "test-webui-secret"
    old = oauth.WEBUI_SECRET_KEY
    oauth.WEBUI_SECRET_KEY = secret
    try:
        token = _make_owui_jwt(secret, {"id": "ow-user-uuid-1", "exp": int(time.time()) + 3600})
        assert resolve_openwebui_session(_Req({"token": token})) == "ow-user-uuid-1"
    finally:
        oauth.WEBUI_SECRET_KEY = old


def test_session_wrong_signature_rejected():
    old = oauth.WEBUI_SECRET_KEY
    oauth.WEBUI_SECRET_KEY = "test-webui-secret"
    try:
        # Token ký bằng secret khác — kẻ tấn công không biết WEBUI_SECRET_KEY
        token = _make_owui_jwt("attacker-secret", {"id": "victim", "exp": int(time.time()) + 3600})
        assert resolve_openwebui_session(_Req({"token": token})) == ""
    finally:
        oauth.WEBUI_SECRET_KEY = old


def test_session_expired_rejected():
    secret = "test-webui-secret"
    old = oauth.WEBUI_SECRET_KEY
    oauth.WEBUI_SECRET_KEY = secret
    try:
        token = _make_owui_jwt(secret, {"id": "u1", "exp": int(time.time()) - 5})
        assert resolve_openwebui_session(_Req({"token": token})) == ""
    finally:
        oauth.WEBUI_SECRET_KEY = old


def test_session_missing_or_no_secret():
    old = oauth.WEBUI_SECRET_KEY
    oauth.WEBUI_SECRET_KEY = "test-webui-secret"
    try:
        assert resolve_openwebui_session(_Req({})) == ""          # không có cookie
        assert resolve_openwebui_session(_Req({"token": "x.y"})) == ""  # sai định dạng
    finally:
        oauth.WEBUI_SECRET_KEY = old
    # Secret rỗng ⇒ luôn từ chối
    oauth.WEBUI_SECRET_KEY = ""
    try:
        token = _make_owui_jwt("whatever", {"id": "u1", "exp": int(time.time()) + 3600})
        assert resolve_openwebui_session(_Req({"token": token})) == ""
    finally:
        oauth.WEBUI_SECRET_KEY = old


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("All OAuth session-binding tests passed!")
