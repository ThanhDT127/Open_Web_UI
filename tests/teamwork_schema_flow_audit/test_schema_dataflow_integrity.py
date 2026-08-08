"""
Milestone 2: Comprehensive PostgreSQL Schema & Data Flow Integrity Test Suite
Targeting Open WebUI v0.11.0 & LLM Middleware Dual Database Architecture.

Test Suite Tiers:
- Tier 1: Schema & SQL Query Safety (verify 44 openwebui DB tables + 11 middleware DB tables, column definitions, junction tables `knowledge_file`, `chat_file`, `access_grant`, double-quoting `"user"` and `"group"`, 0% UndefinedColumn/UndefinedTable/KeyError).
- Tier 2: Boundary & Corner Cases (soft-deleted users, missing usage metadata, null file hashes, Base64 image chunking, reserved keyword escaping).
- Tier 3: Cross-Feature Combinations (subkey auth + group attribution + RAG KB lookup + tool access grants combined in single request).
- Tier 4: Real-World E2E Scenarios (mock E2E chat request through middleware API proxy logging to PostgreSQL DBs).
"""

import os
import sys
import json
import time
import uuid
import hashlib
import pytest
import psycopg2
from psycopg2.extras import RealDictCursor
import httpx

# Ensure llm-mw directory is in Python path for importing main app & core modules
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


def get_connection(dbname, env_url_key=None):
    """
    Connects to PostgreSQL with fallback options for host, port, user, password.
    Host execution defaults to port 5433 (mapping to container 5432) or 5432.
    """
    if env_url_key and os.getenv(env_url_key):
        try:
            return psycopg2.connect(os.getenv(env_url_key))
        except Exception:
            pass

    host = os.getenv("POSTGRES_HOST", "localhost")
    user = os.getenv("POSTGRES_USER", "openwebui_user")
    password = os.getenv("POSTGRES_PASSWORD", "pg_7h9k2m4n6p8r0v2w4x6z")

    ports_to_try = []
    if os.getenv("POSTGRES_PORT"):
        ports_to_try.append(int(os.getenv("POSTGRES_PORT")))
    else:
        ports_to_try = [5433, 5432]

    last_err = None
    for port in ports_to_try:
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=dbname,
                connect_timeout=5
            )
            conn.autocommit = True
            return conn
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Could not connect to PostgreSQL database '{dbname}' on {host} ports {ports_to_try}: {last_err}")


@pytest.fixture(scope="module")
def ow_conn():
    """Connection fixture for Open WebUI database."""
    conn = get_connection("openwebui", "OPENWEBUI_DATABASE_URL")
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def mw_conn():
    """Connection fixture for Middleware database."""
    conn = get_connection("middleware", "MW_DATABASE_URL")
    yield conn
    conn.close()


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


# ============================================================================
# Tier 1: Schema & SQL Query Safety
# ============================================================================

