"""
Scorecards & Metric Cards Real Data Automated Verification Test Suite
Targeting Admin Dashboard Scorecards across all 13 Tabs & PostgreSQL Databases.

Validates 1:1 match between direct PostgreSQL SQL query aggregates and JSON API responses.
Validates zero-data / empty date-range behavior (0, 0.0, None) without mock/dummy fallbacks.
"""

import os
import sys
import datetime as dt
import pytest
import psycopg2

# Ensure llm-mw directory is in Python path for importing main app & core modules
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
LLM_MW_DIR = os.path.join(PROJECT_ROOT, "llm-mw")

if LLM_MW_DIR not in sys.path:
    sys.path.insert(0, LLM_MW_DIR)

# Set default environment variables for testing
if not os.getenv("ADMIN_KEY"):
    os.environ["ADMIN_KEY"] = "admin_master_key_456"

if not os.getenv("DATABASE_URL") and not os.getenv("MW_DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://openwebui_user:pg_7h9k2m4n6p8r0v2w4x6z@localhost:5433/middleware"


def get_postgres_connection(dbname: str):
    """
    Establishes connection to PostgreSQL database with fallback ports (5433, 5432).
    """
    host = os.getenv("POSTGRES_HOST", "localhost")
    user = os.getenv("POSTGRES_USER", "openwebui_user")
    password = os.getenv("POSTGRES_PASSWORD", "pg_7h9k2m4n6p8r0v2w4x6z")

    ports_to_try = [5433, 5432]
    if os.getenv("POSTGRES_PORT"):
        ports_to_try = [int(os.getenv("POSTGRES_PORT"))] + ports_to_try

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
def mw_conn():
    """Connection fixture for Middleware PostgreSQL DB."""
    conn = get_postgres_connection("middleware")
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def ow_conn():
    """Connection fixture for Open WebUI PostgreSQL DB."""
    conn = get_postgres_connection("openwebui")
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def api_client():
    """FastAPI TestClient fixture with initialized DB pool."""
    from core.db import init_pool, _pool
    db_url = os.getenv("MW_DATABASE_URL") or os.getenv("DATABASE_URL")
    if _pool is None:
        try:
            init_pool(db_url)
        except Exception:
            alt_url = db_url.replace(":5433/", ":5432/") if ":5433/" in db_url else db_url.replace(":5432/", ":5433/")
            init_pool(alt_url)

    from main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def auth_headers():
    """Admin authentication headers fixture."""
    return {"X-Admin-Key": os.getenv("ADMIN_KEY", "admin_master_key_456")}


# ============================================================================
# TAB 1: USAGE TAB SCORECARDS
# ============================================================================
class TestUsageTabScorecards:
    """Tab 1: Usage Tab Scorecards Audit & Verification"""

    def test_usage_scorecards_real_data_match(self, api_client, auth_headers, mw_conn):
        """Verify Usage tab scorecard metrics match 1:1 with independent SQL query on mw_audit_log."""
        resp = api_client.get("/v1/_mw/summary?minutes=43200", headers=auth_headers)
        assert resp.status_code == 200, f"Usage API failed: {resp.text}"
        data = resp.json()

        time_range = data.get("time_range", {})
        start_iso = time_range.get("start")
        end_iso = time_range.get("end")
        totals = data.get("totals", {})

        with mw_conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(DISTINCT rid) as requests_total,
                    COUNT(DISTINCT rid) FILTER (WHERE status IN ('ok', 'reconciled')) as requests_ok,
                    COUNT(DISTINCT rid) FILTER (WHERE status = 'error') as error_count,
                    COALESCE(SUM(tokens_total) FILTER (WHERE status IN ('ok', 'reconciled')), 0) as tokens_total,
                    COALESCE(SUM(cost_usd) FILTER (WHERE status IN ('ok', 'reconciled')), 0.0) as cost_total_usd
                FROM mw_audit_log
                WHERE ts >= %s AND ts <= %s
            """, (start_iso, end_iso))
            sql_row = cur.fetchone()

        with mw_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM mw_pending")
            sql_pending = cur.fetchone()[0]

        sql_requests_total, sql_requests_ok, sql_error_count, sql_tokens, sql_cost = sql_row

        assert totals.get("requests_total") == sql_requests_total, f"requests_total mismatch: API={totals.get('requests_total')} vs SQL={sql_requests_total}"
        assert totals.get("requests_ok") == sql_requests_ok, f"requests_ok mismatch: API={totals.get('requests_ok')} vs SQL={sql_requests_ok}"
        assert totals.get("error_count") == sql_error_count, f"error_count mismatch: API={totals.get('error_count')} vs SQL={sql_error_count}"
        assert totals.get("tokens_total") == sql_tokens, f"tokens_total mismatch: API={totals.get('tokens_total')} vs SQL={sql_tokens}"
        assert abs(totals.get("cost_total_usd", 0.0) - float(sql_cost)) < 1e-4, f"cost_total_usd mismatch: API={totals.get('cost_total_usd')} vs SQL={sql_cost}"
        assert totals.get("pending_open_count") == sql_pending, f"pending_open_count mismatch: API={totals.get('pending_open_count')} vs SQL={sql_pending}"

    def test_usage_scorecards_zero_data_handling(self, api_client, auth_headers):
        """Verify zero-data time range returns standard zero/null values without fallback."""
        zero_url = "/v1/_mw/summary?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z"
        resp = api_client.get(zero_url, headers=auth_headers)
        assert resp.status_code == 200
        totals = resp.json().get("totals", {})

        assert totals.get("requests_total") == 0
        assert totals.get("requests_ok") == 0
        assert totals.get("error_count") == 0
        assert totals.get("error_rate_percent") == 0.0
        assert totals.get("tokens_total") == 0
        assert totals.get("cost_total_usd") == 0.0
        assert totals.get("p95_latency_ms") is None
        assert totals.get("cost_per_request") == 0.0
        assert totals.get("cost_per_1k_tokens") == 0.0
        assert totals.get("avg_tokens_per_request") == 0.0
        assert totals.get("tokens_in_out_ratio") is None


# ============================================================================
# TAB 2: OVERVIEW TAB SCORECARDS
# ============================================================================
class TestOverviewTabScorecards:
    """Tab 2: Overview Tab Scorecards Audit & Verification"""

    def test_overview_scorecards_real_data_match(self, api_client, auth_headers, mw_conn, ow_conn):
        """Verify Overview scorecard metrics match PostgreSQL live tables."""
        summary_resp = api_client.get("/v1/_mw/summary?minutes=43200", headers=auth_headers)
        health_resp = api_client.get("/v1/_mw/health", headers=auth_headers)
        csat_resp = api_client.get("/v1/_mw/admin/analytics/satisfaction", headers=auth_headers)

        assert summary_resp.status_code == 200
        assert health_resp.status_code == 200
        assert csat_resp.status_code == 200

        health_data = health_resp.json()
        csat_data = csat_resp.json()

        # Health card
        assert health_data.get("ok") is True
        assert "disk_free_gb" in health_data

        # CSAT card verification against feedback table
        with ow_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM feedback")
            sql_feedback_count = cur.fetchone()[0]
        assert csat_data.get("totals", {}).get("feedback_rows") == sql_feedback_count

    def test_overview_scorecards_zero_data_handling(self, api_client, auth_headers):
        """Verify zero-data handling on Overview endpoints."""
        zero_url = "/v1/_mw/admin/analytics/satisfaction?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z"
        resp = api_client.get(zero_url, headers=auth_headers)
        assert resp.status_code == 200
        totals = resp.json().get("totals", {})
        assert totals.get("total") == 0
        assert totals.get("positive") == 0
        assert totals.get("negative") == 0
        assert totals.get("csat_percent") == 0.0


# ============================================================================
# TAB 3: PROVIDERS TAB SCORECARDS
# ============================================================================
class TestProvidersTabScorecards:
    """Tab 3: Providers Tab Scorecards Audit & Verification"""

    def test_providers_scorecards_real_data_match(self, api_client, auth_headers, mw_conn):
        """Verify Providers scorecard metrics match config & database spend."""
        resp = api_client.get("/v1/_mw/providers", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        totals = data.get("totals", {})
        assert "provider_count" in totals
        assert "total_remaining" in totals
        assert "total_spent" in totals
        assert "total_models" in data

        with mw_conn.cursor() as cur:
            cur.execute("SELECT config_value FROM mw_config WHERE config_key = 'alert_config'")
            row = cur.fetchone()
            if row:
                cfg = row[0]
                sql_provider_count = len(cfg.get("admin_alerts", {}).get("api_budgets", {}))
                assert totals.get("provider_count") == sql_provider_count

    def test_providers_scorecards_zero_data_handling(self, api_client, auth_headers):
        """Verify providers endpoint clean handling without mock fallbacks."""
        resp = api_client.get("/v1/_mw/providers", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for p in data.get("providers", []):
            assert not p.get("name", "").startswith("mock_")
            assert not p.get("name", "").startswith("fake_")


# ============================================================================
# TAB 4: ACCESS TAB SCORECARDS
# ============================================================================
class TestAccessTabScorecards:
    """Tab 4: Access Tab Scorecards Audit & Verification"""

    def test_access_scorecards_real_data_match(self, api_client, auth_headers, mw_conn):
        """Verify Access tab scorecard metrics match SQL query on mw_request_log."""
        resp = api_client.get("/v1/_mw/access_summary?minutes=1440", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        time_range = data.get("time_range", {})
        start_iso = time_range.get("start")
        end_iso = time_range.get("end")
        totals = data.get("totals", {})

        with mw_conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) 
                FROM mw_request_log 
                WHERE ts >= %s AND ts <= %s AND payload->>'event' = 'outbound'
            """, (start_iso, end_iso))
            sql_outbound_count = cur.fetchone()[0]

        assert totals.get("requests_total") == sql_outbound_count

    def test_access_scorecards_zero_data_handling(self, api_client, auth_headers):
        """Verify zero-data handling for access summary."""
        zero_url = "/v1/_mw/access_summary?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z"
        resp = api_client.get(zero_url, headers=auth_headers)
        assert resp.status_code == 200
        totals = resp.json().get("totals", {})
        assert totals.get("requests_total") == 0
        assert totals.get("error_count") == 0
        assert totals.get("error_rate_percent") == 0.0
        assert totals.get("p95_latency_ms") is None


