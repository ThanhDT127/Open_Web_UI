import json
import datetime as dt
from fastapi import Request, Query
from collections import defaultdict
from zoneinfo import ZoneInfo
from config import logger
from core.db import db_conn, db_ow_conn
from utils.auth_guard import require_admin_or_session
from api.summary_v2 import compute_usage_summary, _resolve_range


def _window(minutes, start, end):
    """
    Resolve the request's time parameters through the one shared resolver.

    The helper this replaced swallowed a bad datetime and silently substituted the last
    30 days, so the same malformed parameter produced an error on the usage tabs and a
    plausible-looking chart here — with no way for the reader to tell which window they
    were looking at. _resolve_range raises 400 instead.

    Only the window is taken. Bucket width stays keyed off `minutes` at each call site:
    get_chat_analytics buckets hourly for short ranges, and letting the resolver derive
    the bucket would quietly switch that chart to daily.
    """
    cutoff, end_time, _ = _resolve_range(minutes, start, end)
    return cutoff, end_time


def _resolve_ow_ids_to_emails(ow_ids, strict: bool = False):
    """
    Map Open WebUI user UUIDs to middleware user ids (emails).

    Open WebUI keys users by UUID; the middleware keys them by email. Anything that
    joins the two datasets has to bridge that gap, and joining Open WebUI's `user`
    table directly loses users who were deleted there. These two middleware-side
    tables are not tied to Open WebUI's user lifecycle, so deleted users keep their
    history: mw_users first, then the audit log as a fallback.

    Returns {ow_uuid: email} for whatever could be resolved.

    `strict` decides what a read failure means to the caller. An empty map is the
    honest answer to "nothing resolved" and is also what a failed read leaves behind,
    so the two are indistinguishable from the outside. Callers that turn this map into
    a claim about an account — alive, deleted — must pass strict=True and handle the
    exception, because stating either claim from a map that was never filled is a
    guess presented as a fact. Callers that only use it to improve a display name can
    leave it False and degrade quietly.
    """
    ow_ids = [i for i in ow_ids if i]
    resolved = {}
    if not ow_ids:
        return resolved
    try:
        with db_conn() as conn:
            c = conn.cursor()
            c.execute(
                'SELECT openwebui_user_id, user_id FROM mw_users WHERE openwebui_user_id = ANY(%s)',
                (ow_ids,),
            )
            for ow_id, mw_id in c.fetchall():
                if ow_id and mw_id:
                    resolved[ow_id] = mw_id

            unresolved = [i for i in ow_ids if i not in resolved]
            if unresolved:
                c.execute(
                    '''SELECT DISTINCT openwebui_user_id, user_id FROM mw_audit_log
                       WHERE openwebui_user_id = ANY(%s) AND user_id IS NOT NULL''',
                    (unresolved,),
                )
                for ow_id, mw_id in c.fetchall():
                    if ow_id and mw_id:
                        resolved.setdefault(ow_id, mw_id)
    except Exception as e:
        logger.error("Error resolving Open WebUI ids to emails: %s", e, exc_info=True)
        if strict:
            raise
    return resolved


def _load_mw_user_status() -> dict:
    """
    {email: "active" | "disabled" | "deleted"} for every middleware account.

    Raises on failure rather than returning an empty map: the empty map is what a
    healthy install with no accounts also looks like, and callers read a missing key
    as "this account is fine".
    """
    status = {}
    with db_conn() as conn:
        c = conn.cursor()
        c.execute('SELECT user_id, active, deleted_at FROM mw_users')
        for uid, active, deleted_at in c.fetchall():
            status[uid] = "deleted" if deleted_at else ("active" if active else "disabled")
    return status


