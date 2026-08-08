"""
Milestone R1: PostgreSQL Schema & Data Integrity Test Suite
Targeting Open WebUI v0.11.0 & LLM Middleware Dual Database Architecture.
"""

import os
import json
import hashlib
import time
import pytest
import psycopg2
from psycopg2.extras import RealDictCursor


def get_connection(dbname, env_url_key=None):
    """
    Connects to PostgreSQL with fallback options for host, port, user, password.
    Host execution defaults to port 5433 (mapping to container 5432) or 5432.
    """
    if env_url_key and os.getenv(env_url_key):
        return psycopg2.connect(os.getenv(env_url_key))

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


class TestPostgresqlSchemaExistence:
    """Requirement R1: Core Table, Column, and Extension Existence Verification"""

    def test_openwebui_core_tables_exist(self, ow_conn):
        """
        Verify all 9 core Open WebUI tables and auxiliary tables exist in 'openwebui' DB.
        """
        expected_tables = [
            "user", "group", "group_member", "chat", "feedback",
            "file", "knowledge", "knowledge_file", "document_chunk",
            "access_grant", "tool"
        ]
        with ow_conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
            existing_tables = {row[0] for row in cur.fetchall()}

        for table in expected_tables:
            assert table in existing_tables, f"Core table '{table}' missing from openwebui DB!"

    def test_middleware_core_tables_exist(self, mw_conn):
        """
        Verify core Middleware tables exist in 'middleware' DB.
        """
        expected_tables = [
            "mw_users", "mw_audit_log", "mw_request_log", "mw_pending",
            "mw_prices", "mw_config", "mw_notifications",
            "mw_quota_alert_claims", "mw_migrations", "mw_user_integrations", "mw_tool_approvals"
        ]
        with mw_conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
            existing_tables = {row[0] for row in cur.fetchall()}

        for table in expected_tables:
            assert table in existing_tables, f"Middleware table '{table}' missing from middleware DB!"

    def test_pgvector_extension_installed(self, ow_conn):
        """
        Verify pgvector extension 'vector' is installed and active in openwebui DB.
        """
        with ow_conn.cursor() as cur:
            cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            row = cur.fetchone()
            assert row is not None, "PGVector extension 'vector' is NOT installed in openwebui DB!"
            assert row[0] == "vector"

    def test_openwebui_core_columns_exist(self, ow_conn):
        """
        Verify presence of mandatory columns in core Open WebUI tables.
        """
        expected_columns = {
            "user": ["id", "name", "email", "role", "created_at", "updated_at", "settings", "info", "last_active_at"],
            "group": ["id", "name", "user_id", "meta", "permissions", "created_at", "updated_at"],
            "group_member": ["id", "group_id", "user_id", "created_at"],
            "chat": ["id", "user_id", "title", "chat", "created_at", "updated_at", "share_id", "archived", "pinned", "meta", "folder_id"],
            "feedback": ["id", "user_id", "version", "type", "data", "meta", "snapshot", "created_at", "updated_at"],
            "file": ["id", "user_id", "filename", "meta", "hash", "path", "created_at", "updated_at"],
            "knowledge": ["id", "user_id", "name", "description", "meta", "data", "created_at", "updated_at"],
            "knowledge_file": ["id", "knowledge_id", "file_id", "created_at", "updated_at"],
            "document_chunk": ["id", "collection_name", "text", "vector", "vmetadata"],
            "access_grant": ["id", "resource_type", "resource_id", "principal_type", "principal_id", "permission", "created_at"],
            "tool": ["id", "name"],
        }
        with ow_conn.cursor() as cur:
            for table, cols in expected_columns.items():
                cur.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
                    (table,)
                )
                existing_cols = {row[0] for row in cur.fetchall()}
                missing = set(cols) - existing_cols
                assert not missing, f"Table '{table}' is missing required columns: {missing}"


