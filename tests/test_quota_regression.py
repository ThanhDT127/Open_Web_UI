import datetime as dt
import os
import sys
import unittest
from zoneinfo import ZoneInfo


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "llm-mw"))

from core.alerting import _format_usd  # noqa: E402
from core.quota import maybe_reset_quota, period_anchor_ms  # noqa: E402


class QuotaRegressionTests(unittest.TestCase):
    def test_adaptive_currency_preserves_small_limits(self):
        self.assertEqual(_format_usd(10), "$10.00")
        self.assertEqual(_format_usd(0.1), "$0.1")
        self.assertEqual(_format_usd(0.01), "$0.01")
        self.assertEqual(_format_usd(0.008), "$0.008")
        self.assertEqual(_format_usd(-0.002), "$0")

    def test_monthly_anchor_uses_configured_timezone(self):
        now = dt.datetime(2026, 6, 30, 18, 0, tzinfo=ZoneInfo("UTC"))
        expected = dt.datetime(2026, 7, 1, tzinfo=ZoneInfo("Asia/Bangkok"))
        self.assertEqual(period_anchor_ms("monthly", "Asia/Bangkok", now), int(expected.timestamp() * 1000))

    def test_weekly_anchor_uses_configured_timezone(self):
        now = dt.datetime(2026, 6, 7, 18, 0, tzinfo=ZoneInfo("UTC"))
        expected = dt.datetime(2026, 6, 8, tzinfo=ZoneInfo("Asia/Bangkok"))
        self.assertEqual(period_anchor_ms("weekly", "Asia/Bangkok", now), int(expected.timestamp() * 1000))

    def test_expired_period_resets_usage_and_existing_alert_markers(self):
        user = {
            "alerts_sent": {"alert_80": "old"},
            "quota": {
                "period": "monthly",
                "timezone": "UTC",
                "period_start": 1,
                "used_tokens": 12,
                "used_cost_usd": 0.0114,
                "used_image_requests": 2,
            },
        }
        maybe_reset_quota(user)
        self.assertEqual(user["alerts_sent"], {})
        self.assertEqual(user["quota"]["used_tokens"], 0)
        self.assertEqual(user["quota"]["used_cost_usd"], 0.0)
        self.assertEqual(user["quota"]["used_image_requests"], 0)


if __name__ == "__main__":
    unittest.main()
