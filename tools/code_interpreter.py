"""
title: Code Interpreter (Secure Python Sandbox)
author: Antigravity
version: 1.0.0
requirements: requests,websocket-client
"""

import os
import time
import json
import uuid
import logging
import requests
import websocket
from pydantic import BaseModel, Field
from typing import Optional

logger = logging.getLogger(__name__)

class Tools:
    class Valves(BaseModel):
        SANDBOX_URL: str = Field(
            default="http://code-sandbox:8888",
            description="Jupyter Kernel Gateway endpoint URL inside Docker network"
        )
        OUTPUTS_DIR: str = Field(
            default="/app/backend/data/static/outputs",
            description="Shared volume directory inside OpenWebUI container to read outputs"
        )
        TIMEOUT_SEC: int = Field(
            default=30,
            description="Execution timeout in seconds"
        )

    def __init__(self):
        self.valves = self.Valves()

    def run_python_code(self, code: str, __user__: dict = None) -> str:
        """
        Thực thi mã Python trong môi trường Sandbox an toàn và trả về kết quả (văn bản/hình ảnh đồ thị).
        Hỗ trợ vẽ đồ thị bằng matplotlib (tự động lưu và hiển thị ảnh đồ thị khi gọi plt.show()).
        
        :param code: Đoạn mã Python cần thực thi.
        :return: Kết quả stdout/stderr hoặc hình ảnh đồ thị biểu diễn kết quả.
        """
        # Đảm bảo thư mục output tồn tại
        os.makedirs(self.valves.OUTPUTS_DIR, exist_ok=True)
        
        # 1. Quét danh sách file hiện có trước khi chạy để phát hiện file mới sinh ra
        before_files = set()
        if os.path.exists(self.valves.OUTPUTS_DIR):
            try:
                before_files = set(os.listdir(self.valves.OUTPUTS_DIR))
            except Exception as e:
                logger.error(f"Error reading outputs dir: {e}")

        # 2. Tiền xử lý mã nguồn: tự động tiêm Agg backend và cấu hình lưu ảnh cho matplotlib.pyplot.show()
        #    Chỉ tiêm khi code thực sự sử dụng matplotlib/plt để tránh warning không cần thiết
        needs_matplotlib = any(kw in code for kw in ['matplotlib', 'plt.', 'plt ', 'import plt', 'pyplot'])
        
        if needs_matplotlib:
            setup_code = """import os
os.environ['MPLCONFIGDIR'] = '/tmp/matplotlib_config'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import uuid

# Tự động thay đổi plt.show để lưu biểu đồ vào thư mục shared volume
def _auto_show_wrapper():
    fig = plt.gcf()
    if fig and fig.axes:
        filename = f"chart_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join('/tmp/outputs', filename)
        os.makedirs('/tmp/outputs', exist_ok=True)
        plt.savefig(filepath, bbox_inches='tight', dpi=150)
        plt.close(fig)
plt.show = _auto_show_wrapper
"""
            full_code = setup_code + "\n" + code
        else:
            full_code = code

        # 3. Tạo kernel mới trong Sandbox
        try:
            kernel_res = requests.post(
                f"{self.valves.SANDBOX_URL.rstrip('/')}/api/kernels",
                json={},
                timeout=10
            )
            if kernel_res.status_code != 201:
                return f"Lỗi khởi tạo Sandbox Kernel: {kernel_res.text}"
            
            kernel_id = kernel_res.json()["id"]
        except Exception as e:
            return f"Không thể kết nối đến Sandbox Server: {str(e)}. Vui lòng đảm bảo container code-sandbox đang chạy."

        # 4. Giao tiếp qua WebSocket để chạy code và nhận kết quả
        ws_url = f"ws://{self.valves.SANDBOX_URL.split('//')[1].rstrip('/')}/api/kernels/{kernel_id}/channels"
        
        stdout_parts = []
        stderr_parts = []
        
        try:
            ws = websocket.create_connection(ws_url, timeout=self.valves.TIMEOUT_SEC)
            
            session_id = str(uuid.uuid4())
            msg_id = str(uuid.uuid4())
            
            execute_msg = {
                "header": {
                    "msg_id": msg_id,
                    "username": "openwebui",
                    "session": session_id,
                    "msg_type": "execute_request",
                    "version": "5.0"
                },
                "metadata": {},
                "content": {
                    "code": full_code,
                    "silent": False,
                    "store_history": True,
                    "user_expressions": {},
                    "allow_stdin": False
                },
                "parent_header": {}
            }
            
            ws.send(json.dumps(execute_msg))
            
            # Đọc phản hồi từ WebSocket cho đến khi trạng thái chuyển sang idle
            start_time = time.time()
            while True:
                # Kiểm tra timeout
                if time.time() - start_time > self.valves.TIMEOUT_SEC:
                    stderr_parts.append(f"\n[Lỗi: Thực thi vượt quá thời gian giới hạn {self.valves.TIMEOUT_SEC} giây]")
                    break
                    
                try:
                    raw_msg = ws.recv()
                    msg = json.loads(raw_msg)
                except websocket.WebSocketTimeoutException:
                    continue
                except Exception as e:
                    stderr_parts.append(f"\n[WebSocket Recv Error: {str(e)}]")
                    break
                
                msg_type = msg.get("header", {}).get("msg_type")
                content = msg.get("content", {})
                parent_msg_id = msg.get("parent_header", {}).get("msg_id")
                
                if parent_msg_id != msg_id:
                    continue
                
                if msg_type == "stream":
                    text = content.get("text", "")
                    if content.get("name") == "stdout":
                        stdout_parts.append(text)
                    else:
                        stderr_parts.append(text)
                elif msg_type == "execute_result":
                    data = content.get("data", {})
                    text_plain = data.get("text/plain", "")
                    if text_plain:
                        stdout_parts.append(text_plain + "\n")
                elif msg_type == "error":
                    traceback = "\n".join(content.get("traceback", []))
                    # Loại bỏ mã màu ANSI trong traceback
                    import re
                    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                    clean_traceback = ansi_escape.sub('', traceback)
                    stderr_parts.append(clean_traceback)
                elif msg_type == "status":
                    if content.get("execution_state") == "idle":
                        break
                        
            ws.close()
        except Exception as e:
            stderr_parts.append(f"\n[Lỗi kết nối WebSocket: {str(e)}]")
        finally:
            # Hủy kernel để dọn dẹp tài nguyên
            try:
                requests.delete(
                    f"{self.valves.SANDBOX_URL.rstrip('/')}/api/kernels/{kernel_id}",
                    timeout=5
                )
            except Exception:
                pass

        # 5. Gom kết quả đầu ra
        stdout = "".join(stdout_parts).strip()
        stderr = "".join(stderr_parts).strip()
        
        result_text = ""
        if stdout:
            result_text += stdout
        if stderr:
            if result_text:
                result_text += "\n\n"
            result_text += f"Error:\n{stderr}"
            
        if not result_text:
            result_text = "Thực thi hoàn tất (Không có kết quả stdout)."

        # 6. Phát hiện các file biểu đồ/đồ thị mới và gắn Markdown liên kết ảnh
        time.sleep(0.5) # Chờ một chút để file kịp ghi xuống disk hoàn tất
        after_files = set()
        if os.path.exists(self.valves.OUTPUTS_DIR):
            try:
                after_files = set(os.listdir(self.valves.OUTPUTS_DIR))
            except Exception:
                pass
                
        new_files = after_files - before_files
        
        image_markdowns = []
        for filename in sorted(list(new_files)):
            ext = os.path.splitext(filename)[1].lower()
            if ext in ['.png', '.jpg', '.jpeg', '.gif']:
                image_markdowns.append(f"\n\n![Biểu đồ kết quả](/static/outputs/{filename})")
                
        if image_markdowns:
            result_text += "".join(image_markdowns)
            
        return result_text
