"""
Milestone R2: Middleware API Endpoints Health Test Suite
Targeting Open WebUI v0.11.0 + LLM Middleware API (/v1/_mw/*).

Validates all 8 Middleware API endpoint groups for:
- HTTP 200 OK responses with valid authentication (X-Admin-Key / Bearer token).
- HTTP 403 Forbidden responses when missing or supplying invalid authentication.
- Schema completeness & data integrity for returned JSON payloads
  (Scorecards, Top Spenders, Pareto Analysis, RAG Health, Governance, User Quotas).
"""

import os
import sys
import pytest

# Ensure llm-mw directory is in Python path for importing main app & core modules
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
LLM_MW_DIR = os.path.join(PROJECT_ROOT, "llm-mw")

if LLM_MW_DIR not in sys.path:
    sys.path.insert(0, LLM_MW_DIR)

# Set default env vars if not present before module initialization
if not os.getenv("ADMIN_KEY"):
    os.environ["ADMIN_KEY"] = "admin_master_key_456"

if not os.getenv("DATABASE_URL") and not os.getenv("MW_DATABASE_URL"):
    # Try connecting to postgres on port 5433 (or 5432)
    os.environ["DATABASE_URL"] = "postgresql://openwebui_user:pg_7h9k2m4n6p8r0v2w4x6z@localhost:5433/middleware"


@pytest.fixture(scope="module")
def api_client():
    """
    Module-scoped FastAPI TestClient fixture with initialized PostgreSQL pool.
    """
    from core.db import init_pool, _pool
    db_url = os.getenv("MW_DATABASE_URL") or os.getenv("DATABASE_URL")

    # If pool isn't initialized or failed, try 5433 then 5432
    if _pool is None:
        try:
            init_pool(db_url)
        except Exception:
            # Fallback to port 5432 if port 5433 was default and failed
            alt_url = db_url.replace(":5433/", ":5432/") if ":5433/" in db_url else db_url.replace(":5432/", ":5433/")
            init_pool(alt_url)

    from main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def admin_key():
    """Returns valid admin key for auth headers."""
    return os.getenv("ADMIN_KEY", "admin_master_key_456")


@pytest.fixture(scope="module")
def auth_headers(admin_key):
    """Headers with valid X-Admin-Key."""
    return {"X-Admin-Key": admin_key}


# List of representative endpoints from all 8 groups for auth tests
ALL_GROUPS_SAMPLE_ENDPOINTS = [
    "/v1/_mw/admin/analytics/chat",            # Group 1
    "/v1/_mw/admin/analytics/groups",          # Group 2
    "/v1/_mw/knowledge-analytics/inventory",    # Group 3
    "/v1/_mw/admin/users",                     # Group 4
    "/v1/_mw/adoption",                        # Group 5
    "/v1/_mw/admin/analytics/satisfaction",    # Group 6
    "/v1/_mw/summary",                         # Group 7
    "/v1/_mw/rag-health/ingestion",            # Group 8
]