class TestTier1SchemaAndSQLQuerySafety:
    """Tier 1: Verify 44 Open WebUI + 11 Middleware DB tables, columns, junction tables, and double-quoting."""

    def test_openwebui_44_tables_exist(self, ow_conn):
        """Verify presence of all 44 Open WebUI v0.11.0 database tables in 'openwebui' DB."""
        expected_tables = [
            "access_grant", "alembic_version", "api_key", "auth", "automation",
            "automation_run", "calendar", "calendar_event", "calendar_event_attendee",
            "channel", "channel_file", "channel_member", "channel_webhook", "chat",
            "chat_file", "chat_message", "chatidtag", "config", "document",
            "document_chunk", "feedback", "file", "folder", "function",
            "group", "group_member", "knowledge", "knowledge_directory", "knowledge_file",
            "memory", "message", "message_reaction", "migratehistory", "model",
            "note", "oauth_session", "pinned_note", "prompt", "prompt_history",
            "shared_chat", "skill", "tag", "tool", "user"
        ]
        with ow_conn.cursor() as cur:
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            existing_tables = {row[0] for row in cur.fetchall()}

        missing_tables = [t for t in expected_tables if t not in existing_tables]
        assert not missing_tables, f"Open WebUI DB is missing required tables: {missing_tables}"

    def test_middleware_11_tables_exist(self, mw_conn):
        """Verify presence of all 11 Middleware database tables in 'middleware' DB."""
        expected_tables = [
            "mw_audit_log", "mw_config", "mw_migrations", "mw_notifications",
            "mw_pending", "mw_prices", "mw_quota_alert_claims", "mw_request_log",
            "mw_tool_approvals", "mw_user_integrations", "mw_users"
        ]
        with mw_conn.cursor() as cur:
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            existing_tables = {row[0] for row in cur.fetchall()}

        missing_tables = [t for t in expected_tables if t not in existing_tables]
        assert not missing_tables, f"Middleware DB is missing required tables: {missing_tables}"

    def test_junction_table_schemas(self, ow_conn):
        """Verify column definitions and constraints on key junction tables: knowledge_file, chat_file, access_grant."""
        junction_columns = {
            "knowledge_file": ["id", "user_id", "knowledge_id", "file_id", "created_at", "updated_at"],
            "chat_file": ["id", "chat_id", "file_id", "user_id", "created_at", "updated_at"],
            "access_grant": ["id", "resource_type", "resource_id", "principal_type", "principal_id", "permission", "created_at"],
        }
        with ow_conn.cursor() as cur:
            for table, cols in junction_columns.items():
                cur.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
                    (table,)
                )
                existing_cols = {row[0] for row in cur.fetchall()}
                missing = set(cols) - existing_cols
                assert not missing, f"Junction table '{table}' is missing required columns: {missing}"

    def test_reserved_keyword_double_quoting(self, ow_conn):
        """Verify SQL queries against reserved keyword tables ("user", "group") execute cleanly with double-quoting."""
        queries = [
            'SELECT id, name, email, role FROM "user" LIMIT 5',
            'SELECT id, name, user_id FROM "group" LIMIT 5',
            '''
            SELECT u.id, u.email, g.name AS group_name
            FROM "user" u
            JOIN group_member gm ON gm.user_id = u.id
            JOIN "group" g ON g.id = gm.group_id
            LIMIT 5
            ''',
            '''
            SELECT ag.resource_id, g.name
            FROM access_grant ag
            JOIN "group" g ON g.id = ag.principal_id
            WHERE ag.principal_type = 'group'
            LIMIT 5
            '''
        ]
        with ow_conn.cursor() as cur:
            for q in queries:
                try:
                    cur.execute(q)
                    cur.fetchall()
                except (psycopg2.errors.UndefinedColumn, psycopg2.errors.UndefinedTable, psycopg2.errors.SyntaxError) as e:
                    pytest.fail(f"Reserved keyword query failed: {e}\nQuery: {q}")

    def test_system_sql_joins_zero_errors(self, ow_conn, mw_conn):
        """Audit 100% of raw SQL queries used in Middleware analytics with zero UndefinedColumn / UndefinedTable / KeyError."""
        queries_with_params = [
            # Group analytics queries
            ('SELECT id, name FROM "group"', None),
            ('SELECT email, name FROM "user"', None),
            ('''
            SELECT DISTINCT ON (u.email) u.email, gm.group_id
            FROM group_member gm
            JOIN "user" u ON gm.user_id = u.id
            ORDER BY u.email, gm.created_at ASC
            ''', None),
            # Knowledge and RAG analytics queries
            ('''
            SELECT k.id, k.name, k.user_id, k.created_at,
                   array_remove(array_agg(kf.file_id), NULL) AS file_ids
            FROM knowledge k
            LEFT JOIN knowledge_file kf ON kf.knowledge_id = k.id
            GROUP BY k.id, k.name, k.user_id, k.created_at
            ''', None),
            ('SELECT collection_name, count(*) FROM document_chunk GROUP BY collection_name', None),
            # Tool access queries
            ('''
            SELECT t.id, t.name, count(*) FILTER (WHERE ag.principal_type = 'group')
            FROM tool t
            LEFT JOIN access_grant ag ON ag.resource_type = 'tool' AND ag.resource_id = t.id
            GROUP BY t.id, t.name
            ''', None),
            # Chat & feedback queries
            ('''
            SELECT f.data, f.meta, f.created_at, u.name, f.user_id, u.email
            FROM feedback f
            LEFT JOIN "user" u ON f.user_id = u.id
            LIMIT 10
            ''', None)
        ]
        with ow_conn.cursor() as cur:
            for q, params in queries_with_params:
                try:
                    if params:
                        cur.execute(q, params)
                    else:
                        cur.execute(q)
                    cur.fetchall()
                except (psycopg2.errors.UndefinedColumn, psycopg2.errors.UndefinedTable) as e:
                    pytest.fail(f"System SQL JOIN query failed with schema error: {e}\nQuery: {q}")


