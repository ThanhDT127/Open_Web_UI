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
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import Query, Request

_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _parse_range(start: Optional[str], end: Optional[str], default_hours: int = 24 * 30):
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
