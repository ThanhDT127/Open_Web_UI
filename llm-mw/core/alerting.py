"""
Quota alert system — checks thresholds and sends email notifications.

After each request, check_and_send_alerts() compares current usage
against configured milestones (50/70/90/100%) and sends admin emails
via SMTP when a new milestone is reached.

Alert tracking is stored per-user in alerts_sent{} and reset
each quota period by maybe_reset_quota().
"""

import os
import json
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from config import DATA_DIR, BACKUP_DATA_DIR, logger
from core.auth import claim_quota_alert, load_users, save_users, get_lock


# ─── File paths ───────────────────────────────────────────────

ALERT_CONFIG_FILE = os.path.join(BACKUP_DATA_DIR, "alert_config.json")
SYSTEM_ALERTS_FILE = os.path.join(BACKUP_DATA_DIR, "system_alerts.json")

DEFAULT_ALERT_CONFIG = {
    "smtp": {
        "enabled": False,
        "host": "",
        "port": 587,
        "username": "",
        "password_env": "SMTP_PASSWORD",
        "from_email": "",
        "use_tls": True
    },
    "admin_alerts": {
        "emails": [],
        "api_budgets": {},
        "per_user_quota": {
            "enabled": True,
            "thresholds": [80, 95, 100]
        },
        "daily_digest_enabled": True,
        "send_email_realtime": True,
        "dashboard_alerts_enabled": True
    },
    "user_alerts": {
        "enabled": True,
        "send_email": True,
        "thresholds": [80, 95, 100]
    }
}


def _db_available() -> bool:
    """Check if database pool is initialized."""
    try:
        from core.db import _pool
        return _pool is not None
    except Exception:
        return False


# ─── Config helpers (DB + file fallback) ──────────────────────

def load_alert_config() -> dict:
    """Load alert configuration. DB first, then file fallback."""
    config = DEFAULT_ALERT_CONFIG.copy()

    if _db_available():
        try:
            from core.db import db_conn
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT config_value FROM mw_config WHERE config_key = 'alert_config'")
                row = cur.fetchone()
                cur.close()
            if row:
                # Merge DB config into default
                db_cfg = row[0]
                for k, v in db_cfg.items():
                    if isinstance(v, dict) and isinstance(config.get(k), dict):
                        config[k].update(v)
                    else:
                        config[k] = v
                return config
        except Exception:
            pass

    # File fallback
    if os.path.exists(ALERT_CONFIG_FILE):
        try:
            with open(ALERT_CONFIG_FILE, "r", encoding="utf-8") as f:
                file_cfg = json.load(f)
                for k, v in file_cfg.items():
                    if isinstance(v, dict) and isinstance(config.get(k), dict):
                        config[k].update(v)
                    else:
                        config[k] = v
        except Exception:
            pass
            
    return config


def save_alert_config(config: dict):
    """Save alert config to DB + file backup."""
    if _db_available():
        try:
            from core.db import db_conn
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO mw_config (config_key, config_value, updated_at)
                    VALUES ('alert_config', %s, now())
                    ON CONFLICT (config_key) DO UPDATE SET
                        config_value = EXCLUDED.config_value,
                        updated_at = now()
                """, (json.dumps(config),))
                cur.close()
        except Exception:
            pass
    # Always write file backup
    try:
        with open(ALERT_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("save_alert_config_file_failed: %s", str(e))


def load_system_alerts() -> dict:
    """Load system-level alert tracking. DB first, then file fallback."""
    if _db_available():
        try:
            from core.db import db_conn
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT config_value FROM mw_config WHERE config_key = 'system_alerts'")
                row = cur.fetchone()
                cur.close()
            if row:
                return row[0]
        except Exception:
            pass
    # File fallback
    if not os.path.exists(SYSTEM_ALERTS_FILE):
        return {}
    with open(SYSTEM_ALERTS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_system_alerts(alerts: dict):
    """Save system alert tracking to DB + file backup."""
    if _db_available():
        try:
            from core.db import db_conn
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO mw_config (config_key, config_value, updated_at)
                    VALUES ('system_alerts', %s, now())
                    ON CONFLICT (config_key) DO UPDATE SET
                        config_value = EXCLUDED.config_value,
                        updated_at = now()
                """, (json.dumps(alerts),))
                cur.close()
        except Exception:
            pass
    # Always write file backup
    with open(SYSTEM_ALERTS_FILE, "w", encoding="utf-8") as f:
        json.dump(alerts, f, indent=2, ensure_ascii=False)



