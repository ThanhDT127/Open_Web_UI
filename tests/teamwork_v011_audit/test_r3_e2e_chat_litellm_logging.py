"""
Milestone R3: E2E Chat & LiteLLM Proxy Logging Test Suite
Targeting Open WebUI v0.11.0 + LLM Middleware Proxy (/v1/chat/completions).

Coverage Criteria:
1. Chat completion proxying via /v1/chat/completions (and /chat/completions) with:
   - Subkey auth (Authorization: Bearer <subkey>)
   - Service key auth delegation (X-OpenWebUI-User-Id / X-OpenWebUI-User-Email + OPENWEBUI_SERVICE_KEY / ADMIN_KEY).
2. Upstream LiteLLM mocking (non-streaming JSON and streaming SSE chunks).
3. Cost, token count (in/out/total), USD cost calculation, latency recording in mw_audit_log,
   and detail payload logging in mw_request_log.
4. Single & Group tool access permissions in PostgreSQL access_grant table (resource_type = 'tool'),
   asserting disjunctive permission logic (effective = direct OR inherited_from_group OR public).
5. Quota pre-check enforcement (pre-blocking exceeded users without hitting LLM) and streaming
   quota warning chunk injection (>= 80%, >= 95%, >= 100%).
"""

import os
import sys
import json
import time
import uuid
import pytest
import httpx

# Ensure llm-mw directory is in Python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
LLM_MW_DIR = os.path.join(PROJECT_ROOT, "llm-mw")

if LLM_MW_DIR not in sys.path:
    sys.path.insert(0, LLM_MW_DIR)

# Set environment variables for test execution
if not os.getenv("ADMIN_KEY"):
    os.environ["ADMIN_KEY"] = "admin_master_key_456"

if not os.getenv("OPENWEBUI_SERVICE_KEY"):
    os.environ["OPENWEBUI_SERVICE_KEY"] = "ow_service_key_789"

