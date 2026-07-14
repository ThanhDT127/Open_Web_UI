"""Đọc/ghi quyền dùng tool của Open WebUI (bảng `access_grant`) theo group và theo user.

Open WebUI 0.9.6 chỉ cho biên tập quyền tool từ phía *tool* (Workspace → Tools →
Access Control) và hoàn toàn không có UI phân quyền theo user. Module này lật ngược
trục đó để dashboard biên tập được từ phía *group* và phía *user*.

Ghi thẳng vào DB `openwebui` — cùng pattern với :mod:`core.identity`,
:mod:`core.group_analytics`. Open WebUI đọc `access_grant` tươi từ DB ở mỗi request
(`utils/tools.py: get_tools` gọi lại `AccessGrants.has_access` cho từng tool), không
cache, nên grant có hiệu lực ngay.

Ghi có chủ đích theo từng dòng (INSERT/DELETE đúng principal đang bật/tắt) thay vì
xóa-sạch-ghi-lại như `AccessGrants.set_access_grants` của Open WebUI: bật/tắt tool cho
một group không được phép cuốn theo grant của user khác trên cùng tool đó.
"""

import time
import uuid
from typing import Any, Dict, List
from urllib.parse import urlparse

import psycopg2

from config import DATABASE_URL

RESOURCE_TYPE = "tool"
PERMISSION = "read"


def _openwebui_database_url() -> str:
    parsed = urlparse(DATABASE_URL)
    return DATABASE_URL.replace(parsed.path, "/openwebui")


def _connect():
    return psycopg2.connect(_openwebui_database_url(), connect_timeout=5)


def list_tools() -> List[Dict[str, Any]]:
    """Toàn bộ tool trong workspace, kèm số grant đang có theo group / theo user."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT t.id,
                   t.name,
                   count(*) FILTER (WHERE ag.principal_type = 'group')                        AS n_groups,
                   count(*) FILTER (WHERE ag.principal_type = 'user' AND ag.principal_id <> '*') AS n_users,
                   bool_or(ag.principal_type = 'user' AND ag.principal_id = '*')              AS is_public
            FROM tool t
            LEFT JOIN access_grant ag
                   ON ag.resource_type = %s AND ag.resource_id = t.id AND ag.permission = %s
            GROUP BY t.id, t.name
            ORDER BY t.id
            """,
            (RESOURCE_TYPE, PERMISSION),
        )
        rows = cur.fetchall()
        cur.close()
        return [
            {
                "id": r[0],
                "name": r[1],
                "group_count": r[2] or 0,
                "user_count": r[3] or 0,
                "public": bool(r[4]),
            }
            for r in rows
        ]
    finally:
        conn.close()


def list_groups() -> List[Dict[str, Any]]:
    """Group phòng ban của Open WebUI, kèm số thành viên và các tool đang được cấp."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT g.id,
                   g.name,
                   g.description,
                   (SELECT count(*) FROM group_member gm WHERE gm.group_id = g.id) AS members,
                   COALESCE(
                       (SELECT array_agg(ag.resource_id ORDER BY ag.resource_id)
                          FROM access_grant ag
                         WHERE ag.resource_type = %s
                           AND ag.permission = %s
                           AND ag.principal_type = 'group'
                           AND ag.principal_id = g.id),
                       ARRAY[]::text[]
                   ) AS tool_ids
            FROM "group" g
            ORDER BY g.name
            """,
            (RESOURCE_TYPE, PERMISSION),
        )
        rows = cur.fetchall()
        cur.close()
        return [
            {
                "id": r[0],
                "name": r[1],
                "description": r[2] or "",
                "member_count": r[3] or 0,
                "tool_ids": list(r[4] or []),
            }
            for r in rows
        ]
    finally:
        conn.close()


def _principal_tool_ids(cur, principal_type: str, principal_id: str) -> List[str]:
    cur.execute(
        """
        SELECT resource_id FROM access_grant
         WHERE resource_type = %s AND permission = %s
           AND principal_type = %s AND principal_id = %s
        """,
        (RESOURCE_TYPE, PERMISSION, principal_type, principal_id),
    )
    return [r[0] for r in cur.fetchall()]


