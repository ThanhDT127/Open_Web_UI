"""
Authentication and user management for LLM middleware.
Data stored in PostgreSQL (mw_users table), with JSON file fallback.
"""

import os
import json
import hmac
import hashlib
from typing import Dict, Any, Optional, List
from fastapi import HTTPException, Request
from threading import Lock

from config import USERS_FILE, MW_SECRET

# Thread lock for user operations (backward compat)
_lock = Lock()


def hash_subkey(subkey: str) -> str:
    """
    Generate HMAC-SHA256 hash of subkey using MW_SECRET.
    Returns hex digest for storage/comparison.
    """
    return hmac.new(
        MW_SECRET.encode("utf-8"),
        subkey.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def _db_available() -> bool:
    """Check if database pool is initialized."""
    try:
        from core.db import _pool
        return _pool is not None
    except Exception:
        return False


# ─── DB-backed implementations ───────────────────────────────

def _load_users_db() -> List[Dict[str, Any]]:
    """Load all users from mw_users table, returning same format as JSON."""
    from config import DEFAULT_ALLOWED_MODELS
    from core.db import db_conn
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, role, openwebui_user_id, subkey_hash, active,
                   allowed_models, used_tokens, used_cost_usd, quota, alerts_sent
            FROM mw_users
        """)
        rows = cur.fetchall()
        cur.close()

    users = []
    for row in rows:
        user = {
            "user_id": row[0],
            "role": row[1] or "user",
            "openwebui_user_id": row[2],
            "subkey": None,
            "subkey_hash": row[3],
            "active": row[4],
            "allowed_models": row[5] if row[5] else DEFAULT_ALLOWED_MODELS,
            "used_tokens": row[6] or 0,
            "used_cost_usd": row[7] or 0.0,
            "quota": row[8] if row[8] else {},
            "alerts_sent": row[9] if row[9] else {},
        }
        users.append(user)
    return users


def _save_users_db(users: List[Dict[str, Any]]):
    """Save all users to mw_users table (upsert each user)."""
    from config import DEFAULT_ALLOWED_MODELS
    from core.db import db_conn
    with db_conn() as conn:
        cur = conn.cursor()
        for u in users:
            subkey = u.get("subkey")
            subkey_hash = u.get("subkey_hash")
            if not subkey_hash and subkey:
                subkey_hash = hash_subkey(subkey)

            allowed_models = u.get("allowed_models")
            if not allowed_models:
                allowed_models = DEFAULT_ALLOWED_MODELS

            cur.execute("""
                INSERT INTO mw_users
                    (user_id, role, openwebui_user_id, subkey_hash, active, allowed_models,
                     used_tokens, used_cost_usd, quota, alerts_sent, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (user_id) DO UPDATE SET
                    role = EXCLUDED.role,
                    openwebui_user_id = EXCLUDED.openwebui_user_id,
                    subkey_hash = EXCLUDED.subkey_hash,
                    active = EXCLUDED.active,
                    allowed_models = EXCLUDED.allowed_models,
                    used_tokens = EXCLUDED.used_tokens,
                    used_cost_usd = EXCLUDED.used_cost_usd,
                    quota = EXCLUDED.quota,
                    alerts_sent = EXCLUDED.alerts_sent,
                    updated_at = now()
            """, (
                u.get("user_id"),
                "user" if u.get("role") == "manager" else u.get("role", "user"),
                u.get("openwebui_user_id"),
                subkey_hash,
                u.get("active", True),
                json.dumps(allowed_models),
                u.get("used_tokens", 0),
                u.get("used_cost_usd", 0.0),
                json.dumps(u.get("quota", {})),
                json.dumps(u.get("alerts_sent", {})),
            ))
        cur.close()


def _find_user_db(subkey: str) -> Optional[Dict[str, Any]]:
    """Find user by subkey hash in DB."""
    subkey_hash_val = hash_subkey(subkey)
    from core.db import db_conn
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, role, openwebui_user_id, subkey_hash, active,
                   allowed_models, used_tokens, used_cost_usd, quota, alerts_sent
            FROM mw_users
            WHERE subkey_hash = %s
            LIMIT 1
        """, (subkey_hash_val,))
        row = cur.fetchone()
        cur.close()

    if not row:
        return None

    from config import DEFAULT_ALLOWED_MODELS
    return {
        "user_id": row[0],
        "role": row[1] or "user",
        "openwebui_user_id": row[2],
        "subkey": None,
        "subkey_hash": row[3],
        "active": row[4],
        "allowed_models": row[5] if row[5] else DEFAULT_ALLOWED_MODELS,
        "used_tokens": row[6] or 0,
        "used_cost_usd": row[7] or 0.0,
        "quota": row[8] if row[8] else {},
        "alerts_sent": row[9] if row[9] else {},
    }


# ─── File-backed implementations (fallback) ──────────────────

def _load_users_file() -> List[Dict[str, Any]]:
    """Load users from users.json file."""
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, "r", encoding="utf-8-sig") as f:
        users = json.load(f)
        for user in users:
            if user.get("role") not in ("admin", "user"):
                user["role"] = "user"
        return users


