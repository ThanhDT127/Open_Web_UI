"""
User administration API endpoints.
Provides CRUD operations for user management with RBAC, key lifecycle, and audit trail.
"""

import json
import secrets
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import Request, HTTPException
from pydantic import BaseModel

from config import USERS_FILE, MW_SECRET, LOG_DIR, BACKUP_LOG_DIR, logger
from core.auth import (
    load_users, save_users, hash_subkey, find_user,
    delete_user as auth_delete_user, get_user_by_id, update_user_admin_fields,
    create_user_record,
)
from threading import Lock
import os
from logging.handlers import RotatingFileHandler
import logging

# Thread lock for user operations
_user_lock = Lock()

# Admin audit logger
_admin_audit_logger = None


def _get_admin_audit_logger():
    """Get or create admin audit logger"""
    global _admin_audit_logger
    if _admin_audit_logger is None:
        _admin_audit_logger = logging.getLogger("llm_mw_admin_audit")
        if not _admin_audit_logger.handlers:
            _admin_audit_logger.setLevel(logging.INFO)
            audit_file = os.path.join(BACKUP_LOG_DIR, "admin_audit.jsonl")
            handler = RotatingFileHandler(
                audit_file, maxBytes=20_000_000, backupCount=5, encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            _admin_audit_logger.addHandler(handler)
    return _admin_audit_logger


def _write_admin_audit(actor: str, action: str, target_user: str, changes: Dict, status: str, request: Request):
    """Write admin audit trail entry"""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "target_user": target_user,
        "changes": changes,
        "status": status,
        "ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown")
    }
    _get_admin_audit_logger().info(json.dumps(entry, ensure_ascii=False))


def _generate_subkey() -> str:
    """Generate a secure random subkey"""
    return f"sk_{secrets.token_urlsafe(32)}"


def _scrub_user(user: Dict[str, Any]) -> Dict[str, Any]:
    """Remove sensitive fields from user dict for API responses.
    Keeps subkey_hash (safe for admin view), removes plaintext subkey."""
    scrubbed = user.copy()
    # Remove plaintext key only — hash is safe for admin dashboard
    scrubbed.pop("subkey", None)
    return scrubbed


# Request/Response models
class CreateUserRequest(BaseModel):
    user_id: str
    role: str = "user"  # admin | user
    allowed_models: Optional[List[str]] = None
    limit_tokens: int = 0  # 0 = unlimited
    limit_cost_usd: float = 0.0
    limit_image_requests: int = 0
    period: str = "monthly"
    timezone: str = "Asia/Bangkok"


class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    active: Optional[bool] = None
    allowed_models: Optional[List[str]] = None
    limit_tokens: Optional[int] = None
    limit_cost_usd: Optional[float] = None
    limit_image_requests: Optional[int] = None


class MapOpenWebUIUserRequest(BaseModel):
    openwebui_user_id: Optional[str] = None


# ============================================================================
# API ENDPOINTS
# ============================================================================

def list_users(request: Request):
    """
    GET /v1/_mw/admin/users
    List all users (scrubbed - no keys/hashes)
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)
    
    users = load_users()
    scrubbed_users = [_scrub_user(u) for u in users]
    
    return {
        "users": scrubbed_users,
        "total": len(scrubbed_users)
    }


async def create_user(request: Request):
    """
    POST /v1/_mw/admin/users
    Create new user with generated subkey (returned once)
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)
    
    try:
        body = await request.json()
        req = CreateUserRequest(**body)
    except Exception as e:
        raise HTTPException(400, f"Invalid request: {e}")
    
    # Validate role
    if req.role not in ["admin", "user"]:
        raise HTTPException(400, "Invalid role. Must be: admin or user")
    
    with _user_lock:
        # Generate subkey
        subkey = _generate_subkey()
        subkey_hash = hash_subkey(subkey)
        
        from config import DEFAULT_ALLOWED_MODELS
        allowed = req.allowed_models
        if not allowed:
            allowed = DEFAULT_ALLOWED_MODELS

        # Create user object (do NOT save raw subkey in DB/JSON)
        new_user = {
            "user_id": req.user_id,
            "role": req.role,
            "subkey_hash": subkey_hash,
            "active": True,
            "allowed_models": allowed,
            "used_tokens": 0,
            "used_cost_usd": 0.0,
            "quota": {
                "period": req.period,
                "timezone": req.timezone,
                "limit_tokens": req.limit_tokens,
                "limit_cost_usd": req.limit_cost_usd,
                "limit_image_requests": req.limit_image_requests,
                "period_start": int(datetime.now(timezone.utc).timestamp() * 1000),
                "used_tokens": 0,
                "used_cost_usd": 0.0,
                "used_image_requests": 0
            }
        }
        
        committed_user = create_user_record(new_user)
        if not committed_user:
            raise HTTPException(409, f"User {req.user_id} already exists")
        
        # Audit trail
        _write_admin_audit(
            actor="admin_session",
            action="create_user",
            target_user=req.user_id,
            changes={"role": req.role, "allowed_models": req.allowed_models},
            status="ok",
            request=request
        )
        
        logger.info(f"Created user: {req.user_id} (role={req.role})")
        
        return {
            "message": "User created successfully",
            "user": _scrub_user(committed_user),
            "subkey": subkey,  # ⚠️ Only returned once!
            "warning": "Save this subkey securely. It will not be shown again."
        }


