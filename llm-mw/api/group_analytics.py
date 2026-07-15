import time
from fastapi import Request, HTTPException, Query
from typing import Dict, Any, List, Optional
from collections import defaultdict
import logging

from core.db import db_conn, db_ow_conn, fetch_final_audit_entries
from utils.auth_guard import require_admin_or_session
from api.analytics import _time_boundaries

logger = logging.getLogger("llm_mw")

def get_group_analytics(request: Request, minutes: int = Query(43200), start: str = Query(None), end: str = Query(None)):
    """
    Get aggregated analytics (cost, requests, latency, models) grouped by the user's primary group.
    Primary group is determined automatically by the oldest created_at in Open WebUI's group_member table.
    """
    require_admin_or_session(request)
    start_dt, end_dt = _time_boundaries(minutes, start, end)

    # 1. Fetch group mappings from Open WebUI DB
    user_primary_group = {}
    group_names = {}
    
    try:
        with db_ow_conn() as conn:
            cur = conn.cursor()
            cur.execute('SELECT id, name FROM "group"')
            for row in cur.fetchall():
                group_names[row[0]] = row[1]
                
            cur.execute("""
                SELECT DISTINCT ON (u.email) u.email, gm.group_id
                FROM group_member gm
                JOIN "user" u ON gm.user_id = u.id
                ORDER BY u.email, gm.created_at ASC
            """)
            for row in cur.fetchall():
                user_primary_group[row[0]] = row[1]
            cur.close()
    except Exception as e:
        logger.error(f"Failed to fetch group mappings from Open WebUI: {e}")

    # Aggregate data structures
    group_stats = defaultdict(lambda: {
        "group_id": None,
        "group_name": "Uncategorized",
        "total_requests": 0,
        "total_cost": 0.0,
        "total_tokens": 0,
        "total_latency_ms": 0.0,
        "models": defaultdict(int)
    })

    try:
        for entry in fetch_final_audit_entries(start_dt, end_dt):
            user_id = entry["user_id"]
            is_final = entry["status"] in ('ok', 'reconciled')
            cost = entry["cost_usd"] if is_final else 0.0
            tokens = entry["tokens_total"] if is_final else 0
            latency = entry["latency_ms"] or 0.0
            model = entry["model"] or "unknown"

            g_id = user_primary_group.get(user_id)
            g_name = group_names.get(g_id, "Uncategorized") if g_id else "Uncategorized"
            key = g_id if g_id else "uncategorized"

            stats = group_stats[key]
            stats["group_id"] = g_id
            stats["group_name"] = g_name
            stats["total_requests"] += 1
            stats["total_cost"] += cost
            stats["total_tokens"] += tokens
            stats["total_latency_ms"] += latency
            stats["models"][model] += 1

    except Exception as e:
        logger.error(f"Failed to fetch audit logs: {e}")
        raise HTTPException(status_code=500, detail="Database query failed")

    result = []
    for g_id, stats in group_stats.items():
        reqs = stats["total_requests"]
        avg_latency = stats["total_latency_ms"] / reqs if reqs > 0 else 0
        
        model_prefs = []
        for m, count in stats["models"].items():
            model_prefs.append({
                "model": m,
                "count": count,
                "percentage": round((count / reqs) * 100, 1) if reqs > 0 else 0
            })
        model_prefs.sort(key=lambda x: x["count"], reverse=True)
        
        result.append({
            "group_id": stats["group_id"],
            "group_name": stats["group_name"],
            "total_requests": reqs,
            "total_cost": round(stats["total_cost"], 4),
            "total_tokens": stats["total_tokens"],
            "avg_latency_ms": round(avg_latency, 2),
            "model_preferences": model_prefs
        })
        
    result.sort(key=lambda x: x["total_cost"], reverse=True)
    return {"status": "ok", "groups": result}