def _save_users_file(users: List[Dict[str, Any]]):
    """Save users to users.json file."""
    for user in users:
        if user.get("role") not in ("admin", "user"):
            user["role"] = "user"
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def _find_user_file(subkey: str) -> Optional[Dict[str, Any]]:
    """Find user by subkey hash in JSON file."""
    subkey_hash_val = hash_subkey(subkey)
    from config import DEFAULT_ALLOWED_MODELS
    users = _load_users_file()
    updated = False
    matched_user = None

    for u in users:
        user_hash = u.get("subkey_hash")
        if user_hash == subkey_hash_val:
            matched_user = u
            break
        elif not user_hash and u.get("subkey") == subkey:
            u["subkey_hash"] = subkey_hash_val
            u["subkey"] = None
            matched_user = u
            updated = True
            break

    if matched_user:
        if not matched_user.get("allowed_models"):
            matched_user["allowed_models"] = DEFAULT_ALLOWED_MODELS
        matched_user["subkey"] = None
        if updated:
            try:
                _save_users_file(users)
            except Exception:
                pass
        return matched_user
    return None


# ─── Public API (auto-selects DB or file) ─────────────────────

def load_users() -> List[Dict[str, Any]]:
    """
    Load users. Uses DB if available, falls back to JSON file.
    """
    if _db_available():
        return _load_users_db()
    return _load_users_file()


def save_users(users: List[Dict[str, Any]]):
    """
    Save users. Writes to DB if available, and always writes to JSON file (backup).
    """
    if _db_available():
        _save_users_db(users)
    # Always write to JSON file as backup
    _save_users_file(users)


def snapshot_users_to_json() -> int:
    """Write an explicit JSON snapshot from the committed runtime source."""
    users = _load_users_db() if _db_available() else _load_users_file()
    _save_users_file(users)
    return len(users)


