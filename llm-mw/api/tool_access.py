"""
Tool access administration API endpoints.
Bật/tắt quyền dùng tool của Open WebUI theo GROUP (phòng ban) và theo USER,
ghi vào bảng `access_grant` — điểm chốt quyền duy nhất mà Open WebUI kiểm lại
ở mỗi lần nạp tool (`utils/tools.py: get_tools`).
"""

from typing import List

from fastapi import HTTPException, Request
from pydantic import BaseModel

from config import logger
from core.tool_access import (
    get_group_tools,
    get_user_tools,
    list_groups,
    list_tools,
    set_group_tools,
    set_user_tools,
)


class SetToolsRequest(BaseModel):
    tool_ids: List[str] = []


def _audit(request: Request, action: str, target: str, changes: dict):
    from api.user_admin import _write_admin_audit

    _write_admin_audit(
        actor="admin_session",
        action=action,
        target_user=target,
        changes=changes,
        status="ok",
        request=request,
    )


def _guard(request: Request):
    from utils.auth_guard import require_admin_or_session

    require_admin_or_session(request)


async def _parse(request: Request) -> SetToolsRequest:
    try:
        return SetToolsRequest(**(await request.json()))
    except Exception as e:
        raise HTTPException(400, f"Invalid request body: {e}")


def list_tool_access_tools(request: Request):
    """GET /v1/_mw/admin/tool-access/tools — danh mục tool + số grant hiện có."""
    _guard(request)
    try:
        return {"tools": list_tools()}
    except Exception as e:
        logger.error("list_tool_access_tools failed: %s", e)
        raise HTTPException(500, f"Không đọc được danh sách tool: {e}")


def list_tool_access_groups(request: Request):
    """GET /v1/_mw/admin/tool-access/groups — group phòng ban + tool đang được cấp."""
    _guard(request)
    try:
        return {"groups": list_groups()}
    except Exception as e:
        logger.error("list_tool_access_groups failed: %s", e)
        raise HTTPException(500, f"Không đọc được danh sách group: {e}")


def get_group_tool_access(request: Request, group_id: str):
    """GET /v1/_mw/admin/tool-access/groups/{group_id} — trạng thái toggle của Edit Group."""
    _guard(request)
    try:
        return get_group_tools(group_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error("get_group_tool_access failed group=%s: %s", group_id, e)
        raise HTTPException(500, f"Không đọc được quyền tool của group: {e}")


async def update_group_tool_access(request: Request, group_id: str):
    """PUT /v1/_mw/admin/tool-access/groups/{group_id} — lưu toggle tool của group."""
    _guard(request)
    body = await _parse(request)
    try:
        result = set_group_tools(group_id, body.tool_ids)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("update_group_tool_access failed group=%s: %s", group_id, e)
        raise HTTPException(500, f"Không lưu được quyền tool của group: {e}")

    _audit(request, "set_group_tools", f"group:{group_id}", result)
    logger.info(
        "tool_access group=%s added=%s removed=%s",
        group_id, result["added"], result["removed"],
    )
    return result


def get_user_tool_access(request: Request, openwebui_user_id: str):
    """GET /v1/_mw/admin/tool-access/users/{openwebui_user_id} — trạng thái toggle của Edit User."""
    _guard(request)
    try:
        return get_user_tools(openwebui_user_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error("get_user_tool_access failed user=%s: %s", openwebui_user_id, e)
        raise HTTPException(500, f"Không đọc được quyền tool của user: {e}")


async def update_user_tool_access(request: Request, openwebui_user_id: str):
    """PUT /v1/_mw/admin/tool-access/users/{openwebui_user_id} — lưu grant riêng của user."""
    _guard(request)
    body = await _parse(request)
    try:
        result = set_user_tools(openwebui_user_id, body.tool_ids)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("update_user_tool_access failed user=%s: %s", openwebui_user_id, e)
        raise HTTPException(500, f"Không lưu được quyền tool của user: {e}")

    _audit(request, "set_user_tools", f"user:{openwebui_user_id}", result)
    logger.info(
        "tool_access user=%s added=%s removed=%s",
        openwebui_user_id, result["added"], result["removed"],
    )
    return result
