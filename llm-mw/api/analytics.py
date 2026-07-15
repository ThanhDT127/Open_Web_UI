import json
import datetime as dt
from fastapi import Request, Query
from collections import defaultdict
from zoneinfo import ZoneInfo
from core.db import db_conn, db_ow_conn, fetch_final_audit_entries
from utils.auth_guard import require_admin_or_session

def _time_boundaries(minutes: int = 43200, start: str = None, end: str = None):
    if start and end:
        try:
            start_dt = dt.datetime.fromisoformat(start.replace('Z', '+00:00'))
            end_dt = dt.datetime.fromisoformat(end.replace('Z', '+00:00'))
            return start_dt, end_dt
        except Exception:
            pass
    end_dt = dt.datetime.now(dt.timezone.utc)
    start_dt = end_dt - dt.timedelta(minutes=minutes)
    return start_dt, end_dt

def get_chat_analytics(request: Request, minutes: int = Query(43200), start: str = Query(None), end: str = Query(None)):
    require_admin_or_session(request)
    start_dt, end_dt = _time_boundaries(minutes, start, end)
    
    # 1. Open WebUI metrics
    total_chats = 0
    active_users = 0
    total_messages = 0
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
                
            cursor.execute('''
                SELECT COUNT(id)
                FROM message
                WHERE created_at >= %s AND created_at <= %s
            ''', (start_ts, end_ts))
            row = cursor.fetchone()
            if row:
                total_messages = row[0]
                
            cursor.execute('''
                SELECT user_id, COUNT(id)
                FROM chat
                WHERE created_at >= %s AND created_at <= %s
                GROUP BY user_id
            ''', (start_ts, end_ts))
            for r in cursor.fetchall():
                user_chat_counts[r[0]] = r[1]
    except Exception as e:
        print(f"Error querying OW DB for chat analytics: {e}")

    # 2. Middleware metrics — one row per request (final state per rid),
    # same counting semantics as the Usage tab (summary_v2)
    total_reqs = 0
    total_tokens = 0
    total_cost = 0.0
    timeseries_dict = defaultdict(lambda: {"requests": 0, "cost_usd": 0.0})
    hourly_dict = {i: 0 for i in range(24)}
    model_dict = defaultdict(lambda: {"requests": 0, "cost_usd": 0.0})
    user_dict = defaultdict(lambda: {"request_count": 0, "tokens": 0, "cost_usd": 0.0, "models": defaultdict(int)})

    is_hourly = minutes <= 1440

    try:
        for entry in fetch_final_audit_entries(start_dt, end_dt):
            u_id, mod, ts, status = entry["user_id"], entry["model"], entry["ts"], entry["status"]
            # Tokens/cost only count once the request reached a billable final state
            is_final = status in ('ok', 'reconciled')
            cst = entry["cost_usd"] if is_final else 0.0
            toks = entry["tokens_total"] if is_final else 0

            total_reqs += 1
            total_tokens += toks
            total_cost += cst

            # Timeseries
            if is_hourly:
                period_key = ts.strftime('%Y-%m-%d %H:00')
            else:
                period_key = ts.strftime('%Y-%m-%d')

            timeseries_dict[period_key]["requests"] += 1
            timeseries_dict[period_key]["cost_usd"] += cst

            # Hourly Activity
            hourly_dict[ts.hour] += 1

            # Model Breakdown
            model_dict[mod]["requests"] += 1
            model_dict[mod]["cost_usd"] += cst

            # User Leaderboard
            user_dict[u_id]["request_count"] += 1
            user_dict[u_id]["tokens"] += toks
            user_dict[u_id]["cost_usd"] += cst
            user_dict[u_id]["models"][mod] += 1

    except Exception as e:
        print(f"Error querying MW DB for chat analytics: {e}")
        
    # Format timeseries
    timeseries = [{"period": k, "requests": v["requests"], "cost_usd": v["cost_usd"]} for k, v in sorted(timeseries_dict.items())]
    hourly_activity = [{"hour": k, "count": v} for k, v in hourly_dict.items()]
    model_breakdown = [{"model": k, "requests": v["requests"], "cost_usd": v["cost_usd"]} for k, v in sorted(model_dict.items(), key=lambda x: x[1]["cost_usd"], reverse=True)]
    
    # Leaderboard formatting.
    # Audit log keys users by email while Open WebUI keys by uuid — map uuid -> email
    # so display names and chat counts resolve. Status comes from mw_users, which
    # outlives the Open WebUI account (soft delete keeps the row).
    leaderboard = []
    user_names = {}       # email -> display name
    email_by_uuid = {}
    try:
        with db_ow_conn() as conn:
            c = conn.cursor()
            c.execute('SELECT id, email, name FROM "user"')
            for r in c.fetchall():
                email_by_uuid[r[0]] = r[1]
                user_names[r[1]] = r[2]
    except:
        pass

    chat_counts_by_email = {}
    for ow_uuid, cnt in user_chat_counts.items():
        email = email_by_uuid.get(ow_uuid)
        if email:
            chat_counts_by_email[email] = cnt

    user_status = {}      # email -> active | disabled | deleted
    try:
        with db_conn() as conn:
            c = conn.cursor()
            c.execute('SELECT user_id, active, deleted_at FROM mw_users')
            for uid, active, deleted_at in c.fetchall():
                user_status[uid] = "deleted" if deleted_at else ("active" if active else "disabled")
    except Exception as e:
        print(f"Error loading user status for leaderboard: {e}")

    for u_id, stats in user_dict.items():
        top_model = max(stats["models"].items(), key=lambda x: x[1])[0] if stats["models"] else "unknown"
        # Absent from mw_users = hard-deleted before soft delete existed
        status = user_status.get(u_id, "deleted") if u_id else "unknown"
        leaderboard.append({
            "user_id": u_id,
            "display_name": user_names.get(u_id) or u_id,
            "user_status": status,
            "chat_count": chat_counts_by_email.get(u_id, 0),
            "request_count": stats["request_count"],
            "tokens": stats["tokens"],
            "cost_usd": stats["cost_usd"],
            "top_model": top_model
        })
    
    leaderboard = sorted(leaderboard, key=lambda x: x["cost_usd"], reverse=True)[:50]

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