def _apply_grants(principal_type: str, principal_id: str, tool_ids: List[str]) -> Dict[str, Any]:
    """Đưa tập tool của một principal về đúng `tool_ids`. Không đụng principal khác."""
    known = {t["id"] for t in list_tools()}
    unknown = [t for t in tool_ids if t not in known]
    if unknown:
        raise ValueError(f"Tool không tồn tại: {', '.join(sorted(unknown))}")

    desired = set(tool_ids)
    conn = _connect()
    try:
        cur = conn.cursor()
        current = set(_principal_tool_ids(cur, principal_type, principal_id))
        added = sorted(desired - current)
        removed = sorted(current - desired)

        for tool_id in added:
            cur.execute(
                """
                INSERT INTO access_grant
                    (id, resource_type, resource_id, principal_type, principal_id, permission, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT ON CONSTRAINT uq_access_grant_grant DO NOTHING
                """,
                (
                    str(uuid.uuid4()),
                    RESOURCE_TYPE,
                    tool_id,
                    principal_type,
                    principal_id,
                    PERMISSION,
                    int(time.time()),
                ),
            )
        if removed:
            cur.execute(
                """
                DELETE FROM access_grant
                 WHERE resource_type = %s AND permission = %s
                   AND principal_type = %s AND principal_id = %s
                   AND resource_id = ANY(%s)
                """,
                (RESOURCE_TYPE, PERMISSION, principal_type, principal_id, removed),
            )
        conn.commit()
        cur.close()
        return {"granted": sorted(desired), "added": added, "removed": removed}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_group_tools(group_id: str) -> Dict[str, Any]:
    """Trạng thái bật/tắt từng tool của một group — dùng để dựng modal Edit Group."""
    group = next((g for g in list_groups() if g["id"] == group_id), None)
    if not group:
        raise ValueError("Group không tồn tại")
    enabled = set(group["tool_ids"])
    return {
        "group": {k: group[k] for k in ("id", "name", "description", "member_count")},
        "tools": [
            {"id": t["id"], "name": t["name"], "enabled": t["id"] in enabled, "public": t["public"]}
            for t in list_tools()
        ],
    }


def set_group_tools(group_id: str, tool_ids: List[str]) -> Dict[str, Any]:
    if not any(g["id"] == group_id for g in list_groups()):
        raise ValueError("Group không tồn tại")
    return _apply_grants("group", group_id, tool_ids)


def get_user_tools(openwebui_user_id: str) -> Dict[str, Any]:
    """Trạng thái từng tool của một user: cấp trực tiếp, kế thừa từ group, hay public.

    `effective` = cái user thực sự thấy trong tool picker; `direct` = cái admin bật/tắt
    được ở đây. Tool đã kế thừa từ group vẫn cho bật trực tiếp — grant thừa là vô hại và
    giữ được quyền khi user rời group.
    """
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute('SELECT id, name, email FROM "user" WHERE id = %s', (openwebui_user_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("User không tồn tại trong Open WebUI")
        user = {"id": row[0], "name": row[1], "email": row[2]}

        cur.execute(
            """
            SELECT g.id, g.name FROM "group" g
            JOIN group_member gm ON gm.group_id = g.id
            WHERE gm.user_id = %s ORDER BY g.name
            """,
            (openwebui_user_id,),
        )
        groups = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]

        direct = set(_principal_tool_ids(cur, "user", openwebui_user_id))

        inherited: Dict[str, List[str]] = {}
        if groups:
            cur.execute(
                """
                SELECT ag.resource_id, g.name
                  FROM access_grant ag
                  JOIN "group" g ON g.id = ag.principal_id
                 WHERE ag.resource_type = %s AND ag.permission = %s
                   AND ag.principal_type = 'group'
                   AND ag.principal_id = ANY(%s)
                """,
                (RESOURCE_TYPE, PERMISSION, [g["id"] for g in groups]),
            )
            for tool_id, group_name in cur.fetchall():
                inherited.setdefault(tool_id, []).append(group_name)
        cur.close()
    finally:
        conn.close()

    tools = []
    for tool in list_tools():
        from_groups = sorted(inherited.get(tool["id"], []))
        tools.append(
            {
                "id": tool["id"],
                "name": tool["name"],
                "direct": tool["id"] in direct,
                "inherited_from": from_groups,
                "public": tool["public"],
                "effective": tool["id"] in direct or bool(from_groups) or tool["public"],
            }
        )
    return {"user": user, "groups": groups, "tools": tools}


def set_user_tools(openwebui_user_id: str, tool_ids: List[str]) -> Dict[str, Any]:
    """Ghi grant trực tiếp cho user. Không đụng grant của group user đang thuộc."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute('SELECT 1 FROM "user" WHERE id = %s', (openwebui_user_id,))
        exists = cur.fetchone() is not None
        cur.close()
    finally:
        conn.close()
    if not exists:
        raise ValueError("User không tồn tại trong Open WebUI")
    return _apply_grants("user", openwebui_user_id, tool_ids)
