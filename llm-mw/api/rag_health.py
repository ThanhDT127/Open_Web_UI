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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import Query, Request

_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _parse_range(start: Optional[str], end: Optional[str], default_hours: int = 24 * 7):
    """Parse ISO start/end query params, defaulting to the last ``default_hours``."""
    now = datetime.now(_TZ)
    if start:
        try:
            cutoff = datetime.fromisoformat(start.replace("Z", "+00:00"))
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=_TZ)
        except ValueError:
            cutoff = now - timedelta(hours=default_hours)
    else:
        cutoff = now - timedelta(hours=default_hours)

    if end:
        try:
            end_time = datetime.fromisoformat(end.replace("Z", "+00:00"))
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=_TZ)
        except ValueError:
            end_time = now
    else:
        end_time = now

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