if not os.getenv("DATABASE_URL") and not os.getenv("MW_DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://openwebui_user:pg_7h9k2m4n6p8r0v2w4x6z@localhost:5433/middleware"

if not os.getenv("OPENWEBUI_DATABASE_URL"):
    os.environ["OPENWEBUI_DATABASE_URL"] = "postgresql://openwebui_user:pg_7h9k2m4n6p8r0v2w4x6z@localhost:5433/openwebui"


@pytest.fixture(scope="module", autouse=True)
def init_db_environment():
    """
    Initialize PostgreSQL connection pools for middleware and openwebui databases.
    """
    from core.db import init_pool, _pool
    db_url = os.getenv("MW_DATABASE_URL") or os.getenv("DATABASE_URL")

    if _pool is None:
        try:
            init_pool(db_url)
        except Exception:
            alt_url = db_url.replace(":5433/", ":5432/") if ":5433/" in db_url else db_url.replace(":5432/", ":5433/")
            init_pool(alt_url)


@pytest.fixture(scope="module")
def api_client():
    """
    FastAPI TestClient fixture.
    """
    from main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def admin_key():
    return os.getenv("ADMIN_KEY", "admin_master_key_456")


@pytest.fixture(scope="module")
def service_key():
    return os.getenv("OPENWEBUI_SERVICE_KEY", "ow_service_key_789")


class TestAuthenticationAndRouting:
    """Requirement R3: Authentication (Subkey & Service Key) and Route Alias Verification"""

    def test_chat_completion_v1_endpoint_with_subkey_auth(self, api_client, monkeypatch):
        """
        Verify POST /v1/chat/completions succeeds with Authorization: Bearer <subkey>.
        """
        from core.auth import create_user_record, delete_user

        user_id = f"r3_subkey_user_{uuid.uuid4().hex[:6]}@example.com"
        subkey = f"sk_test_r3_subkey_{uuid.uuid4().hex[:8]}"

        create_user_record({
            "user_id": user_id,
            "active": True,
            "allowed_models": ["gpt-5"],
            "subkey": subkey,
            "quota": {"limit_cost_usd": 10.0, "used_cost_usd": 0.0}
        })

        try:
            # Mock LiteLLM upstream response
            original_post = httpx.AsyncClient.post
            async def mock_post(self_client, url, *args, **kwargs):
                if "chat/completions" in str(url):
                    class MockResp:
                        status_code = 200
                        headers = {"x-litellm-response-cost": "0.0010"}
                        def json(self):
                            return {
                                "id": "chatcmpl-v1-subkey-123",
                                "choices": [{"message": {"role": "assistant", "content": "Subkey auth successful!"}}],
                                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
                            }
                    return MockResp()
                return await original_post(self_client, url, *args, **kwargs)

            monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

            headers = {"Authorization": f"Bearer {subkey}"}
            payload = {
                "model": "gpt-5",
                "messages": [{"role": "user", "content": "Hello!"}],
                "stream": False
            }
            resp = api_client.post("/v1/chat/completions", headers=headers, json=payload)
            assert resp.status_code == 200, f"Expected 200 OK, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert data["choices"][0]["message"]["content"] == "Subkey auth successful!"
            assert data["_mw_user"] == user_id

        finally:
            delete_user(user_id)

    def test_chat_completion_root_alias_endpoint(self, api_client, monkeypatch):
        """
        Verify POST /chat/completions (root alias path without /v1) works identically.
        """
        from core.auth import create_user_record, delete_user

        user_id = f"r3_alias_user_{uuid.uuid4().hex[:6]}@example.com"
        subkey = f"sk_test_r3_alias_{uuid.uuid4().hex[:8]}"

        create_user_record({
            "user_id": user_id,
            "active": True,
            "allowed_models": ["gpt-5"],
            "subkey": subkey,
            "quota": {"limit_cost_usd": 10.0, "used_cost_usd": 0.0}
        })

        try:
            original_post = httpx.AsyncClient.post
            async def mock_post(self_client, url, *args, **kwargs):
                if "chat/completions" in str(url):
                    class MockResp:
                        status_code = 200
                        headers = {"x-litellm-response-cost": "0.0005"}
                        def json(self):
                            return {
                                "id": "chatcmpl-root-alias-456",
                                "choices": [{"message": {"role": "assistant", "content": "Root alias auth successful!"}}],
                                "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}
                            }
                    return MockResp()
                return await original_post(self_client, url, *args, **kwargs)

            monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

            headers = {"Authorization": f"Bearer {subkey}"}
            payload = {
                "model": "gpt-5",
                "messages": [{"role": "user", "content": "Test alias"}],
                "stream": False
            }
            resp = api_client.post("/chat/completions", headers=headers, json=payload)
            assert resp.status_code == 200, f"Expected 200 OK for /chat/completions, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert data["choices"][0]["message"]["content"] == "Root alias auth successful!"
            assert data["_mw_user"] == user_id

        finally:
            delete_user(user_id)

    def test_service_key_delegation_auth(self, api_client, service_key, monkeypatch):
        """
        Verify service key authentication using Authorization: Bearer <OPENWEBUI_SERVICE_KEY>
        with X-OpenWebUI-User-Id delegation header.
        """
        from core.auth import create_user_record, delete_user

        user_id = f"r3_service_delegated_{uuid.uuid4().hex[:6]}@example.com"
        ow_user_id = f"ow_user_id_{uuid.uuid4().hex[:8]}"

        create_user_record({
            "user_id": user_id,
            "openwebui_user_id": ow_user_id,
            "active": True,
            "allowed_models": ["gpt-5"],
            "quota": {"limit_cost_usd": 10.0, "used_cost_usd": 0.0}
        })

        try:
            original_post = httpx.AsyncClient.post
            async def mock_post(self_client, url, *args, **kwargs):
                if "chat/completions" in str(url):
                    class MockResp:
                        status_code = 200
                        headers = {"x-litellm-response-cost": "0.0012"}
                        def json(self):
                            return {
                                "id": "chatcmpl-service-key-789",
                                "choices": [{"message": {"role": "assistant", "content": "Service key delegation OK!"}}],
                                "usage": {"prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18}
                            }
                    return MockResp()
                return await original_post(self_client, url, *args, **kwargs)

            monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

            headers = {
                "Authorization": f"Bearer {service_key}",
                "X-OpenWebUI-User-Id": ow_user_id,
            }
            payload = {
                "model": "gpt-5",
                "messages": [{"role": "user", "content": "Service key test"}],
                "stream": False
            }
            resp = api_client.post("/v1/chat/completions", headers=headers, json=payload)
            assert resp.status_code == 200, f"Expected 200 OK, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert data["choices"][0]["message"]["content"] == "Service key delegation OK!"
            assert data["_mw_user"] == user_id

        finally:
            delete_user(user_id)

    def test_missing_auth_returns_401(self, api_client):
        """Verify request without Authorization header is rejected with 401 Unauthorized."""
        payload = {"model": "gpt-5", "messages": [{"role": "user", "content": "Test"}]}
        resp = api_client.post("/v1/chat/completions", json=payload)
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        assert resp.json().get("detail") == "Missing sub-key"

    def test_invalid_subkey_returns_401(self, api_client):
        """Verify request with invalid subkey is rejected with 401 Unauthorized."""
        headers = {"Authorization": "Bearer invalid_subkey_000000000"}
        payload = {"model": "gpt-5", "messages": [{"role": "user", "content": "Test"}]}
        resp = api_client.post("/v1/chat/completions", headers=headers, json=payload)
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        assert resp.json().get("detail") == "Invalid sub-key"

    def test_deactivated_user_returns_403(self, api_client):
        """Verify deactivated user account is rejected with 403 Forbidden."""
        from core.auth import create_user_record, delete_user

        user_id = f"r3_deactivated_{uuid.uuid4().hex[:6]}@example.com"
        subkey = f"sk_test_r3_inactive_{uuid.uuid4().hex[:8]}"

        create_user_record({
            "user_id": user_id,
            "active": False,
            "allowed_models": ["gpt-5"],
            "subkey": subkey,
            "quota": {"limit_cost_usd": 10.0, "used_cost_usd": 0.0}
        })

        try:
            headers = {"Authorization": f"Bearer {subkey}"}
            payload = {"model": "gpt-5", "messages": [{"role": "user", "content": "Test"}]}
            resp = api_client.post("/v1/chat/completions", headers=headers, json=payload)
            assert resp.status_code == 403, f"Expected 403 Forbidden, got {resp.status_code}"
            assert resp.json().get("detail") == "User account is deactivated"

        finally:
            delete_user(user_id)


class TestLiteLLMProxyAndAuditLogging:
    """Requirement R3: Mock LiteLLM Upstream & Verify mw_audit_log and mw_request_log Records"""

    def test_non_streaming_chat_logging(self, api_client, monkeypatch):
        """
        Verify non-streaming chat completion proxying records cost, tokens, latency,
        and auth_source into mw_audit_log and mw_request_log.
        """
        from core.auth import create_user_record, delete_user
        from core.db import db_conn

        user_id = f"r3_audit_nonstream_{uuid.uuid4().hex[:6]}@example.com"
        subkey = f"sk_test_r3_audit_{uuid.uuid4().hex[:8]}"

        create_user_record({
            "user_id": user_id,
            "active": True,
            "allowed_models": ["gpt-5"],
            "subkey": subkey,
            "quota": {"limit_cost_usd": 10.0, "used_cost_usd": 0.0}
        })

        try:
            original_post = httpx.AsyncClient.post
            async def mock_post(self_client, url, *args, **kwargs):
                if "chat/completions" in str(url):
                    class MockResp:
                        status_code = 200
                        headers = {"x-litellm-response-cost": "0.0025"}
                        def json(self):
                            return {
                                "id": "chatcmpl-nonstream-logging-101",
                                "choices": [{"message": {"role": "assistant", "content": "Non-streaming log test"}}],
                                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}
                            }
                    return MockResp()
                return await original_post(self_client, url, *args, **kwargs)

            monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

            headers = {"Authorization": f"Bearer {subkey}"}
            payload = {
                "model": "gpt-5",
                "messages": [{"role": "user", "content": "Log test"}],
                "stream": False
            }
            resp = api_client.post("/v1/chat/completions", headers=headers, json=payload)
            assert resp.status_code == 200
            req_id = resp.json().get("_mw_request_id")
            assert req_id is not None

            # Verify PostgreSQL mw_audit_log entry
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT user_id, endpoint, model, status, status_code, tokens_in, tokens_out, tokens_total, cost_usd, latency_ms, auth_source
                    FROM mw_audit_log
                    WHERE rid = %s OR (user_id = %s AND status = 'ok')
                    ORDER BY id DESC LIMIT 1
                """, (req_id, user_id))
                row = cur.fetchone()
                assert row is not None, "Audit log row missing from mw_audit_log!"
                assert row[0] == user_id
                assert row[1] == "/v1/chat/completions"
                assert row[2] == "gpt-5"
                assert row[3] == "ok"
                assert row[4] == 200
                assert row[5] == 20
                assert row[6] == 10
                assert row[7] == 30
                assert abs(row[8] - 0.0025) < 1e-5
                assert row[9] is not None and row[9] >= 0.0  # Latency ms recorded
                assert row[10] == "direct_subkey"

            # Verify PostgreSQL mw_request_log entry
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT payload FROM mw_request_log
                    WHERE payload->>'user' = %s ORDER BY id DESC LIMIT 1
                """, (user_id,))
                req_row = cur.fetchone()
                assert req_row is not None, "Request log row missing from mw_request_log!"
                payload_data = req_row[0]
                assert payload_data.get("user") == user_id
                assert payload_data.get("status") == 200

        finally:
            delete_user(user_id)

    def test_streaming_chat_logging(self, api_client, monkeypatch):
        """
        Verify streaming SSE chat completion proxying reconciles usage and cost
        into mw_audit_log with status='reconciled'.
        """
        from core.auth import create_user_record, delete_user
        from core.db import db_conn

        user_id = f"r3_audit_stream_{uuid.uuid4().hex[:6]}@example.com"
        subkey = f"sk_test_r3_stream_{uuid.uuid4().hex[:8]}"

        create_user_record({
            "user_id": user_id,
            "active": True,
            "allowed_models": ["gpt-5"],
            "subkey": subkey,
            "quota": {"limit_cost_usd": 10.0, "used_cost_usd": 0.0}
        })

        chunk1 = json.dumps({"choices": [{"delta": {"content": "Streamed response "}}]})
        chunk2 = json.dumps({
            "choices": [{"delta": {"content": "completed."}}],
            "usage": {"prompt_tokens": 15, "completion_tokens": 15, "total_tokens": 30}
        })

        try:
            original_send = httpx.AsyncClient.send
            async def mock_send(self_client, request, *args, **kwargs):
                if "chat/completions" in str(request.url):
                    class MockStreamResp:
                        status_code = 200
                        headers = {"content-type": "text/event-stream"}
                        async def aiter_bytes(self):
                            yield f"data: {chunk1}\n\n".encode("utf-8")
                            yield f"data: {chunk2}\n\n".encode("utf-8")
                            yield b"data: [DONE]\n\n"
                        async def aclose(self):
                            pass
                    return MockStreamResp()
                return await original_send(self_client, request, *args, **kwargs)

            monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

            headers = {"Authorization": f"Bearer {subkey}"}
            payload = {
                "model": "gpt-5",
                "messages": [{"role": "user", "content": "Stream test"}],
                "stream": True
            }
            resp = api_client.post("/v1/chat/completions", headers=headers, json=payload)
            assert resp.status_code == 200
            content_text = resp.text
            assert "Streamed response" in content_text
            assert "data: [DONE]" in content_text

            # Give non-blocking async tasks time to settle
            time.sleep(0.2)

            # Verify PostgreSQL mw_audit_log reconciled row
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT user_id, endpoint, model, status, tokens_total, cost_usd
                    FROM mw_audit_log
                    WHERE user_id = %s AND status = 'reconciled'
                    ORDER BY id DESC LIMIT 1
                """, (user_id,))
                row = cur.fetchone()
                assert row is not None, "Reconciled audit log row missing for streaming chat!"
                assert row[0] == user_id
                assert row[1] == "/v1/chat/completions"
                assert row[2] == "gpt-5"
                assert row[3] == "reconciled"
                assert row[4] == 30
                assert row[5] >= 0.0

        finally:
            delete_user(user_id)

    def test_cost_usd_calculation_from_prices(self, api_client, monkeypatch):
        """
        Verify cost_usd is correctly calculated via calc_cost_usd when LiteLLM
        does not provide an explicit x-litellm-response-cost header.
        """
        from core.auth import create_user_record, delete_user
        from core.db import db_conn

        user_id = f"r3_cost_calc_{uuid.uuid4().hex[:6]}@example.com"
        subkey = f"sk_test_r3_cost_{uuid.uuid4().hex[:8]}"

        create_user_record({
            "user_id": user_id,
            "active": True,
            "allowed_models": ["gpt-5"],
            "subkey": subkey,
            "quota": {"limit_cost_usd": 10.0, "used_cost_usd": 0.0}
        })

        try:
            original_post = httpx.AsyncClient.post
            async def mock_post(self_client, url, *args, **kwargs):
                if "chat/completions" in str(url):
                    class MockResp:
                        status_code = 200
                        headers = {}  # No cost header provided
                        def json(self):
                            return {
                                "id": "chatcmpl-calc-cost-202",
                                "choices": [{"message": {"role": "assistant", "content": "Cost calc test"}}],
                                "usage": {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}
                            }
                    return MockResp()
                return await original_post(self_client, url, *args, **kwargs)

            monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

            headers = {"Authorization": f"Bearer {subkey}"}
            payload = {"model": "gpt-5", "messages": [{"role": "user", "content": "Cost test"}], "stream": False}
            resp = api_client.post("/v1/chat/completions", headers=headers, json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("_mw_added_cost_usd") is not None
            assert data["_mw_added_cost_usd"] > 0.0

            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT tokens_total, cost_usd FROM mw_audit_log
                    WHERE user_id = %s ORDER BY id DESC LIMIT 1
                """, (user_id,))
                row = cur.fetchone()
                assert row is not None
                assert row[0] == 1500
                assert row[1] > 0.0

        finally:
            delete_user(user_id)