def create_user_record(user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Create exactly one user without replacing concurrent user state."""
    if _db_available():
        from core.db import create_user_db
        return create_user_db(user)
    with _lock:
        if get_user_by_id(user.get("user_id")):
            return None
        users = _load_users_file()
        users.append(user)
        _save_users_file(users)
        return get_user_by_id(user.get("user_id"))


def _delete_user_db(user_id: str) -> bool:
    """Delete a user from mw_users table. Returns True if deleted."""
    from core.db import db_conn
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM mw_quota_alert_claims WHERE user_id = %s", (user_id,))
        cur.execute("DELETE FROM mw_users WHERE user_id = %s", (user_id,))
        deleted = cur.rowcount > 0
        cur.close()
    return deleted


def delete_user(user_id: str) -> bool:
    """
    Delete user by user_id. Removes from DB + JSON file.
    Returns True if user was found and deleted.
    """
    deleted = False
    if _db_available():
        deleted = _delete_user_db(user_id)
    # Also remove from JSON backup
    users = _load_users_file()
    original_len = len(users)
    users = [u for u in users if u.get("user_id") != user_id]
    if len(users) < original_len:
        _save_users_file(users)
        deleted = True
    return deleted


def find_user(subkey: str) -> Optional[Dict[str, Any]]:
    """
    Find user by subkey. Uses DB if available, falls back to JSON.
    """
    if _db_available():
        return _find_user_db(subkey)
    return _find_user_file(subkey)


def require_user(request: Request) -> Dict[str, Any]:
    """
    Require valid user authentication from Authorization header.
    Raises HTTPException with differentiated error codes:
      - 401: Missing Bearer token
      - 401: Invalid sub-key (not found in DB)
      - 403: User account is deactivated
    """
    from config import logger, OPENWEBUI_SERVICE_KEY

    auth = request.headers.get("Authorization", "")
    client_ip = request.client.host if request.client else "unknown"
    req_path = request.url.path

    if not auth.startswith("Bearer "):
        logger.warning(
            "auth_fail reason=missing_token path=%s client_ip=%s",
            req_path, client_ip,
        )
        raise HTTPException(401, "Missing sub-key")

    subkey = auth.split(" ", 1)[1].strip()
    forwarded_id = request.headers.get("X-OpenWebUI-User-Id", "").strip()
    if forwarded_id and subkey == OPENWEBUI_SERVICE_KEY and OPENWEBUI_SERVICE_KEY:
        user = get_user_by_openwebui_id(forwarded_id)
        auth_source = "openwebui_service"
    else:
        user = find_user(subkey)
        auth_source = "direct_subkey"

    if not user:
        # Log first 8 chars of hashed subkey for debugging (safe to log)
        hashed_prefix = hash_subkey(subkey)[:8]
        logger.warning(
            "auth_fail reason=invalid_subkey hash_prefix=%s path=%s client_ip=%s",
            hashed_prefix, req_path, client_ip,
        )
        raise HTTPException(401, "Invalid sub-key")

    if not user.get("active", True):
        logger.warning(
            "auth_fail reason=user_inactive user_id=%s path=%s client_ip=%s",
            user.get("user_id"), req_path, client_ip,
        )
        raise HTTPException(403, "User account is deactivated")

    request.state.mw_user_id = user.get("user_id")
    request.state.mw_auth_source = auth_source
    request.state.mw_openwebui_user_id = user.get("openwebui_user_id")
    return user


def assert_model_allowed(user: Dict[str, Any], model: str):
    """
    Check if user is allowed to use specified model.
    Auto-model names (e.g. 'openai-auto') are allowed if user has wildcard
    access or access to any model from that provider.
    """
    allowed_models = user.get("allowed_models", [])
    if allowed_models == ["*"]:
        return  # Wildcard: all models allowed

    # If the model itself is explicitly allowed, let it pass
    if model in allowed_models:
        return

    # Auto-model check: allow if user has access to any model in that provider's tiers
    from core.smart_routing import PROVIDER_TIERS
    if model in PROVIDER_TIERS:
        tier_models = set(PROVIDER_TIERS[model].values())
        if any(m in allowed_models for m in tier_models):
            return
        raise HTTPException(403, f"Model '{model}' not allowed for {user['user_id']}")

    if model not in allowed_models:
        raise HTTPException(403, f"Model '{model}' not allowed for {user['user_id']}")


def get_lock() -> Lock:
    """Get the shared thread lock for user operations."""
    return _lock


# ─── Single-user O(1) API ─────────────────────────────────────

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a single user by user_id. O(1) indexed query.
    Uses DB if available, falls back to JSON file linear search.
    """
    if _db_available():
        from core.db import get_user_by_id_db
        return get_user_by_id_db(user_id)
    # File fallback: linear search (unavoidable without index)
    for u in _load_users_file():
        if u.get("user_id") == user_id:
            return u
    return None


def get_user_by_openwebui_id(openwebui_user_id: str) -> Optional[Dict[str, Any]]:
    """Resolve a canonical Open WebUI UUID to its middleware quota record."""
    if _db_available():
        from core.db import get_user_by_openwebui_id_db
        return get_user_by_openwebui_id_db(openwebui_user_id)
    for user in _load_users_file():
        if user.get("openwebui_user_id") == openwebui_user_id:
            return user
    return None


def _update_user_in_file(user_id: str, updates: Dict[str, Any]):
    """
    Update a single user entry in the JSON backup file.
    Reads file → modifies one entry → writes back.
    For quota increments, use keys prefixed with '_add_' (e.g. _add_used_tokens).
    """
    if not os.path.exists(USERS_FILE):
        return
    try:
        with open(USERS_FILE, "r", encoding="utf-8-sig") as f:
            users = json.load(f)

        for u in users:
            if u.get("user_id") != user_id:
                continue
            for key, value in updates.items():
                if key.startswith("_add_"):
                    # Increment mode: _add_used_tokens=500 → used_tokens += 500
                    real_key = key[5:]  # strip '_add_'
                    if "." in real_key:
                        # Nested: _add_quota.used_tokens → quota["used_tokens"] += value
                        parts = real_key.split(".", 1)
                        sub = u.setdefault(parts[0], {})
                        sub[parts[1]] = (sub.get(parts[1]) or 0) + value
                    else:
                        u[real_key] = (u.get(real_key) or 0) + value
                else:
                    # Replace mode
                    if "." in key:
                        parts = key.split(".", 1)
                        sub = u.setdefault(parts[0], {})
                        sub[parts[1]] = value
                    else:
                        u[key] = value
            break

        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
    except Exception:
        pass  # File backup is best-effort


def update_user_quota(
    user_id: str,
    *,
    add_tokens: int = 0,
    add_cost_usd: float = 0.0,
    add_image_requests: int = 0,
    add_stt_requests: int = 0,
) -> bool:
    """
    Atomically increment quota counters for a single user. O(1).
    Updates DB (atomic SQL) + JSON file backup only when DB is not available.
    Returns True if user was found and updated.
    """
    current = get_user_by_id(user_id)
    if not current:
        return False
    quota = current.get("quota", {})
    from core.quota import period_anchor_ms
    reset_user_quota_period(
        user_id,
        period_anchor_ms(quota.get("period", "monthly"), quota.get("timezone", "UTC")),
    )

    updated = False
    if _db_available():
        from core.db import update_user_quota_db
        updated = update_user_quota_db(
            user_id,
            add_tokens=add_tokens,
            add_cost_usd=add_cost_usd,
            add_image_requests=add_image_requests,
            add_stt_requests=add_stt_requests,
        )
    else:
        # Only update JSON file backup when DB is not available
        file_updates = {}
        if add_tokens:
            file_updates["_add_used_tokens"] = add_tokens
            file_updates["_add_quota.used_tokens"] = add_tokens
        if add_cost_usd:
            file_updates["_add_used_cost_usd"] = add_cost_usd
            file_updates["_add_quota.used_cost_usd"] = add_cost_usd
        if add_image_requests:
            file_updates["_add_quota.used_image_requests"] = add_image_requests
        if add_stt_requests:
            file_updates["_add_quota.used_stt_requests"] = add_stt_requests
        if file_updates:
            _update_user_in_file(user_id, file_updates)
        updated = True
    return updated


def update_user_alerts(user_id: str, alerts_sent: dict) -> bool:
    """
    Update alerts_sent field for a single user. O(1).
    Updates DB + JSON file backup only when DB is not available.
    Returns True if user was found and updated.
    """
    updated = False
    if _db_available():
        from core.db import update_user_alerts_db
        updated = update_user_alerts_db(user_id, alerts_sent)
    else:
        # Only update JSON file backup when DB is not available
        _update_user_in_file(user_id, {"alerts_sent": alerts_sent})
        updated = True
    return updated


def reset_user_quota_period(user_id: str, period_start: int) -> Optional[Dict[str, Any]]:
    """Persist a period reset for one user, returning the committed record."""
    if _db_available():
        from core.db import reset_user_quota_period_db
        return reset_user_quota_period_db(user_id, period_start)

    with _lock:
        user = get_user_by_id(user_id)
        if not user:
            return None
        quota = user.setdefault("quota", {})
        if int(quota.get("period_start", 0) or 0) < period_start:
            quota.update({
                "period_start": period_start,
                "used_tokens": 0,
                "used_cost_usd": 0.0,
                "used_image_requests": 0,
                "used_stt_requests": 0,
            })
            user["alerts_sent"] = {}
            _update_user_in_file(user_id, {"quota": quota, "alerts_sent": {}})
        return get_user_by_id(user_id)


def clear_user_quota_usage(user_id: str) -> Optional[Dict[str, Any]]:
    """Explicit admin reset for one user's period counters."""
    if _db_available():
        from core.db import clear_user_quota_usage_db
        return clear_user_quota_usage_db(user_id)
    with _lock:
        user = get_user_by_id(user_id)
        if not user:
            return None
        quota = user.setdefault("quota", {})
        quota.update({
            "used_tokens": 0,
            "used_cost_usd": 0.0,
            "used_image_requests": 0,
            "used_stt_requests": 0,
        })
        _update_user_in_file(user_id, {"quota": quota})
        return get_user_by_id(user_id)


def update_user_admin_fields(
    user_id: str,
    *,
    active=None,
    allowed_models=None,
    quota_limits: Optional[Dict[str, Any]] = None,
    subkey_hash=None,
    role=None,
    openwebui_user_id=None,
    update_openwebui_mapping: bool = False,
) -> Optional[Dict[str, Any]]:
    """Update mutable admin fields without replacing concurrent usage."""
    if _db_available():
        from core.db import update_user_admin_fields_db
        return update_user_admin_fields_db(
            user_id,
            active=active,
            allowed_models=allowed_models,
            quota_limits=quota_limits,
            subkey_hash=subkey_hash,
            role=role,
            openwebui_user_id=openwebui_user_id,
            update_openwebui_mapping=update_openwebui_mapping,
        )

    with _lock:
        user = get_user_by_id(user_id)
        if not user:
            return None
        updates = {}
        if active is not None:
            updates["active"] = active
        if role is not None:
            updates["role"] = role
        if update_openwebui_mapping:
            updates["openwebui_user_id"] = openwebui_user_id
        if allowed_models is not None:
            updates["allowed_models"] = allowed_models
        if subkey_hash is not None:
            updates["subkey_hash"] = subkey_hash
        for key, value in (quota_limits or {}).items():
            updates[f"quota.{key}"] = value
        _update_user_in_file(user_id, updates)
        return get_user_by_id(user_id)


def claim_quota_alert(
    user_id: str,
    period_start: int,
    threshold: int,
    alert_type: str,
    snapshot: Dict[str, Any],
) -> bool:
    """Claim one alert threshold so concurrent requests cannot duplicate it."""
    if _db_available():
        from core.db import claim_quota_alert_db
        return claim_quota_alert_db(user_id, period_start, threshold, alert_type, snapshot)

    with _lock:
        user = get_user_by_id(user_id)
        if not user:
            return False
        alerts = user.setdefault("alerts_sent", {})
        key = f"alert_{threshold}"
        if key in alerts:
            return False
        from datetime import datetime, timezone
        alerts[key] = datetime.now(timezone.utc).isoformat()
        _update_user_in_file(user_id, {"alerts_sent": alerts})
        return True