# ─── Main alert check ────────────────────────────────────────

async def _legacy_check_and_send_alerts(user_id: str, add_cost_usd: float = 0.0):
    """
    Check quota thresholds and send notifications.
    
    Runs ASYNC after quota bump — does NOT block user response.
    Three checks:
      1. Per-user quota vs their limit → alert USER email + admin dashboard
      2. Per-provider API budget → alert ADMIN email
    
    Args:
        user_id: The user who just made a request
        add_cost_usd: Cost of the request (for logging context)
    """
    try:
        config = load_alert_config()
        smtp_enabled = config.get("smtp", {}).get("enabled", False)

        admin_alerts_cfg = config.get("admin_alerts", {})
        admin_emails = admin_alerts_cfg.get("emails", [])

        # Collect emails to send OUTSIDE the lock
        pending_emails = []
        pending_notifications = []

        lock = get_lock()
        with lock:
            users = load_users()

            # ═══════════════════════════════════════════
            # CHECK 1: Per-user quota → dashboard + user email
            # ═══════════════════════════════════════════
            user = next((u for u in users if u.get("user_id") == user_id), None)
            if user:
                quota = user.get("quota", {})
                limit_cost = float(quota.get("limit_cost_usd", 0) or 0)
                used_cost = float(quota.get("used_cost_usd", 0) or 0)

                if limit_cost > 0:
                    percent = (used_cost / limit_cost) * 100
                    alerts_sent = user.setdefault("alerts_sent", {})

                    # Admin dashboard thresholds
                    admin_thresholds = admin_alerts_cfg.get("per_user_quota", {}).get("thresholds", [80, 95, 100])
                    # User email thresholds
                    user_cfg = config.get("user_alerts", {})
                    user_thresholds = user_cfg.get("thresholds", [80, 95, 100])
                    user_email_enabled = user_cfg.get("enabled") and user_cfg.get("send_email") and smtp_enabled

                    # Merge all thresholds, use unified key
                    all_thresholds = sorted(set(admin_thresholds + user_thresholds))

                    for threshold in all_thresholds:
                        key = f"alert_{threshold}"  # Unified key — prevents duplicates
                        if percent >= threshold and key not in alerts_sent:
                            # Determine level
                            if threshold >= 100:
                                level = "critical"
                                notif_type = "quota_blocked"
                                send_admin_email = True
                            elif threshold >= 95:
                                level = "warning"
                                notif_type = "quota_critical"
                                send_admin_email = False
                            else:
                                level = "info"
                                notif_type = "quota_warning"
                                send_admin_email = False

                            title = f"User {user_id} đạt {threshold}% quota"
                            message = (
                                f"User {user_id} đã sử dụng ${used_cost:.2f}/${limit_cost:.2f} ({percent:.0f}%). "
                                f"Còn lại: ${limit_cost - used_cost:.2f}"
                            )
                            metadata = {
                                "user_id": user_id,
                                "percent": round(percent, 1),
                                "used_usd": round(used_cost, 4),
                                "limit_usd": round(limit_cost, 2),
                                "threshold": threshold,
                            }

                            # Queue dashboard notification
                            pending_notifications.append({
                                "user_id": user_id,
                                "type": notif_type,
                                "level": level,
                                "title": title,
                                "message": message,
                                "metadata": metadata,
                                "send_email_realtime": send_admin_email,
                            })

                            # Queue user email (if enabled)
                            if user_email_enabled and threshold in user_thresholds:
                                user_email = _get_user_email(user_id)
                                if user_email:
                                    pending_emails.append({
                                        "type": "user_quota",
                                        "to": user_email,
                                        "user_id": user_id,
                                        "threshold": threshold,
                                        "used": used_cost,
                                        "limit": limit_cost,
                                        "percent": percent,
                                    })

                            # Mark as sent (unified key)
                            alerts_sent[key] = datetime.now(timezone.utc).isoformat()
                            logger.info(
                                "alert_threshold user=%s threshold=%d%% level=%s",
                                user_id, threshold, level
                            )

            # ═══════════════════════════════════════════
            # CHECK 2: Per-provider API budget → notify ADMIN
            # ═══════════════════════════════════════════
            api_budgets = admin_alerts_cfg.get("api_budgets", {})
            if api_budgets and admin_emails:
                _check_provider_budget_alerts(
                    config, api_budgets, admin_emails,
                    pending_notifications, pending_emails
                )

            save_users(users)

        # ═══════════════════════════════════════════
        # OUTSIDE LOCK: send notifications + emails (non-blocking)
        # ═══════════════════════════════════════════
        for notif in pending_notifications:
            try:
                from core.notification import send_notification
                await send_notification(**notif)
            except Exception as e:
                logger.error("alert_notification_failed: %s", str(e))

        if pending_emails and smtp_enabled:
            smtp_cfg = config.get("smtp", {})
            for email_task in pending_emails:
                try:
                    await asyncio.to_thread(
                        _send_queued_email, smtp_cfg, email_task
                    )
                except Exception as e:
                    logger.error("alert_email_failed: %s", str(e))

    except Exception as e:
        logger.error("alert_check_failed user=%s: %s", user_id, str(e))
        # NEVER raise — alert failures must not block users