class TestToolAccessPermissions:
    """Requirement R3: Single & Group Tool Access Permissions in access_grant Table"""

    def test_direct_user_tool_permission(self):
        """
        Verify single direct user permission grant in access_grant table.
        """
        from core.tool_access import get_user_tools, set_user_tools, list_tools
        from core.db import db_ow_conn

        tools = list_tools()
        if not tools:
            pytest.skip("No tools found in workspace database")

        target_tool_id = tools[0]["id"]

        with db_ow_conn() as conn:
            cur = conn.cursor()
            cur.execute('SELECT id FROM "user" LIMIT 1')
            user_row = cur.fetchone()

        if not user_row:
            pytest.skip("No Open WebUI user found in database")

        ow_user_id = user_row[0]

        try:
            res_set = set_user_tools(ow_user_id, [target_tool_id])
            assert target_tool_id in res_set["granted"]

            user_tools = get_user_tools(ow_user_id)
            tool_entry = next((t for t in user_tools["tools"] if t["id"] == target_tool_id), None)
            assert tool_entry is not None
            assert tool_entry["direct"] is True
            assert tool_entry["effective"] is True

        finally:
            set_user_tools(ow_user_id, [])

    def test_inherited_group_tool_permission(self):
        """
        Verify group tool grant (principal_type = 'group') is inherited by group members.
        """
        from core.tool_access import get_user_tools, set_group_tools, list_groups, list_tools
        from core.db import db_ow_conn

        groups = list_groups()
        tools = list_tools()
        if not groups or not tools:
            pytest.skip("No groups or tools found in workspace database")

        group_id = groups[0]["id"]
        group_name = groups[0]["name"]
        target_tool_id = tools[0]["id"]

        with db_ow_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM group_member WHERE group_id = %s LIMIT 1", (group_id,))
            member_row = cur.fetchone()

        if not member_row:
            pytest.skip(f"No members in group '{group_name}'")

        ow_user_id = member_row[0]

        try:
            res_group = set_group_tools(group_id, [target_tool_id])
            assert target_tool_id in res_group["granted"]

            user_tools = get_user_tools(ow_user_id)
            tool_entry = next((t for t in user_tools["tools"] if t["id"] == target_tool_id), None)
            assert tool_entry is not None
            assert group_name in tool_entry["inherited_from"]
            assert tool_entry["effective"] is True

        finally:
            set_group_tools(group_id, [])

    def test_disjunctive_permission_check(self):
        """
        Verify disjunctive tool permission evaluation:
        effective = direct OR bool(inherited_from) OR public.
        """
        from core.tool_access import get_user_tools, list_tools
        from core.db import db_ow_conn

        tools = list_tools()
        if not tools:
            pytest.skip("No tools found in workspace database")

        with db_ow_conn() as conn:
            cur = conn.cursor()
            cur.execute('SELECT id FROM "user" LIMIT 1')
            user_row = cur.fetchone()

        if not user_row:
            pytest.skip("No user found in openwebui DB")

        ow_user_id = user_row[0]
        user_tools = get_user_tools(ow_user_id)

        for t in user_tools["tools"]:
            expected_effective = t["direct"] or bool(t["inherited_from"]) or t["public"]
            assert t["effective"] == expected_effective, (
                f"Disjunctive permission check failed for tool {t['id']}: "
                f"expected {expected_effective}, got {t['effective']}"
            )

    def test_tool_access_admin_api_endpoints(self, api_client, auth_headers):
        """
        Verify all Admin Tool Access API endpoints return HTTP 200 OK + expected schema.
        """
        # 1. GET /v1/_mw/admin/tool-access/tools
        res_tools = api_client.get("/v1/_mw/admin/tool-access/tools", headers=auth_headers)
        assert res_tools.status_code == 200
        assert "tools" in res_tools.json() and isinstance(res_tools.json()["tools"], list)

        # 2. GET /v1/_mw/admin/tool-access/groups
        res_groups = api_client.get("/v1/_mw/admin/tool-access/groups", headers=auth_headers)
        assert res_groups.status_code == 200
        groups = res_groups.json().get("groups", [])
        assert isinstance(groups, list)

        if groups:
            g_id = groups[0]["id"]
            # 3. GET /v1/_mw/admin/tool-access/groups/{group_id}
            res_g_detail = api_client.get(f"/v1/_mw/admin/tool-access/groups/{g_id}", headers=auth_headers)
            assert res_g_detail.status_code == 200
            assert "group" in res_g_detail.json()
            assert "tools" in res_g_detail.json()

            # 4. PUT /v1/_mw/admin/tool-access/groups/{group_id}
            existing_tools = res_g_detail.json()["group"].get("tool_ids", [])
            res_g_put = api_client.put(f"/v1/_mw/admin/tool-access/groups/{g_id}", headers=auth_headers, json={"tool_ids": existing_tools})
            assert res_g_put.status_code == 200

        # 5. GET /v1/_mw/admin/tool-access/users/{openwebui_user_id}
        from core.db import db_ow_conn
        with db_ow_conn() as conn:
            cur = conn.cursor()
            cur.execute('SELECT id FROM "user" LIMIT 1')
            user_row = cur.fetchone()

        if user_row:
            u_id = user_row[0]
            res_u_detail = api_client.get(f"/v1/_mw/admin/tool-access/users/{u_id}", headers=auth_headers)
            assert res_u_detail.status_code == 200
            u_json = res_u_detail.json()
            assert "user" in u_json
            assert "tools" in u_json

            # 6. PUT /v1/_mw/admin/tool-access/users/{openwebui_user_id}
            direct_tools = [t["id"] for t in u_json.get("tools", []) if t.get("direct")]
            res_u_put = api_client.put(f"/v1/_mw/admin/tool-access/users/{u_id}", headers=auth_headers, json={"tool_ids": direct_tools})
            assert res_u_put.status_code == 200
            assert "granted" in res_u_put.json()