class TestMiddlewareSQLNoCrash:
    """Requirement R1: 100% of Raw SQL Queries in Middleware Execute Without UndefinedColumn or UndefinedTable Errors"""

    def test_group_analytics_raw_queries(self, ow_conn):
        queries = [
            'SELECT id, name FROM "group"',
            'SELECT email, name FROM "user"',
            '''
            SELECT DISTINCT ON (u.email) u.email, gm.group_id
            FROM group_member gm
            JOIN "user" u ON gm.user_id = u.id
            ORDER BY u.email, gm.created_at ASC
            ''',
            '''
            SELECT u.email, count(*)
            FROM group_member gm
            JOIN "user" u ON gm.user_id = u.id
            GROUP BY u.email
            '''
        ]
        with ow_conn.cursor() as cur:
            for q in queries:
                try:
                    cur.execute(q)
                    cur.fetchall()
                except (psycopg2.errors.UndefinedColumn, psycopg2.errors.UndefinedTable) as e:
                    pytest.fail(f"Group analytics query failed with schema exception: {e}\nQuery: {q}")

    def test_chat_and_feedback_analytics_raw_queries(self, ow_conn):
        now_ts = int(time.time())
        past_ts = now_ts - 86400 * 30
        queries_with_params = [
            ('SELECT COUNT(id), COUNT(DISTINCT user_id) FROM chat WHERE created_at >= %s AND created_at <= %s', (past_ts, now_ts)),
            ('SELECT user_id, COUNT(id) FROM chat WHERE created_at >= %s AND created_at <= %s GROUP BY user_id', (past_ts, now_ts)),
            ('SELECT email, name FROM "user"', None),
            ('''
            SELECT
                COALESCE(SUM(CASE WHEN data::json->>'rating' = '1' THEN 1 ELSE 0 END), 0) as positive,
                COALESCE(SUM(CASE WHEN data::json->>'rating' = '-1' THEN 1 ELSE 0 END), 0) as negative,
                COUNT(*) as feedback_rows
            FROM feedback
            WHERE created_at >= %s AND created_at <= %s
            ''', (past_ts, now_ts)),
            ('''
            SELECT
                COALESCE(meta::json->>'model_id', 'unknown') as model_id,
                COALESCE(SUM(CASE WHEN data::json->>'rating' = '1' THEN 1 ELSE 0 END), 0) as positive,
                COALESCE(SUM(CASE WHEN data::json->>'rating' = '-1' THEN 1 ELSE 0 END), 0) as negative
            FROM feedback
            WHERE created_at >= %s AND created_at <= %s
              AND (data::json->>'rating' = '1' OR data::json->>'rating' = '-1')
            GROUP BY meta::json->>'model_id'
            ''', (past_ts, now_ts)),
            ('''
            SELECT f.data, f.meta, f.created_at, u.name, f.user_id, u.email
            FROM feedback f
            LEFT JOIN "user" u ON f.user_id = u.id
            WHERE f.created_at >= %s AND f.created_at <= %s
              AND (f.data::json->>'rating' = '1' OR f.data::json->>'rating' = '-1')
            ORDER BY f.created_at DESC
            LIMIT 50
            ''', (past_ts, now_ts)),
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
                    pytest.fail(f"Chat/feedback analytics query failed with schema exception: {e}\nQuery: {q}")

    def test_knowledge_and_rag_analytics_raw_queries(self, ow_conn):
        queries = [
            'SELECT id, name, user_id, created_at, updated_at FROM knowledge',
            'SELECT id, filename, user_id, meta, hash, created_at FROM file',
            'SELECT collection_name, count(*) FROM document_chunk GROUP BY collection_name',
            'SELECT id, name, email FROM "user"',
            '''
            SELECT k.id, k.name, k.user_id, k.created_at,
                   array_remove(array_agg(kf.file_id), NULL) AS file_ids
            FROM knowledge k
            LEFT JOIN knowledge_file kf ON kf.knowledge_id = k.id
            GROUP BY k.id, k.name, k.user_id, k.created_at
            ''',
            'SELECT id FROM knowledge',
            'SELECT id, filename, user_id, meta FROM file',
        ]
        with ow_conn.cursor() as cur:
            for q in queries:
                try:
                    cur.execute(q)
                    cur.fetchall()
                except (psycopg2.errors.UndefinedColumn, psycopg2.errors.UndefinedTable) as e:
                    pytest.fail(f"Knowledge/RAG query failed with schema exception: {e}\nQuery: {q}")

    def test_tool_access_raw_queries(self, ow_conn):
        queries_with_params = [
            ('''
            SELECT t.id, t.name, count(*) FILTER (WHERE ag.principal_type = 'group')
            FROM tool t
            LEFT JOIN access_grant ag ON ag.resource_type = 'tool' AND ag.resource_id = t.id
            GROUP BY t.id, t.name
            ''', None),
            ('''
            SELECT g.id, g.name, (SELECT count(*) FROM group_member gm WHERE gm.group_id = g.id) AS members
            FROM "group" g
            ORDER BY g.name
            ''', None),
            ('''
            SELECT resource_id FROM access_grant
            WHERE resource_type = %s AND permission = %s AND principal_type = %s AND principal_id = %s
            ''', ('tool', 'read', 'group', 'dummy-group-id')),
            ('''
            SELECT id, name, email FROM "user" WHERE id = %s
            ''', ('dummy-user-id',)),
            ('''
            SELECT g.id, g.name FROM "group" g
            JOIN group_member gm ON gm.group_id = g.id
            WHERE gm.user_id = %s ORDER BY g.name
            ''', ('dummy-user-id',)),
            ('''
            SELECT ag.resource_id, g.name
            FROM access_grant ag
            JOIN "group" g ON g.id = ag.principal_id
            WHERE ag.resource_type = %s AND ag.permission = %s AND ag.principal_type = 'group'
            ''', ('tool', 'read')),
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
                    pytest.fail(f"Tool access query failed with schema exception: {e}\nQuery: {q}")

    def test_identity_and_admin_raw_queries(self, ow_conn):
        queries_with_params = [
            ('SELECT id, name, email, role FROM "user" ORDER BY email', None),
            ('SELECT email, name, role FROM "user"', None),
            ('SELECT role, name FROM "user" WHERE email = %s LIMIT 1', ('user@example.com',)),
            ('SELECT role FROM "user" WHERE email = %s LIMIT 1', ('user@example.com',)),
            ('SELECT email FROM "user" WHERE name = %s OR email = %s LIMIT 1', ('user@example.com', 'user@example.com')),
            ("SELECT column_name FROM information_schema.columns WHERE table_name = 'user' AND column_name IN ('email', 'role', 'name')", None),
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
                    pytest.fail(f"Identity/Admin query failed with schema exception: {e}\nQuery: {q}")


class Test100PercentDataPreservation:
    """Requirement R1 Acceptance Criteria: 100% Data Preservation Verification"""

    def test_user_records_preservation(self, ow_conn):
        with ow_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT COUNT(*) as total, COUNT(email) as emails, COUNT(DISTINCT email) as distinct_emails FROM "user"')
            row = cur.fetchone()
            total = row['total']
            emails = row['emails']
            distinct_emails = row['distinct_emails']

            assert total >= 17, f"User count dropped below baseline! Expected >= 17, got {total}"
            assert total == emails, f"Found {total - emails} user records with NULL email!"
            assert total == distinct_emails, "Duplicate email addresses detected in 'user' table!"

            cur.execute('SELECT COUNT(*) as null_fields FROM "user" WHERE id IS NULL OR name IS NULL OR role IS NULL')
            assert cur.fetchone()['null_fields'] == 0, "User records contain NULL id, name, or role!"

            cur.execute('SELECT settings FROM "user" WHERE settings IS NOT NULL')
            settings_rows = cur.fetchall()
            for r in settings_rows:
                s = r['settings']
                if s:
                    if isinstance(s, str):
                        try:
                            json.loads(s)
                        except Exception as e:
                            pytest.fail(f"User settings failed JSON parsing: {e}")
                    elif not isinstance(s, (dict, list)):
                        pytest.fail(f"User settings is neither JSON string nor dict/list: {type(s)}")

    def test_department_groups_preservation(self, ow_conn):
        with ow_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT COUNT(*) as group_count FROM "group"')
            g_count = cur.fetchone()['group_count']
            assert g_count >= 1, f"Group count dropped below baseline! Expected >= 1, got {g_count}"

            cur.execute('SELECT COUNT(*) as gm_count FROM group_member')
            gm_count = cur.fetchone()['gm_count']
            assert gm_count >= 2, f"Group member count dropped below baseline! Expected >= 2, got {gm_count}"

            # Zero orphan records check in group_member -> "group"
            cur.execute('''
                SELECT COUNT(*) as orphan_groups
                FROM group_member gm
                LEFT JOIN "group" g ON gm.group_id = g.id
                WHERE g.id IS NULL
            ''')
            assert cur.fetchone()['orphan_groups'] == 0, "Orphan group_member records found (missing group)!"

            # Zero orphan records check in group_member -> "user"
            cur.execute('''
                SELECT COUNT(*) as orphan_users
                FROM group_member gm
                LEFT JOIN "user" u ON gm.user_id = u.id
                WHERE u.id IS NULL
            ''')
            assert cur.fetchone()['orphan_users'] == 0, "Orphan group_member records found (missing user)!"

    def test_uploaded_files_and_knowledge_preservation(self, ow_conn):
        with ow_conn.cursor(cursor_factory=RealDictCursor) as cur:
            # File count assertion
            cur.execute('SELECT COUNT(*) as file_count FROM file')
            f_count = cur.fetchone()['file_count']
            assert f_count >= 105, f"File count dropped below baseline! Expected >= 105, got {f_count}"

            # Knowledge count assertion
            cur.execute('SELECT COUNT(*) as k_count FROM knowledge')
            k_count = cur.fetchone()['k_count']
            assert k_count >= 1, f"Knowledge count dropped below baseline! Expected >= 1, got {k_count}"

            # Knowledge file count assertion
            cur.execute('SELECT COUNT(*) as kf_count FROM knowledge_file')
            kf_count = cur.fetchone()['kf_count']
            assert kf_count >= 8, f"Knowledge file count dropped below baseline! Expected >= 8, got {kf_count}"

            # Document chunk count assertion
            cur.execute('SELECT COUNT(*) as chunk_count FROM document_chunk')
            chunk_count = cur.fetchone()['chunk_count']
            assert chunk_count >= 1921, f"Document chunk count dropped below baseline! Expected >= 1921, got {chunk_count}"

            # Zero orphan knowledge_file records -> knowledge
            cur.execute('''
                SELECT COUNT(*) as orphan_k
                FROM knowledge_file kf
                LEFT JOIN knowledge k ON kf.knowledge_id = k.id
                WHERE k.id IS NULL
            ''')
            assert cur.fetchone()['orphan_k'] == 0, "Orphan knowledge_file records found (missing knowledge)!"

            # Zero orphan knowledge_file records -> file
            cur.execute('''
                SELECT COUNT(*) as orphan_f
                FROM knowledge_file kf
                LEFT JOIN file f ON kf.file_id = f.id
                WHERE f.id IS NULL
            ''')
            assert cur.fetchone()['orphan_f'] == 0, "Orphan knowledge_file records found (missing file)!"

    def test_zero_orphan_user_references(self, ow_conn):
        """
        Verify zero orphan user references in chat, file, and knowledge tables.
        """
        with ow_conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Chat -> user orphan check
            cur.execute('''
                SELECT COUNT(*) as orphan_chats
                FROM chat c
                LEFT JOIN "user" u ON c.user_id = u.id
                WHERE u.id IS NULL
            ''')
            assert cur.fetchone()['orphan_chats'] == 0, "Orphan chat records found (missing user)!"

            # File -> user orphan check
            cur.execute('''
                SELECT COUNT(*) as orphan_files
                FROM file f
                LEFT JOIN "user" u ON f.user_id = u.id
                WHERE u.id IS NULL
            ''')
            assert cur.fetchone()['orphan_files'] == 0, "Orphan file records found (missing user)!"

            # Knowledge -> user orphan check
            cur.execute('''
                SELECT COUNT(*) as orphan_knowledge
                FROM knowledge k
                LEFT JOIN "user" u ON k.user_id = u.id
                WHERE u.id IS NULL
            ''')
            assert cur.fetchone()['orphan_knowledge'] == 0, "Orphan knowledge records found (missing user)!"


class TestBackupFixtureIntegrity:
    """Verification of Backup Fixtures under backups/ directory"""

    def test_backup_manifest_and_checksums(self):
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        manifest_path = os.path.join(root_dir, "backups", "backup_20260616_092924", "manifest.json")
        
        if not os.path.exists(manifest_path):
            pytest.skip(f"Backup manifest path {manifest_path} does not exist in environment.")

        with open(manifest_path, "r", encoding="utf-8-sig") as f:
            manifest = json.load(f)

        assert manifest.get("complete") is True, "Backup manifest indicates incomplete backup!"

        backup_dir = os.path.dirname(manifest_path)
        for comp_name, comp_info in manifest.get("components", {}).items():
            file_name = comp_info.get("file")
            expected_sha256 = comp_info.get("sha256")
            file_path = os.path.join(backup_dir, file_name)

            assert os.path.exists(file_path), f"Backup file '{file_name}' specified in manifest is missing!"

            hasher = hashlib.sha256()
            with open(file_path, "rb") as bf:
                while chunk := bf.read(65536):
                    hasher.update(chunk)
            computed_sha256 = hasher.hexdigest()

            assert computed_sha256 == expected_sha256, (
                f"Backup component '{comp_name}' ({file_name}) SHA256 checksum mismatch!\n"
                f"Expected: {expected_sha256}\nGot: {computed_sha256}"
            )