def _format_usd(value: float) -> str:
    """Format small quota values without hiding their actual magnitude."""
    value = max(0.0, float(value or 0))
    if value >= 1:
        return f"${value:.2f}"
    return f"${value:.6f}".rstrip("0").rstrip(".")


def _quota_alert_kind(threshold: int):
    if threshold >= 100:
        return "critical", "quota_blocked", True
    if threshold >= 95:
        return "warning", "quota_critical", False
    return "info", "quota_warning", False


# Replaces the legacy full-user-list implementation defined above.
async def check_and_send_alerts(user_id: str, add_cost_usd: float = 0.0):
    """Evaluate and claim alerts from one freshly committed quota record."""
    try:
        config = load_alert_config()
        smtp_enabled = config.get("smtp", {}).get("enabled", False)
        admin_cfg = config.get("admin_alerts", {})
        pending_emails = []
        pending_notifications = []

        from core.quota import get_current_quota_user
        user = get_current_quota_user(user_id)
        if user:
            quota = user.get("quota", {})
            limit_cost = float(quota.get("limit_cost_usd", 0) or 0)
            used_cost = float(quota.get("used_cost_usd", 0) or 0)
            period_start = int(quota.get("period_start", 0) or 0)
            if limit_cost > 0:
                percent = used_cost / limit_cost * 100
                admin_thresholds = admin_cfg.get("per_user_quota", {}).get("thresholds", [80, 95, 100])
                user_cfg = config.get("user_alerts", {})
                user_thresholds = user_cfg.get("thresholds", [80, 95, 100])
                user_email_enabled = user_cfg.get("enabled") and user_cfg.get("send_email") and smtp_enabled

                for threshold in sorted(set(admin_thresholds + user_thresholds)):
                    if percent < threshold:
                        continue
                    level, alert_type, send_admin_email = _quota_alert_kind(threshold)
                    snapshot = {
                        "user_id": user_id,
                        "percent": percent,
                        "used_usd": used_cost,
                        "limit_usd": limit_cost,
                        "remaining_usd": max(0.0, limit_cost - used_cost),
                        "threshold": threshold,
                        "period_start": period_start,
                    }
                    if not claim_quota_alert(user_id, period_start, threshold, alert_type, snapshot):
                        continue
                    pending_notifications.append({
                        "user_id": user_id,
                        "type": alert_type,
                        "level": level,
                        "title": f"User {user_id} dat {threshold}% quota",
                        "message": (
                            f"User {user_id} da su dung {_format_usd(used_cost)}/{_format_usd(limit_cost)} "
                            f"({percent:.1f}%). Con lai: {_format_usd(max(0.0, limit_cost - used_cost))}"
                        ),
                        "metadata": snapshot,
                        "send_email_realtime": send_admin_email,
                    })
                    if user_email_enabled and threshold in user_thresholds:
                        email = _get_user_email(user_id)
                        if email:
                            pending_emails.append({
                                "type": "user_quota", "to": email, "user_id": user_id,
                                "threshold": threshold, "used": used_cost,
                                "limit": limit_cost, "percent": percent,
                            })

        api_budgets = admin_cfg.get("api_budgets", {})
        admin_emails = admin_cfg.get("emails", [])
        if api_budgets and admin_emails:
            _check_provider_budget_alerts(config, api_budgets, admin_emails, pending_notifications, pending_emails)

        from core.notification import send_notification
        for notification in pending_notifications:
            await send_notification(**notification)
        if pending_emails and smtp_enabled:
            smtp_cfg = config.get("smtp", {})
            for email_task in pending_emails:
                await asyncio.to_thread(_send_queued_email, smtp_cfg, email_task)
    except Exception as e:
        logger.error("alert_check_failed user=%s: %s", user_id, str(e))