@pytest.fixture(scope="module")
def auth_headers(admin_key):
    return {"X-Admin-Key": admin_key}


class TestQuotaEnforcementAndWarningInjection:
    """Requirement R3: Quota Pre-check Enforcement & Quota Warning Chunk Injection"""

    def test_quota_pre_check_block_non_streaming(self, api_client):
        """
        Verify user who has exceeded quota is blocked at pre-check stage BEFORE hitting LLM
        and receives HTTP 200 JSON with _mw_quota_blocked: True.
        """
        from core.auth import create_user_record, delete_user, update_user_quota
        from core.quota import period_anchor_ms

        user_id = f"r3_quota_block_ns_{uuid.uuid4().hex[:6]}@example.com"
        subkey = f"sk_test_r3_qblock_ns_{uuid.uuid4().hex[:8]}"
        anchor = period_anchor_ms("monthly", "UTC")

        create_user_record({
            "user_id": user_id,
            "active": True,
            "allowed_models": ["*"],
            "subkey": subkey,
            "quota": {
                "limit_cost_usd": 1.0,
                "used_cost_usd": 0.0,
                "period": "monthly",
                "timezone": "UTC",
                "period_start": anchor
            }
        })
        update_user_quota(user_id, add_cost_usd=1.5)

        try:
            headers = {"Authorization": f"Bearer {subkey}"}
            payload = {
                "model": "gpt-5",
                "messages": [{"role": "user", "content": "Should be blocked"}],
                "stream": False
            }
            resp = api_client.post("/v1/chat/completions", headers=headers, json=payload)
            assert resp.status_code == 200, f"Expected HTTP 200 (graceful fake response), got {resp.status_code}"
            data = resp.json()
            assert data.get("_mw_quota_blocked") is True
            assert "hết quota" in data["choices"][0]["message"]["content"]

        finally:
            delete_user(user_id)

    def test_quota_pre_check_block_streaming(self, api_client):
        """
        Verify user who has exceeded quota is blocked at pre-check stage BEFORE hitting LLM
        and receives HTTP 200 SSE stream containing quota block message + data: [DONE].
        """
        from core.auth import create_user_record, delete_user, update_user_quota
        from core.quota import period_anchor_ms

        user_id = f"r3_quota_block_stream_{uuid.uuid4().hex[:6]}@example.com"
        subkey = f"sk_test_r3_qblock_str_{uuid.uuid4().hex[:8]}"
        anchor = period_anchor_ms("monthly", "UTC")

        create_user_record({
            "user_id": user_id,
            "active": True,
            "allowed_models": ["*"],
            "subkey": subkey,
            "quota": {
                "limit_cost_usd": 1.0,
                "used_cost_usd": 0.0,
                "period": "monthly",
                "timezone": "UTC",
                "period_start": anchor
            }
        })
        update_user_quota(user_id, add_cost_usd=1.5)

        try:
            headers = {"Authorization": f"Bearer {subkey}"}
            payload = {
                "model": "gpt-5",
                "messages": [{"role": "user", "content": "Should be blocked"}],
                "stream": True
            }
            resp = api_client.post("/v1/chat/completions", headers=headers, json=payload)
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")
            stream_text = resp.text
            assert "hết quota" in stream_text
            assert "data: [DONE]" in stream_text

        finally:
            delete_user(user_id)

    def test_quota_warning_chunk_injection_streaming(self, api_client, monkeypatch):
        """
        Verify streaming chat completion injects an extra quota warning SSE chunk
        before data: [DONE] when user's quota usage is >= 80%.
        """
        from core.auth import create_user_record, delete_user
        from core.quota import period_anchor_ms

        user_id = f"r3_quota_warning_{uuid.uuid4().hex[:6]}@example.com"
        subkey = f"sk_test_r3_qwarn_{uuid.uuid4().hex[:8]}"
        anchor = period_anchor_ms("monthly", "UTC")

        create_user_record({
            "user_id": user_id,
            "active": True,
            "allowed_models": ["*"],
            "subkey": subkey,
            "quota": {
                "limit_cost_usd": 1.0,
                "used_cost_usd": 0.85,
                "period": "monthly",
                "timezone": "UTC",
                "period_start": anchor
            }
        })

        chunk1 = json.dumps({"choices": [{"delta": {"content": "Normal completion text"}}]})
        chunk2 = json.dumps({
            "choices": [{"delta": {}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200}
        })

        try:
            original_send = httpx.AsyncClient.send
            async def mock_send(self_client, request, *args, **kwargs):
                if "chat/completions" in str(request.url):
                    class MockStreamResp:
                        status_code = 200
                        headers = {"content-type": "text/event-stream"}
                        async def aiter_bytes(self):
                            yield f"data: {chunk1}\n\n".encode("utf-8")
                            yield f"data: {chunk2}\n\n".encode("utf-8")
                            yield b"data: [DONE]\n\n"
                        async def aclose(self):
                            pass
                    return MockStreamResp()
                return await original_send(self_client, request, *args, **kwargs)

            monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

            headers = {"Authorization": f"Bearer {subkey}"}
            payload = {
                "model": "gpt-5",
                "messages": [{"role": "user", "content": "Quota warning test"}],
                "stream": True
            }
            resp = api_client.post("/v1/chat/completions", headers=headers, json=payload)
            assert resp.status_code == 200
            stream_text = resp.text

            assert "Cảnh báo hạn mức" in stream_text or "quota" in stream_text
            assert "data: [DONE]" in stream_text

        finally:
            delete_user(user_id)