def get_satisfaction_analytics(request: Request, minutes: int = Query(43200), start: str = Query(None), end: str = Query(None)):
    require_admin_or_session(request)
    start_dt, end_dt = _time_boundaries(minutes, start, end)
    
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    
    totals = {"positive": 0, "negative": 0, "total": 0, "csat_percent": 0}
    model_stats = defaultdict(lambda: {"positive": 0, "negative": 0, "total": 0})
    recent_feedback = []
    
    try:
        with db_ow_conn() as conn:
            cursor = conn.cursor()
            
            # 1. SQL Aggregation for Totals
            cursor.execute('''
                SELECT 
                    COALESCE(SUM(CASE WHEN data::json->>'rating' = '1' THEN 1 ELSE 0 END), 0) as positive,
                    COALESCE(SUM(CASE WHEN data::json->>'rating' = '-1' THEN 1 ELSE 0 END), 0) as negative
                FROM feedback 
                WHERE created_at >= %s AND created_at <= %s
            ''', (start_ts, end_ts))
            row = cursor.fetchone()
            if row:
                totals["positive"] = int(row[0])
                totals["negative"] = int(row[1])
                totals["total"] = totals["positive"] + totals["negative"]
                if totals["total"] > 0:
                    totals["csat_percent"] = int((totals["positive"] / totals["total"]) * 100)
            
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
                        "csat_percent": int((pos / tot) * 100)
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

    except Exception as e:
        print(f"Error querying OW DB for satisfaction analytics: {e}")

    # Feedback from users deleted in Open WebUI has no name/email to join against.
    # Fall back to middleware identity records, which are not tied to OW's user lifecycle:
    # mw_users mapping -> audit log mapping -> stable email.
    missing_ids = list({fb["user_id"] for fb in recent_feedback if not fb["email"] and fb["user_id"]})
    resolved = {}
    if missing_ids:
        try:
            with db_conn() as conn:
                c = conn.cursor()
                c.execute('SELECT openwebui_user_id, user_id FROM mw_users WHERE openwebui_user_id = ANY(%s)', (missing_ids,))
                for ow_id, mw_id in c.fetchall():
                    resolved[ow_id] = mw_id
                unresolved = [i for i in missing_ids if i not in resolved]
                if unresolved:
                    c.execute('''SELECT DISTINCT openwebui_user_id, user_id FROM mw_audit_log
                                 WHERE openwebui_user_id = ANY(%s) AND user_id IS NOT NULL''', (unresolved,))
                    for ow_id, mw_id in c.fetchall():
                        resolved.setdefault(ow_id, mw_id)
        except Exception as e:
            print(f"Error resolving deleted user names for satisfaction: {e}")

    # The badge must reflect each account's CURRENT middleware status, keyed by
    # email — so a deleted-then-recreated account (same email, new uuid) is no
    # longer tagged as deleted even on feedback it left under the old uuid.
    mw_status = {}
    try:
        with db_conn() as conn:
            c = conn.cursor()
            c.execute('SELECT user_id, active, deleted_at FROM mw_users')
            for uid, active, deleted_at in c.fetchall():
                mw_status[uid] = "deleted" if deleted_at else ("active" if active else "disabled")
    except Exception as e:
        print(f"Error loading user status for satisfaction: {e}")

    for fb in recent_feedback:
        email = fb.get("email") or resolved.get(fb.get("user_id") or "")
        if email and email in mw_status:
            fb["user_status"] = mw_status[email]
        elif email:
            # Present in Open WebUI but not provisioned in middleware -> not deleted
            fb["user_status"] = "active"
        else:
            fb["user_status"] = "deleted" if fb.get("user_id") else "unknown"
        if not fb["user_name"]:
            uid = fb.get("user_id") or ""
            fb["user_name"] = email or (f"Đã xóa ({uid[:8]})" if uid else "Unknown")
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