class TestAuthenticationGuard:
    """Requirement R2: Authentication Guard Enforcement (X-Admin-Key / Bearer Token)"""

    @pytest.mark.parametrize("endpoint", ALL_GROUPS_SAMPLE_ENDPOINTS)
    def test_missing_auth_header_returns_403(self, api_client, endpoint):
        """Verify requests missing authentication headers are rejected with 403 Forbidden."""
        resp = api_client.get(endpoint)
        assert resp.status_code == 403, f"Expected 403 Forbidden for {endpoint} without auth, got {resp.status_code}"
        data = resp.json()
        assert data.get("detail") == "Invalid admin key or session"

    @pytest.mark.parametrize("endpoint", ALL_GROUPS_SAMPLE_ENDPOINTS)
    def test_invalid_admin_key_returns_403(self, api_client, endpoint):
        """Verify requests with an invalid X-Admin-Key are rejected with 403 Forbidden."""
        resp = api_client.get(endpoint, headers={"X-Admin-Key": "invalid_secret_key_99999"})
        assert resp.status_code == 403, f"Expected 403 Forbidden for {endpoint} with invalid key, got {resp.status_code}"
        data = resp.json()
        assert data.get("detail") == "Invalid admin key or session"

    def test_valid_x_admin_key_header_returns_200(self, api_client, admin_key):
        """Verify X-Admin-Key header allows access to guarded endpoints."""
        resp = api_client.get("/v1/_mw/summary", headers={"X-Admin-Key": admin_key})
        assert resp.status_code == 200, f"Expected 200 OK with X-Admin-Key, got {resp.status_code}"

    def test_valid_bearer_token_header_returns_200(self, api_client, admin_key):
        """Verify Authorization: Bearer <ADMIN_KEY> header allows access to guarded endpoints."""
        resp = api_client.get("/v1/_mw/summary", headers={"Authorization": f"Bearer {admin_key}"})
        assert resp.status_code == 200, f"Expected 200 OK with Bearer token, got {resp.status_code}"


