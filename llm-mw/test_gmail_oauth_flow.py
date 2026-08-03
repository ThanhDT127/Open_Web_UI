"""
Regression test end-to-end cho flow gmail tool sau khi OAuth chuyển sang session-binding
(OpenSpec change: department-plugin-access, D4 — danh tính-tại-callback + nonce double-submit).

Chạy trong container middleware, gọi API thật qua HTTP:
    docker cp tools/google_gmail_tool.py openwebui-middleware:/tmp/google_gmail_tool.py
    docker exec openwebui-middleware python test_gmail_oauth_flow.py

Không cần credential Google thật: thiếu GOOGLE_CLIENT_ID ⇒ oauth.py chạy nhánh mock exchange.
Danh tính lấy từ cookie phiên Open WebUI ⇒ test tự ký một JWT `token` bằng WEBUI_SECRET_KEY
(giống Open WebUI). Cookie `mw_oauth_nonce` = nonce trong state nên gửi lại được ở callback.
"""

import base64
import hashlib
import hmac
import importlib.util
import json
import os
import sys
import time
import urllib.parse

import requests

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.oauth import verify_state, NONCE_COOKIE  # noqa: E402
from config import OPENWEBUI_SERVICE_KEY, WEBUI_SECRET_KEY  # noqa: E402
from core.db import db_conn  # noqa: E402

MW_URL = os.environ.get("MW_URL", "http://localhost:5000")
TOOL_PATH = os.environ.get("GMAIL_TOOL_PATH", "/tmp/google_gmail_tool.py")
PROVIDER = "google_gmail"

ok = lambda msg: print(f"  ✓ {msg}")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def make_owui_cookie(ow_id: str) -> str:
    """JWT `token` giống Open WebUI (HS256, ký WEBUI_SECRET_KEY, claim id)."""
    if not WEBUI_SECRET_KEY:
        sys.exit("WEBUI_SECRET_KEY rỗng trong middleware — build lại với biến này rồi chạy lại.")
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps({"id": ow_id, "exp": int(time.time()) + 3600}, separators=(",", ":")).encode())
    sig = hmac.new(WEBUI_SECRET_KEY.encode(), f"{header}.{payload}".encode("ascii"), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(sig)}"


