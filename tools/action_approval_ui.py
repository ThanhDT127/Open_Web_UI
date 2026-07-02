"""
title: Tool Approval UI Action
author: Antigravity
version: 1.0.0
requirements: requests
"""

import logging
import re
import requests
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Action:
    class Valves(BaseModel):
        MW_BASE_URL: str = Field(
            default="http://middleware:5000/v1",
            description="Base URL of the Middleware API (internal container address)"
        )
        SUBKEY_ADMIN: str = Field(
            default="YOUR_SUBKEY_ADMIN",
            description="Admin key for authenticating with the Middleware API"
        )

    def __init__(self):
        self.valves = self.Valves()

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
            logger.warning("No event call function provided.")
            return None

        # 1. Scan assistant messages for pending approval token
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
            if __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {
                        "description": "❌ Không tìm thấy yêu cầu phê duyệt nào trong tin nhắn này.",
                        "done": True
                    }
                })
            return None

        # 2. Get approval request details from Middleware
        get_url = f"{self.valves.MW_BASE_URL.rstrip('/')}/_mw/approvals/{action_id}"
        headers = {
            "Authorization": f"Bearer {self.valves.SUBKEY_ADMIN}"
        }

        try:
            res = requests.get(get_url, headers=headers, timeout=10)
            if res.status_code == 404:
                if __event_emitter__:
                    await __event_emitter__({
                        "type": "status",
                        "data": {
                            "description": "❌ Không tìm thấy thông tin phê duyệt trên server.",
                            "done": True
                        }
                    })
                return None
            elif res.status_code != 200:
                if __event_emitter__:
                    await __event_emitter__({
                        "type": "status",
                        "data": {
                            "description": f"❌ Lỗi Middleware API: {res.text[:100]}",
                            "done": True
                        }
                    })
                return None

            approval_data = res.json()
        except Exception as e:
            logger.error("Error communicating with middleware: %s", str(e))
            if __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {
                        "description": f"❌ Lỗi kết nối Middleware: {str(e)[:100]}",
                        "done": True
                    }
                })
            return None

        # Check status
        status = approval_data.get("status", "pending")
        if status != "pending":
            if __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {
                        "description": f"ℹ️ Yêu cầu này đã được xử lý (Trạng thái: {status.upper()})",
                        "done": True
                    }
                })
            return None

        # 3. Build detailed explanation for the UI modal
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

        # 4. Inject JS Modal
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
        await __event_call__({"type": "execute", "data": {"code": js}})
        return body
