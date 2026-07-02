"""Controlled DB integration test for quota reset, updates, and alert claims."""

import os
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor

from config import DATABASE_URL
from core.auth import (
    claim_quota_alert,
    create_user_record,
    delete_user,
    get_user_by_id,
    reset_user_quota_period,
    update_user_admin_fields,
    update_user_quota,
)
from core.db import init_pool
from core.quota import period_anchor_ms


def main():
    init_pool(DATABASE_URL)
    user_id = f"quota-regression-{uuid.uuid4().hex[:8]}"
    try:
        created = create_user_record({
            "user_id": user_id,
            "active": True,
            "allowed_models": ["*"],
            "quota": {
                "period": "monthly",
                "timezone": "UTC",
                "period_start": 1,
                "used_tokens": 9,
                "used_cost_usd": 0.009,
                "limit_cost_usd": 0.008,
            },
            "alerts_sent": {"alert_80": "old"},
        })
        assert created

        anchor = period_anchor_ms("monthly", "UTC")
        reset = reset_user_quota_period(user_id, anchor)
        assert reset["quota"]["used_cost_usd"] == 0
        assert reset["alerts_sent"] == {}

        with ThreadPoolExecutor(max_workers=8) as executor:
            operations = [lambda: update_user_quota(user_id, add_cost_usd=0.001) for _ in range(20)]
            operations += [lambda: reset_user_quota_period(user_id, anchor) for _ in range(5)]
            operations += [lambda: update_user_admin_fields(user_id, quota_limits={"limit_cost_usd": 0.008})]
            list(executor.map(lambda operation: operation(), operations))
            claims = list(executor.map(
                lambda _: claim_quota_alert(
                    user_id, anchor, 50, "test_claim", {"limit_usd": 0.008}
                ),
                range(20),
            ))
        assert sum(claims) == 1

        update_user_admin_fields(user_id, quota_limits={"limit_cost_usd": 10})
        committed = get_user_by_id(user_id)
        assert abs(committed["quota"]["used_cost_usd"] - 0.02) < 1e-9
        assert committed["quota"]["limit_cost_usd"] == 10

        for limit in (0.1, 0.01, 0.008, 10):
            update_user_admin_fields(user_id, quota_limits={"limit_cost_usd": limit})
            assert get_user_by_id(user_id)["quota"]["limit_cost_usd"] == limit

        # Controlled threshold verification: no SMTP and notifications captured in memory.
        import core.alerting as alerting
        import core.notification as notification
        delivered = []

        async def capture_notification(**payload):
            delivered.append(payload)

        original_config = alerting.load_alert_config
        original_send = notification.send_notification
        alerting.load_alert_config = lambda: {
            "smtp": {"enabled": False},
            "admin_alerts": {"emails": [], "per_user_quota": {"thresholds": [80, 95, 100]}},
            "user_alerts": {"enabled": False, "send_email": False, "thresholds": [80, 95, 100]},
        }
        notification.send_notification = capture_notification
        try:
            update_user_admin_fields(user_id, quota_limits={"limit_cost_usd": 0.025})
            asyncio.run(alerting.check_and_send_alerts(user_id))
            update_user_quota(user_id, add_cost_usd=0.00375)
            asyncio.run(alerting.check_and_send_alerts(user_id))
            update_user_quota(user_id, add_cost_usd=0.00125)
            asyncio.run(alerting.check_and_send_alerts(user_id))
            assert [item["metadata"]["threshold"] for item in delivered] == [80, 95, 100]
        finally:
            alerting.load_alert_config = original_config
            notification.send_notification = original_send
        print("quota integration test: OK")
    finally:
        delete_user(user_id)


if __name__ == "__main__":
    main()
