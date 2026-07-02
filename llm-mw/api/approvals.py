"""
API endpoints for managing Human-in-the-loop tool approvals.
Supports registering pending actions, reading approval status, and updating status.
"""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional

from core.auth import require_user
from core.db import save_tool_approval_db, get_tool_approval_db, update_tool_approval_status_db

router = APIRouter(prefix="/_mw/approvals", tags=["Tool Approvals"])


class ApprovalCreate(BaseModel):
    id: str
    tool_name: str
    user_id: str
    payload: Dict[str, Any]


class StatusUpdate(BaseModel):
    status: str


@router.post("")
def create_approval(approval: ApprovalCreate, request: Request):
    """
    Register a new pending tool approval request.
    Requires a valid subkey or auth token.
    """
    require_user(request)
    success = save_tool_approval_db(
        approval_id=approval.id,
        user_id=approval.user_id,
        tool_name=approval.tool_name,
        payload=approval.payload
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save approval request to database")
    return {"status": "success", "id": approval.id}


@router.get("/{approval_id}")
def get_approval(approval_id: str, request: Request):
    """
    Retrieve status and payload of a registered tool approval.
    """
    require_user(request)
    details = get_tool_approval_db(approval_id)
    if not details:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return details


@router.post("/{approval_id}/status")
def update_approval_status(approval_id: str, status_update: StatusUpdate, request: Request):
    """
    Update status of an approval request (e.g. approve/reject).
    """
    require_user(request)
    status = status_update.status.lower()
    if status not in ["approved", "rejected", "pending"]:
        raise HTTPException(status_code=400, detail="Invalid status value. Must be 'approved', 'rejected', or 'pending'")
    success = update_tool_approval_status_db(approval_id, status)
    if not success:
        raise HTTPException(status_code=404, detail="Approval request not found or could not be updated")
    return {"status": "success", "id": approval_id, "new_status": status}
