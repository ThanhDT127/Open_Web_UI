"""
title: Tool Approval Handler Filter
author: Antigravity
description: Intercepts /approve and /reject commands, updates status, and executes approved actions.
version: 1.0.0
type: filter
requirements: requests
"""

import logging
import re
import requests
from typing import Optional
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

        # Call Middleware to update status
        status_url = f"{self.valves.middleware_url.rstrip('/')}/_mw/approvals/{action_id}/status"
        headers = {
            "Authorization": f"Bearer {self.valves.admin_token}"
        }
        status_val = "approved" if cmd == "approve" else "rejected"

        try:
            # 1. Update approval status in Middleware
            res = requests.post(status_url, headers=headers, json={"status": status_val}, timeout=10)
            if res.status_code != 200:
                last_msg["content"] = f"[SYSTEM: Lỗi cập nhật trạng thái Middleware: {res.text[:200]}]"
                return body

            if cmd == "reject":
                last_msg["content"] = f"[SYSTEM: Người dùng từ chối phê duyệt hành động {action_id}. Vui lòng thông báo cho người dùng rằng hành động này đã bị hủy bỏ theo ý của họ.]"
                return body

            # 2. Get details for execution
            get_url = f"{self.valves.middleware_url.rstrip('/')}/_mw/approvals/{action_id}"
            res_details = requests.get(get_url, headers=headers, timeout=10)
            if res_details.status_code != 200:
                last_msg["content"] = f"[SYSTEM: Không tìm thấy chi tiết hành động: {res_details.text[:200]}]"
                return body

            approval_data = res_details.json()
            tool_name = approval_data.get("tool_name")
            payload = approval_data.get("payload", {})

            # 3. Execute approved action
            if tool_name == "google_gmail_tool":
                recipient = payload.get("recipient")
                subject = payload.get("subject")
                mail_body = payload.get("body")

                # Fetch user OAuth token via integrations API
                token_url = f"{self.valves.middleware_url.rstrip('/')}/_mw/integrations/get_token"
                token_params = {
                    "provider": "google_gmail",
                    "openwebui_user_id": user_id
                }
                res_token = requests.get(token_url, headers=headers, params=token_params, timeout=10)
                
                if res_token.status_code != 200:
                    last_msg["content"] = f"[SYSTEM: Phê duyệt thành công, nhưng không lấy được Gmail OAuth token từ Middleware: {res_token.text[:200]}]"
                    return body
                
                token_data = res_token.json()
                access_token = token_data.get("access_token")
                if not access_token:
                    last_msg["content"] = "[SYSTEM: Gmail access token bị rỗng từ Middleware.]"
                    return body
                
                # Call Gmail API to send email
                import base64
                from email.mime.text import MIMEText
                
                gmail_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
                gmail_headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
                
                message = MIMEText(mail_body)
                message["to"] = recipient
                message["subject"] = subject
                raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
                
                res_gmail = requests.post(
                    gmail_url,
                    headers=gmail_headers,
                    json={"raw": raw_message},
                    timeout=15
                )
                
                if res_gmail.status_code == 200:
                    res_json = res_gmail.json()
                    last_msg["content"] = (
                        f"[SYSTEM: Hành động đã được phê duyệt và thực hiện thành công. "
                        f"Kết quả gửi Gmail: Gửi email thành công tới {recipient} (Message ID: {res_json.get('id')}). "
                        f"Hãy xác nhận thành công này cho người dùng một cách ngắn gọn, tự nhiên.]"
                    )
                else:
                    last_msg["content"] = (
                        f"[SYSTEM: Hành động đã được phê duyệt nhưng gọi Gmail API thất bại với mã {res_gmail.status_code}: {res_gmail.text[:200]}. "
                        f"Hãy báo lỗi này cho người dùng.]"
                    )
            else:
                last_msg["content"] = f"[SYSTEM: Hành động đã được phê duyệt nhưng filter không hỗ trợ thực thi công cụ '{tool_name}'.]"

        except Exception as e:
            logger.error("Error processing filter approval: %s", str(e))
            last_msg["content"] = f"[SYSTEM: Lỗi hệ thống trong quá trình phê duyệt: {str(e)}]"

        return body

    async def outlet(
        self,
        body: dict,
        __user__: dict = None,
        __event_call__=None,
        __event_emitter__=None,
    ) -> dict:
        """
        Scans final response for pending approval markers and automatically pops up the approval modal.
        """
        logger.info("=== Tool Approval Filter: outlet() called ===")
        if not __event_call__:
            logger.warning("No event call function provided in outlet filter.")
            return body

        # Scan assistant messages for pending approval token
        action_id = None
        for m in reversed(body.get("messages", [])):
            if isinstance(m, dict) and m.get("role") == "assistant":
                content = m.get("content", "")
                if isinstance(content, str) and "[PENDING_APPROVAL:" in content:
                    match = re.search(r"\[PENDING_APPROVAL:([a-zA-Z0-9_-]+)\]", content)
                    if match:
                        action_id = match.group(1)
                        break

        if not action_id:
            return body

        # Query middleware to get detail of approval
        get_url = f"{self.valves.middleware_url.rstrip('/')}/_mw/approvals/{action_id}"
        headers = {
            "Authorization": f"Bearer {self.valves.admin_token}"
        }

        try:
            res = requests.get(get_url, headers=headers, timeout=10)
            if res.status_code != 200:
                logger.error(f"Failed to fetch approval details from middleware: {res.status_code} {res.text}")
                return body
            approval_data = res.json()
        except Exception as e:
            logger.error("Error communicating with middleware: %s", str(e))
            return body

        status = approval_data.get("status", "pending")
        if status != "pending":
            logger.info(f"Approval {action_id} is not pending (status: {status}), skipping UI popup.")
            return body

        tool_name = approval_data.get("tool_name", "unknown")
        payload = approval_data.get("payload", {})
        
        detail_html = ""
        if tool_name == "google_gmail_tool":
            recipient = payload.get("recipient", "")
            subject = payload.get("subject", "")
            mail_body = payload.get("body", "")
            detail_html = f"""
                <div style="margin-bottom: 12px;">
                    <span style="font-weight: 600; color: #475569;">Công cụ:</span> Gmail Send Tool
                </div>
                <div style="margin-bottom: 8px;">
                    <span style="font-weight: 600; color: #475569;">Người nhận:</span> <span style="font-family: monospace; background: #f1f5f9; padding: 2px 6px; border-radius: 4px;">{recipient}</span>
                </div>
                <div style="margin-bottom: 8px;">
                    <span style="font-weight: 600; color: #475569;">Tiêu đề:</span> <strong>{subject}</strong>
                </div>
                <div style="margin-top: 12px;">
                    <span style="font-weight: 600; color: #475569; display: block; margin-bottom: 4px;">Nội dung email:</span>
                    <div style="background: #f8fafc; border: 1px solid #e2e8f0; padding: 8px 12px; border-radius: 6px; max-height: 150px; overflow-y: auto; white-space: pre-wrap; font-size: 13px; color: #334155;">{mail_body}</div>
                </div>
            """
        else:
            detail_html = f"""
                <div style="margin-bottom: 12px;">
                    <span style="font-weight: 600; color: #475569;">Công cụ:</span> {tool_name}
                </div>
                <div style="margin-top: 12px;">
                    <span style="font-weight: 600; color: #475569; display: block; margin-bottom: 4px;">Thông số (Payload):</span>
                    <pre style="background: #f8fafc; border: 1px solid #e2e8f0; padding: 8px 12px; border-radius: 6px; max-height: 150px; overflow-y: auto; font-size: 12px; color: #334155;">{str(payload)}</pre>
                </div>
            """

        def clean_js_str(s):
            return s.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$").replace("\n", "\\n")

        clean_details = clean_js_str(detail_html)
        clean_action_id = clean_js_str(action_id)

        js = f"""
(() => {{
  const ID = "owui_approval_modal";
  if (document.getElementById(ID)) return;

  const overlay = document.createElement("div");
  overlay.id = ID;
  overlay.style.cssText = `
    position: fixed; inset: 0; z-index: 999999;
    background: rgba(15, 23, 42, 0.65);
    backdrop-filter: blur(4px);
    display: flex; align-items: center; justify-content: center;
    font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
  `;

  overlay.innerHTML = `
    <div style="
      width: min(500px, 94vw);
      background: #ffffff; border-radius: 16px;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
      border: 1px solid #e2e8f0;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    ">
      <!-- Header -->
      <div style="
        padding: 16px 20px;
        background: linear-gradient(135deg, #1e293b, #0f172a);
        color: #ffffff;
        display: flex;
        align-items: center;
        gap: 12px;
      ">
        <svg style="width: 24px; height: 24px; fill: #f59e0b;" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944a11.954 11.954 0 007.834 3.056 12.006 12.006 0 01-5.83 9.877 12.002 12.002 0 01-10.008 0 12.006 12.006 0 01-5.83-9.877zm8.835 1.001a1 1 0 10-2 0v3a1 1 0 102 0v-3zm-1 7a1 1 0 110-2 1 1 0 010 2z" clip-rule="evenodd" />
        </svg>
        <span style="font-size: 16px; font-weight: 700; letter-spacing: 0.5px;">Phê duyệt Hành động Nhạy cảm</span>
      </div>

      <!-- Content -->
      <div style="padding: 20px; font-size: 14px; color: #334155; line-height: 1.5; flex: 1;">
        <div style="margin-bottom: 16px; font-weight: 600; font-size: 15px; color: #1e293b;">
          Yêu cầu phê duyệt hành động của trợ lý AI:
        </div>
        <div style="
          padding: 14px;
          background: #f8fafc;
          border: 1px solid #f1f5f9;
          border-radius: 10px;
          margin-bottom: 20px;
        ">
          {clean_details}
        </div>
        <div style="font-size: 12.5px; color: #64748b;">
          Nhấp <strong>Duyệt</strong> để cho phép trợ lý AI thực hiện tác vụ này, hoặc <strong>Từ chối</strong> để hủy bỏ.
        </div>
      </div>

      <!-- Footer / Actions -->
      <div style="
        padding: 12px 20px;
        background: #f8fafc;
        border-top: 1px solid #e2e8f0;
        display: flex;
        justify-content: flex-end;
        gap: 10px;
      ">
        <button id="btn_reject" style="
          padding: 8px 16px;
          border-radius: 8px;
          border: 1px solid #ef4444;
          background: #ffffff;
          color: #ef4444;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        ">Từ chối</button>
        <button id="btn_approve" style="
          padding: 8px 16px;
          border-radius: 8px;
          border: none;
          background: #10b981;
          color: #ffffff;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        ">Duyệt</button>
        <button id="btn_close" style="
          padding: 8px 16px;
          border-radius: 8px;
          border: 1px solid #cbd5e1;
          background: #ffffff;
          color: #64748b;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s;
        ">Hủy</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  // Submit chat function
  const submitChat = (msg) => {{
    const textarea = document.getElementById("chat-textarea") || document.querySelector("textarea[placeholder*='Send a message']");
    if (textarea) {{
      textarea.value = msg;
      textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
      setTimeout(() => {{
        const sendBtn = document.querySelector("button[type='submit']") || textarea.parentElement.querySelector("button");
        if (sendBtn) sendBtn.click();
      }}, 100);
    }}
  }};

  const close = () => {{
    document.body.removeChild(overlay);
  }};

  overlay.querySelector("#btn_close").addEventListener("click", close);

  overlay.querySelector("#btn_reject").addEventListener("click", () => {{
    submitChat("/reject {clean_action_id}");
    close();
  }});

  overlay.querySelector("#btn_approve").addEventListener("click", () => {{
    submitChat("/approve {clean_action_id}");
    close();
  }});
}})();
"""
        logger.info(f"Emitting auto-execute approval JS for action: {action_id}")
        await __event_call__({"type": "execute", "data": {"code": js}})
        return body