async def update_user(request: Request, user_id: str):
    """
    PATCH /v1/_mw/admin/users/{user_id}
    Update user role, active status, allowed models, or quota limits
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)
    
    try:
        body = await request.json()
        req = UpdateUserRequest(**body)
    except Exception as e:
        raise HTTPException(400, f"Invalid request: {e}")

    if req.role is not None and req.role not in ["admin", "user"]:
        raise HTTPException(400, "Invalid role")

    quota_limits = {
        key: value for key, value in {
            "limit_tokens": req.limit_tokens,
            "limit_cost_usd": req.limit_cost_usd,
            "limit_image_requests": req.limit_image_requests,
        }.items() if value is not None
    }
    changes = {}
    if req.role is not None:
        changes["role"] = req.role
    if req.active is not None:
        changes["active"] = req.active
    if req.allowed_models is not None:
        changes["allowed_models"] = req.allowed_models
    changes.update(quota_limits)

    if not changes:
        return {"message": "No changes provided"}

    committed_user = update_user_admin_fields(
        user_id,
        active=req.active,
        allowed_models=req.allowed_models,
        quota_limits=quota_limits,
        role=req.role,
    )
    if not committed_user:
        raise HTTPException(404, f"User {user_id} not found")
    _write_admin_audit(
        actor="admin_session", action="update_user", target_user=user_id,
        changes=changes, status="ok", request=request,
    )
    logger.info("Updated user with targeted write: %s - %s", user_id, changes)
    return {
        "message": "User updated successfully",
        "user": _scrub_user(committed_user),
        "changes": changes,
    }


def reconciliation_report(request: Request):
    """Return a read-only identity reconciliation report."""
    from utils.auth_guard import require_admin_or_session
    from core.identity import build_reconciliation_report
    require_admin_or_session(request)
    return build_reconciliation_report()


async def map_openwebui_user(request: Request, user_id: str):
    """Explicitly confirm, change, or clear an Open WebUI identity mapping."""
    from utils.auth_guard import require_admin_or_session
    from core.identity import set_user_mapping
    require_admin_or_session(request)
    try:
        req = MapOpenWebUIUserRequest(**(await request.json()))
        if req.openwebui_user_id:
            user = set_user_mapping(user_id, req.openwebui_user_id)
        else:
            user = update_user_admin_fields(
                user_id, openwebui_user_id=None, update_openwebui_mapping=True,
            )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not user:
        raise HTTPException(404, f"User {user_id} not found")
    _write_admin_audit(
        actor="admin_session", action="map_openwebui_user", target_user=user_id,
        changes={"openwebui_user_id": req.openwebui_user_id}, status="ok", request=request,
    )
    return {"message": "Mapping updated", "user": _scrub_user(user)}


async def rotate_user_key(request: Request, user_id: str):
    """
    POST /v1/_mw/admin/users/{user_id}/rotate_key
    Rotate user's subkey (generates new key, invalidates old)
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    new_subkey = _generate_subkey()
    committed_user = update_user_admin_fields(
        user_id, subkey_hash=hash_subkey(new_subkey),
    )
    if not committed_user:
        raise HTTPException(404, f"User {user_id} not found")
    _write_admin_audit(
        actor="admin_session", action="rotate_key", target_user=user_id,
        changes={"key_rotated": True}, status="ok", request=request,
    )
    return {
        "message": "Key rotated successfully",
        "user_id": user_id,
        "subkey": new_subkey,
        "warning": "Save this subkey securely. The old key is now invalid.",
    }


