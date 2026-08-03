from fastapi import Request, HTTPException, Query
from typing import Dict, Any, Optional, NamedTuple
from collections import defaultdict, Counter
import logging

from core.db import db_conn, db_ow_conn
from utils.auth_guard import require_admin_or_session
from api.summary_v2 import _resolve_range, compute_usage_summary
from core.quota import period_anchor_ms

# Groups reads no timeseries, so the bucket is fixed rather than derived from the window
# length. Passing it explicitly keeps the grouped figures from depending on the range
# through a code path nobody intended (same discipline as the chat-analytics endpoint).
_GROUP_BUCKET = "day"

logger = logging.getLogger("llm_mw")

# Label for spending that cannot be traced to a department. It covers three different
# things: staff with an Open WebUI account who are in no group, accounts deleted from
# Open WebUI (the group_member FK cascades, so the mapping is gone while the audit
# history remains), and non-user system identities such as "admin" that can never be
# put in a group. "Not yet assigned" would be wrong for the last two.
UNRESOLVED_GROUP_LABEL = "Chưa quy được phòng ban"
UNRESOLVED_GROUP_KEY = "uncategorized"


class _GroupContext(NamedTuple):
    """Everything the two endpoints need from Open WebUI, read in one connection."""
    group_names: Dict[str, str]         # group_id -> department name
    user_primary_group: Dict[str, str]  # email -> group_id of the earliest-joined group
    primary_member_counts: Counter      # group_id -> people whose primary group it is
    multi_group_users: int              # how many people sit in more than one group
    user_names: Dict[str, str]          # email -> display name


def _fetch_group_context() -> _GroupContext:
    """Read the department frame, the primary-group map and display names from Open WebUI.

    Raises instead of returning empty dicts on failure: the group list IS the frame of
    the table, so carrying on without it would silently relabel every row as unresolved
    and report the organisation as having no departments at all.
    """
    group_names: Dict[str, str] = {}
    user_primary_group: Dict[str, str] = {}
    membership_counts: Dict[str, int] = {}
    user_names: Dict[str, str] = {}
    try:
        with db_ow_conn() as conn:
            cur = conn.cursor()
            cur.execute('SELECT id, name FROM "group"')
            for row in cur.fetchall():
                group_names[row[0]] = row[1]

            # Keyed by email, because that is what mw_audit_log records. Users deleted
            # from Open WebUI simply will not be here; callers fall back to the raw
            # identifier so their spending history stays visible.
            cur.execute('SELECT email, name FROM "user"')
            for row in cur.fetchall():
                user_names[row[0]] = row[1] or row[0]

            # Primary group = earliest joined. Kept deliberately: an Open WebUI group is
            # also the unit tool access is granted through, so being added to a second
            # group is usually a permission change rather than a department transfer.
            # Taking the newest would move that person's whole history onto the
            # permission group.
            cur.execute("""
                SELECT DISTINCT ON (u.email) u.email, gm.group_id
                FROM group_member gm
                JOIN "user" u ON gm.user_id = u.id
                ORDER BY u.email, gm.created_at ASC
            """)
            for row in cur.fetchall():
                user_primary_group[row[0]] = row[1]

            # Same join without DISTINCT ON, to surface people in more than one group.
            # Their cost lands on exactly one group, which is worth saying out loud
            # rather than leaving as a silent rule.
            cur.execute("""
                SELECT u.email, count(*)
                FROM group_member gm
                JOIN "user" u ON gm.user_id = u.id
                GROUP BY u.email
            """)
            for row in cur.fetchall():
                membership_counts[row[0]] = row[1]
            cur.close()
    except Exception as e:
        logger.error("Failed to fetch group mappings from Open WebUI: %s", e, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="Open WebUI directory unavailable — cannot attribute cost to departments",
        )

    return _GroupContext(
        group_names=group_names,
        user_primary_group=user_primary_group,
        primary_member_counts=Counter(user_primary_group.values()),
        multi_group_users=sum(1 for n in membership_counts.values() if n > 1),
        user_names=user_names,
    )