def _send_queued_email(smtp_cfg: dict, email_task: dict):
    """Send a queued email. Called via asyncio.to_thread() to avoid blocking."""
    task_type = email_task.get("type")
    if task_type == "user_quota":
        user_id = email_task["user_id"]
        threshold = email_task["threshold"]
        used = email_task["used"]
        limit = email_task["limit"]
        percent = email_task["percent"]

        if threshold >= 100:
            subject = f"🚨 Quota hết — Tài khoản {user_id} đã đạt 100% hạn mức"
        elif threshold >= 95:
            subject = f"⚠️ Cảnh báo quota — {user_id} đạt {threshold}%"
        else:
            subject = f"ℹ️ Nhắc nhở quota — {user_id} đạt {threshold}%"

        body = (
            f"Xin chào {user_id},\n\n"
            f"Tài khoản của bạn đã sử dụng {percent:.0f}% hạn mức chi phí.\n\n"
            f"  • Đã dùng: ${used:.4f}\n"
            f"  • Hạn mức:  {_format_usd(limit)}\n"
            f"  • Còn lại:  {_format_usd(max(0.0, limit - used))}\n\n"
        )
        if threshold >= 100:
            body += (
                "❌ Tài khoản của bạn đã BỊ CHẶN do hết hạn mức.\n"
                "Vui lòng liên hệ admin để được nâng hạn mức.\n"
            )
        else:
            body += "Vui lòng sử dụng tiết kiệm để tránh bị chặn.\n"

        _smtp_send(smtp_cfg, [email_task["to"]], subject, body)
        logger.info("user_quota_email_sent user=%s email=%s threshold=%d%%",
                    user_id, email_task["to"], threshold)


def _check_provider_budget_alerts(
    config: dict, api_budgets: dict, admin_emails: list,
    pending_notifications: list, pending_emails: list
):
    """Check per-provider API budget thresholds from audit log.
    Queues notifications and emails instead of sending directly."""
    system_alerts = load_system_alerts()

    # Calculate spend per provider from audit log
    provider_spend = _get_provider_spend()

    for provider_name, pcfg in api_budgets.items():
        if not pcfg.get("enabled", True):
            continue

        budget = float(pcfg.get("budget_usd", 0) or 0)
        if budget <= 0:
            continue

        spend = provider_spend.get(provider_name, 0.0)
        percent = (spend / budget) * 100
        thresholds = pcfg.get("thresholds", [70, 90, 100])

        for threshold in thresholds:
            key = f"provider_{provider_name}_{threshold}"
            if percent >= threshold and key not in system_alerts:
                if threshold >= 100:
                    level = "critical"
                    send_email = True
                elif threshold >= 90:
                    level = "warning"
                    send_email = False
                else:
                    level = "info"
                    send_email = False

                title = f"API {provider_name.upper()} đạt {threshold}% budget (${spend:.2f}/${budget:.2f})"
                message = (
                    f"Chi phí {provider_name.upper()} tháng này: ${spend:.2f}/{budget:.2f} ({percent:.0f}%). "
                    f"Còn lại: ${budget - spend:.2f}"
                )
                metadata = {
                    "provider": provider_name,
                    "spend_usd": round(spend, 2),
                    "budget_usd": round(budget, 2),
                    "percent": round(percent, 1),
                    "threshold": threshold,
                }

                logger.info(
                    "alert_provider_budget provider=%s threshold=%d%% spend=$%.2f budget=$%.2f email=%s",
                    provider_name, threshold, spend, budget, send_email
                )

                # Queue notification (will be sent outside lock)
                pending_notifications.append({
                    "user_id": None,
                    "type": "budget_provider",
                    "level": level,
                    "title": title,
                    "message": message,
                    "metadata": metadata,
                    "send_email_realtime": send_email,
                })

                system_alerts[key] = datetime.now(timezone.utc).isoformat()

    save_system_alerts(system_alerts)


