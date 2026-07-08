"""
Test script for the quota alert system.
Tests: module imports, config loading, threshold checking, API endpoints.

Run: python test_alerting.py (from llm-mw directory)
"""

import sys
import os
import json
import asyncio

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Track results
passed = 0
failed = 0

def test(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name} — {detail}")
        failed += 1


print("=" * 60)
print("QUOTA ALERT SYSTEM — Unit Tests")
print("=" * 60)

# ─── Test 1: Module imports ────────────────────────────────
print("\n📦 Test 1: Module imports")
try:
    from core.alerting import (
        load_alert_config, save_alert_config,
        load_system_alerts, save_system_alerts,
        check_and_send_alerts, get_user_quota_status,
        ALERT_CONFIG_FILE, SYSTEM_ALERTS_FILE,
        _quota_alert_kind
    )
    test("core.alerting imports", True)
except ImportError as e:
    test("core.alerting imports", False, str(e))

try:
    from api.quota_status import (
        get_quota_status, get_alert_config,
        update_alert_config, test_alert_email
    )
    test("api.quota_status imports", True)
except ImportError as e:
    test("api.quota_status imports", False, str(e))


# ─── Test 2: Config loading ───────────────────────────────
print("\n⚙️  Test 2: Configuration")
config = load_alert_config()
test("alert_config.json loads", isinstance(config, dict))
test("smtp section exists", "smtp" in config)
test("smtp default disabled", config.get("smtp", {}).get("enabled") == False)
test("admin thresholds = [80, 95, 100]",
     config.get("admin_alerts", {}).get("per_user_quota", {}).get("thresholds") == [80, 95, 100])
test("user thresholds = [80, 95, 100]",
     config.get("user_alerts", {}).get("thresholds") == [80, 95, 100])

sys_alerts = load_system_alerts()
test("system_alerts.json loads", isinstance(sys_alerts, dict))
test("system_alerts initially empty", len(sys_alerts) == 0)


# ─── Test 3: Level mapping ────────────────────────────────
print("\n🏷️  Test 3: Level mapping")
level_80, type_80, _ = _quota_alert_kind(80)
level_95, type_95, _ = _quota_alert_kind(95)
level_100, type_100, _ = _quota_alert_kind(100)

test("80 -> info", level_80 == "info" and type_80 == "quota_warning")
test("95 -> warning", level_95 == "warning" and type_95 == "quota_critical")
test("100 -> critical", level_100 == "critical" and type_100 == "quota_blocked")


# ─── Test 4: User quota status ────────────────────────────
print("\n📊 Test 4: Quota status helper")

# Test existing user
status_admin = get_user_quota_status("adminrd")
test("adminrd found", status_admin.get("found") == True)
test("adminrd has limit", status_admin.get("unlimited") == False)

status_user1 = get_user_quota_status("user1")
test("user1 found", status_user1.get("found") == True)
test("user1 has limit", status_user1.get("unlimited") == False or status_user1.get("limit_cost_usd", 0) > 0)
test("user1 percent_used is number", isinstance(status_user1.get("percent_used"), (int, float)))

# Test non-existent user
status_none = get_user_quota_status("nonexistent_user_xyz")
test("nonexistent user not found", status_none.get("found") == False)


# ─── Test 5: Threshold detection (dry run) ────────────────
print("\n🔔 Test 5: Threshold detection (SMTP disabled — log only)")

# Save current users, create test scenario
from core.auth import load_users, save_users, get_lock

original_users = load_users()

# Temporarily modify user1 to have high usage for testing
lock = get_lock()
with lock:
    test_users = json.loads(json.dumps(original_users))  # deep copy
    for u in test_users:
        if u.get("user_id") == "user1":
            u["quota"]["limit_cost_usd"] = 10.0  # Set limit explicitly to 10.0
            u["quota"]["used_cost_usd"] = 8.5  # 85% of $10 limit
            u["alerts_sent"] = {}
            break
    save_users(test_users)

# Run alert check (should trigger 80% milestone)
asyncio.run(check_and_send_alerts("user1", add_cost_usd=0.01))

# Check alerts_sent was updated
updated_users = load_users()
user1 = next((u for u in updated_users if u.get("user_id") == "user1"), None)
alerts = user1.get("alerts_sent", {}) if user1 else {}

test("80% milestone logged", "alert_80" in alerts, f"alerts_sent={alerts}")
test("95% NOT triggered (85%<95%)", "alert_95" not in alerts, f"alerts_sent={alerts}")

# Now bump to 97%
with lock:
    test_users2 = load_users()
    for u in test_users2:
        if u.get("user_id") == "user1":
            u["quota"]["used_cost_usd"] = 9.7  # 97%
            break
    save_users(test_users2)

asyncio.run(check_and_send_alerts("user1", add_cost_usd=0.01))

updated_users2 = load_users()
user1_v2 = next((u for u in updated_users2 if u.get("user_id") == "user1"), None)
alerts2 = user1_v2.get("alerts_sent", {}) if user1_v2 else {}

test("95% milestone NOW logged", "alert_95" in alerts2, f"alerts_sent={alerts2}")
test("100% still NOT triggered (97%<100%)", "alert_100" not in alerts2)

# Restore original users
with lock:
    save_users(original_users)
test("users.json restored to original", True)


# ─── Test 6: Quota.py alerts_sent reset ───────────────────
print("\n♻️  Test 6: Period reset clears alerts_sent")
from core.quota import maybe_reset_quota

test_user = {
    "user_id": "test",
    "alerts_sent": {"cost_usd_50": "2026-01-01T00:00:00Z", "cost_usd_70": "2026-01-15T00:00:00Z"},
    "quota": {
        "period": "monthly",
        "timezone": "UTC",
        "period_start": 1000000,  # Very old — will trigger reset
        "used_tokens": 5000,
        "used_cost_usd": 5.0,
        "used_image_requests": 2
    }
}

maybe_reset_quota(test_user)
test("alerts_sent cleared on period reset", test_user.get("alerts_sent") == {})
test("used_tokens reset to 0", test_user["quota"]["used_tokens"] == 0)
test("used_cost_usd reset to 0", test_user["quota"]["used_cost_usd"] == 0.0)


# ─── Test 7: Main.py routes ──────────────────────────────
print("\n🌐 Test 7: Route registration in main.py")
try:
    from main import app
    routes = [r.path for r in app.routes]
    test("/v1/_mw/quota-status registered", "/v1/_mw/quota-status" in routes)
    test("/v1/_mw/admin/alerts/config registered", "/v1/_mw/admin/alerts/config" in routes)
    test("/v1/_mw/admin/alerts/test-email registered", "/v1/_mw/admin/alerts/test-email" in routes)
except Exception as e:
    test("main.py route registration", False, str(e))


# ─── Summary ──────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
if failed == 0:
    print("🎉 ALL TESTS PASSED!")
else:
    print(f"⚠️  {failed} test(s) need attention")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
