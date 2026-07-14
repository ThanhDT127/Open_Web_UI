"""
title: Duyệt gửi email
author: Antigravity
version: 2.1.0
requirements: requests
icon_url: data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGZpbGw9Im5vbmUiIHZpZXdCb3g9IjAgMCAyNCAyNCIgc3Ryb2tlLXdpZHRoPSIxLjgiIHN0cm9rZT0iIzAwMDAwMCI+PHBhdGggc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIiBkPSJNMjEuNzUgNi43NXYxMC41YTIuMjUgMi4yNSAwIDAgMS0yLjI1IDIuMjVoLTE1YTIuMjUgMi4yNSAwIDAgMS0yLjI1LTIuMjVWNi43NW0xOS41IDBBMi4yNSAyLjI1IDAgMCAwIDE5LjUgNC41aC0xNWEyLjI1IDIuMjUgMCAwIDAtMi4yNSAyLjI1bTE5LjUgMHYuMjQzYTIuMjUgMi4yNSAwIDAgMS0xLjA3IDEuOTE2bC03LjUgNC42MTVhMi4yNSAyLjI1IDAgMCAxLTIuMzYgMEwzLjMyIDguOTFhMi4yNSAyLjI1IDAgMCAxLTEuMDctMS45MTZWNi43NSIvPjwvc3ZnPg==
"""

import base64
import logging
import re
from email.header import Header
from email.mime.text import MIMEText
from typing import Optional

import requests
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MARKER_RE = re.compile(r"\[PENDING_APPROVAL:([a-zA-Z0-9_-]+)\]")

icon_url = (
    "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIGZpbGw9Im5vbmUiIHZpZXdCb3g9IjAgMCAyNCAyNCIgc3Ryb2tlLXdpZHRoPSIxLjgiIHN0cm9rZT0iIzAwMDAwMCI+PHBhdGggc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIiBkPSJNMjEuNzUgNi43NXYxMC41YTIuMjUgMi4yNSAwIDAgMS0yLjI1IDIuMjVoLTE1YTIuMjUgMi4yNSAwIDAgMS0yLjI1LTIuMjVWNi43NW0xOS41IDBBMi4yNSAyLjI1IDAgMCAwIDE5LjUgNC41aC0xNWEyLjI1IDIuMjUgMCAwIDAtMi4yNSAyLjI1bTE5LjUgMHYuMjQzYTIuMjUgMi4yNSAwIDAgMS0xLjA3IDEuOTE2bC03LjUgNC42MTVhMi4yNSAyLjI1IDAgMCAxLTIuMzYgMEwzLjMyIDguOTFhMi4yNSAyLjI1IDAgMCAxLTEuMDctMS45MTZWNi43NSIvPjwvc3ZnPg=="
)