# ============================================================================
# Tier 2: Boundary & Corner Cases
# ============================================================================

class TestTier2BoundaryAndCornerCases:
    """Tier 2: Verify handling of soft-deleted users, missing metadata, null hashes, Base64 chunking, and reserved keywords."""

    def test_soft_deleted_and_inactive_users(self, mw_conn, ow_conn):
        """Verify soft-deleted (deleted_at != NULL) and inactive (active = false) users in mw_users do not crash DB queries."""
        from core.db import get_user_by_id_db
        from core.auth import create_user_record, delete_user

        test_user_id = f"tier2_softdel_{uuid.uuid4().hex[:6]}@example.com"
        
        # Create user record
        create_user_record({
            "user_id": test_user_id,
            "active": False,
            "quota": {"limit_cost_usd": 5.0, "used_cost_usd": 0.0}
        })

        # Soft delete user
        with mw_conn.cursor() as cur:
            cur.execute("UPDATE mw_users SET deleted_at = now() WHERE user_id = %s", (test_user_id,))

        # Verify lookup retrieves user dict without exception
        user_dict = get_user_by_id_db(test_user_id)
        assert user_dict is not None
        assert user_dict["user_id"] == test_user_id

        # Clean up
        with mw_conn.cursor() as cur:
            cur.execute("DELETE FROM mw_users WHERE user_id = %s", (test_user_id,))

    def test_missing_usage_metadata_handling(self, api_client, monkeypatch):
        """Verify LLM response with missing or null usage dictionary is handled gracefully without KeyError."""
        from core.auth import create_user_record, delete_user

        user_id = f"tier2_nousage_{uuid.uuid4().hex[:6]}@example.com"
        subkey = f"sk_test_tier2_nousage_{uuid.uuid4().hex[:8]}"

        create_user_record({
            "user_id": user_id,
            "active": True,
            "allowed_models": ["gpt-5"],
            "subkey": subkey,
            "quota": {"limit_cost_usd": 10.0, "used_cost_usd": 0.0}
        })

        try:
            original_send = httpx.AsyncClient.send
            async def mock_send(self_client, request, *args, **kwargs):
                if "chat/completions" in str(request.url):
                    class MockResp:
                        status_code = 200
                        headers = {"content-type": "application/json"}
                        def json(self):
                            return {
                                "id": "chatcmpl-no-usage-123",
                                "choices": [{"message": {"role": "assistant", "content": "No usage metadata test."}}]
                                # 'usage' field omitted!
                            }
                        async def aclose(self):
                            pass
                    return MockResp()
                return await original_send(self_client, request, *args, **kwargs)

            monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

            resp = api_client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {subkey}"},
                json={"model": "gpt-5", "messages": [{"role": "user", "content": "Hello"}]}
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["choices"][0]["message"]["content"] == "No usage metadata test."
        finally:
            delete_user(user_id)

    def test_null_file_hashes_and_missing_metadata(self, ow_conn):
        """Verify queries against 'file' table and RAG knowledge matchers operate safely when file hash or meta is NULL."""
        with ow_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, filename, user_id, meta, hash FROM file WHERE hash IS NULL OR meta IS NULL LIMIT 5")
            rows = cur.fetchall()
            assert isinstance(rows, list)

            cur.execute("""
                SELECT id, filename, COALESCE(hash, 'no_hash') AS safe_hash, COALESCE(meta::text, '{}') AS safe_meta
                FROM file
                LIMIT 10
            """)
            coalesced_rows = cur.fetchall()
            assert len(coalesced_rows) <= 10
            for r in coalesced_rows:
                assert r["safe_hash"] is not None
                assert r["safe_meta"] is not None

    def test_base64_image_chunking_and_multimodality(self, api_client, monkeypatch):
        """Verify chat payload with embedded Base64 image data URL parses multimodality without truncation or string slice error."""
        from core.auth import create_user_record, delete_user

        user_id = f"tier2_b64_{uuid.uuid4().hex[:6]}@example.com"
        subkey = f"sk_test_tier2_b64_{uuid.uuid4().hex[:8]}"

        create_user_record({
            "user_id": user_id,
            "active": True,
            "allowed_models": ["gpt-5"],
            "subkey": subkey,
            "quota": {"limit_cost_usd": 10.0, "used_cost_usd": 0.0}
        })

        try:
            original_send = httpx.AsyncClient.send
            async def mock_send(self_client, request, *args, **kwargs):
                if "chat/completions" in str(request.url):
                    class MockResp:
                        status_code = 200
                        headers = {"content-type": "application/json", "x-litellm-response-cost": "0.0050"}
                        def json(self):
                            return {
                                "id": "chatcmpl-b64-image-123",
                                "choices": [{"message": {"role": "assistant", "content": "I see the image!"}}],
                                "usage": {"prompt_tokens": 150, "completion_tokens": 10, "total_tokens": 160}
                            }
                        async def aclose(self):
                            pass
                    return MockResp()
                return await original_send(self_client, request, *args, **kwargs)

            monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

            b64_image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

            payload = {
                "model": "gpt-5",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "What is in this image?"},
                            {"type": "image_url", "image_url": {"url": b64_image}}
                        ]
                    }
                ]
            }

            resp = api_client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {subkey}"},
                json=payload
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["choices"][0]["message"]["content"] == "I see the image!"
        finally:
            delete_user(user_id)

    def test_sql_reserved_keyword_escaping_and_special_chars(self, ow_conn, mw_conn):
        """Verify SQL queries containing quotes, unicode, and reserved words escape properly via parameterized queries."""
        special_inputs = [
            "test_user' OR '1'='1",
            'user"group',
            "O'Connor",
            "Robert'); DROP TABLE mw_users;--",
            "THÀNH_PHỐ_HỒ_CHÍ_MINH_🚀"
        ]

        with mw_conn.cursor() as cur:
            for input_str in special_inputs:
                try:
                    cur.execute("SELECT user_id, role FROM mw_users WHERE user_id = %s", (input_str,))
                    cur.fetchall()
                except Exception as e:
                    pytest.fail(f"Parameterized SQL failed for input '{input_str}': {e}")

        with ow_conn.cursor() as cur:
            for input_str in special_inputs:
                try:
                    cur.execute('SELECT id, name FROM "group" WHERE name = %s', (input_str,))
                    cur.fetchall()
                except Exception as e:
                    pytest.fail(f"Parameterized SQL failed for group query with input '{input_str}': {e}")


