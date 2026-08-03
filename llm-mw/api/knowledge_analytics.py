"""
Knowledge Analytics API — inventory, KB value and governance for the dashboard.

Endpoints (admin only):
  * GET /v1/_mw/knowledge-analytics/inventory   — corpus totals, growth, distributions
  * GET /v1/_mw/knowledge-analytics/kb-value     — per-KB value matrix + disclosures
  * GET /v1/_mw/knowledge-analytics/governance   — duplicates, orphans, ownership

Inventory and KB-value accept a ``start`` / ``end`` date-range filter; all three
accept ``refresh=true`` to bypass the corpus cache. Read-only.
"""

from typing import Optional

from fastapi import Query, Request

from api.summary_v2 import _resolve_range

# This tab's historical default when the caller sends no explicit window — 30 days,
# where RAG Health uses 7. Two different silent defaults for the same missing
# parameter is exactly why the parse itself must not also be silent.
_DEFAULT_MINUTES = 60 * 24 * 30


def _parse_range(start: Optional[str], end: Optional[str]):
    """Resolve the window through the single shared resolver (raises 400 on bad input)."""
    cutoff, end_time, _ = _resolve_range(minutes=_DEFAULT_MINUTES, start=start, end=end)
    return cutoff, end_time


def get_knowledge_inventory(
    request: Request,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    refresh: bool = Query(False),
):
    """Corpus inventory and growth for a date range."""
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    from core.knowledge_analytics import query_inventory

    cutoff, end_time = _parse_range(start, end)
    try:
        data = query_inventory(cutoff, end_time, force_refresh=refresh)
    except Exception as e:  # pragma: no cover - defensive
        return {
            "totals": {"knowledge_bases": 0, "files": 0, "chunks": 0, "storage_bytes": 0},
            "growth": [], "type_distribution": [], "size_distribution": [],
            "error": str(e),
        }
    data["time_range"] = {"start": cutoff.isoformat(), "end": end_time.isoformat()}
    return data


def get_knowledge_kb_value(
    request: Request,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    refresh: bool = Query(False),
):
    """Per-KB value classification for a date range."""
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    from core.knowledge_analytics import query_kb_value

    cutoff, end_time = _parse_range(start, end)
    try:
        data = query_kb_value(cutoff, end_time, force_refresh=refresh)
    except Exception as e:  # pragma: no cover - defensive
        return {
            "knowledge_bases": [],
            "category_counts": {"star": 0, "needs_tuning": 0, "dead": 0, "unproven": 0},
            "ambiguous_sources": [], "unattributed_sources": [],
            "error": str(e),
        }
    data["time_range"] = {"start": cutoff.isoformat(), "end": end_time.isoformat()}
    return data


def get_knowledge_governance(
    request: Request,
    refresh: bool = Query(False),
):
    """Governance signals — duplicates, orphans, owner concentration."""
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    from core.knowledge_analytics import query_governance

    try:
        return query_governance(force_refresh=refresh)
    except Exception as e:  # pragma: no cover - defensive
        return {
            "duplicates": [], "reclaimable_bytes": 0,
            "orphans": {"adhoc_count": 0, "adhoc_bytes": 0, "dangling_count": 0, "dangling_bytes": 0},
            "owners": [], "error": str(e),
        }
