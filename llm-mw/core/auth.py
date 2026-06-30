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

from config import USERS_FILE, MW_SECRET, logger

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
    from core.db import db_conn
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, subkey, subkey_hash, active, allowed_models,
                   used_tokens, used_cost_usd, quota, alerts_sent
            FROM mw_users
        """)
        rows = cur.fetchall()
        cur.close()

    users = []
    for row in rows:
        user = {
            "user_id": row[0],
            "subkey": row[1],
            "subkey_hash": row[2],
            "active": row[3],
            "allowed_models": row[4] if row[4] else ["*"],
            "used_tokens": row[5] or 0,
            "used_cost_usd": row[6] or 0.0,
            "quota": row[7] if row[7] else {},
            "alerts_sent": row[8] if row[8] else {},
        }
        users.append(user)
    return users


def _save_users_db(users: List[Dict[str, Any]]):
    """Save all users to mw_users table (upsert each user)."""
    from core.db import db_conn
    with db_conn() as conn:
        cur = conn.cursor()
        for u in users:
            cur.execute("""
                INSERT INTO mw_users
                    (user_id, subkey, subkey_hash, active, allowed_models,
                     used_tokens, used_cost_usd, quota, alerts_sent, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (user_id) DO UPDATE SET
                    subkey = EXCLUDED.subkey,
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
                u.get("subkey"),
                u.get("subkey_hash"),
                u.get("active", True),
                json.dumps(u.get("allowed_models", ["*"])),
                u.get("used_tokens", 0),
                u.get("used_cost_usd", 0.0),
                json.dumps(u.get("quota", {})),
                json.dumps(u.get("alerts_sent", {})),
            ))
        cur.close()