def _get_provider_spend() -> dict:
    """Calculate current month spending per provider from audit log."""
    try:
        from core.db import db_conn, _pool
        if _pool is None:
            return {}

        config = load_alert_config()
        api_budgets = config.get("admin_alerts", {}).get("api_budgets", {})

        result = {}
        with db_conn() as conn:
            cur = conn.cursor()
            for provider_name, pcfg in api_budgets.items():
                prefixes = pcfg.get("model_prefixes", [])
                if not prefixes:
                    continue

                # Build LIKE conditions for model prefixes
                like_conditions = " OR ".join(
                    "model LIKE %s" for _ in prefixes
                )
                like_params = [f"{p}%" for p in prefixes]

                cur.execute(f"""
                    SELECT COALESCE(SUM(cost_usd), 0)
                    FROM mw_audit_log
                    WHERE ts >= date_trunc('month', now())
                      AND ({like_conditions})
                """, like_params)

                spend = cur.fetchone()[0]
                result[provider_name] = float(spend)

            cur.close()
        return result

    except Exception as e:
        logger.error("get_provider_spend_failed: %s", str(e))
        return {}


# _send_user_quota_email removed — unified into check_and_send_alerts
# User emails are now queued as pending_emails and sent via asyncio.to_thread


# Cache for OpenWebUI DB URL to avoid reparsing
_openwebui_url_cache: Optional[str] = None


def _get_user_email(user_id: str) -> str:
    """
    Get user email from Open WebUI database.
    Uses a separate connection (not from MW pool) since it's a different database.
    Caches the connection URL to avoid reparsing.
    """
    global _openwebui_url_cache

    # Method 1: Check if user_id IS an email
    if "@" in user_id:
        return user_id

    # Method 2: Query Open WebUI 'openwebui' database
    try:
        if _openwebui_url_cache is None:
            db_url = os.environ.get("DATABASE_URL", "")
            if not db_url:
                return ""
            from urllib.parse import urlparse
            parsed = urlparse(db_url)
            _openwebui_url_cache = db_url.replace(parsed.path, "/openwebui")

        import psycopg2
        conn = psycopg2.connect(_openwebui_url_cache, connect_timeout=3)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT email FROM \"user\" WHERE name = %s OR email = %s LIMIT 1",
                (user_id, user_id)
            )
            row = cur.fetchone()
            cur.close()
            if row and row[0]:
                return row[0]
        finally:
            conn.close()
    except Exception as e:
        logger.debug("get_user_email_openwebui_failed user=%s: %s", user_id, str(e))

    return ""


# ─── Email sending ────────────────────────────────────────────
# Dead code (_send_admin_email_per_user, _send_admin_email_system_budget) removed.
# Email sending is now unified through _send_queued_email + asyncio.to_thread.


def _smtp_send(smtp_cfg: dict, to_emails: list, subject: str, body: str):
    """
    Send email via SMTP. This is BLOCKING I/O.
    Should be called from asyncio.to_thread() or directly in sync context.
    """
    password = os.environ.get(smtp_cfg.get("password_env", "SMTP_PASSWORD"), "")

    msg = MIMEMultipart()
    msg["From"] = smtp_cfg.get("from_email", "noreply@localhost")
    msg["To"] = ", ".join(to_emails)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(smtp_cfg["host"], smtp_cfg["port"], timeout=10) as server:
            if smtp_cfg.get("use_tls"):
                server.starttls()
            if smtp_cfg.get("username") and password:
                server.login(smtp_cfg["username"], password)
            server.send_message(msg)
        logger.info("alert_email_sent to=%s subject=%s", to_emails, subject)
    except Exception as e:
        logger.error("alert_smtp_error: %s", str(e))
        raise


# ─── Quota status helper (for API endpoint) ──────────────────

def get_user_quota_status(user_id: str) -> dict:
    """
    Get quota usage status for a user.
    Used by /v1/_mw/quota-status endpoint (lightweight, no auth required).
    
    Returns:
        Dict with percent_used, remaining_usd, unlimited flag
    """
    from core.quota import get_current_quota_user

    user = get_current_quota_user(user_id)

    if not user:
        return {"found": False}

    quota = user.get("quota", {})
    limit = float(quota.get("limit_cost_usd", 0) or 0)
    used = float(quota.get("used_cost_usd", 0) or 0)

    if limit <= 0:
        return {
            "found": True,
            "user_id": user_id,
            "percent_used": 0,
            "remaining_usd": None,
            "unlimited": True,
            "alert_level": None
        }

    percent = round(used / limit * 100, 1)
    remaining = max(0, limit - used)

    # Determine alert level
    alert_level = None
    if percent >= 95:
        alert_level = "critical"
    elif percent >= 80:
        alert_level = "warning"

    return {
        "found": True,
        "user_id": user_id,
        "percent_used": percent,
        "used_cost_usd": round(used, 4),
        "limit_cost_usd": limit,
        "remaining_usd": remaining,
        "unlimited": False,
        "alert_level": alert_level
    }