async def disable_user(request: Request, user_id: str):
    """
    POST /v1/_mw/admin/users/{user_id}/disable
    Disable user (sets active=False)
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    user = update_user_admin_fields(user_id, active=False)
    if not user:
        raise HTTPException(404, f"User {user_id} not found")
    _write_admin_audit(
        actor="admin_session", action="disable_user", target_user=user_id,
        changes={"active": False}, status="ok", request=request,
    )
    return {"message": f"User {user_id} disabled successfully", "user": _scrub_user(user)}


async def enable_user(request: Request, user_id: str):
    """
    POST /v1/_mw/admin/users/{user_id}/enable
    Enable user (sets active=True)
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    user = update_user_admin_fields(user_id, active=True)
    if not user:
        raise HTTPException(404, f"User {user_id} not found")
    _write_admin_audit(
        actor="admin_session", action="enable_user", target_user=user_id,
        changes={"active": True}, status="ok", request=request,
    )
    return {"message": f"User {user_id} enabled successfully", "user": _scrub_user(user)}


async def delete_user_endpoint(request: Request, user_id: str):
    """
    DELETE /v1/_mw/admin/users/{user_id}
    Permanently delete a user
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)
    
    with _user_lock:
        users = load_users()
        
        # Check user exists
        user = next((u for u in users if u["user_id"] == user_id), None)
        if not user:
            raise HTTPException(404, f"User {user_id} not found")
        
        # Prevent self-deletion
        if hasattr(request.state, 'mw_user_id') and request.state.mw_user_id == user_id:
            raise HTTPException(400, "Cannot delete yourself")
        
        # Delete from DB + JSON
        deleted = auth_delete_user(user_id)
        if not deleted:
            raise HTTPException(500, f"Failed to delete user {user_id}")
        
        # Audit trail
        _write_admin_audit(
            actor="admin_session",
            action="delete_user",
            target_user=user_id,
            changes={"deleted": True, "role": user.get("role"), "active": user.get("active")},
            status="ok",
            request=request
        )
        
        logger.info(f"Deleted user: {user_id}")
        
        return {
            "message": f"User {user_id} deleted permanently",
            "user_id": user_id
        }


def get_admin_audit(
    request: Request,
    minutes: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None
):
    """
    GET /v1/_mw/admin/audit
    Get admin audit trail
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)
    
    audit_file = os.path.join(BACKUP_LOG_DIR, "admin_audit.jsonl")
    
    if not os.path.exists(audit_file):
        return {"audit_trail": [], "total": 0}
    
    # Determine time range
    now_utc = datetime.now(timezone.utc)
    
    if start and end:
        try:
            cutoff = datetime.fromisoformat(start)
            end_time = datetime.fromisoformat(end)
        except ValueError as e:
            raise HTTPException(400, f"Invalid datetime format: {e}")
    else:
        if minutes is None:
            minutes = 1440  # Default: last 24 hours
        cutoff = now_utc - __import__('datetime').timedelta(minutes=minutes)
        end_time = now_utc
    
    # Read audit log
    entries = []
    try:
        with open(audit_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    entry_time = datetime.fromisoformat(entry.get("ts", ""))
                    
                    if cutoff <= entry_time <= end_time:
                        entries.append(entry)
                except Exception:
                    continue
    except Exception as e:
        return {"error": str(e)}
    
    # Sort by timestamp descending (newest first)
    entries.sort(key=lambda x: x.get("ts", ""), reverse=True)
    
    return {
        "audit_trail": entries[:100],  # Last 100 events
        "total": len(entries)
    }


def get_users_sync_status(request: Request):
    """
    GET /v1/_mw/admin/users/sync-status
    Retrieve user sync status comparing Open WebUI and Middleware database.
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    from core.auth import _db_available
    if not _db_available():
        raise HTTPException(400, "Database connection not available (running in file-only mode)")

    from core.db import db_ow_conn, db_conn

    # 1. Query Open WebUI users
    ow_users = []
    try:
        with db_ow_conn() as conn:
            cur = conn.cursor()
            cur.execute('SELECT email, name, role FROM "user"')
            rows = cur.fetchall()
            for r in rows:
                ow_users.append({
                    "email": r[0],
                    "name": r[1],
                    "role": r[2]
                })
            cur.close()
    except Exception as e:
        logger.error("get_users_sync_status: failed to query Open WebUI: %s", str(e))
        raise HTTPException(500, f"Failed to query Open WebUI database: {str(e)}")

    # 2. Query Middleware users
    mw_users_list = []
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, active, subkey FROM mw_users")
            rows = cur.fetchall()
            for r in rows:
                mw_users_list.append({
                    "user_id": r[0],
                    "active": r[1],
                    "subkey": r[2]
                })
            cur.close()
    except Exception as e:
        logger.error("get_users_sync_status: failed to query Middleware: %s", str(e))
        raise HTTPException(500, f"Failed to query Middleware database: {str(e)}")

    # 3. Match and calculate sync status
    ow_map = {u["email"]: u for u in ow_users}
    mw_map = {u["user_id"]: u for u in mw_users_list}

    all_emails = set(ow_map.keys()).union(mw_map.keys())

    sync_list = []
    for email in all_emails:
        ow_u = ow_map.get(email)
        mw_u = mw_map.get(email)

        name = ow_u["name"] if ow_u else email.split("@")[0]
        ow_role = ow_u["role"] if ow_u else None
        mw_active = mw_u["active"] if mw_u else None
        subkey = mw_u["subkey"] if mw_u else None

        if ow_u and not mw_u:
            if ow_role in ("user", "admin"):
                status = "pending_sync"
            else:
                status = "pending_ow_approval"
        elif not ow_u and mw_u:
            status = "orphan_middleware"
        else:
            # Exists in both
            ow_is_active = (ow_role in ("user", "admin"))
            if ow_is_active == mw_active:
                status = "synced"
            else:
                status = "mismatch"

        sync_list.append({
            "email": email,
            "name": name,
            "ow_role": ow_role,
            "mw_active": mw_active,
            "subkey": subkey,
            "status": status
        })

    # Sort: mismatch and orphan first, then pending_sync, then synced
    sync_list.sort(key=lambda x: (
        0 if x["status"] in ("mismatch", "orphan_middleware") else 1 if x["status"] == "pending_sync" else 2,
        x["email"]
    ))

    return {"users": sync_list}


async def sync_user_now(request: Request):
    """
    POST /v1/_mw/admin/users/sync-now
    Force synchronization of a specific user.
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    try:
        body = await request.json()
        user_id = body.get("user_id")
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    if not user_id:
        raise HTTPException(400, "user_id is required")

    from core.auth import lazy_provision_user, _db_available
    if not _db_available():
        raise HTTPException(400, "Database connection not available")

    from core.db import db_conn, db_ow_conn

    # Check if user exists in Open WebUI
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
        raise HTTPException(500, f"Open WebUI DB error: {str(e)}")

    if not role:
        raise HTTPException(404, f"User {user_id} not found in Open WebUI")

    # Audit log changes
    changes = {}

    if role in ("user", "admin"):
        # Provision/Activate
        user = lazy_provision_user(user_id)
        if not user:
            # If already exists, make sure it is activated
            try:
                with db_conn() as conn:
                    cur = conn.cursor()
                    cur.execute("UPDATE mw_users SET active = true, updated_at = now() WHERE user_id = %s", (user_id,))
                    cur.close()
                changes["active"] = True
            except Exception as e:
                raise HTTPException(500, f"Failed to activate user: {str(e)}")
        else:
            changes["provisioned"] = True
            changes["active"] = True
    else:
        # Banned/pending in Open WebUI, force deactivate in Middleware
        try:
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute("UPDATE mw_users SET active = false, updated_at = now() WHERE user_id = %s", (user_id,))
                cur.close()
            # Sync to JSON backup
            try:
                from core.auth import _load_users_file, _save_users_file
                users = _load_users_file()
                for u in users:
                    if u.get("user_id") == user_id:
                        u["active"] = False
                        break
                _save_users_file(users)
            except Exception:
                pass
            changes["active"] = False
        except Exception as e:
            raise HTTPException(500, f"Failed to deactivate user: {str(e)}")

    # Audit trail
    _write_admin_audit(
        actor="admin_session",
        action="sync_user",
        target_user=user_id,
        changes=changes,
        status="ok",
        request=request
    )

    return {
        "status": "ok",
        "message": f"Successfully synchronized user {user_id}",
        "changes": changes
    }