def get_chat_analytics(request: Request, minutes: int = Query(43200), start: str = Query(None), end: str = Query(None)):
    require_admin_or_session(request)
    start_dt, end_dt = _window(minutes, start, end)
    
    # 1. Open WebUI metrics
    total_chats = 0
    active_users = 0
    user_chat_counts = {}
    try:
        with db_ow_conn() as conn:
            cursor = conn.cursor()
            start_ts = int(start_dt.timestamp())
            end_ts = int(end_dt.timestamp())
            
            
            cursor.execute('''
                SELECT COUNT(id), COUNT(DISTINCT user_id) 
                FROM chat 
                WHERE created_at >= %s AND created_at <= %s
            ''', (start_ts, end_ts))
            row = cursor.fetchone()
            if row:
                total_chats = row[0]
                active_users = row[1]
                
            # NOTE: no COUNT(*) FROM message here. This Open WebUI build stores messages
            # inside the chat.chat JSON, leaving the message table empty, so the old query
            # made Total Requests read 0 forever. Request counts come from mw_audit_log now.

            cursor.execute('''
                SELECT user_id, COUNT(id)
                FROM chat
                WHERE created_at >= %s AND created_at <= %s
                GROUP BY user_id
            ''', (start_ts, end_ts))
            for r in cursor.fetchall():
                user_chat_counts[r[0]] = r[1]
    except Exception as e:
        logger.error("Error querying OW DB for chat analytics: %s", e, exc_info=True)

    # chat.user_id is an Open WebUI UUID, but the leaderboard is keyed by email.
    # Re-key here or every chat_count lookup silently misses and renders as 0.
    if user_chat_counts:
        ow_to_email = _resolve_ow_ids_to_emails(list(user_chat_counts.keys()))
        by_email = defaultdict(int)
        for ow_id, count in user_chat_counts.items():
            email = ow_to_email.get(ow_id)
            if email:
                by_email[email] += count
        user_chat_counts = dict(by_email)

    # 2. Middleware metrics — delegated to the single shared aggregation of mw_audit_log.
    # This endpoint must NOT re-aggregate that table; doing so is what made these numbers
    # disagree with the Usage tab (row counting: 264) instead of counting distinct rids (189).
    # bucket_size is passed explicitly (not "auto") to keep this tab's historical bucketing.
    bucket_size = "hour" if minutes <= 1440 else "day"
    summary = compute_usage_summary(start_dt, end_dt, bucket_size)
    if "error" in summary:
        # compute_usage_summary swallows its own exceptions. Surface it here, or a broken
        # aggregation renders as a tab full of zeros with nothing in the logs.
        logger.error("Usage aggregation failed for chat analytics: %s", summary["error"])
    s_totals = summary.get("totals", {})

    total_reqs = s_totals.get("requests_total", 0)
    total_tokens = s_totals.get("tokens_total", 0)
    total_cost = s_totals.get("cost_total_usd", 0.0)

    # Map the shared shape onto this endpoint's existing field names so the
    # dashboard JS keeps working untouched.
    timeseries = [
        {"period": b["ts"], "requests": b["requests_total"], "cost_usd": b["cost_usd"]}
        for b in summary.get("timeseries", [])
    ]
    hourly_activity = summary.get("hourly_activity", [{"hour": h, "count": 0} for h in range(24)])
    model_breakdown = [
        {"model": m["model"], "requests": m["requests_total"], "cost_usd": m["cost_usd"]}
        for m in summary.get("breakdown_by_model", [])
    ]

    # Leaderboard formatting. Open WebUI keys users by UUID while the middleware keys
    # them by email, so names are looked up by email here.
    user_names = {}
    try:
        with db_ow_conn() as conn:
            c = conn.cursor()
            c.execute('SELECT email, name FROM "user"')
            for r in c.fetchall():
                if r[0]:
                    user_names[r[0]] = r[1]
    except Exception as e:
        logger.error("Error loading user names for chat analytics: %s", e, exc_info=True)

    leaderboard = []
    for u in summary.get("breakdown_by_user", []):
        u_id = u["user_id"]
        leaderboard.append({
            "user_id": u_id,
            "display_name": user_names.get(u_id) or u_id,
            "chat_count": user_chat_counts.get(u_id, 0),
            "request_count": u["requests_total"],
            "tokens": u["tokens_total"],
            "cost_usd": u["cost_usd"],
            "top_model": u.get("top_model", "unknown")
        })

    # Already ordered by cost descending upstream; keep this endpoint's historical cap.
    leaderboard = leaderboard[:50]



    return {
        "totals": {
            "chats": total_chats,
            "requests": total_reqs,
            "tokens": total_tokens,
            "cost_usd": total_cost,
            "active_users": active_users
        },
        "timeseries": timeseries,
        "hourly_activity": hourly_activity,
        "model_breakdown": model_breakdown,
        "leaderboard": leaderboard
    }

