"""
RAG Health API — ingestion, retrieval and storage health for the dashboard.

Endpoints (admin only):
  * GET /v1/_mw/rag-health/ingestion  — embedding failure metrics + recent failures
  * GET /v1/_mw/rag-health/retrieval  — citation hit-rate + breakdowns + zero-citation list
  * GET /v1/_mw/rag-health/storage    — zero-chunk KBs, orphaned chunks, chunk-count outliers

All three share the ``start`` / ``end`` date-range filter; retrieval additionally
accepts ``model`` and ``user_id``.
"""

from typing import Optional

from fastapi import Query, Request

from api.summary_v2 import _resolve_range

# This tab's historical default when the caller sends no explicit window. The
# dashboard always sends absolute start/end (buildRangeParams), so it only applies
# to direct API calls.
_DEFAULT_MINUTES = 60 * 24 * 7


def _parse_range(start: Optional[str], end: Optional[str]):
    """Resolve the window through the single shared resolver.

    The local copy this replaces swallowed ``ValueError`` and silently fell back to
    the last 7 days, so a malformed ``start`` rendered a full page of plausible
    numbers for a window nobody asked for — while the Usage tab answered 400 for the
    same input. One bad parameter, two behaviours, no way for the reader to tell.
    """
    cutoff, end_time, _ = _resolve_range(minutes=_DEFAULT_MINUTES, start=start, end=end)
    return cutoff, end_time


def get_rag_ingestion(
    request: Request,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Embedding ingestion health for a date range."""
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    from core.rag_health import query_ingestion_summary, query_recent_embedding_failures

    cutoff, end_time = _parse_range(start, end)
    summary = query_ingestion_summary(cutoff, end_time)
    failures = query_recent_embedding_failures(cutoff, end_time, limit=limit)
    return {
        "summary": summary,
        "recent_failures": failures,
        "time_range": {"start": cutoff.isoformat(), "end": end_time.isoformat()},
    }


def get_rag_retrieval(
    request: Request,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
):
    """Retrieval citation hit-rate for a date range, optionally filtered."""
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    from core.rag_health import query_retrieval_health

    cutoff, end_time = _parse_range(start, end)
    data = query_retrieval_health(cutoff, end_time, model=model or None, user_id=user_id or None)
    data["time_range"] = {"start": cutoff.isoformat(), "end": end_time.isoformat()}
    return data


def get_rag_storage(
    request: Request,
    refresh: bool = Query(False),
):
    """Storage-health anomalies (cached; ``refresh=true`` bypasses the cache)."""
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    from core.rag_health import query_storage_health
    return query_storage_health(force_refresh=refresh)