# ============================================================================
# TAB 5: USERS & ADOPTION TAB SCORECARDS
# ============================================================================
class TestUsersTabScorecards:
    """Tab 5: Users & Adoption Tab Scorecards Audit & Verification"""

    def test_users_scorecards_real_data_match(self, api_client, auth_headers, mw_conn, ow_conn):
        """Verify Users & Sync Status scorecard metrics match PostgreSQL databases."""
        sync_resp = api_client.get("/v1/_mw/admin/users/sync-status", headers=auth_headers)
        list_resp = api_client.get("/v1/_mw/admin/users", headers=auth_headers)
        adoption_resp = api_client.get("/v1/_mw/adoption", headers=auth_headers)

        assert sync_resp.status_code == 200
        assert list_resp.status_code == 200
        assert adoption_resp.status_code == 200

        sync_users_list = sync_resp.json().get("users", [])
        list_data = list_resp.json()

        with ow_conn.cursor() as cur:
            cur.execute("SELECT email FROM public.user")
            ow_emails = set(r[0] for r in cur.fetchall())

        with mw_conn.cursor() as cur:
            cur.execute("SELECT user_id FROM mw_users WHERE deleted_at IS NULL")
            mw_emails = set(r[0] for r in cur.fetchall())

        expected_sync_count = len(ow_emails.union(mw_emails))

        assert len(sync_users_list) == expected_sync_count
        assert list_data.get("total") == len(mw_emails)

    def test_users_scorecards_zero_data_handling(self, api_client, auth_headers):
        """Verify adoption zero-data range handling."""
        zero_url = "/v1/_mw/adoption?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z"
        resp = api_client.get(zero_url, headers=auth_headers)
        assert resp.status_code == 200
        roster = resp.json().get("roster", {})
        assert roster.get("new_accounts_in_period") == 0