def get_group_users(request: Request, group_id: str, minutes: int = Query(43200), start: str = Query(None), end: str = Query(None)):
    """
    Get usage breakdown for all users belonging to a specific group_id.
    """
    require_admin_or_session(request)
    start_dt, end_dt = _time_boundaries(minutes, start, end)
    
    # 1. Fetch group members from Open WebUI DB
    group_users = set()
    user_names = {}
    try:
        with db_ow_conn() as conn:
            cur = conn.cursor()
            # If group_id is 'uncategorized' or similar, we won't find it here, 
            # but we still fetch names for all users.
            cur.execute('SELECT id, name, email FROM "user"')
            for row in cur.fetchall():
                user_names[row[2]] = row[1] or row[2] # email is row[2], map email->name
            
            # Fetch users in this group
            cur.execute("""
                SELECT u.email 
                FROM group_member gm
                JOIN "user" u ON gm.user_id = u.id
                WHERE gm.group_id = %s
            """, (group_id,))
            for row in cur.fetchall():
                group_users.add(row[0])
            cur.close()
    except Exception as e:
        logger.error(f"Failed to fetch group members: {e}")

    # Aggregate data structures
    # user_id -> stats
    user_stats = defaultdict(lambda: {
        "user_id": None,
        "user_name": "Unknown",
        "total_requests": 0,
        "total_cost": 0.0,
        "total_tokens": 0,
        "total_latency_ms": 0.0,
        "models": defaultdict(int)
    })

    try:
        for entry in fetch_final_audit_entries(start_dt, end_dt):
            user_id = entry["user_id"] # email in middleware

            # Filter to only the users in the group.
            # If group is 'uncategorized', we include users NOT in any group?
            # For simplicity, if group_id is passed and it's a real group, check membership.
            if group_id and group_id != "uncategorized" and group_id != "None" and user_id not in group_users:
                continue

            # If it's uncategorized, we check if they are in ANY group.
            # But to accurately filter uncategorized, we'd need to know if they have a primary group.
            # Since the current feature targets drill-down of actual groups, we just return those in group_users.
            # If group_id == uncategorized, we might just not filter or filter those without groups.

            is_final = entry["status"] in ('ok', 'reconciled')
            cost = entry["cost_usd"] if is_final else 0.0
            tokens = entry["tokens_total"] if is_final else 0
            latency = entry["latency_ms"] or 0.0
            model = entry["model"] or "unknown"

            stats = user_stats[user_id]
            stats["user_id"] = user_id
            stats["user_name"] = user_names.get(user_id, user_id)
            stats["total_requests"] += 1
            stats["total_cost"] += cost
            stats["total_tokens"] += tokens
            stats["total_latency_ms"] += latency
            stats["models"][model] += 1

    except Exception as e:
        logger.error(f"Failed to fetch audit logs for group: {e}")
        raise HTTPException(status_code=500, detail="Database query failed")

    # If it was uncategorized, we need to filter OUT users who actually belong to a group.
    if not group_id or group_id == "uncategorized" or group_id == "None":
        try:
            with db_ow_conn() as conn:
                cur = conn.cursor()
                cur.execute('SELECT u.email FROM group_member gm JOIN "user" u ON gm.user_id = u.id')
                all_grouped_users = set([r[0] for r in cur.fetchall()])
                cur.close()
            
            filtered_stats = {}
            for k, v in user_stats.items():
                if k not in all_grouped_users:
                    filtered_stats[k] = v
            user_stats = filtered_stats
        except:
            pass

    # active / disabled / deleted per email, from middleware records
    # (mw_users outlives the Open WebUI account thanks to soft delete)
    user_status = {}
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, active, deleted_at FROM mw_users")
            for uid, active, deleted_at in cur.fetchall():
                user_status[uid] = "deleted" if deleted_at else ("active" if active else "disabled")
            cur.close()
    except Exception as e:
        logger.error(f"Failed to load user status for group drilldown: {e}")

    result = []
    for u_id, stats in user_stats.items():
        reqs = stats["total_requests"]
        avg_latency = stats["total_latency_ms"] / reqs if reqs > 0 else 0

        model_prefs = []
        for m, count in stats["models"].items():
            model_prefs.append({
                "model": m,
                "count": count,
                "percentage": round((count / reqs) * 100, 1) if reqs > 0 else 0
            })
        model_prefs.sort(key=lambda x: x["count"], reverse=True)

        result.append({
            "user_id": stats["user_id"],
            "user_name": stats["user_name"],
            # Absent from mw_users = hard-deleted before soft delete existed
            "user_status": (user_status.get(u_id, "deleted") if u_id else "unknown"),
            "total_requests": reqs,
            "total_cost": round(stats["total_cost"], 4),
            "total_tokens": stats["total_tokens"],
            "avg_latency_ms": round(avg_latency, 2),
            "model_preferences": model_prefs
        })

    result.sort(key=lambda x: x["total_cost"], reverse=True)
    return {"status": "ok", "users": result}