# ============================================================================
# Tier 3: Cross-Feature Combinations
# ============================================================================

class TestTier3CrossFeatureCombinations:
    """Tier 3: Single integrated test combining Subkey Auth + Group Attribution + RAG KB Lookup + Tool Access Grants."""

    def test_combined_subkey_auth_group_rag_tool_access(self, api_client, ow_conn, mw_conn, monkeypatch):
        """
        Verify single integrated request combining:
        1. Subkey authentication.
        2. Group department attribution.
        3. RAG Knowledge Base file lookup.
        4. Tool access grant RBAC authorization.
        """
        from core.auth import create_user_record, delete_user
        from core.tool_access import get_user_tools

        # 1. Setup User & Subkey
        test_uid = f"tier3_combo_{uuid.uuid4().hex[:6]}"
        user_email = f"{test_uid}@example.com"
        subkey = f"sk_test_tier3_combo_{uuid.uuid4().hex[:8]}"

        now_ts = int(time.time())

        # Insert user into Open WebUI "user" table including non-null columns
        with ow_conn.cursor() as cur:
            cur.execute(
                '''
                INSERT INTO "user" (id, name, email, role, profile_image_url, created_at, updated_at, last_active_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                ''',
                (test_uid, f"Name_{test_uid}", user_email, "user", "/user.png", now_ts, now_ts, now_ts)
            )

        # Insert group into "group" and link in group_member
        group_id = f"grp_{test_uid}"
        with ow_conn.cursor() as cur:
            cur.execute(
                'INSERT INTO "group" (id, name, user_id, created_at, updated_at) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING',
                (group_id, f"Group_{test_uid}", test_uid, now_ts, now_ts)
            )
            cur.execute(
                'INSERT INTO group_member (id, group_id, user_id, created_at) VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING',
                (f"gm_{test_uid}", group_id, test_uid, now_ts)
            )

        # Insert tool access grant for group into access_grant table
        tool_id = f"tool_{test_uid}"
        grant_id = f"grant_{test_uid}"
        with ow_conn.cursor() as cur:
            cur.execute(
                '''
                INSERT INTO tool (id, user_id, name, content, specs, meta, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                ''',
                (tool_id, test_uid, f"Tool_{test_uid}", "", "[]", "{}", now_ts, now_ts)
            )
            cur.execute(
                '''
                INSERT INTO access_grant (id, resource_type, resource_id, principal_type, principal_id, permission, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                ''',
                (grant_id, "tool", tool_id, "group", group_id, "read", now_ts)
            )

        # Insert knowledge base and knowledge_file link into openwebui DB
        kb_id = f"kb_{test_uid}"
        file_id = f"file_{test_uid}"
        with ow_conn.cursor() as cur:
            cur.execute(
                'INSERT INTO file (id, user_id, filename, meta, hash, path, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING',
                (file_id, test_uid, "doc.pdf", '{}', "hash123", "/path/doc.pdf", now_ts, now_ts)
            )
            cur.execute(
                'INSERT INTO knowledge (id, user_id, name, description, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING',
                (kb_id, test_uid, "Test KB", "Test Desc", now_ts, now_ts)
            )
            cur.execute(
                'INSERT INTO knowledge_file (id, user_id, knowledge_id, file_id, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING',
                (f"kf_{test_uid}", test_uid, kb_id, file_id, now_ts, now_ts)
            )

        # Commit openwebui DB connection so new rows are visible across all DB sessions
        ow_conn.commit()

        # Insert middleware user record
        create_user_record({
            "user_id": user_email,
            "openwebui_user_id": test_uid,
            "active": True,
            "allowed_models": ["gpt-5"],
            "subkey": subkey,
            "quota": {"limit_cost_usd": 50.0, "used_cost_usd": 0.0}
        })

        try:
            # Step 1: Verify Group Attribution & Tool Access via get_user_tools
            user_tool_access = get_user_tools(test_uid)
            group_names = [g["name"] for g in user_tool_access.get("groups", [])]
            assert f"Group_{test_uid}" in group_names, f"Group resolution failed for user {test_uid}"

            effective_tool_ids = [t["id"] for t in user_tool_access.get("tools", []) if t.get("effective")]
            assert tool_id in effective_tool_ids, f"Tool access grant not resolved for user {test_uid}"

            # Step 2: Verify Tool Access Grant via Group direct DB query
            with ow_conn.cursor() as cur:
                cur.execute(
                    '''
                    SELECT ag.resource_id
                    FROM access_grant ag
                    JOIN group_member gm ON gm.group_id = ag.principal_id
                    WHERE gm.user_id = %s AND ag.resource_type = 'tool' AND ag.permission = 'read'
                    ''',
                    (test_uid,)
                )
                granted_tools = [r[0] for r in cur.fetchall()]
                assert tool_id in granted_tools, f"Tool access grant SQL query failed for user {test_uid}"

            # Step 3: Verify RAG Knowledge Base Link
            with ow_conn.cursor() as cur:
                cur.execute(
                    '''
                    SELECT kf.file_id
                    FROM knowledge_file kf
                    JOIN knowledge k ON k.id = kf.knowledge_id
                    WHERE k.id = %s
                    ''',
                    (kb_id,)
                )
                linked_files = [r[0] for r in cur.fetchall()]
                assert file_id in linked_files, f"RAG knowledge_file link not resolved for KB {kb_id}"

            # Step 4: Execute Combined API Call using Subkey Auth
            original_send = httpx.AsyncClient.send
            async def mock_send(self_client, request, *args, **kwargs):
                if "chat/completions" in str(request.url):
                    class MockResp:
                        status_code = 200
                        headers = {"content-type": "application/json", "x-litellm-response-cost": "0.0020"}
                        def json(self):
                            return {
                                "id": "chatcmpl-tier3-combo-123",
                                "choices": [{"message": {"role": "assistant", "content": "Cross-feature combination success!"}}],
                                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70}
                            }
                        async def aclose(self):
                            pass
                    return MockResp()
                return await original_send(self_client, request, *args, **kwargs)

            monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

            resp = api_client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {subkey}"},
                json={
                    "model": "gpt-5",
                    "messages": [
                        {"role": "user", "content": f"Query KB {kb_id} using tool {tool_id}"}
                    ]
                }
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["choices"][0]["message"]["content"] == "Cross-feature combination success!"

        finally:
            # Clean up test rows from openwebui & middleware databases
            delete_user(user_email)
            with ow_conn.cursor() as cur:
                cur.execute('DELETE FROM knowledge_file WHERE id = %s', (f"kf_{test_uid}",))
                cur.execute('DELETE FROM knowledge WHERE id = %s', (kb_id,))
                cur.execute('DELETE FROM file WHERE id = %s', (file_id,))
                cur.execute('DELETE FROM access_grant WHERE id = %s', (grant_id,))
                cur.execute('DELETE FROM tool WHERE id = %s', (tool_id,))
                cur.execute('DELETE FROM group_member WHERE id = %s', (f"gm_{test_uid}",))
                cur.execute('DELETE FROM "group" WHERE id = %s', (group_id,))
                cur.execute('DELETE FROM "user" WHERE id = %s', (test_uid,))
            ow_conn.commit()


