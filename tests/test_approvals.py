"""
Tests for Human-in-the-loop tool approval database operations and API endpoints.
Can be executed inside the middleware app container.
"""

import os
import sys
import unittest
from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "llm-mw"))

# Setup environment variables for testing database
os.environ["DATABASE_URL"] = os.getenv("DATABASE_URL", "postgresql://openwebui_user:YOUR_DB_PASSWORD@postgres:5432/middleware")
os.environ["SUBKEY_ADMIN"] = os.getenv("SUBKEY_ADMIN", "YOUR_SUBKEY_ADMIN")

from core.db import (
    init_pool, save_tool_approval_db, get_tool_approval_db, 
    update_tool_approval_status_db, db_conn
)
from main import app


class ToolApprovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize database pool
        init_pool(os.environ["DATABASE_URL"])
        cls.client = TestClient(app)

    def setUp(self):
        # Clean up any leftover test approvals
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM mw_tool_approvals WHERE id LIKE 'test_%'")
            cur.close()

    def tearDown(self):
        # Clean up after test
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM mw_tool_approvals WHERE id LIKE 'test_%'")
            cur.close()

    def test_database_helpers(self):
        approval_id = "test_action_001"
        user_id = "user_test_123"
        tool_name = "test_tool"
        payload = {"param1": "value1", "param2": 42}

        # 1. Save approval
        success = save_tool_approval_db(approval_id, user_id, tool_name, payload)
        self.assertTrue(success)

        # 2. Get approval details
        details = get_tool_approval_db(approval_id)
        self.assertIsNotNone(details)
        self.assertEqual(details["id"], approval_id)
        self.assertEqual(details["user_id"], user_id)
        self.assertEqual(details["tool_name"], tool_name)
        self.assertEqual(details["status"], "pending")
        self.assertEqual(details["payload"], payload)

        # 3. Update status
        success = update_tool_approval_status_db(approval_id, "approved")
        self.assertTrue(success)

        # Verify status update
        details = get_tool_approval_db(approval_id)
        self.assertEqual(details["status"], "approved")

    def test_api_endpoints(self):
        approval_id = "test_api_action_001"
        user_id = "user_api_123"
        tool_name = "api_test_tool"
        payload = {"email": "test@example.com"}

        headers = {"Authorization": "Bearer YOUR_SUBKEY_ADMIN"}

        # 1. POST /v1/_mw/approvals
        resp = self.client.post(
            "/v1/_mw/approvals",
            headers=headers,
            json={
                "id": approval_id,
                "tool_name": tool_name,
                "user_id": user_id,
                "payload": payload
            }
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "success")

        # 2. GET /v1/_mw/approvals/{approval_id}
        resp = self.client.get(
            f"/v1/_mw/approvals/{approval_id}",
            headers=headers
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], approval_id)
        self.assertEqual(data["status"], "pending")

        # 3. POST /v1/_mw/approvals/{approval_id}/status (reject)
        resp = self.client.post(
            f"/v1/_mw/approvals/{approval_id}/status",
            headers=headers,
            json={"status": "rejected"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["new_status"], "rejected")

        # Verify reject status
        resp = self.client.get(
            f"/v1/_mw/approvals/{approval_id}",
            headers=headers
        )
        self.assertEqual(resp.json()["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
