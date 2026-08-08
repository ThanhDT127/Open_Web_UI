"""
Adversarial Stress Testing Suite for Dashboard Scorecards & Metric Cards (All 13 Tabs)
Tests edge case parameters, null handling, zero-row aggregations, precision, and performance.
"""

import os
import sys
import time
import datetime as dt
import pytest

# Ensure llm-mw directory is in Python path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
LLM_MW_DIR = os.path.join(PROJECT_ROOT, "llm-mw")

if LLM_MW_DIR not in sys.path:
    sys.path.insert(0, LLM_MW_DIR)

if not os.getenv("ADMIN_KEY"):
    os.environ["ADMIN_KEY"] = "admin_master_key_456"

if not os.getenv("DATABASE_URL") and not os.getenv("MW_DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://openwebui_user:pg_7h9k2m4n6p8r0v2w4x6z@localhost:5433/middleware"


@pytest.fixture(scope="module")
def api_client():
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
    return {"X-Admin-Key": os.getenv("ADMIN_KEY", "admin_master_key_456")}


def _assert_no_mock_strings(data, path="root"):
    """Recursively verify no mock/fake/dummy string markers exist anywhere in JSON."""
    if isinstance(data, dict):
        for k, v in data.items():
            _assert_no_mock_strings(v, f"{path}.{k}")
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            _assert_no_mock_strings(item, f"{path}[{idx}]")
    elif isinstance(data, str):
        val_lower = data.lower()
        for mock_word in ["mock_data", "fake_value", "dummy_metric", "hardcoded_fallback"]:
            assert mock_word not in val_lower, f"Found mock marker '{mock_word}' at {path}: '{data}'"


# ============================================================================
# ADVERSARIAL TEST CATEGORY 1: INVALID & INVERTED DATE RANGE PARAMETERS
# ============================================================================
class TestAdversarialParameterValidation:
    """Stress test endpoints with inverted ranges, malformed dates, and extreme values."""

    def test_inverted_date_range_returns_400(self, api_client, auth_headers):
        """Inverted start > end should return 400 Bad Request across endpoints."""
        endpoints = [
            "/v1/_mw/summary?start=2026-12-31T00:00:00Z&end=2026-01-01T00:00:00Z",
            "/v1/_mw/access_summary?start=2026-12-31T00:00:00Z&end=2026-01-01T00:00:00Z",
            "/v1/_mw/adoption?start=2026-12-31T00:00:00Z&end=2026-01-01T00:00:00Z",
            "/v1/_mw/rag-health/ingestion?start=2026-12-31T00:00:00Z&end=2026-01-01T00:00:00Z",
        ]
        for ep in endpoints:
            resp = api_client.get(ep, headers=auth_headers)
            assert resp.status_code == 400, f"Expected 400 for inverted range on {ep}, got {resp.status_code}"
            assert "start" in resp.text.lower() or "before" in resp.text.lower()

    def test_malformed_datetime_strings(self, api_client, auth_headers):
        """Malformed ISO dates should return 400 Bad Request, not 500 internal crash."""
        endpoints = [
            "/v1/_mw/summary?start=invalid-date&end=2026-01-01T00:00:00Z",
            "/v1/_mw/summary?start=2026-01-01T00:00:00Z&end=not-a-timestamp",
        ]
        for ep in endpoints:
            resp = api_client.get(ep, headers=auth_headers)
            assert resp.status_code == 400, f"Expected 400 for malformed date on {ep}, got {resp.status_code}"

    def test_extreme_minutes_parameter(self, api_client, auth_headers):
        """Very large minutes parameter should not overflow or crash."""
        resp = api_client.get("/v1/_mw/summary?minutes=52560000", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "totals" in data


# ============================================================================
# ADVERSARIAL TEST CATEGORY 2: ZERO-ROW & DIVISION-BY-ZERO RESILIENCE
# ============================================================================
class TestAdversarialZeroRowResilience:
    """Stress test zero-row aggregations for division by zero, NaN, or Infinity."""

    ALL_SCORECARD_ENDPOINTS_ZERO_DATA = [
        "/v1/_mw/summary?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/access_summary?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/adoption?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/audit/query?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/rag-health/ingestion?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/rag-health/retrieval?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/knowledge-analytics/inventory?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/knowledge-analytics/kb-value?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/admin/analytics/groups?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/admin/analytics/chat?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
        "/v1/_mw/admin/analytics/satisfaction?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z",
    ]

    @pytest.mark.parametrize("endpoint", ALL_SCORECARD_ENDPOINTS_ZERO_DATA)
    def test_zero_row_no_nan_or_inf(self, api_client, auth_headers, endpoint):
        """Verify zero-data response contains no 'NaN', 'Infinity', or division errors."""
        resp = api_client.get(endpoint, headers=auth_headers)
        assert resp.status_code == 200
        text = resp.text
        assert "NaN" not in text
        assert "Infinity" not in text
        _assert_no_mock_strings(resp.json())

    def test_usage_derived_metrics_zero_denominators(self, api_client, auth_headers):
        """Verify Usage tab request-lens derived metrics when total requests/tokens are 0."""
        zero_url = "/v1/_mw/summary?start=2099-01-01T00:00:00Z&end=2099-01-02T00:00:00Z"
        resp = api_client.get(zero_url, headers=auth_headers)
        totals = resp.json().get("totals", {})

        # Ratios with 0 denominators must return 0.0 or None, never fail or return float('nan')
        assert totals.get("cost_per_request") == 0.0
        assert totals.get("cost_per_1k_tokens") == 0.0
        assert totals.get("avg_tokens_per_request") == 0.0
        assert totals.get("tokens_in_out_ratio") is None
        assert totals.get("error_rate_percent") == 0.0
        assert totals.get("p95_latency_ms") is None


# ============================================================================
# ADVERSARIAL TEST CATEGORY 3: SCORECARD DATA TYPE INTEGRITY ACROSS 13 TABS
# ============================================================================
class TestAdversarialDataTypeIntegrity:
    """Verify exact data types for all numeric metrics (int counts, float costs/percentages)."""

    def test_usage_scorecard_data_types(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/summary?minutes=1440", headers=auth_headers)
        totals = resp.json().get("totals", {})

        assert isinstance(totals.get("requests_total"), int)
        assert isinstance(totals.get("requests_ok"), int)
        assert isinstance(totals.get("error_count"), int)
        assert isinstance(totals.get("tokens_total"), int)
        assert isinstance(totals.get("cost_total_usd"), (float, int))
        assert isinstance(totals.get("error_rate_percent"), (float, int))

    def test_access_scorecard_data_types(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/access_summary?minutes=1440", headers=auth_headers)
        totals = resp.json().get("totals", {})

        assert isinstance(totals.get("requests_total"), int)
        assert isinstance(totals.get("error_count"), int)
        assert isinstance(totals.get("failures"), int)
        assert isinstance(totals.get("denied"), int)
        assert isinstance(totals.get("throttled"), int)

    def test_satisfaction_scorecard_data_types(self, api_client, auth_headers):
        resp = api_client.get("/v1/_mw/admin/analytics/satisfaction", headers=auth_headers)
        totals = resp.json().get("totals", {})

        assert isinstance(totals.get("total"), int)
        assert isinstance(totals.get("positive"), int)
        assert isinstance(totals.get("negative"), int)
        assert isinstance(totals.get("csat_percent"), (float, int))


# ============================================================================
# ADVERSARIAL TEST CATEGORY 4: PERFORMANCE BENCHMARK
# ============================================================================
class TestAdversarialPerformance:
    """Verify scorecard endpoint latency is under 2.0s SLA."""

    ALL_PRIMARY_SCORECARD_ENDPOINTS = [
        "/v1/_mw/summary?minutes=1440",
        "/v1/_mw/health",
        "/v1/_mw/providers",
        "/v1/_mw/access_summary?minutes=1440",
        "/v1/_mw/admin/users/sync-status",
        "/v1/_mw/adoption",
        "/v1/_mw/audit/query?limit=50",
        "/v1/_mw/rag-health/ingestion",
        "/v1/_mw/knowledge-analytics/inventory",
        "/v1/_mw/admin/analytics/groups",
        "/v1/_mw/admin/analytics/chat",
        "/v1/_mw/admin/analytics/satisfaction",
        "/v1/_mw/admin/prices",
        "/v1/_mw/admin/alerts/config",
    ]

    @pytest.mark.parametrize("endpoint", ALL_PRIMARY_SCORECARD_ENDPOINTS)
    def test_scorecard_endpoint_latency(self, api_client, auth_headers, endpoint):
        """Verify API responds within 2000 milliseconds."""
        t0 = time.perf_counter()
        resp = api_client.get(endpoint, headers=auth_headers)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        assert resp.status_code == 200, f"Endpoint {endpoint} failed with {resp.status_code}"
        assert elapsed_ms < 2000.0, f"Endpoint {endpoint} took {elapsed_ms:.1f} ms (> 2000 ms SLA)"