def _count_provisioned_users() -> Optional[int]:
    """Accounts that exist and are not soft-deleted, for the headcount card's denominator.

    Returns None rather than 0 when the roster cannot be read: 0 would claim the
    organisation has no accounts, which reads as a fact instead of a missing figure.
    """
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM mw_users WHERE deleted_at IS NULL")
            row = cur.fetchone()
            cur.close()
        return int(row[0]) if row else 0
    except Exception as e:
        logger.error("Failed to count provisioned users: %s", e, exc_info=True)
        return None


def compute_group_analytics(cutoff, end_time, bucket_size: str) -> Dict[str, Any]:
    """Aggregate usage by primary department.

    Pure — takes no Request and performs no auth, so both the dashboard endpoint and the
    Excel export can call it without one calling the other's handler.

    Figures come from compute_usage_summary rather than a second pass over mw_audit_log.
    That is what makes a department's share of cost meaningful: the numerator here and the
    system total a caller divides by are the same aggregation, so the parts sum to the
    whole by construction instead of by inspection.
    """
    ctx = _fetch_group_context()

    summary = compute_usage_summary(cutoff, end_time, bucket_size)
    if "error" in summary:
        # compute_usage_summary returns its error instead of raising. Surface it, or the
        # tab renders zeros for every department with nothing in the logs to explain why.
        logger.error("Usage aggregation failed for group analytics: %s", summary["error"])
        raise HTTPException(status_code=500, detail="Usage aggregation failed")

    def _blank(group_id: Optional[str], group_name: str) -> Dict[str, Any]:
        return {
            "group_id": group_id,
            "group_name": group_name,
            "requests": 0,
            "cost": 0.0,
            "tokens": 0,
            "latency_sum_ms": 0.0,
            "latency_samples": 0,
            "models": defaultdict(int),
            # Who actually sent something in this window. A set, because the count has to
            # be the INTERSECTION of activity and membership — see the loop below.
            "active_users": set(),
        }

    # Frame first: every department gets a row whether or not it used anything.
    group_stats: Dict[str, Dict[str, Any]] = {
        gid: _blank(gid, gname) for gid, gname in ctx.group_names.items()
    }

    for user in summary.get("breakdown_by_user", []):
        gid = ctx.user_primary_group.get(user["user_id"])
        key = gid if gid else UNRESOLVED_GROUP_KEY
        if key not in group_stats:
            # Normally only the unresolved bucket lands here. A group_id present in the
            # membership map but missing from the group table would mean the two Open
            # WebUI queries disagreed with each other.
            group_stats[key] = _blank(
                gid,
                ctx.group_names.get(gid, UNRESOLVED_GROUP_LABEL) if gid else UNRESOLVED_GROUP_LABEL,
            )

        stats = group_stats[key]
        stats["requests"] += user["requests_total"]
        # The unrounded value on purpose: rounding each user and then adding cannot equal
        # totals.cost_total_usd, which rounds once at the end.
        stats["cost"] += user["cost_usd_raw"]
        stats["tokens"] += user["tokens_total"]
        # Sum and sample count travel together; the average is taken once, at the end.
        stats["latency_sum_ms"] += user.get("latency_sum_ms") or 0.0
        stats["latency_samples"] += user.get("latency_sample_count") or 0
        for model, count in (user.get("model_counts") or {}).items():
            stats["models"][model] += count
        # Reached only for users that appear in breakdown_by_user, i.e. that sent at least
        # one request in the window, and only under the group their primary membership
        # points at. So this set is already the intersection of "was active" and "belongs
        # here" — the same intersection that stopped the adoption rate reading 108% in
        # Phase 4. Counting activity without it would let someone who has since left the
        # department push a group's active count above its headcount.
        stats["active_users"].add(user["user_id"])

    # Denominator for the share column: the population total, summed from the same
    # unrounded per-user values the numerators come from.
    #
    # NOT totals.cost_total_usd — that one is rounded to six decimals for display, and a
    # rounded denominator against unrounded numerators makes the shares miss 100 by ~5e-4.
    # NOT the sum of the rows finally returned either: this list happens to be complete
    # today, but breakdown_by_user is the population by definition, so deriving from it
    # keeps each row's share true even if the table is ever capped.
    system_cost = sum(u["cost_usd_raw"] for u in summary.get("breakdown_by_user", []))

    result = []
    for stats in group_stats.values():
        reqs = stats["requests"]
        samples = stats["latency_samples"]
        is_department = stats["group_id"] is not None

        # Per-head figures describe a department's population, so they do not apply to the
        # unresolved row: that row has spenders but no members. Reporting its active count
        # would also make the "active <= members" check meaningless against a null.
        member_count = ctx.primary_member_counts.get(stats["group_id"], 0) if is_department else None
        active_count = len(stats["active_users"]) if is_department else None
        # Divide by the number of requests that actually recorded a latency, not by the
        # number of requests. The old code divided the latency total by every audit row,
        # including rows that carry no latency at all, so the figure always read low.
        avg_latency = round(stats["latency_sum_ms"] / samples, 2) if samples > 0 else None

        model_prefs = [
            {
                "model": model,
                "count": count,
                "percentage": round((count / reqs) * 100, 1) if reqs > 0 else 0,
            }
            for model, count in stats["models"].items()
        ]
        model_prefs.sort(key=lambda x: x["count"], reverse=True)

        result.append({
            "group_id": stats["group_id"],
            "group_name": stats["group_name"],
            "total_requests": reqs,
            # Unrounded on purpose. Rounding here would move the same accumulation error
            # one level up — a client adding the department rows would land beside
            # totals.cost_total_usd instead of on it — and the one check that proves this
            # endpoint correct is exactly that sum. Formatting belongs to the caller:
            # the dashboard renders it through usd4(), the Excel sheet rounds per cell.
            "total_cost": stats["cost"],
            "total_tokens": stats["tokens"],
            "avg_latency_ms": avg_latency,
            # How many requests the average is based on. latency_ms is absent on every
            # reconciled row, so it never covers all successful requests; an average
            # without its sample size hides that.
            "latency_sample_count": samples,
            "model_preferences": model_prefs,
            # Members whose PRIMARY group is this one, so the population described here is
            # the population the cost above is summed over. Deliberately not the same
            # figure as the "members" count in the tool-access section below the table,
            # which counts every membership — hence the distinct label on the column.
            "primary_member_count": member_count,
            "active_member_count": active_count,
            # Named for its denominator. The drill-down carries a share too, against the
            # department instead of the system; one name for both would be the same
            # collision this tab is being cleaned of, one level down.
            # Unrounded, for the same reason the cost is: rounding each row to one decimal
            # and then adding gives 99.9, not 100. The caller rounds for display and the
            # sum stays exact in the payload, so the "parts equal the whole" check is a
            # plain equality rather than a tolerance.
            "cost_share_of_system_percent": (stats["cost"] / system_cost * 100) if system_cost > 0 else 0.0,
            # None, not 0, when there is nobody to divide by: a department with no members
            # has no cost per head, and 0 would read as "free".
            "cost_per_member": (stats["cost"] / member_count) if member_count else None,
            "cost_per_active_member": (stats["cost"] / active_count) if active_count else None,
        })

    result.sort(key=lambda x: x["total_cost"], reverse=True)

    # Scorecard numerators/denominators are computed here rather than left to the frontend:
    # every one of them has to exclude the unresolved row, and a filter written once server
    # side cannot drift from the rows it describes.
    departments = [r for r in result if r["group_id"] is not None]
    return {
        "groups": result,
        # Excludes the unresolved row: it is not a department, and this figure has to stay
        # the organisation's rather than the time window's.
        "department_count": len(ctx.group_names),
        # Cost that IS attributable to a department — the numerator of "average per
        # department". Deliberately smaller than the sum of the table, which also contains
        # the unresolved row; that gap is what the note under the scorecard explains.
        "dept_cost_total": sum(r["total_cost"] for r in departments),
        # Staff who have a department, over staff who have an account. Shown as a pair
        # because the difference is the actionable half of the story: people with no
        # department are exactly why some spending cannot be attributed, and unlike the
        # spending itself, that is fixable.
        "assigned_member_count": sum(r["primary_member_count"] or 0 for r in departments),
        "provisioned_user_count": _count_provisioned_users(),
        # Surfaced so the UI can state the rule instead of leaving a surprising number to
        # be discovered. Cost lands on the earliest-joined group only.
        "multi_group_user_count": ctx.multi_group_users,
    }


