"""Controlled integration tests for unified Open WebUI and middleware identity."""

import asyncio
import os
import uuid

from fastapi import HTTPException

from config import DATABASE_URL, OPENWEBUI_SERVICE_KEY
from core.auth import (
    create_user_record,
    delete_user,
    get_user_by_id,
    require_user,
    update_user_quota,
    update_user_admin_fields,
)
from core.db import init_pool
import core.identity as identity
from core.identity import build_reconciliation_report, set_user_mapping
from api.quota_status import get_quota_status


class FakeRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}
        self.cookies = {}
        self.state = type("State", (), {})()
        self.client = type("Client", (), {"host": "test"})()
        self.url = type("URL", (), {"path": "/v1/_mw/quota-status"})()


def main():
    init_pool(DATABASE_URL)
    suffix = uuid.uuid4().hex[:8]
    user_id = f"identity-test-{suffix}"
    openwebui_user_id = str(uuid.uuid4())
    subkey = f"test-subkey-{suffix}"
    try:
        before = build_reconciliation_report()
        created = create_user_record({
            "user_id": user_id,
            "role": "admin",
            "openwebui_user_id": openwebui_user_id,
            "subkey": subkey,
            "active": True,
            "allowed_models": ["*"],
            "quota": {"limit_cost_usd": 10, "used_cost_usd": 0},
        })
        assert created["role"] == "admin"
        assert created["openwebui_user_id"] == openwebui_user_id
        assert get_user_by_id(user_id)["role"] == "admin"

        direct = require_user(FakeRequest({"Authorization": f"Bearer {subkey}"}))
        assert direct["user_id"] == user_id

        service_request = FakeRequest({
            "Authorization": f"Bearer {OPENWEBUI_SERVICE_KEY}",
            "X-OpenWebUI-User-Id": openwebui_user_id,
        })
        mapped = require_user(service_request)
        assert mapped["user_id"] == user_id
        assert service_request.state.mw_auth_source == "openwebui_service"

        duplicate_user_id = f"{user_id}-duplicate"
        create_user_record({"user_id": duplicate_user_id, "active": True, "quota": {}})
        original_load_openwebui_users = identity.load_openwebui_users
        identity.load_openwebui_users = lambda: [{
            "id": openwebui_user_id,
            "name": "identity-test",
            "email": "identity-test@example.com",
            "role": "user",
        }]
        try:
            set_user_mapping(duplicate_user_id, openwebui_user_id)
            raise AssertionError("duplicate Open WebUI mapping was not rejected")
        except ValueError as exc:
            assert user_id in str(exc)
        finally:
            identity.load_openwebui_users = original_load_openwebui_users
            delete_user(duplicate_user_id)

        forged = FakeRequest({
            "Authorization": f"Bearer {subkey}",
            "X-OpenWebUI-User-Id": openwebui_user_id,
        })
        assert require_user(forged)["user_id"] == user_id
        assert forged.state.mw_auth_source == "direct_subkey"

        before_usage = get_user_by_id(user_id)["quota"].get("used_cost_usd", 0)
        update_user_quota(direct["user_id"], add_cost_usd=0.001)
        update_user_quota(mapped["user_id"], add_cost_usd=0.001)
        after_usage = get_user_by_id(user_id)["quota"].get("used_cost_usd", 0)
        assert abs(after_usage - before_usage - 0.002) < 1e-9

        own = asyncio.run(get_quota_status(
            FakeRequest({"Authorization": f"Bearer {subkey}"}), user_id=None
        ))
        assert own.status_code == 200
        try:
            asyncio.run(get_quota_status(
                FakeRequest({"Authorization": f"Bearer {subkey}"}), user_id="adminrd"
            ))
            raise AssertionError("cross-user quota lookup was not rejected")
        except HTTPException as exc:
            assert exc.status_code == 403

        update_user_admin_fields(user_id, role="user")
        assert get_user_by_id(user_id)["role"] == "user"
        after = build_reconciliation_report()
        assert len(after["unmatched_openwebui"]) == len(before["unmatched_openwebui"])
        print("unified identity integration test: OK")
    finally:
        delete_user(user_id)


if __name__ == "__main__":
    main()