def _find_user_db(subkey: str) -> Optional[Dict[str, Any]]:
    """Find user by subkey hash or plaintext subkey in DB."""
    subkey_hash_val = hash_subkey(subkey)
    from core.db import db_conn
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, subkey, subkey_hash, active, allowed_models,
                   used_tokens, used_cost_usd, quota, alerts_sent
            FROM mw_users
            WHERE subkey_hash = %s OR subkey = %s
            LIMIT 1
        """, (subkey_hash_val, subkey))
        row = cur.fetchone()
        cur.close()

    if not row:
        return None

    return {
        "user_id": row[0],
        "subkey": row[1],
        "subkey_hash": row[2],
        "active": row[3],
        "allowed_models": row[4] if row[4] else ["*"],
        "used_tokens": row[5] or 0,
        "used_cost_usd": row[6] or 0.0,
        "quota": row[7] if row[7] else {},
        "alerts_sent": row[8] if row[8] else {},
    }


# ─── File-backed implementations (fallback) ──────────────────

def _load_users_file() -> List[Dict[str, Any]]:
    """Load users from users.json file."""
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def _save_users_file(users: List[Dict[str, Any]]):
    """Save users to users.json file."""
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def _find_user_file(subkey: str) -> Optional[Dict[str, Any]]:
    """Find user by subkey in JSON file."""
    subkey_hash_val = hash_subkey(subkey)
    for u in _load_users_file():
        if u.get("subkey_hash") == subkey_hash_val:
            return u
        if u.get("subkey") == subkey:
            return u
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


def _delete_user_db(user_id: str) -> bool:
    """Delete a user from mw_users table. Returns True if deleted."""
    from core.db import db_conn
    with db_conn() as conn:
        cur = conn.cursor()
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
    from config import logger

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
    user = find_user(subkey)

    if not user:
        # Log first 8 chars of hashed subkey for debugging (safe to log)
        hashed_prefix = hash_subkey(subkey)[:8]
        logger.warning(
            "auth_fail reason=invalid_subkey hash_prefix=%s path=%s client_ip=%s",
            hashed_prefix, req_path, client_ip,
        )
        raise HTTPException(401, "Invalid sub-key")

    # Sync block: check if user has been deactivated/banned in Open WebUI
    if _db_available() and user.get("user_id"):
        from core.db import db_ow_conn, db_conn
        try:
            with db_ow_conn() as conn:
                cur = conn.cursor()
                cur.execute('SELECT role FROM "user" WHERE email = %s LIMIT 1', (user["user_id"],))
                row = cur.fetchone()
                cur.close()
            if row:
                role = row[0]
                if role not in ("user", "admin"):
                    # User is banned/pending in Open WebUI! Invalidate Middleware DB state.
                    with db_conn() as conn:
                        cur = conn.cursor()
                        cur.execute("UPDATE mw_users SET active = false, updated_at = now() WHERE user_id = %s", (user["user_id"],))
                        cur.close()
                    # Also update JSON backup
                    try:
                        users = _load_users_file()
                        for u in users:
                            if u.get("user_id") == user["user_id"]:
                                u["active"] = False
                                break
                        _save_users_file(users)
                    except Exception:
                        pass
                    # Update local state
                    user["active"] = False
                    logger.info("auth: user %s has been deactivated due to role change in Open WebUI (role=%s)", user["user_id"], role)
        except Exception as e:
            logger.warning("auth: failed to verify Open WebUI active status for user %s: %s", user["user_id"], str(e))

    if not user.get("active", True):
        logger.warning(
            "auth_fail reason=user_inactive user_id=%s path=%s client_ip=%s",
            user.get("user_id"), req_path, client_ip,
        )
        raise HTTPException(403, "User account is deactivated")

    request.state.mw_user_id = user.get("user_id")
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

def lazy_provision_user(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Check if user exists and is active in Open WebUI database, and if so,
    automatically provision them in the Middleware database with default quota.
    Safe against race conditions using _lock.
    """
    from core.db import db_ow_conn, db_conn, _ow_pool
    from datetime import datetime, timezone
    import secrets

    # Check if DB is available (required for cross-DB sync)
    if _ow_pool is None:
        return None

    # Step 1: Check if user exists and is active (role is 'user' or 'admin') in Open WebUI
    role, name = None, None
    try:
        with db_ow_conn() as conn:
            cur = conn.cursor()
            cur.execute('SELECT role, name FROM "user" WHERE email = %s LIMIT 1', (user_id,))
            row = cur.fetchone()
            cur.close()
            if row:
                role, name = row[0], row[1]
    except Exception as e:
        logger.error("lazy_provision: failed to check Open WebUI DB for user %s: %s", user_id, str(e))
        return None

    if not role or role not in ("user", "admin"):
        logger.info("lazy_provision: user %s not found or not active in Open WebUI (role=%s)", user_id, role)
        return None

    # Step 2: Use lock to serialize insertion and avoid duplicate keys
    with _lock:
        # Check if user was provisioned by another thread in the meantime
        from core.db import get_user_by_id_db
        existing = get_user_by_id_db(user_id)
        if existing:
            return existing

        # Generate new subkey and hash
        subkey = f"sk_{secrets.token_urlsafe(32)}"
        subkey_hash = hash_subkey(subkey)

        # Set default quota
        quota = {
            "period": "monthly",
            "timezone": "Asia/Bangkok",
            "limit_tokens": 0,
            "limit_cost_usd": 2.0,
            "limit_image_requests": 0,
            "period_start": int(datetime.now(timezone.utc).timestamp() * 1000),
            "used_tokens": 0,
            "used_cost_usd": 0.0,
            "used_image_requests": 0
        }

        try:
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO mw_users (user_id, subkey, subkey_hash, active, allowed_models, quota)
                    VALUES (%s, %s, %s, true, '["*"]'::jsonb, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        subkey = COALESCE(mw_users.subkey, EXCLUDED.subkey),
                        subkey_hash = COALESCE(mw_users.subkey_hash, EXCLUDED.subkey_hash),
                        active = true
                    RETURNING user_id, subkey, subkey_hash, active, allowed_models, quota
                """, (user_id, subkey, subkey_hash, json.dumps(quota)))
                row = cur.fetchone()
                cur.close()
                
            if row:
                logger.info("lazy_provision: successfully provisioned user %s", user_id)
                # Also save to JSON file backup
                try:
                    users = _load_users_file()
                    if not any(u.get("user_id") == user_id for u in users):
                        new_user = {
                            "user_id": user_id,
                            "role": "user",
                            "subkey": subkey,
                            "subkey_hash": subkey_hash,
                            "active": True,
                            "allowed_models": ["*"],
                            "used_tokens": 0,
                            "used_cost_usd": 0.0,
                            "quota": quota
                        }
                        users.append(new_user)
                        _save_users_file(users)
                except Exception as fe:
                    logger.warning("lazy_provision: failed to update JSON backup for user %s: %s", user_id, str(fe))

                return {
                    "user_id": row[0],
                    "subkey": row[1],
                    "subkey_hash": row[2],
                    "active": row[3],
                    "allowed_models": row[4] if row[4] else ["*"],
                    "used_tokens": 0,
                    "used_cost_usd": 0.0,
                    "quota": row[5] if row[5] else {},
                    "alerts_sent": {}
                }
        except Exception as e:
            logger.error("lazy_provision: failed to insert user %s: %s", user_id, str(e))
            return None

    return None


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a single user by user_id. O(1) indexed query.
    Uses DB if available, falls back to JSON file linear search.
    If not found and database is available, attempts Lazy Provisioning.
    """
    if _db_available():
        from core.db import get_user_by_id_db
        user = get_user_by_id_db(user_id)
        if user:
            return user
        
        # Lazy provision if email contains '@'
        if "@" in user_id:
            user = lazy_provision_user(user_id)
            if user:
                return user
    else:
        # File fallback: linear search (unavoidable without index)
        for u in _load_users_file():
            if u.get("user_id") == user_id:
                return u
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
    Updates DB (atomic SQL) + JSON file backup.
    Returns True if user was found and updated.
    """
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
    # Always update JSON file backup
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
    return updated


def update_user_alerts(user_id: str, alerts_sent: dict) -> bool:
    """
    Update alerts_sent field for a single user. O(1).
    Updates DB + JSON file backup.
    Returns True if user was found and updated.
    """
    updated = False
    if _db_available():
        from core.db import update_user_alerts_db
        updated = update_user_alerts_db(user_id, alerts_sent)
    # Always update JSON file backup
    _update_user_in_file(user_id, {"alerts_sent": alerts_sent})
    return updated