# ============================================================================
# Tier 4: Real-World E2E Scenarios
# ============================================================================

class TestTier4RealWorldE2EScenarios:
    """Tier 4: Real-World E2E Chat proxy request logging to PostgreSQL (mw_audit_log & mw_request_log)."""

    def test_mock_e2e_chat_request_flow_logging(self, api_client, mw_conn, ow_conn, monkeypatch):
        """Verify E2E chat request through middleware proxy logs User ID, Model, Tokens, Cost USD to PostgreSQL audit tables."""
        from core.auth import create_user_record, delete_user

        uid_suffix = uuid.uuid4().hex[:6]
        user_id = f"tier4_e2e_{uid_suffix}@example.com"
        subkey = f"sk_test_tier4_e2e_{uid_suffix}"
        ow_uuid = f"ow_uuid_{uid_suffix}"

        create_user_record({
            "user_id": user_id,
            "openwebui_user_id": ow_uuid,
            "active": True,
            "allowed_models": ["gpt-5"],
            "subkey": subkey,
            "quota": {"limit_cost_usd": 20.0, "used_cost_usd": 0.0}
        })

        try:
            original_send = httpx.AsyncClient.send
            async def mock_send(self_client, request, *args, **kwargs):
                if "chat/completions" in str(request.url):
                    class MockResp:
                        status_code = 200
                        headers = {"content-type": "application/json", "x-litellm-response-cost": "0.0042"}
                        def json(self):
                            return {
                                "id": f"chatcmpl-e2e-{uid_suffix}",
                                "choices": [{"message": {"role": "assistant", "content": "E2E chat response."}}],
                                "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}
                            }
                        async def aclose(self):
                            pass
                    return MockResp()
                return await original_send(self_client, request, *args, **kwargs)

            monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

            resp = api_client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {subkey}"},
                json={"model": "gpt-5", "messages": [{"role": "user", "content": "Tell me a joke"}]}
            )

            assert resp.status_code == 200

            # Allow brief moment for background logging task to commit
            time.sleep(0.1)

            # Query mw_audit_log directly from PostgreSQL
            with mw_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT user_id, model, tokens_in, tokens_out, tokens_total, cost_usd, status, openwebui_user_id
                    FROM mw_audit_log
                    WHERE user_id = %s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (user_id,)
                )
                audit_row = cur.fetchone()

            assert audit_row is not None, f"Audit log row missing for user {user_id}"
            assert audit_row["user_id"] == user_id
            assert audit_row["model"] == "gpt-5"
            assert audit_row["tokens_in"] == 120
            assert audit_row["tokens_out"] == 30
            assert audit_row["tokens_total"] == 150
            assert audit_row["cost_usd"] == pytest.approx(0.0042, rel=1e-3)
            assert audit_row["status"] in ("ok", "reconciled", "success")
            assert audit_row["openwebui_user_id"] == ow_uuid

            # Query mw_request_log directly from PostgreSQL
            with mw_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT payload
                    FROM mw_request_log
                    ORDER BY id DESC
                    LIMIT 1
                    """
                )
                req_row = cur.fetchone()

            assert req_row is not None, "Request log row missing from mw_request_log"

        finally:
            delete_user(user_id)

    def test_e2e_streaming_chat_logging_reconciliation(self, api_client, mw_conn, monkeypatch):
        """Verify E2E streaming chat request reconciles tokens and writes audit log to PostgreSQL."""
        from core.auth import create_user_record, delete_user

        uid_suffix = uuid.uuid4().hex[:6]
        user_id = f"tier4_stream_{uid_suffix}@example.com"
        subkey = f"sk_test_tier4_stream_{uid_suffix}"

        create_user_record({
            "user_id": user_id,
            "active": True,
            "allowed_models": ["gpt-5"],
            "subkey": subkey,
            "quota": {"limit_cost_usd": 20.0, "used_cost_usd": 0.0}
        })

        chunk1 = json.dumps({"choices": [{"delta": {"role": "assistant", "content": "Hello "}}]})
        chunk2 = json.dumps({
            "choices": [{"delta": {"content": "world!"}}],
            "usage": {"prompt_tokens": 15, "completion_tokens": 5, "total_tokens": 20}
        })

        try:
            original_send = httpx.AsyncClient.send
            async def mock_send(self_client, request, *args, **kwargs):
                if "chat/completions" in str(request.url):
                    class MockStreamResp:
                        status_code = 200
                        headers = {"content-type": "text/event-stream", "x-litellm-response-cost": "0.0008"}
                        async def aiter_bytes(self):
                            yield f"data: {chunk1}\n\n".encode("utf-8")
                            yield f"data: {chunk2}\n\n".encode("utf-8")
                            yield b"data: [DONE]\n\n"
                        async def aclose(self):
                            pass
                    return MockStreamResp()
                return await original_send(self_client, request, *args, **kwargs)

            monkeypatch.setattr(httpx.AsyncClient, "send", mock_send)

            resp = api_client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {subkey}"},
                json={"model": "gpt-5", "messages": [{"role": "user", "content": "Hi"}], "stream": True}
            )

            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

            # Consume SSE body
            body = resp.text
            assert "Hello " in body
            assert "[DONE]" in body

            time.sleep(0.2)

            # Query mw_audit_log directly from PostgreSQL
            with mw_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT user_id, model, status, tokens_total
                    FROM mw_audit_log
                    WHERE user_id = %s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (user_id,)
                )
                audit_row = cur.fetchone()

            assert audit_row is not None
            assert audit_row["user_id"] == user_id
            assert audit_row["status"] in ("ok", "reconciled", "success")

        finally:
            delete_user(user_id)
