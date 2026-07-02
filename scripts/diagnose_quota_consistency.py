"""Compare committed quota records with their API projection and recent alerts."""

import json
import os
import sys

import psycopg2


def main() -> int:
    database_url = os.environ.get("MIDDLEWARE_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        print("Set MIDDLEWARE_DATABASE_URL or DATABASE_URL.", file=sys.stderr)
        return 2

    conn = psycopg2.connect(database_url)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT u.user_id, u.quota,
                   COALESCE((
                       SELECT jsonb_agg(n.metadata ORDER BY n.ts DESC)
                       FROM (
                           SELECT metadata, ts FROM mw_notifications
                           WHERE user_id = u.user_id
                             AND type IN ('quota_warning', 'quota_critical', 'quota_blocked')
                           ORDER BY ts DESC LIMIT 3
                       ) n
                   ), '[]'::jsonb)
            FROM mw_users u
            ORDER BY u.user_id
        """)
        report = []
        for user_id, quota, alerts in cur.fetchall():
            used = float(quota.get("used_cost_usd", 0) or 0)
            limit = float(quota.get("limit_cost_usd", 0) or 0)
            report.append({
                "user_id": user_id,
                "persisted": {"used_cost_usd": used, "limit_cost_usd": limit},
                "quota_status_projection": {
                    "used_cost_usd": used,
                    "limit_cost_usd": limit,
                    "percent_used": round(used / limit * 100, 1) if limit > 0 else 0,
                    "remaining_usd": max(0, limit - used) if limit > 0 else None,
                },
                "recent_alert_snapshots": alerts,
            })
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