def get_group_analytics(request: Request, minutes: int = Query(43200), start: str = Query(None), end: str = Query(None)):
    """
    Get aggregated analytics (cost, requests, latency, models) grouped by the user's primary group.
    Primary group is determined automatically by the oldest created_at in Open WebUI's group_member table.
    """
    require_admin_or_session(request)
    # _resolve_range raises 400 on a malformed or reversed range. The old helper swallowed
    # the parse error and silently served the last 30 days instead.
    cutoff, end_time, bucket_size = _resolve_range(minutes, start, end, _GROUP_BUCKET)
    return {"status": "ok", **compute_group_analytics(cutoff, end_time, bucket_size)}



# Quota states the drill-down can report. Kept distinct on purpose: "we could not look it
# up" and "there is no cap" are opposite meanings, and collapsing both into a dash would be
# the same mislabelling this tab was cleaned of.
QUOTA_OK = "ok"                  # a real percentage
QUOTA_UNLIMITED = "unlimited"    # looked up fine, and the answer is no cap
QUOTA_NO_ACCOUNT = "no_account"  # not a provisioned user: system identity, or deleted in OW
QUOTA_DELETED = "deleted"        # soft-deleted account: spending stands, a cap no longer does


def _fetch_quota_by_user() -> Dict[str, Dict[str, Any]]:
    """Read every account's quota in ONE query, keyed by user_id.

    Deliberately not get_current_quota_user(): that helper calls reset_user_quota_period(),
    which WRITES. Calling it once per drill-down row would mean opening a page silently
    resets the quota counters of everyone in the department.

    Because nothing is written here, a stored counter can belong to a period that has
    already lapsed — the reset is normally triggered by the next request. _quota_state()
    applies the same period arithmetic in memory instead, so a lapsed period reads as 0%
    rather than as last period's figure.
    """
    roster: Dict[str, Dict[str, Any]] = {}
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, quota, deleted_at FROM mw_users")
            for user_id, quota, deleted_at in cur.fetchall():
                roster[user_id] = {
                    "quota": quota if isinstance(quota, dict) else {},
                    "deleted_at": deleted_at,
                }
            cur.close()
    except Exception as e:
        logger.error("Failed to bulk-read quota from mw_users: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail="Quota data unavailable")
    return roster


def _quota_state(user_id: str, roster: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Read-only quota status for one identity, same formula as get_user_quota_status."""
    record = roster.get(user_id)
    if record is None:
        return {"quota_state": QUOTA_NO_ACCOUNT, "quota_percent_used": None}
    if record["deleted_at"] is not None:
        # Cost already incurred stays meaningful forever; an allowance does not outlive the
        # account it belonged to.
        return {"quota_state": QUOTA_DELETED, "quota_percent_used": None}

    quota = record["quota"] or {}
    try:
        limit = float(quota.get("limit_cost_usd", 0) or 0)
        used = float(quota.get("used_cost_usd", 0) or 0)
    except (TypeError, ValueError):
        limit, used = 0.0, 0.0

    if limit <= 0:
        return {"quota_state": QUOTA_UNLIMITED, "quota_percent_used": None}

    # If the stored counter belongs to an earlier period, the effective usage is zero: the
    # reset simply has not been written yet.
    try:
        anchor = period_anchor_ms(quota.get("period", "monthly"), quota.get("timezone", "UTC"))
        if int(quota.get("period_start", 0) or 0) < anchor:
            used = 0.0
    except Exception:
        # Unknown period or timezone: report the stored figure rather than guess at zero.
        pass

    return {"quota_state": QUOTA_OK, "quota_percent_used": used / limit * 100}


def compute_group_users(cutoff, end_time, bucket_size: str, group_id: Optional[str]) -> Dict[str, Any]:
    """Per-member usage for one department. Pure — no Request, no auth.

    Membership is resolved the same way the parent table resolves it: by primary group.
    The two used to disagree — the parent grouped by primary group while this listed every
    membership — so a person in two groups appeared under both here while their cost was
    counted under one there, and the rows could not add up to the row that opened them.
    """
    ctx = _fetch_group_context()

    summary = compute_usage_summary(cutoff, end_time, bucket_size)
    if "error" in summary:
        logger.error("Usage aggregation failed for group drill-down: %s", summary["error"])
        raise HTTPException(status_code=500, detail="Usage aggregation failed")

    # Normalise the ways the frontend can ask for the unresolved bucket.
    wants_unresolved = not group_id or group_id in (UNRESOLVED_GROUP_KEY, "None", "null")

    # One query for the whole list, before the loop. Inside the loop it would be one query
    # per row, and with the per-user helper it would also be one WRITE per row.
    quota_roster = _fetch_quota_by_user()

    members = []
    result = []
    for user in summary.get("breakdown_by_user", []):
        user_id = user["user_id"]
        primary = ctx.user_primary_group.get(user_id)

        if wants_unresolved:
            if primary:
                continue
        elif primary != group_id:
            continue

        model_counts = user.get("model_counts") or {}
        reqs = user["requests_total"]
        samples = user.get("latency_sample_count") or 0
        model_prefs = [
            {
                "model": model,
                "count": count,
                "percentage": round((count / reqs) * 100, 1) if reqs > 0 else 0,
            }
            for model, count in model_counts.items()
        ]
        model_prefs.sort(key=lambda x: x["count"], reverse=True)

        members.append({
            "user_id": user_id,
            # Falls back to the identifier itself, which is what keeps a user deleted from
            # Open WebUI visible here: their audit history outlives their directory entry.
            "user_name": ctx.user_names.get(user_id) or user_id,
            "total_requests": reqs,
            # Unrounded, like the parent row, so the members add up to the department.
            "total_cost": user["cost_usd_raw"],
            "total_tokens": user["tokens_total"],
            "avg_latency_ms": round((user.get("latency_sum_ms") or 0.0) / samples, 2) if samples > 0 else None,
            "latency_sample_count": samples,
            "model_preferences": model_prefs,
            # Read-only: see _fetch_quota_by_user for why the per-user helper is avoided.
            **_quota_state(user_id, quota_roster),
        })

    # Denominator is the DEPARTMENT, not the system — hence the field name. Summed from the
    # unrounded member costs so the shares add to exactly 100 instead of nearly.
    group_cost = sum(m["total_cost"] for m in members)
    for m in members:
        m["cost_share_of_group_percent"] = (m["total_cost"] / group_cost * 100) if group_cost > 0 else 0.0

    result = members
    result.sort(key=lambda x: x["total_cost"], reverse=True)
    return {"users": result}


def get_group_users(request: Request, group_id: str, minutes: int = Query(43200), start: str = Query(None), end: str = Query(None)):
    """
    Get usage breakdown for all users belonging to a specific group_id.
    """
    require_admin_or_session(request)
    cutoff, end_time, bucket_size = _resolve_range(minutes, start, end, _GROUP_BUCKET)
    return {"status": "ok", **compute_group_users(cutoff, end_time, bucket_size, group_id)}
