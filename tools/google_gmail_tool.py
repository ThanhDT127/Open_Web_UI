"""
title: Google Gmail Tool
author: Antigravity
version: 1.0.0
requirements: requests
"""

import os
import requests
from pydantic import BaseModel, Field

class Tools:
    class Valves(BaseModel):
        MW_BASE_URL: str = Field(
            default="http://middleware:5000/v1",
            description="Base URL of the Middleware API (internal container address)"
        )
        SUBKEY_ADMIN: str = Field(
            default="YOUR_SUBKEY_ADMIN",
            description="Admin key for authenticating with the Middleware API"
        )
        MW_PUBLIC_URL: str = Field(
            default="https://localhost:3000",
            description="Public face URL of the application for oauth redirection"
        )

    def __init__(self):
        self.valves = self.Valves()
        # Overwrite valves with environment variables if available
        if os.getenv("SUBKEY_ADMIN"):
            self.valves.SUBKEY_ADMIN = os.getenv("SUBKEY_ADMIN")
        if os.getenv("MW_PUBLIC_URL"):
            self.valves.MW_PUBLIC_URL = os.getenv("MW_PUBLIC_URL")

    def send_gmail(self, recipient: str, subject: str, body: str, __user__: dict = None) -> str:
        """
        Gửi email thông qua tài khoản Gmail cá nhân của người dùng bằng cách sử dụng Google OAuth token.
        Nếu tài khoản chưa được liên kết, công cụ sẽ trả về liên kết yêu cầu người dùng kết nối.
        
        :param recipient: Địa chỉ email của người nhận.
        :param subject: Tiêu đề email.
        :param body: Nội dung email.
        :param __user__: Thông tin người dùng hiện tại từ OpenWebUI (được tự động tiêm vào).
        :return: Chuỗi kết quả gửi email hoặc hướng dẫn liên kết tài khoản.
        """
        if not __user__ or not __user__.get("id"):
            return "Lỗi: Không tìm thấy thông tin định danh người dùng OpenWebUI."

        user_id = __user__["id"]
        provider = "google_gmail"
        
        # 1. Gọi Middleware để lấy access token của user
        token_url = f"{self.valves.MW_BASE_URL.rstrip('/')}/_mw/integrations/get_token"
        headers = {
            "Authorization": f"Bearer {self.valves.SUBKEY_ADMIN}"
        }
        params = {
            "provider": provider,
            "openwebui_user_id": user_id
        }
        
        try:
            response = requests.get(token_url, headers=headers, params=params, timeout=10)
            if response.status_code == 404:
                # Chưa liên kết tài khoản
                connect_url = f"{self.valves.MW_PUBLIC_URL.rstrip('/')}/v1/_mw/oauth/connect?provider={provider}&openwebui_user_id={user_id}"
                return (
                    f"⚠️ Tài khoản Gmail của bạn chưa được liên kết.\n\n"
                    f"Vui lòng click vào liên kết dưới đây để kết nối tài khoản Gmail của bạn:\n"
                    f"👉 [**Kết nối tài khoản Gmail của bạn**]({connect_url})\n\n"
                    f"Sau khi hoàn tất kết nối, hãy thử gửi email lại."
                )
            elif response.status_code != 200:
                return f"Lỗi từ Middleware API ({response.status_code}): {response.text}"
            
            token_data = response.json()
            access_token = token_data.get("access_token")
            if not access_token:
                return "Lỗi: Không nhận được access token từ Middleware."
            
        except Exception as e:
            return f"Lỗi khi kết nối tới Middleware: {str(e)}"
            
        # 2. Thay vì gửi ngay, tạo một mã phê duyệt (Hành động nhạy cảm)
        import uuid
        approval_id = f"gmail_send_{uuid.uuid4().hex[:8]}"
        
        # Đăng ký với Middleware
        register_url = f"{self.valves.MW_BASE_URL.rstrip('/')}/_mw/approvals"
        register_payload = {
            "id": approval_id,
            "tool_name": "google_gmail_tool",
            "user_id": user_id,
            "payload": {
                "recipient": recipient,
                "subject": subject,
                "body": body
            }
        }
        
        try:
            reg_res = requests.post(
                register_url,
                headers=headers,
                json=register_payload,
                timeout=10
            )
            if reg_res.status_code != 200:
                return f"Lỗi khi đăng ký phê duyệt với Middleware: {reg_res.text}"
        except Exception as e:
            return f"Lỗi kết nối Middleware khi đăng ký phê duyệt: {str(e)}"
            
        return (
            f"⚠️ Yêu cầu gửi email của bạn cần được phê duyệt.\n"
            f"Người nhận: **{recipient}**\n"
            f"Tiêu đề: **{subject}**\n"
            f"[PENDING_APPROVAL:{approval_id}]"
        )