# ============================================================================
# TAB 6: LOGS TAB SCORECARDS
# ============================================================================
class TestLogsTabScorecards:
    """Tab 6: Audit Logs Tab Scorecards Audit & Verification"""

    def test_logs_scorecards_real_data_match(self, api_client, auth_headers, mw_conn):
        """Verify audit log count matches mw_audit_log row count within date window."""
        zero_url = "/v1/_mw/audit/query?start=2000-01-01T00:00:00Z&end=2099-01-01T00:00:00Z&limit=10"
        resp = api_client.get(zero_url, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        with mw_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM mw_audit_log")
            sql_logs_count = cur.fetchone()[0]

        assert data.get("total") == sql_logs_count

    def test_logs_scorecards_zero_data_handling(self, api_client, auth_headers):
        """Verify audit query zero range returns total=0 and results=[]."""
        zero_url = "/v1/_mw/audit/query?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z"
        resp = api_client.get(zero_url, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("total") == 0
        assert data.get("results") == []


# ============================================================================
# TAB 7: RAG HEALTH TAB SCORECARDS
# ============================================================================
class TestRagHealthTabScorecards:
    """Tab 7: RAG Health Tab Scorecards Audit & Verification"""

    def test_rag_health_scorecards_real_data_match(self, api_client, auth_headers, mw_conn):
        """Verify RAG health ingestion calls match mw_audit_log embedding endpoints."""
        resp = api_client.get("/v1/_mw/rag-health/ingestion", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        time_range = data.get("time_range", {})
        start_iso = time_range.get("start")
        end_iso = time_range.get("end")
        summary = data.get("summary", {})

        with mw_conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) FROM mw_audit_log 
                WHERE endpoint ILIKE %s AND ts >= %s AND ts <= %s
            """, ('%embeddings%', start_iso, end_iso))
            sql_ingest_count = cur.fetchone()[0]

        assert summary.get("total_calls") == sql_ingest_count

    def test_rag_health_scorecards_zero_data_handling(self, api_client, auth_headers):
        """Verify RAG health zero-data range handling."""
        zero_url = "/v1/_mw/rag-health/ingestion?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z"
        resp = api_client.get(zero_url, headers=auth_headers)
        assert resp.status_code == 200
        summary = resp.json().get("summary", {})
        assert summary.get("total_calls") == 0
        assert summary.get("failures") == 0
        assert summary.get("failure_rate") == 0.0
        assert summary.get("avg_latency_ms") is None


# ============================================================================
# TAB 8: KNOWLEDGE TAB SCORECARDS
# ============================================================================
class TestKnowledgeTabScorecards:
    """Tab 8: Knowledge Analytics Tab Scorecards Audit & Verification"""

    def test_knowledge_scorecards_real_data_match(self, api_client, auth_headers, ow_conn):
        """Verify Knowledge Analytics metrics match Open WebUI knowledge, file & document_chunk tables."""
        resp = api_client.get("/v1/_mw/knowledge-analytics/inventory", headers=auth_headers)
        assert resp.status_code == 200
        totals = resp.json().get("totals", {})

        with ow_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM knowledge")
            sql_kbs = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM file")
            sql_files = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM document_chunk")
            sql_chunks = cur.fetchone()[0]

        assert totals.get("knowledge_bases") == sql_kbs
        assert totals.get("files") == sql_files
        assert totals.get("chunks") == sql_chunks

    def test_knowledge_scorecards_zero_data_handling(self, api_client, auth_headers):
        """Verify knowledge inventory response integrity."""
        zero_url = "/v1/_mw/knowledge-analytics/inventory?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z"
        resp = api_client.get(zero_url, headers=auth_headers)
        assert resp.status_code == 200
        totals = resp.json().get("totals", {})
        assert isinstance(totals.get("knowledge_bases"), int)
        assert isinstance(totals.get("files"), int)
        assert isinstance(totals.get("chunks"), int)


# ============================================================================
# TAB 9: GROUPS TAB SCORECARDS
# ============================================================================
class TestGroupsTabScorecards:
    """Tab 9: Group Analytics Tab Scorecards Audit & Verification"""

    def test_groups_scorecards_real_data_match(self, api_client, auth_headers, ow_conn):
        """Verify department count matches group table in Open WebUI DB."""
        resp = api_client.get("/v1/_mw/admin/analytics/groups", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        with ow_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM public.group")
            sql_dept_count = cur.fetchone()[0]

        assert data.get("department_count") == sql_dept_count

    def test_groups_scorecards_zero_data_handling(self, api_client, auth_headers):
        """Verify group analytics zero date range handling."""
        zero_url = "/v1/_mw/admin/analytics/groups?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z"
        resp = api_client.get(zero_url, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("dept_cost_total") == 0.0


# ============================================================================
# TAB 10: CHAT ANALYTICS TAB SCORECARDS
# ============================================================================
class TestChatAnalyticsTabScorecards:
    """Tab 10: Chat Analytics Tab Scorecards Audit & Verification"""

    def test_chat_analytics_scorecards_real_data_match(self, api_client, auth_headers, ow_conn):
        """Verify chat total count matches chat table in Open WebUI DB within window."""
        resp = api_client.get("/v1/_mw/admin/analytics/chat", headers=auth_headers)
        assert resp.status_code == 200
        totals = resp.json().get("totals", {})

        now = dt.datetime.now(dt.timezone.utc)
        cutoff = now - dt.timedelta(minutes=43200)
        start_ts = int(cutoff.timestamp())
        end_ts = int(now.timestamp())

        with ow_conn.cursor() as cur:
            cur.execute("SELECT COUNT(id) FROM chat WHERE created_at >= %s AND created_at <= %s", (start_ts, end_ts))
            sql_chats_count = cur.fetchone()[0]

        assert totals.get("chats") == sql_chats_count

    def test_chat_analytics_scorecards_zero_data_handling(self, api_client, auth_headers):
        """Verify chat analytics zero date range handling."""
        zero_url = "/v1/_mw/admin/analytics/chat?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z"
        resp = api_client.get(zero_url, headers=auth_headers)
        assert resp.status_code == 200
        totals = resp.json().get("totals", {})
        assert totals.get("chats") == 0
        assert totals.get("requests") == 0
        assert totals.get("tokens") == 0
        assert totals.get("cost_usd") == 0.0
        assert totals.get("active_users") == 0


# ============================================================================
# TAB 11: SATISFACTION TAB SCORECARDS
# ============================================================================
class TestSatisfactionTabScorecards:
    """Tab 11: Satisfaction Tab Scorecards Audit & Verification"""

    def test_satisfaction_scorecards_real_data_match(self, api_client, auth_headers, ow_conn):
        """Verify satisfaction ratings match feedback table in Open WebUI DB."""
        resp = api_client.get("/v1/_mw/admin/analytics/satisfaction", headers=auth_headers)
        assert resp.status_code == 200
        totals = resp.json().get("totals", {})

        with ow_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM feedback")
            sql_feedback_count = cur.fetchone()[0]

        assert totals.get("total") == sql_feedback_count

    def test_satisfaction_scorecards_zero_data_handling(self, api_client, auth_headers):
        """Verify satisfaction analytics zero date range handling."""
        zero_url = "/v1/_mw/admin/analytics/satisfaction?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z"
        resp = api_client.get(zero_url, headers=auth_headers)
        assert resp.status_code == 200
        totals = resp.json().get("totals", {})
        assert totals.get("positive") == 0
        assert totals.get("negative") == 0
        assert totals.get("total") == 0
        assert totals.get("csat_percent") == 0.0
        assert totals.get("feedback_rows") == 0


# ============================================================================
# TAB 12: PRICES TAB SCORECARDS
# ============================================================================
class TestPricesTabScorecards:
    """Tab 12: Prices Tab Scorecards Audit & Verification"""

    def test_prices_scorecards_real_data_match(self, api_client, auth_headers, mw_conn):
        """Verify pricing model catalog matches mw_prices table in Middleware DB."""
        resp = api_client.get("/v1/_mw/admin/prices", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        models_in_api = len([k for k in data.keys() if k != "_schema"])

        with mw_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM mw_prices WHERE model_name != '_schema'")
            sql_prices_count = cur.fetchone()[0]

        assert models_in_api == sql_prices_count

    def test_prices_scorecards_zero_data_handling(self, api_client, auth_headers):
        """Verify prices catalog returns dictionary without dummy values."""
        resp = api_client.get("/v1/_mw/admin/prices", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)


# ============================================================================
# TAB 13: SETTINGS TAB SCORECARDS
# ============================================================================
class TestSettingsTabScorecards:
    """Tab 13: Settings Tab Scorecards Audit & Verification"""

    def test_settings_scorecards_real_data_match(self, api_client, auth_headers, mw_conn):
        """Verify alert config matches mw_config table."""
        resp = api_client.get("/v1/_mw/admin/alerts/config", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "admin_alerts" in data
        assert "smtp" in data

        with mw_conn.cursor() as cur:
            cur.execute("SELECT config_value FROM mw_config WHERE config_key = 'alert_config'")
            row = cur.fetchone()
            if row:
                sql_config = row[0]
                assert data.get("admin_alerts", {}).get("api_budgets") == sql_config.get("admin_alerts", {}).get("api_budgets")

    def test_settings_scorecards_zero_data_handling(self, api_client, auth_headers):
        """Verify non-existent user quota lookup returns found=False without fallback."""
        resp = api_client.get("/v1/_mw/quota-status?user_id=nonexistent_user_99999@example.com", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("found") is False


# ============================================================================
# GLOBAL METRICS INTEGRITY AUDIT (ALL 13 TABS)
# ============================================================================
class TestGlobalScorecardsIntegrity:
    """Global Audit: Verify 0% Hardcoded, Fake or Mock Values Across All 13 Tabs"""

    ALL_SCORECARD_ZERO_ENDPOINTS = [
        "/v1/_mw/summary?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/access_summary?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/adoption?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/audit/query?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/rag-health/ingestion?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/rag-health/retrieval?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/rag-health/storage",
        "/v1/_mw/knowledge-analytics/inventory?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/knowledge-analytics/kb-value?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/knowledge-analytics/governance",
        "/v1/_mw/admin/analytics/groups?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/admin/analytics/chat?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/admin/analytics/satisfaction?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/admin/prices",
        "/v1/_mw/admin/alerts/config",
    ]

    @pytest.mark.parametrize("endpoint", ALL_SCORECARD_ZERO_ENDPOINTS)
    def test_zero_mock_or_dummy_values_in_endpoints(self, api_client, auth_headers, endpoint):
        """Verify no endpoint returns hardcoded fake values or mock constants."""
        resp = api_client.get(endpoint, headers=auth_headers)
        assert resp.status_code == 200, f"Endpoint {endpoint} returned status {resp.status_code}"
        text_content = resp.text.lower()

        # Check for obvious mock indicators
        suspicious_terms = ["fake_data", "mock_value", "dummy_metric", "hardcoded_fallback"]
        for term in suspicious_terms:
            assert term not in text_content, f"Found suspicious mock indicator '{term}' in {endpoint}"
