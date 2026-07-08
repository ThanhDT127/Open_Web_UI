"""Open WebUI identity reconciliation and explicit mapping operations."""

from typing import Any, Dict, List
from urllib.parse import urlparse

import psycopg2

from config import DATABASE_URL
from core.auth import get_user_by_openwebui_id, load_users, update_user_admin_fields


def _openwebui_database_url() -> str:
    parsed = urlparse(DATABASE_URL)
    return DATABASE_URL.replace(parsed.path, "/openwebui")


def load_openwebui_users() -> List[Dict[str, Any]]:
    """Read the minimum identity fields from Open WebUI without modifying them."""
    conn = psycopg2.connect(_openwebui_database_url(), connect_timeout=5)
    try:
        cur = conn.cursor()
        cur.execute('SELECT id, name, email, role FROM "user" ORDER BY email')
        rows = cur.fetchall()
        cur.close()
        return [{"id": r[0], "name": r[1], "email": r[2], "role": r[3]} for r in rows]
    finally:
        conn.close()


def build_reconciliation_report() -> Dict[str, Any]:
    """Classify identity records without creating, merging, disabling, or deleting."""
    openwebui_users = load_openwebui_users()
    middleware_users = load_users()
    by_uuid = {u.get("openwebui_user_id"): u for u in middleware_users if u.get("openwebui_user_id")}
    candidates = {}
    for middleware_user in middleware_users:
        for value in (middleware_user.get("user_id"),):
            if value:
                candidates.setdefault(value.lower(), []).append(middleware_user)

    matched, unmatched_openwebui, conflicts, disabled, pending = [], [], [], [], []
    matched_middleware_ids = set()
    for ow_user in openwebui_users:
        mapped = by_uuid.get(ow_user["id"])
        if mapped:
            item = {"openwebui": ow_user, "middleware": mapped, "match_type": "mapped"}
            matched.append(item)
            matched_middleware_ids.add(mapped["user_id"])
            if not mapped.get("active", True):
                disabled.append(item)
            continue
        if ow_user.get("role") == "pending":
            pending.append({"openwebui": ow_user, "reason": "pending_not_provisioned"})
            continue
        possible = []
        for key in (ow_user.get("email"), ow_user.get("name")):
            possible.extend(candidates.get((key or "").lower(), []))
        possible = list({u["user_id"]: u for u in possible}.values())
        if len(possible) == 1:
            matched.append({"openwebui": ow_user, "middleware": possible[0], "match_type": "suggested"})
            matched_middleware_ids.add(possible[0]["user_id"])
        elif len(possible) > 1:
            conflicts.append({"openwebui": ow_user, "middleware_candidates": possible})
        else:
            unmatched_openwebui.append(ow_user)

    unmatched_middleware = [u for u in middleware_users if u["user_id"] not in matched_middleware_ids]
    duplicate_mappings = [
        {"openwebui_user_id": key, "middleware_users": users}
        for key, users in _group_by_mapping(middleware_users).items() if key and len(users) > 1
    ]
    return {
        "matched": matched,
        "unmatched_openwebui": unmatched_openwebui,
        "unmatched_middleware": unmatched_middleware,
        "conflicts": conflicts,
        "duplicate_mappings": duplicate_mappings,
        "disabled": disabled,
        "pending": pending,
    }


def _group_by_mapping(users):
    grouped = {}
    for user in users:
        grouped.setdefault(user.get("openwebui_user_id"), []).append(user)
    return grouped


def set_user_mapping(middleware_user_id: str, openwebui_user_id: str):
    """Explicitly map an approved Open WebUI user to one middleware user."""
    openwebui_user = next((u for u in load_openwebui_users() if u["id"] == openwebui_user_id), None)
    if not openwebui_user:
        raise ValueError("Open WebUI user not found")
    if openwebui_user.get("role") == "pending":
        raise ValueError("Pending Open WebUI users cannot receive middleware access")
    existing = get_user_by_openwebui_id(openwebui_user_id)
    if existing and existing.get("user_id") != middleware_user_id:
        raise ValueError(
            f"Open WebUI user is already mapped to middleware user {existing['user_id']}"
        )
    return update_user_admin_fields(
        middleware_user_id,
        openwebui_user_id=openwebui_user_id,
        update_openwebui_mapping=True,
    )
