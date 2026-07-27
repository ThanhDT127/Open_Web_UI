"""
Notification service — central fan-out for all alert channels.

After each quota check, send_notification() stores in DB (always)
and optionally sends email (only for critical alerts).

Daily digest is triggered by scheduler at 8:00 AM VN time.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("llm_mw")


# ─── Core: insert notification ──────────────────────────────

def _db_available() -> bool:
    try:
        from core.db import _pool
        return _pool is not None
    except Exception:
        return False


def insert_notification(
    user_id: Optional[str],
    type: str,
    level: str,
    title: str,
    message: str,
    metadata: dict = None,
) -> Optional[int]:
    """
    Insert a notification into mw_notifications.
    Returns the notification ID, or None if DB unavailable.
    """
    if not _db_available():
        logger.warning("notification_skip: DB not available, type=%s user=%s", type, user_id)
        return None

    try:
        from core.db import db_conn
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO mw_notifications (user_id, type, level, title, message, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                user_id, type, level, title, message,
                json.dumps(metadata or {}, ensure_ascii=False),
            ))
            row = cur.fetchone()
            cur.close()
            notif_id = row[0] if row else None
            logger.info(
                "notification_created id=%s type=%s level=%s user=%s",
                notif_id, type, level, user_id
            )
            return notif_id
    except Exception as e:
        logger.error("notification_insert_failed: %s", str(e))
        return None


# ─── Fan-out: notification + optional email ──────────────────

async def send_notification(
    user_id: Optional[str],
    type: str,
    level: str,
    title: str,
    message: str,
    metadata: dict = None,
    send_email_realtime: bool = False,
):
    """
    Central notification dispatcher.

    1. Always insert into DB (dashboard notification)
    2. Send realtime email ONLY if send_email_realtime=True (critical only)
    3. All notifications will be included in daily digest regardless

    Args:
        user_id: Target user, or None for system-wide
        type: 'quota_warning', 'quota_critical', 'quota_blocked', 'budget_warning', etc.
        level: 'info', 'warning', 'critical'
        title: Short title for notification
        message: Full message body
        metadata: Extra data (percent, used, limit, etc.)
        send_email_realtime: If True, also send email immediately
    """
    # 1. Always store in DB
    notif_id = insert_notification(user_id, type, level, title, message, metadata)

    # 2. Send realtime email for critical alerts
    if send_email_realtime:
        try:
            from core.alerting import load_alert_config, _smtp_send
            config = load_alert_config()
            smtp_cfg = config.get("smtp", {})
            admin_emails = config.get("admin_alerts", {}).get("emails", [])

            if smtp_cfg.get("enabled") and admin_emails:
                email_body = _format_email_body(type, level, title, message, metadata)
                _smtp_send(smtp_cfg, admin_emails, f"🚨 {title}", email_body)

                # Mark as emailed
                if notif_id and _db_available():
                    try:
                        from core.db import db_conn
                        with db_conn() as conn:
                            cur = conn.cursor()
                            cur.execute(
                                "UPDATE mw_notifications SET emailed = true WHERE id = %s",
                                (notif_id,)
                            )
                            cur.close()
                    except Exception:
                        pass

                logger.info("notification_emailed id=%s to=%s", notif_id, admin_emails)
            else:
                logger.info("notification_email_skip: SMTP disabled or no admin emails")
        except Exception as e:
            logger.error("notification_email_failed id=%s: %s", notif_id, str(e))


def _format_email_body(type: str, level: str, title: str, message: str, metadata: dict = None) -> str:
    """Format notification as plain-text email body."""
    level_icon = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(level, "📋")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{level_icon} {title}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        message,
        "",
    ]

    if metadata:
        lines.append("Chi tiết:")
        for k, v in metadata.items():
            lines.append(f"  • {k}: {v}")
        lines.append("")

    lines.extend([
        f"Thời gian: {now}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ])
    return "\n".join(lines)


# ─── Daily digest ────────────────────────────────────────────

async def send_daily_digest():
    """
    Send daily digest email at 8:00 AM VN time.
    Aggregates all notifications from the last 24 hours into one email.
    Called by APScheduler.
    """
    if not _db_available():
        logger.warning("daily_digest_skip: DB not available")
        return

    try:
        from core.db import db_conn
        from core.alerting import load_alert_config, _smtp_send
        from core.auth import load_users

        config = load_alert_config()
        smtp_cfg = config.get("smtp", {})
        admin_emails = config.get("admin_alerts", {}).get("emails", [])

        if not smtp_cfg.get("enabled") or not admin_emails:
            logger.info("daily_digest_skip: SMTP disabled or no admin emails")
            return

        # Get notifications from last 24 hours
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, ts, user_id, type, level, title, message, metadata
                FROM mw_notifications
                WHERE ts >= now() - interval '24 hours'
                ORDER BY ts DESC
            """)
            rows = cur.fetchall()
            cur.close()

        if not rows:
            logger.info("daily_digest_skip: no notifications in last 24h")
            return

        # Get user quota summary
        users = load_users()
        user_summaries = []
        for u in sorted(users, key=lambda x: float(x.get("quota", {}).get("used_cost_usd", 0) or 0), reverse=True):
            uid = u.get("user_id", "?")
            quota = u.get("quota", {})
            used = float(quota.get("used_cost_usd", 0) or 0)
            limit = float(quota.get("limit_cost_usd", 0) or 0)
            if used > 0 or limit > 0:
                pct = (used / limit * 100) if limit > 0 else 0
                user_summaries.append(f"  • {uid}: ${used:.2f}/${limit:.2f} ({pct:.0f}%)")

        # Count by level
        critical_count = sum(1 for r in rows if r[4] == "critical")
        warning_count = sum(1 for r in rows if r[4] == "warning")
        info_count = sum(1 for r in rows if r[4] == "info")

        # Build email body
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "📊 LLM Gateway — Daily Digest",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            f"Thời gian: {now}",
            f"Tổng cảnh báo 24h: {len(rows)} ({critical_count} critical, {warning_count} warning, {info_count} info)",
            "",
        ]

        if critical_count > 0:
            lines.append("🚨 CRITICAL ALERTS:")
            for r in rows:
                if r[4] == "critical":
                    lines.append(f"  • [{r[1].strftime('%H:%M')}] {r[3]}: {r[5]}")
            lines.append("")

        if warning_count > 0:
            lines.append("⚠️ WARNINGS:")
            for r in rows:
                if r[4] == "warning":
                    lines.append(f"  • [{r[1].strftime('%H:%M')}] {r[3]}: {r[5]}")
            lines.append("")

        lines.extend([
            "📊 QUOTA SUMMARY (toàn bộ users):",
            *(user_summaries if user_summaries else ["  (không có usage)"]),
            "",
        ])

        # Per-provider API budget breakdown
        try:
            from core.alerting import _get_provider_spend
            provider_spend = _get_provider_spend()
            api_budgets = config.get("admin_alerts", {}).get("api_budgets", {})
            if provider_spend:
                lines.append("💳 CREDIT THEO PROVIDER (từ lần nạp gần nhất):")
                for pname, spend in provider_spend.items():
                    deposited = float(api_budgets.get(pname, {}).get("deposited", 0) or 0)
                    remaining = deposited - spend
                    pct = (spend / deposited * 100) if deposited > 0 else 0
                    lines.append(
                        f"  • {pname.upper()}: đã dùng ${spend:.2f}/${deposited:.2f} "
                        f"({pct:.0f}%) · còn ${remaining:.2f}"
                    )
                lines.append("")
        except Exception:
            pass

        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "Dashboard: /dashboard",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ])

        body = "\n".join(lines)
        subject = f"📊 LLM Gateway Daily Digest — {critical_count} critical, {warning_count} warning ({now})"

        _smtp_send(smtp_cfg, admin_emails, subject, body)

        # Mark all as emailed
        with db_conn() as conn:
            cur = conn.cursor()
            notif_ids = [r[0] for r in rows]
            cur.execute(
                "UPDATE mw_notifications SET emailed = true WHERE id = ANY(%s)",
                (notif_ids,)
            )
            cur.close()

        logger.info("daily_digest_sent notifications=%d to=%s", len(rows), admin_emails)

    except Exception as e:
        logger.error("daily_digest_failed: %s", str(e))