class Action:
    """Nút bấm thủ công để mở lại hộp thoại phê duyệt của một tin nhắn.

    Luồng chính đã do filter_approval_handler.outlet lo (tự hỏi xác nhận ngay khi tool tạo
    yêu cầu). Action này chỉ dùng khi người dùng lỡ tắt hộp thoại và muốn mở lại.
    """

    class Valves(BaseModel):
        MW_BASE_URL: str = Field(
            default="http://middleware:5000/v1",
            description="Base URL of the Middleware API (internal container address)",
        )
        SUBKEY_ADMIN: str = Field(
            default="YOUR_SUBKEY_ADMIN",
            description="Admin key for authenticating with the Middleware API",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ------------------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------------------

    def _find_marker(self, message: dict) -> Optional[str]:
        """Tìm mã phê duyệt trong một message assistant.

        Marker do tool sinh ra và nằm trong tool output (sources). Model diễn giải lại câu
        trả lời nên thường làm rụng marker — chỉ quét content là không đủ.
        """
        content = message.get("content")
        if isinstance(content, str):
            match = MARKER_RE.search(content)
            if match:
                return match.group(1)

        for source in message.get("sources") or []:
            for doc in source.get("document") or []:
                if isinstance(doc, str):
                    match = MARKER_RE.search(doc)
                    if match:
                        return match.group(1)
        return None

    async def _status(self, emitter, text: str) -> None:
        if emitter:
            await emitter({"type": "status", "data": {"description": text, "done": True}})

    def _send_gmail(self, payload: dict, user_id: str, headers: dict) -> str:
        recipient = payload.get("recipient")
        subject = payload.get("subject")
        mail_body = payload.get("body")

        res = requests.get(
            f"{self.valves.MW_BASE_URL.rstrip('/')}/_mw/integrations/get_token",
            headers=headers,
            params={"provider": "google_gmail", "openwebui_user_id": user_id},
            timeout=10,
        )
        if res.status_code != 200:
            return f"❌ Đã duyệt nhưng không lấy được Gmail OAuth token: {res.text[:200]}"
        access_token = res.json().get("access_token")
        if not access_token:
            return "❌ Gmail access token rỗng từ Middleware."

        message = MIMEText(mail_body, _charset="utf-8")
        message["to"] = recipient
        message["subject"] = Header(subject, "utf-8")
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        res = requests.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"raw": raw},
            timeout=15,
        )
        if res.status_code != 200:
            return f"❌ Đã duyệt nhưng Gmail API lỗi {res.status_code}: {res.text[:200]}"
        return f"✅ Đã gửi email tới {recipient} (Message ID: {res.json().get('id')})."

    def _parse_edited(self, text: str, orig_subject: str, orig_body: str):
        """Tách lại tiêu đề/nội dung từ khung soạn thảo. Mất dòng "Tiêu đề:" thì giữ tiêu đề gốc."""
        lines = (text or "").split("\n")
        if lines and lines[0].strip().lower().startswith("tiêu đề:"):
            subject = lines[0].split(":", 1)[1].strip() or orig_subject
            body = "\n".join(lines[1:]).lstrip("\n")
            return subject, body
        return orig_subject, text

    def _resolve_approval(
        self,
        action_id: str,
        user_id: str,
        approve: bool,
        subject: str = None,
        body: str = None,
    ) -> str:
        headers = {"Authorization": f"Bearer {self.valves.SUBKEY_ADMIN}"}
        base = f"{self.valves.MW_BASE_URL.rstrip('/')}/_mw/approvals/{action_id}"

        try:
            # Lấy chi tiết TRƯỚC khi đổi trạng thái, và chỉ hành động khi còn 'pending'.
            # Thiếu chốt này thì duyệt lại một yêu cầu đã duyệt sẽ gửi email lần thứ hai.
            res = requests.get(base, headers=headers, timeout=10)
            if res.status_code != 200:
                return f"⚠️ Không tìm thấy yêu cầu {action_id} (có thể đã bị dọn)."
            approval = res.json()

            status = approval.get("status")
            if status != "pending":
                return f"⚠️ Yêu cầu đã được xử lý trước đó (trạng thái: {status}), không làm lại."

            new_status = "approved" if approve else "rejected"
            res = requests.post(
                f"{base}/status", headers=headers, json={"status": new_status}, timeout=10
            )
            if res.status_code != 200:
                return f"❌ Lỗi cập nhật trạng thái ở Middleware: {res.text[:200]}"

            if not approve:
                return "❌ Bạn đã từ chối. Email KHÔNG được gửi."

            tool_name = approval.get("tool_name")
            if tool_name != "google_gmail_tool":
                return f"⚠️ Đã duyệt nhưng không hỗ trợ thực thi công cụ '{tool_name}'."

            payload = dict(approval.get("payload", {}))
            if subject is not None:
                payload["subject"] = subject
            if body is not None:
                payload["body"] = body
            return self._send_gmail(payload, user_id, headers)

        except Exception as e:
            logger.error("Lỗi khi xử lý phê duyệt %s: %s", action_id, e)
            return f"❌ Lỗi hệ thống trong quá trình phê duyệt: {e}"

    # ------------------------------------------------------------------------------
    # Action
    # ------------------------------------------------------------------------------

    async def action(
        self,
        body: dict,
        __user__=None,
        __event_emitter__=None,
        __event_call__=None,
        __model__=None,
        __request__=None,
        __id__=None,
    ) -> Optional[dict]:
        logger.info("=== Tool Approval UI: action() called ===")

        if not __event_call__:
            logger.warning("Action: thiếu __event_call__, bỏ qua.")
            return None

        last_assistant = next(
            (
                m
                for m in reversed(body.get("messages", []))
                if isinstance(m, dict) and m.get("role") == "assistant"
            ),
            None,
        )
        action_id = self._find_marker(last_assistant) if last_assistant else None
        if not action_id:
            await self._status(
                __event_emitter__, "❌ Không tìm thấy yêu cầu phê duyệt nào trong tin nhắn này."
            )
            return None

        headers = {"Authorization": f"Bearer {self.valves.SUBKEY_ADMIN}"}
        try:
            res = requests.get(
                f"{self.valves.MW_BASE_URL.rstrip('/')}/_mw/approvals/{action_id}",
                headers=headers,
                timeout=10,
            )
        except Exception as e:
            await self._status(__event_emitter__, f"❌ Lỗi kết nối Middleware: {e}")
            return None

        if res.status_code != 200:
            await self._status(
                __event_emitter__, f"❌ Không tìm thấy yêu cầu {action_id} (có thể đã bị dọn)."
            )
            return None

        approval = res.json()
        if approval.get("status") != "pending":
            await self._status(
                __event_emitter__,
                f"ℹ️ Yêu cầu này đã được xử lý (trạng thái: {approval.get('status')}).",
            )
            return None

        payload = approval.get("payload", {})
        recipient = payload.get("recipient", "")
        subject = payload.get("subject", "")
        mail_body = payload.get("body", "")
        user_id = (__user__ or {}).get("id", "")

        # Hộp thoại soạn thảo có sẵn của Open WebUI: type "input" cho ra <textarea> điền sẵn,
        # xem trước và sửa được rồi mới gửi. Bản cũ tự chèn HTML + JS rồi giả lập gõ
        # "/approve <id>" vào #chat-textarea — phần tử đó không còn tồn tại nên nút bấm chết.
        edited = await __event_call__(
            {
                "type": "input",
                "data": {
                    "title": "✉️ Xem lại email trước khi gửi",
                    "message": (
                        f"Người nhận: {recipient}\n\n"
                        f"Sửa lại tiêu đề/nội dung bên dưới nếu cần, rồi bấm Xác nhận để gửi."
                    ),
                    "placeholder": "Nội dung email…",
                    "value": f"Tiêu đề: {subject}\n\n{mail_body}",
                },
            }
        )

        if edited is False:
            result = self._resolve_approval(action_id, user_id, approve=False)
        elif edited is True or not str(edited).strip():
            self._resolve_approval(action_id, user_id, approve=False)
            result = "❌ Nội dung email trống nên không gửi. Yêu cầu đã bị huỷ."
        else:
            new_subject, new_body = self._parse_edited(str(edited), subject, mail_body)
            if not new_body.strip():
                self._resolve_approval(action_id, user_id, approve=False)
                result = "❌ Nội dung email trống nên không gửi. Yêu cầu đã bị huỷ."
            else:
                result = self._resolve_approval(
                    action_id, user_id, approve=True, subject=new_subject, body=new_body
                )
                if (new_subject, new_body) != (subject, mail_body) and result.startswith("✅"):
                    result += " (đã gửi theo bản bạn chỉnh sửa)"

        logger.info("Action: %s -> %s", action_id, result[:80])
        await self._status(__event_emitter__, result)
        return None
