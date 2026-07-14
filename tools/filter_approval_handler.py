"""
title: Tool Approval Handler Filter
author: Antigravity
description: Intercepts /approve and /reject commands, updates status, and executes approved actions.
version: 1.0.0
type: filter
requirements: requests
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


class Filter:
    class Valves(BaseModel):
        middleware_url: str = Field(
            default="http://middleware:5000/v1",
            description="Base URL of the Middleware API (internal container address)"
        )
        admin_token: str = Field(
            default="YOUR_SUBKEY_ADMIN",
            description="Admin key for authenticating with the Middleware API"
        )

    def __init__(self):
        self.valves = self.Valves()

    def _find_marker(self, message: dict) -> Optional[str]:
        """Tìm mã phê duyệt trong một message assistant.

        Marker do tool sinh ra và nằm trong tool output (sources). Model thường diễn giải
        lại câu trả lời và làm rụng marker (nó viết "Trạng thái: PENDING_APPROVAL" thay vì
        "[PENDING_APPROVAL:<id>]"), nên chỉ quét content là không đủ — phải quét cả sources.
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

    async def inlet(self, body: dict, __user__: dict = None) -> dict:
        """
        Intercepts incoming user prompts before they reach the LLM.
        Detects `/approve` and `/reject` commands.
        """
        logger.info("=== Tool Approval Filter: inlet() called ===")
        
        messages = body.get("messages", [])
        if not messages or not __user__:
            return body

        last_msg = messages[-1]
        content = last_msg.get("content", "")
        if not isinstance(content, str):
            return body

        # Match /approve or /reject commands
        content_stripped = content.strip()
        match = re.match(r"^/(approve|reject)\s+([a-zA-Z0-9_-]+)$", content_stripped)
        if not match:
            return body

        cmd = match.group(1)      # "approve" or "reject"
        action_id = match.group(2)
        user_id = __user__.get("id", "")

        logger.info("Intercepted command: /%s for action %s by user %s", cmd, action_id, user_id)

        result = self._resolve_approval(action_id, user_id, approve=(cmd == "approve"))
        last_msg["content"] = (
            f"[SYSTEM: {result} Hãy thông báo lại việc này cho người dùng một cách ngắn gọn, tự nhiên.]"
        )
        return body

    def _parse_edited(self, text: str, orig_subject: str, orig_body: str):
        """Tách lại tiêu đề/nội dung từ khung soạn thảo người dùng vừa sửa.

        Khung có dạng "Tiêu đề: ...\\n\\n<nội dung>". Nếu người dùng xoá mất dòng tiêu đề thì
        giữ tiêu đề gốc và coi toàn bộ text là nội dung.
        """
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
        """Duyệt/từ chối một yêu cầu rồi thực thi nếu được duyệt. Trả về câu mô tả kết quả
        cho người dùng đọc (không phải chỉ thị cho model).

        `subject`/`body` nếu có sẽ đè lên payload đã lưu — đó là bản người dùng vừa sửa
        trong hộp thoại xem trước.
        """
        headers = {"Authorization": f"Bearer {self.valves.admin_token}"}
        base = f"{self.valves.middleware_url.rstrip('/')}/_mw/approvals/{action_id}"

        try:
            # Lấy chi tiết TRƯỚC khi đổi trạng thái, và chỉ hành động khi còn 'pending'.
            # Thiếu chốt này thì duyệt lại một yêu cầu đã duyệt sẽ gửi email lần thứ hai.
            res = requests.get(base, headers=headers, timeout=10)
            if res.status_code != 200:
                return (
                    f"⚠️ Không tìm thấy yêu cầu phê duyệt `{action_id}` (có thể đã bị dọn). "
                    f"Bạn cần tạo lại yêu cầu."
                )
            approval = res.json()

            status = approval.get("status")
            if status != "pending":
                return (
                    f"⚠️ Yêu cầu `{action_id}` đã được xử lý trước đó (trạng thái: {status}), "
                    f"nên không thực hiện lại."
                )

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
                return f"⚠️ Đã duyệt nhưng filter không hỗ trợ thực thi công cụ '{tool_name}'."

            payload = dict(approval.get("payload", {}))
            if subject is not None:
                payload["subject"] = subject
            if body is not None:
                payload["body"] = body
            return self._send_gmail(payload, user_id, headers)

        except Exception as e:
            logger.error("Lỗi khi xử lý phê duyệt %s: %s", action_id, e)
            return f"❌ Lỗi hệ thống trong quá trình phê duyệt: {e}"

    def _send_gmail(self, payload: dict, user_id: str, headers: dict) -> str:
        recipient = payload.get("recipient")
        subject = payload.get("subject")
        mail_body = payload.get("body")

        token_url = f"{self.valves.middleware_url.rstrip('/')}/_mw/integrations/get_token"
        res = requests.get(
            token_url,
            headers=headers,
            params={"provider": "google_gmail", "openwebui_user_id": user_id},
            timeout=10,
        )
        if res.status_code != 200:
            return f"❌ Đã duyệt nhưng không lấy được Gmail OAuth token: {res.text[:200]}"
        access_token = res.json().get("access_token")
        if not access_token:
            return "❌ Gmail access token rỗng từ Middleware."

        # Tiêu đề tiếng Việt phải mã hoá RFC 2047, nếu không as_bytes() sẽ vỡ/hỏng dấu.
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
        return f"✅ Đã gửi email tới **{recipient}** (Message ID: `{res.json().get('id')}`)."

    async def outlet(
        self,
        body: dict,
        __user__: dict = None,
        __event_call__=None,
        __event_emitter__=None,
    ) -> dict:
        """Thấy yêu cầu đang chờ duyệt thì hỏi xác nhận, và thực thi ngay tại đây."""
        logger.info("=== Tool Approval Filter: outlet() called ===")
        if not __event_call__:
            logger.warning("Outlet: thiếu __event_call__, bỏ qua.")
            return body

        # Chỉ xét message assistant vừa sinh ra. Quét ngược cả lịch sử sẽ khiến một yêu cầu
        # cũ còn pending bật hộp thoại lại ở những lượt chat chẳng liên quan.
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
            logger.info("Outlet: không có marker PENDING_APPROVAL trong lượt này, bỏ qua.")
            return body

        headers = {"Authorization": f"Bearer {self.valves.admin_token}"}
        base = f"{self.valves.middleware_url.rstrip('/')}/_mw/approvals/{action_id}"
        try:
            res = requests.get(base, headers=headers, timeout=10)
            if res.status_code != 200:
                logger.error("Outlet: không lấy được chi tiết %s: %s", action_id, res.status_code)
                return body
            approval = res.json()
        except Exception as e:
            logger.error("Outlet: lỗi gọi middleware: %s", e)
            return body

        if approval.get("status") != "pending":
            logger.info("Outlet: %s không còn pending, bỏ qua.", action_id)
            return body

        payload = approval.get("payload", {})
        logger.info("Outlet: hỏi xác nhận cho %s", action_id)

        recipient = payload.get("recipient", "")
        subject = payload.get("subject", "")
        mail_body = payload.get("body", "")
        user_id = (__user__ or {}).get("id", "")

        # Bấm ra ngoài hoặc Escape thì ConfirmDialog chỉ đóng lại, KHÔNG dispatch gì — nghĩa là
        # __event_call__ dưới đây không bao giờ resolve và hộp thoại mất luôn. Ghi sẵn lối thoát
        # vào tin nhắn. Dòng này tự biến mất khi hộp thoại được xử lý xong, vì lúc đó outlet ghi
        # đè content bằng bản chưa có nó (body được dựng trước khi emit).
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "message",
                    "data": {
                        "content": (
                            "\n\n_Lỡ đóng hộp thoại? Bấm nút **✉️ Duyệt gửi email** ngay dưới "
                            "tin nhắn này để mở lại._"
                        )
                    },
                }
            )

        # Hộp thoại soạn thảo có sẵn của Open WebUI: type "input" cho ra <textarea> điền sẵn,
        # người dùng xem trước và sửa được rồi mới gửi.
        # Trả về: chuỗi đã sửa nếu bấm Xác nhận; True nếu xác nhận khi ô trống; False nếu Huỷ.
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
            # Xác nhận nhưng để trống -> coi như huỷ, không gửi email rỗng.
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
                    result += " _(đã gửi theo bản bạn chỉnh sửa)_"

        logger.info("Outlet: %s -> %s", action_id, result[:80])

        # Gắn kết quả vào chính câu trả lời; Open WebUI sẽ lưu lại và đẩy về frontend
        # qua event chat:outlet.
        last_assistant["content"] = (last_assistant.get("content") or "") + "\n\n---\n" + result
        return body