# ─── Query helpers (for API) ─────────────────────────────────

def get_notifications(limit: int = 50, unread_only: bool = False, user_id: str = None) -> list:
    """Get notifications from DB, newest first."""
    if not _db_available():
        return []

    try:
        from core.db import db_conn
        with db_conn() as conn:
            cur = conn.cursor()

            conditions = []
            params = []

            if unread_only:
                conditions.append("read = false")
            if user_id:
                conditions.append("(user_id = %s OR user_id IS NULL)")
                params.append(user_id)

            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            params.append(limit)

            cur.execute(f"""
                SELECT id, ts, user_id, type, level, title, message, read, emailed, metadata
                FROM mw_notifications
                {where}
                ORDER BY ts DESC
                LIMIT %s
            """, params)

            rows = cur.fetchall()
            cur.close()

            return [
                {
                    "id": r[0],
                    "ts": r[1].isoformat() if r[1] else None,
                    "user_id": r[2],
                    "type": r[3],
                    "level": r[4],
                    "title": r[5],
                    "message": r[6],
                    "read": r[7],
                    "emailed": r[8],
                    "metadata": r[9] if r[9] else {},
                }
                for r in rows
            ]
    except Exception as e:
        logger.error("get_notifications_failed: %s", str(e))
        return []


def get_unread_count() -> int:
    """Get count of unread notifications."""
    if not _db_available():
        return 0

    try:
        from core.db import db_conn
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM mw_notifications WHERE read = false")
            count = cur.fetchone()[0]
            cur.close()
            return count
    except Exception as e:
        logger.error("get_unread_count_failed: %s", str(e))
        return 0


def mark_as_read(notif_id: int = None, all: bool = False) -> bool:
    """Mark notification(s) as read."""
    if not _db_available():
        return False

    try:
        from core.db import db_conn
        with db_conn() as conn:
            cur = conn.cursor()
            if all:
                cur.execute("UPDATE mw_notifications SET read = true WHERE read = false")
            elif notif_id:
                cur.execute("UPDATE mw_notifications SET read = true WHERE id = %s", (notif_id,))
            cur.close()
            return True
    except Exception as e:
        logger.error("mark_as_read_failed: %s", str(e))
        return False
