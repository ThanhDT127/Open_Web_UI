"""
title: Quota Alert Filter
author: LLM Gateway Admin
description: Hiển thị cảnh báo quota cho user khi sử dụng ≥80% trong mỗi response chat.
version: 2.0.1
type: filter
"""

from pydantic import BaseModel, Field
import requests
from typing import Optional


class Filter:
    """
    Filter này chạy SAU KHI nhận response từ LLM (outlet).
    Gọi Middleware API kiểm tra % quota đã dùng.
    Nếu ≥80% → thêm dòng cảnh báo vào cuối response.
    
    v2.1.0:
    - Uses the Open WebUI service credential with the authenticated user UUID
    - Does not fall back to untrusted name, email, or query parameters
    - Skip nếu middleware đã inject warning (tránh trùng lặp)
    """

    class Valves(BaseModel):
        middleware_url: str = Field(
            default="http://middleware:5000",
            description="URL của Middleware server (Docker service name)"
        )
        enabled: bool = Field(
            default=True,
            description="Bật/tắt cảnh báo quota"
        )
        warning_threshold: int = Field(
            default=80,
            description="Ngưỡng cảnh báo vàng (%) - mặc định 80%"
        )
        critical_threshold: int = Field(
            default=95,
            description="Ngưỡng cảnh báo đỏ (%) - mặc định 95%"
        )
        use_bearer_auth: bool = Field(
            default=True,
            description="Authenticate quota lookup with the configured Open WebUI service credential"
        )
        bearer_token: str = Field(
            default="",
            description="Open WebUI service credential used for trusted forwarded user identity"
        )

    def __init__(self):
        self.valves = self.Valves()

    async def outlet(self, body: dict, __user__: dict = None) -> dict:
        """
        Chạy SAU KHI nhận response từ LLM.
        Kiểm tra quota và thêm cảnh báo nếu cần.
        """
        # Skip nếu disabled hoặc không có user
        if not self.valves.enabled or not __user__:
            return body

        # Skip nếu không có messages
        messages = body.get("messages", [])
        if not messages:
            return body

        # Skip nếu middleware đã inject warning (tránh trùng lặp)
        last_msg = messages[-1] if messages else None
        if last_msg and isinstance(last_msg.get("content"), str):
            content = last_msg["content"]
            # Check markers that middleware injects
            if any(marker in content for marker in [
                "**Cảnh báo quota**",
                "**Quota đã hết**",
                "⚠️ Bạn đã sử dụng",
                "🔴 **Cảnh báo quota**",
                "🚫 **Quota đã hết**",
            ]):
                return body  # Middleware đã inject → skip

        try:
            # Lấy user_id từ Open WebUI user info
            # Only the authenticated Open WebUI UUID is accepted for service identity.
            user_name = __user__.get("name", "")
            user_email = __user__.get("email", "")
            user_id_uuid = __user__.get("id", "")
            
            # Thử từng identifier cho đến khi tìm thấy user trong middleware
            result_data = None
            for candidate_id in [user_id_uuid]:
                if not candidate_id:
                    continue
                try:
                    req_headers = {}
                    req_params = {}
                    
                    if self.valves.use_bearer_auth and self.valves.bearer_token:
                        req_headers["Authorization"] = f"Bearer {self.valves.bearer_token}"
                        req_headers["X-OpenWebUI-User-Id"] = candidate_id
                    else:
                        return body
                    
                    resp = requests.get(
                        f"{self.valves.middleware_url}/v1/_mw/quota-status",
                        params=req_params,
                        headers=req_headers,
                        timeout=2
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("found"):
                            result_data = data
                            break
                except Exception:
                    continue
            
            if not result_data:
                return body

            data = result_data

            # Bỏ qua nếu user không giới hạn
            if data.get("unlimited"):
                return body

            percent = data.get("percent_used", 0)
            remaining = data.get("remaining_usd", 0)

            # Thêm cảnh báo vào cuối response
            alert_text = None

            if percent >= 100:
                alert_text = (
                    f"\n\n---\n"
                    f"🚫 **Quota đã hết**: Bạn đã sử dụng hết quota tháng này "
                    f"(${data.get('used_cost_usd', 0):.2f}/${data.get('limit_cost_usd', 0):.2f}). "
                    f"Các request tiếp theo sẽ bị chặn. "
                    f"Vui lòng liên hệ admin để được nâng hạn mức."
                )
            elif percent >= self.valves.critical_threshold:
                alert_text = (
                    f"\n\n---\n"
                    f"🔴 **Cảnh báo quota**: Bạn đã sử dụng "
                    f"**{percent:.0f}%** quota tháng này "
                    f"(còn ~${remaining:.2f}). "
                    f"Vui lòng liên hệ admin nếu cần tăng quota."
                )
            elif percent >= self.valves.warning_threshold:
                alert_text = (
                    f"\n\n---\n"
                    f"⚠️ Bạn đã sử dụng "
                    f"**{percent:.0f}%** quota tháng này "
                    f"(còn ~${remaining:.2f})."
                )

            if alert_text and messages:
                # Thêm vào message cuối cùng (response của LLM)
                last_msg = messages[-1]
                if isinstance(last_msg.get("content"), str):
                    last_msg["content"] += alert_text

        except requests.exceptions.Timeout:
            pass  # Timeout → bỏ qua, không block response
        except requests.exceptions.ConnectionError:
            pass  # MW không chạy → bỏ qua
        except Exception:
            pass  # Bất kỳ lỗi nào → bỏ qua, không block user

        return body