class TestGroup1ChatAnalytics:
    """Group 1: Chat Analytics (GET /v1/_mw/admin/analytics/chat)"""

    def test_chat_analytics_endpoint_200_and_schema(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/admin/analytics/chat", headers=auth_headers)
        assert resp.status_code == 200, f"Chat analytics returned status {resp.status_code}"
        data = resp.json()

        # Assert top-level keys
        expected_keys = {"totals", "timeseries", "hourly_activity", "model_breakdown", "leaderboard"}
        assert expected_keys.issubset(data.keys()), f"Missing keys in Chat Analytics response: {expected_keys - data.keys()}"

        # Totals structure assertion
        totals = data["totals"]
        assert isinstance(totals, dict)
        for field in ["chats", "requests", "tokens", "cost_usd", "active_users"]:
            assert field in totals, f"Field '{field}' missing from Chat Analytics totals"
            assert isinstance(totals[field], (int, float))

        # Hourly activity format check (24-hour breakdown)
        assert isinstance(data["hourly_activity"], list)
        assert len(data["hourly_activity"]) == 24, "hourly_activity should contain 24 elements (0..23)"
        assert data["hourly_activity"][0].get("hour") == 0


class TestGroup2GroupAnalytics:
    """Group 2: Group Analytics (GET /v1/_mw/admin/analytics/groups & /groups/{group_id}/users)"""

    def test_group_analytics_overview_endpoint_200_and_schema(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/admin/analytics/groups", headers=auth_headers)
        assert resp.status_code == 200, f"Group analytics returned status {resp.status_code}"
        data = resp.json()

        expected_keys = {
            "status", "groups", "department_count", "dept_cost_total",
            "assigned_member_count", "provisioned_user_count", "multi_group_user_count"
        }
        assert expected_keys.issubset(data.keys()), f"Missing keys in Group Analytics response: {expected_keys - data.keys()}"
        assert data["status"] == "ok"
        assert isinstance(data["groups"], list)

        if data["groups"]:
            g = data["groups"][0]
            for field in ["group_id", "group_name", "total_requests", "total_cost", "total_tokens", "cost_share_of_system_percent"]:
                assert field in g, f"Group object missing field '{field}'"

    def test_group_users_drilldown_endpoint_200_and_schema(self, api_client, auth_headers):
        # Fetch group list to obtain a real group_id
        groups_resp = api_client.get("/v1/_mw/admin/analytics/groups", headers=auth_headers)
        groups = groups_resp.json().get("groups", [])

        group_id = groups[0]["group_id"] if groups and groups[0].get("group_id") else "dummy-group-id"

        resp = api_client.get(f"/v1/_mw/admin/analytics/groups/{group_id}/users", headers=auth_headers)
        assert resp.status_code == 200, f"Group users drill-down returned status {resp.status_code}"
        data = resp.json()

        assert "status" in data and data["status"] == "ok"
        assert "users" in data and isinstance(data["users"], list)


class TestGroup3KnowledgeAnalytics:
    """Group 3: Knowledge Analytics (GET /v1/_mw/knowledge-analytics/inventory, /kb-value, /governance)"""

    def test_knowledge_inventory_endpoint_200_and_schema(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/knowledge-analytics/inventory", headers=auth_headers)
        assert resp.status_code == 200, f"Knowledge inventory returned status {resp.status_code}"
        data = resp.json()

        expected_keys = {"totals", "growth", "type_distribution", "size_distribution", "time_range"}
        assert expected_keys.issubset(data.keys()), f"Missing keys in Knowledge Inventory response: {expected_keys - data.keys()}"

        totals = data["totals"]
        for field in ["knowledge_bases", "files", "unique_documents", "dangling_files", "chunks", "storage_bytes"]:
            assert field in totals, f"Totals missing field '{field}'"
            assert totals[field] >= 0

    def test_knowledge_kb_value_endpoint_200_and_schema(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/knowledge-analytics/kb-value", headers=auth_headers)
        assert resp.status_code == 200, f"Knowledge KB Value returned status {resp.status_code}"
        data = resp.json()

        expected_keys = {"knowledge_bases", "category_counts", "ambiguous_sources", "unattributed_sources", "time_range"}
        assert expected_keys.issubset(data.keys()), f"Missing keys in Knowledge KB Value response: {expected_keys - data.keys()}"

        cat = data["category_counts"]
        for category in ["star", "needs_tuning", "dead", "unproven"]:
            assert category in cat, f"Category '{category}' missing from category_counts"
            assert isinstance(cat[category], int)

    def test_knowledge_governance_endpoint_200_and_schema(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/knowledge-analytics/governance", headers=auth_headers)
        assert resp.status_code == 200, f"Knowledge governance returned status {resp.status_code}"
        data = resp.json()

        expected_keys = {"duplicates", "reclaimable_bytes", "orphans", "owners"}
        assert expected_keys.issubset(data.keys()), f"Missing keys in Knowledge Governance response: {expected_keys - data.keys()}"
        assert isinstance(data["duplicates"], list)
        assert isinstance(data["reclaimable_bytes"], (int, float))
        assert isinstance(data["orphans"], dict)


class TestGroup4AdminUsers:
    """Group 4: Admin Users (GET /v1/_mw/admin/users, /sync-status, /reconciliation)"""

    def test_admin_users_list_endpoint_200_and_schema(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/admin/users", headers=auth_headers)
        assert resp.status_code == 200, f"Admin users list returned status {resp.status_code}"
        data = resp.json()

        assert "users" in data and isinstance(data["users"], list)
        assert "total" in data and isinstance(data["total"], int)
        assert data["total"] == len(data["users"])

        if data["users"]:
            user = data["users"][0]
            for field in ["user_id", "role", "active", "allowed_models", "used_tokens", "used_cost_usd", "quota"]:
                assert field in user, f"User object missing required field '{field}'"

    def test_admin_users_sync_status_endpoint_200_and_schema(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/admin/users/sync-status", headers=auth_headers)
        assert resp.status_code == 200, f"Users sync-status returned status {resp.status_code}"
        data = resp.json()
        assert "users" in data and isinstance(data["users"], list)

    def test_admin_users_reconciliation_endpoint_200_and_schema(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/admin/users/reconciliation", headers=auth_headers)
        assert resp.status_code == 200, f"Users reconciliation returned status {resp.status_code}"
        data = resp.json()

        expected_keys = {"matched", "unmatched_openwebui", "unmatched_middleware", "conflicts", "duplicate_mappings", "disabled", "pending"}
        assert expected_keys.issubset(data.keys()), f"Missing keys in User Reconciliation response: {expected_keys - data.keys()}"


class TestGroup5AdoptionMetrics:
    """Group 5: Adoption Metrics (GET /v1/_mw/adoption)"""

    def test_adoption_metrics_endpoint_200_and_schema(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/adoption", headers=auth_headers)
        assert resp.status_code == 200, f"Adoption metrics returned status {resp.status_code}"
        data = resp.json()

        expected_keys = {"time_range", "roster", "adoption", "activity_series", "dormant", "quota_histogram", "pareto"}
        assert expected_keys.issubset(data.keys()), f"Missing keys in Adoption metrics response: {expected_keys - data.keys()}"

        adoption = data["adoption"]
        for field in ["active_users", "provisioned", "adoption_rate_percent"]:
            assert field in adoption, f"Adoption object missing field '{field}'"

        pareto = data["pareto"]
        assert "top10_pct_cost_share" in pareto
        assert "breakdown_by_user" in pareto


class TestGroup6SatisfactionAnalytics:
    """Group 6: Satisfaction Analytics (GET /v1/_mw/admin/analytics/satisfaction)"""

    def test_satisfaction_analytics_endpoint_200_and_schema(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/admin/analytics/satisfaction", headers=auth_headers)
        assert resp.status_code == 200, f"Satisfaction analytics returned status {resp.status_code}"
        data = resp.json()

        expected_keys = {"totals", "model_leaderboard", "recent_feedback"}
        assert expected_keys.issubset(data.keys()), f"Missing keys in Satisfaction response: {expected_keys - data.keys()}"

        totals = data["totals"]
        for field in ["positive", "negative", "total", "csat_percent", "feedback_rows"]:
            assert field in totals, f"Totals missing field '{field}'"


class TestGroup7EnhancedSummary:
    """Group 7: Enhanced Summary (GET /v1/_mw/summary)"""

    def test_enhanced_summary_endpoint_200_and_schema(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/summary", headers=auth_headers)
        assert resp.status_code == 200, f"Enhanced summary returned status {resp.status_code}"
        data = resp.json()

        expected_keys = {"time_range", "totals", "breakdown_by_user", "breakdown_by_model", "timeseries", "hourly_activity"}
        assert expected_keys.issubset(data.keys()), f"Missing keys in Enhanced Summary response: {expected_keys - data.keys()}"

        totals = data["totals"]
        for field in [
            "requests_total", "requests_ok", "error_count", "error_rate_percent",
            "tokens_total", "cost_total_usd", "top10_pct_cost_share", "cost_per_request",
            "cost_per_1k_tokens", "rpm_avg"
        ]:
            assert field in totals, f"Summary totals missing field '{field}'"


class TestGroup8OperationalRAGAndToolAccess:
    """Group 8: Operational RAG & Tool Access (GET /v1/_mw/rag-health/*, /admin/tool-access/*, /audit/query)"""

    def test_rag_health_ingestion_endpoint_200_and_schema(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/rag-health/ingestion", headers=auth_headers)
        assert resp.status_code == 200, f"RAG health ingestion returned status {resp.status_code}"
        data = resp.json()

        expected_keys = {"summary", "recent_failures", "time_range"}
        assert expected_keys.issubset(data.keys()), f"Missing keys in RAG ingestion response: {expected_keys - data.keys()}"

    def test_rag_health_retrieval_endpoint_200_and_schema(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/rag-health/retrieval", headers=auth_headers)
        assert resp.status_code == 200, f"RAG health retrieval returned status {resp.status_code}"
        data = resp.json()

        expected_keys = {"kb_attached", "evaluated", "unpaired", "cited", "hit_rate", "by_model", "coverage"}
        assert expected_keys.issubset(data.keys()), f"Missing keys in RAG retrieval response: {expected_keys - data.keys()}"

    def test_rag_health_storage_endpoint_200_and_schema(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/rag-health/storage", headers=auth_headers)
        assert resp.status_code == 200, f"RAG health storage returned status {resp.status_code}"
        data = resp.json()

        expected_keys = {"zero_chunk_kbs", "orphaned_chunks", "chunk_count_outliers", "cached"}
        assert expected_keys.issubset(data.keys()), f"Missing keys in RAG storage response: {expected_keys - data.keys()}"

    def test_admin_tool_access_groups_endpoint_200_and_schema(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/admin/tool-access/groups", headers=auth_headers)
        assert resp.status_code == 200, f"Tool access groups returned status {resp.status_code}"
        data = resp.json()
        assert "groups" in data and isinstance(data["groups"], list)

    def test_audit_query_endpoint_200_and_schema(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/audit/query", headers=auth_headers)
        assert resp.status_code == 200, f"Audit query returned status {resp.status_code}"
        data = resp.json()

        expected_keys = {"total", "limit", "offset", "results", "source", "distinct_users", "distinct_models"}
        assert expected_keys.issubset(data.keys()), f"Missing keys in Audit query response: {expected_keys - data.keys()}"
        assert isinstance(data["results"], list)


class TestPayloadMetricsIntegrity:
    """Acceptance Criteria Verification: Metric Structures (Scorecards, Top Spenders, Pareto, RAG Health)"""

    def test_scorecards_metric_structure(self, api_client, auth_headers):
        """Verify Scorecards (Totals, KPI Metrics) structure in summary & chat analytics."""
        summary_resp = api_client.get("/v1/_mw/summary", headers=auth_headers)
        summary_totals = summary_resp.json().get("totals", {})

        assert "requests_total" in summary_totals
        assert "tokens_total" in summary_totals
        assert "cost_total_usd" in summary_totals

        # P95 Latency field check (can be None or float)
        assert "p95_latency_ms" in summary_totals
        if summary_totals["p95_latency_ms"] is not None:
            assert summary_totals["p95_latency_ms"] >= 0.0

    def test_top_spenders_metric_structure(self, api_client, auth_headers):
        """Verify Top Spenders metric breakdown in summary & chat analytics leaderboard."""
        summary_resp = api_client.get("/v1/_mw/summary", headers=auth_headers)
        breakdown_by_user = summary_resp.json().get("breakdown_by_user", [])
        assert isinstance(breakdown_by_user, list)

        if breakdown_by_user:
            user_entry = breakdown_by_user[0]
            assert "user_id" in user_entry
            assert "tokens_total" in user_entry
            assert "cost_usd" in user_entry

        chat_resp = api_client.get("/v1/_mw/admin/analytics/chat", headers=auth_headers)
        leaderboard = chat_resp.json().get("leaderboard", [])
        assert isinstance(leaderboard, list)

    def test_pareto_analysis_metric_structure(self, api_client, auth_headers):
        """Verify Pareto Analysis (top 10% cost concentration) structure in adoption metrics."""
        adoption_resp = api_client.get("/v1/_mw/adoption", headers=auth_headers)
        pareto = adoption_resp.json().get("pareto", {})

        assert "top10_pct_cost_share" in pareto
        share = pareto["top10_pct_cost_share"]
        if share is not None:
            assert isinstance(share, (int, float))
            assert 0.0 <= share <= 100.0, f"Pareto cost share out of range [0, 100]: {share}"

    def test_rag_health_metric_structure(self, api_client, auth_headers):
        """Verify RAG Health metrics across ingestion, retrieval, and storage endpoints."""
        retrieval_resp = api_client.get("/v1/_mw/rag-health/retrieval", headers=auth_headers)
        retrieval = retrieval_resp.json()
        assert "hit_rate" in retrieval
        hit_rate = retrieval["hit_rate"]
        if hit_rate is not None:
            assert 0.0 <= hit_rate <= 100.0, f"RAG hit_rate percentage out of range [0, 100]: {hit_rate}"

        storage_resp = api_client.get("/v1/_mw/rag-health/storage", headers=auth_headers)
        storage = storage_resp.json()
        assert "zero_chunk_kbs" in storage
        assert "orphaned_chunks" in storage