def load_gmail_tool():
    spec = importlib.util.spec_from_file_location("google_gmail_tool", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tool = module.Tools()
    tool.valves.MW_BASE_URL = f"{MW_URL}/v1"
    tool.valves.SUBKEY_ADMIN = OPENWEBUI_SERVICE_KEY
    tool.valves.MW_PUBLIC_URL = "https://localhost:3000"
    return tool


def pick_test_user():
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT openwebui_user_id, user_id, subkey_hash
            FROM mw_users
            WHERE openwebui_user_id IS NOT NULL AND subkey_hash IS NOT NULL AND active
            ORDER BY user_id LIMIT 1
            """
        )
        row = cur.fetchone()
        cur.close()
    if not row:
        sys.exit("Không có user nào trong mw_users mang openwebui_user_id — đăng nhập Open WebUI rồi chạy lại.")
    return {"ow_id": row[0], "email": row[1], "subkey_hash": row[2]}


def integration_row(subkey_hash: str):
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT access_token, refresh_token FROM mw_user_integrations WHERE user_id_hash = %s AND provider = %s",
            (subkey_hash, PROVIDER),
        )
        row = cur.fetchone()
        cur.close()
    return row


def delete_integration(subkey_hash: str):
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM mw_user_integrations WHERE user_id_hash = %s AND provider = %s",
            (subkey_hash, PROVIDER),
        )
        conn.commit()
        cur.close()


def test_tool_chua_ket_noi(tool, user):
    """Chưa liên kết → tool trả link connect (không còn openwebui_user_id), không gửi mail."""
    out = tool.send_gmail("ai.do@example.com", "Test", "Noi dung", __user__={"id": user["ow_id"]})
    assert "chưa được liên kết" in out, out
    assert f"provider={PROVIDER}" in out, out
    assert "openwebui_user_id" not in out, "Link connect KHÔNG được mang openwebui_user_id nữa"
    assert "PENDING_APPROVAL" not in out
    ok("Chưa kết nối → link connect không lộ user_id, không thực hiện action")


def test_connect_can_phien(user):
    """/connect không cookie phiên → 401; có cookie phiên → redirect Google + state ký."""
    no_sess = requests.get(
        f"{MW_URL}/v1/_mw/oauth/connect", params={"provider": PROVIDER},
        allow_redirects=False, timeout=10,
    )
    assert no_sess.status_code == 401, f"connect không phiên phải 401, nhận {no_sess.status_code}"

    res = requests.get(
        f"{MW_URL}/v1/_mw/oauth/connect", params={"provider": PROVIDER},
        cookies={"token": make_owui_cookie(user["ow_id"])},
        allow_redirects=False, timeout=10,
    )
    assert res.status_code in (302, 307), f"connect trả {res.status_code}"
    location = res.headers["location"]
    assert location.startswith("https://accounts.google.com/"), location
    state = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)["state"][0]
    payload = verify_state(state)
    assert payload["provider"] == PROVIDER, payload
    assert payload.get("nonce"), "state phải mang nonce"
    assert "id_val" not in payload and user["ow_id"] not in state, "state KHÔNG được chứa user_id"
    # cookie nonce phải được đặt và bằng nonce trong state
    assert NONCE_COOKIE in res.cookies, "connect phải đặt cookie nonce"
    assert res.cookies[NONCE_COOKIE] == payload["nonce"], "cookie nonce phải khớp state"
    ok("connect: không phiên→401; có phiên→redirect Google, state ký (không lộ user_id) + cookie nonce")
    return state, payload["nonce"]


def test_callback_chan_state_gia(user):
    """State sai chữ ký / thiếu binding → 400, không lưu token."""
    cookies_ok = {"token": make_owui_cookie(user["ow_id"]), NONCE_COOKIE: "whatever"}
    for bad_state in [f"a.b", f"khong-hop-le", ""]:
        res = requests.get(
            f"{MW_URL}/v1/_mw/oauth/callback",
            params={"code": "fake", "state": bad_state}, cookies=cookies_ok, timeout=10,
        )
        assert res.status_code == 400, f"state giả phải 400, nhận {res.status_code}"
    assert integration_row(user["subkey_hash"]) is None, "State giả không được lưu token!"
    ok("callback chặn state sai chữ ký/định dạng → 400, không lưu token")


def test_callback_thieu_nonce_cookie(user):
    """State hợp lệ nhưng KHÔNG có cookie nonce (biến thể tấn công 1) → 400."""
    location = requests.get(
        f"{MW_URL}/v1/_mw/oauth/connect", params={"provider": PROVIDER},
        cookies={"token": make_owui_cookie(user["ow_id"])}, allow_redirects=False, timeout=10,
    ).headers["location"]
    state = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)["state"][0]
    res = requests.get(
        f"{MW_URL}/v1/_mw/oauth/callback",
        params={"code": "mock-auth-code", "state": state},
        cookies={"token": make_owui_cookie(user["ow_id"])},  # có phiên, THIẾU nonce
        timeout=10,
    )
    assert res.status_code == 400, f"thiếu cookie nonce phải 400, nhận {res.status_code}"
    assert integration_row(user["subkey_hash"]) is None
    ok("callback thiếu cookie nonce (URL provider dựng sẵn) → 400, không lưu token")


def test_callback_khong_phien(user, state, nonce):
    """State + nonce khớp nhưng KHÔNG có phiên Open WebUI → 400."""
    res = requests.get(
        f"{MW_URL}/v1/_mw/oauth/callback",
        params={"code": "mock-auth-code", "state": state},
        cookies={NONCE_COOKIE: nonce},  # có nonce, THIẾU token phiên
        timeout=10,
    )
    assert res.status_code == 400, f"không phiên phải 400, nhận {res.status_code}"
    assert integration_row(user["subkey_hash"]) is None
    ok("callback không phiên Open WebUI → 400, không lưu token")


def test_callback_luu_token(user, state, nonce):
    """Đủ state + nonce + phiên → callback đổi code (mock) và lưu token dưới đúng user."""
    res = requests.get(
        f"{MW_URL}/v1/_mw/oauth/callback",
        params={"code": "mock-auth-code", "state": state},
        cookies={NONCE_COOKIE: nonce, "token": make_owui_cookie(user["ow_id"])},
        timeout=15,
    )
    assert res.status_code == 200, f"callback trả {res.status_code}: {res.text[:200]}"
    assert "Kết Nối Thành Công" in res.text
    row = integration_row(user["subkey_hash"])
    assert row is not None and row[0] and row[1], "Không lưu token dưới subkey_hash của user"
    ok("callback đủ điều kiện → lưu token (mã hóa) dưới đúng subkey_hash user (theo phiên)")


def test_get_token_tra_dung_user(user):
    res = requests.get(
        f"{MW_URL}/v1/_mw/integrations/get_token",
        headers={"Authorization": f"Bearer {OPENWEBUI_SERVICE_KEY}"},
        params={"provider": PROVIDER, "openwebui_user_id": user["ow_id"]},
        timeout=10,
    )
    assert res.status_code == 200, f"get_token trả {res.status_code}: {res.text[:200]}"
    token = res.json().get("access_token")
    assert token and token.startswith("mock-access-token-google_gmail"), token
    ok("get_token trả access_token của đúng user (service key path không đổi)")


def test_tool_da_ket_noi(tool, user):
    out = tool.send_gmail("ai.do@example.com", "Lịch họp", "Nội dung thử", __user__={"id": user["ow_id"]})
    assert "[PENDING_APPROVAL:" in out, out
    assert "chưa được liên kết" not in out, out
    ok("Đã kết nối → tool tạo yêu cầu phê duyệt (human-in-the-loop) đúng như trước")


def main():
    user = pick_test_user()
    tool = load_gmail_tool()
    print(f"Regression gmail flow (session-binding) — user test: {user['email']} ({user['ow_id']})\n")

    delete_integration(user["subkey_hash"])
    try:
        test_tool_chua_ket_noi(tool, user)
        state, nonce = test_connect_can_phien(user)
        test_callback_chan_state_gia(user)
        test_callback_thieu_nonce_cookie(user)
        test_callback_khong_phien(user, state, nonce)
        test_callback_luu_token(user, state, nonce)
        test_get_token_tra_dung_user(user)
        test_tool_da_ket_noi(tool, user)
    finally:
        delete_integration(user["subkey_hash"])
        print("\n(đã xóa token mock của user test)")

    print("\nAll gmail OAuth session-binding regression tests passed!")


if __name__ == "__main__":
    main()