def compute_satisfaction(start_dt, end_dt) -> dict:
    """
    Satisfaction aggregation over a resolved window. Pure: no Request, no auth.

    Split out so the report export can call it directly. Calling the handler forced the
    exporter to catch HTTPException, and catching it turned a failed feedback query into
    an empty sheet — indistinguishable from "nobody rated anything", in a file that
    downloaded as though it were complete. Let failures raise; see _collect_groups.
    """
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    totals = {"positive": 0, "negative": 0, "total": 0, "csat_percent": 0, "feedback_rows": 0}
    model_stats = defaultdict(lambda: {"positive": 0, "negative": 0, "total": 0})
    recent_feedback = []

    # No try/except around this block. It used to log the error and fall through with
    # every counter at zero, which renders as "nobody has rated anything" — a reading
    # indistinguishable from the truth, so the failure was invisible both on the tab
    # and in the exported file.
    with db_ow_conn() as conn:
        cursor = conn.cursor()

        # 1. SQL Aggregation for Totals
        # feedback_rows counts every row, while total counts only thumbs up plus
        # thumbs down. They are equal today because Open WebUI writes nothing else,
        # but a neutral or null rating would make "total" quietly undercount while
        # still being labelled as the number of feedback entries. The display only
        # mentions the difference when there is one.
        cursor.execute('''
            SELECT
                COALESCE(SUM(CASE WHEN data::json->>'rating' = '1' THEN 1 ELSE 0 END), 0) as positive,
                COALESCE(SUM(CASE WHEN data::json->>'rating' = '-1' THEN 1 ELSE 0 END), 0) as negative,
                COUNT(*) as feedback_rows
            FROM feedback
            WHERE created_at >= %s AND created_at <= %s
        ''', (start_ts, end_ts))
        row = cursor.fetchone()
        if row:
            totals["positive"] = int(row[0])
            totals["negative"] = int(row[1])
            totals["feedback_rows"] = int(row[2])
            totals["total"] = totals["positive"] + totals["negative"]
            if totals["total"] > 0:
                # Unrounded on purpose. int() truncates, so 2/3 rendered as 66% —
                # biased low every time, and unrecoverable once the backend has cut
                # it. Rounding happens once, in the display layer.
                totals["csat_percent"] = (totals["positive"] / totals["total"]) * 100
        
        # 2. SQL Aggregation for Model Leaderboard
        cursor.execute('''
            SELECT 
                COALESCE(meta::json->>'model_id', 'unknown') as model_id,
                COALESCE(SUM(CASE WHEN data::json->>'rating' = '1' THEN 1 ELSE 0 END), 0) as positive,
                COALESCE(SUM(CASE WHEN data::json->>'rating' = '-1' THEN 1 ELSE 0 END), 0) as negative
            FROM feedback 
            WHERE created_at >= %s AND created_at <= %s
              AND (data::json->>'rating' = '1' OR data::json->>'rating' = '-1')
            GROUP BY meta::json->>'model_id'
        ''', (start_ts, end_ts))
        
        for row in cursor.fetchall():
            m_id, pos, neg = row[0], int(row[1]), int(row[2])
            tot = pos + neg
            if tot > 0:
                model_stats[m_id] = {
                    "positive": pos,
                    "negative": neg,
                    "total": tot,
                    # Unrounded, like the overall figure above.
                    "csat_percent": (pos / tot) * 100
                }
                
        # 3. Fetch Recent Feedback (Limit 50)
        cursor.execute('''
            SELECT f.data, f.meta, f.created_at, u.name, f.user_id, u.email
            FROM feedback f
            LEFT JOIN "user" u ON f.user_id = u.id
            WHERE f.created_at >= %s AND f.created_at <= %s
              AND (f.data::json->>'rating' = '1' OR f.data::json->>'rating' = '-1')
            ORDER BY f.created_at DESC
            LIMIT 50
        ''', (start_ts, end_ts))
        
        for row in cursor.fetchall():
            data_str, meta_str, created_at, user_name, fb_user_id, ow_email = row
            try:
                data = data_str if isinstance(data_str, dict) else (json.loads(data_str) if data_str else {})
                meta = meta_str if isinstance(meta_str, dict) else (json.loads(meta_str) if meta_str else {})
            except:
                continue
            
            recent_feedback.append({
                "rating": int(data.get("rating", 0)),
                "created_at": created_at,
                "reason": data.get("reason", ""),
                "comment": data.get("comment", ""),
                "user_name": user_name,
                "user_id": fb_user_id,
                # Current OW email when the account still exists; resolved below otherwise
                "email": ow_email,
                "model_id": meta.get("model_id", "unknown")
            })
            
    # Feedback from users deleted in Open WebUI has no name/email to join against.
    # Fall back to middleware identity records, which are not tied to OW's user lifecycle:
    # mw_users mapping -> audit log mapping -> stable email.
    missing_ids = list({fb["user_id"] for fb in recent_feedback if not fb["email"] and fb["user_id"]})

    # Both reads below decide the same thing — whether an account is still with us — and
    # both used to swallow their own failure, in opposite directions: a failed lookup left
    # a live user reading as "Đã xóa", while a failed status read left a deleted user
    # reading as active. Neither could be defaulted away, since a default that fixes one
    # breaks the other. So the failure is recorded instead, and the verdict is withheld.
    identity_ok = True
    resolved, mw_status = {}, {}
    try:
        resolved = _resolve_ow_ids_to_emails(missing_ids, strict=True)
        # Status keyed by email, not uuid, so a deleted-then-recreated account (same
        # email, new uuid) is no longer tagged as deleted on feedback it left before.
        mw_status = _load_mw_user_status()
    except Exception as e:
        logger.error("Error resolving feedback author identity: %s", e, exc_info=True)
        identity_ok = False

    for fb in recent_feedback:
        email = fb.get("email") or resolved.get(fb.get("user_id") or "")
        if not identity_ok:
            fb["user_status"] = "unknown"
        elif email and email in mw_status:
            fb["user_status"] = mw_status[email]
        elif email:
            # Present in Open WebUI but not provisioned in middleware -> not deleted
            fb["user_status"] = "active"
        else:
            fb["user_status"] = "deleted" if fb.get("user_id") else "unknown"
        if not fb["user_name"]:
            uid = fb.get("user_id") or ""
            if email:
                fb["user_name"] = email
            elif not uid:
                fb["user_name"] = "Unknown"
            else:
                # "Đã xóa" is a claim about the account, so it is only made when the
                # records backing it were actually read.
                fb["user_name"] = f"Đã xóa ({uid[:8]})" if identity_ok else f"Không rõ ({uid[:8]})"
        fb.pop("email", None)

    model_leaderboard = []
    for m_id, stats in model_stats.items():
        model_leaderboard.append({
            "model_id": m_id,
            "positive": stats["positive"],
            "negative": stats["negative"],
            "total": stats["total"],
            "csat_percent": stats["csat_percent"]
        })
        
    model_leaderboard = sorted(model_leaderboard, key=lambda x: (x["csat_percent"], x["total"]), reverse=True)

    return {
        "totals": totals,
        "model_leaderboard": model_leaderboard,
        "recent_feedback": recent_feedback
    }


def get_satisfaction_analytics(request: Request, minutes: int = Query(43200), start: str = Query(None), end: str = Query(None)):
    """HTTP wrapper: auth and parameter resolution only. The aggregation is pure."""
    require_admin_or_session(request)
    start_dt, end_dt = _window(minutes, start, end)
    return compute_satisfaction(start_dt, end_dt)
