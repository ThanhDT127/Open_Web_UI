## 1. Docker Compose & Network Configuration

- [x] 1.1 Thêm mạng `openwebui-sandbox-network` (internal) và dịch vụ `code-sandbox` sử dụng image `jupyter/kernel-gateway` trong [docker-compose.yml](file:///d:/Works/openwebui_clone/docker-compose.yml).
- [x] 1.2 Cấu hình giới hạn tài nguyên cho `code-sandbox` (CPU limit `1.0`, RAM limit `512M`, root filesystem read-only, 64MB `tmpfs` cho `/tmp`).
- [x] 1.3 Cấu hình volume dùng chung `sandbox_outputs` giữa `open-webui` (mount vào `/app/backend/data/static/outputs`) và `code-sandbox` (mount vào `/tmp/outputs`) để chia sẻ tệp hình ảnh đồ thị.
- [x] 1.4 Thêm mạng `openwebui-sandbox-network` vào service `open-webui` trong docker-compose.

## 2. Code Interpreter Custom Tool

- [x] 2.1 Viết Custom Tool [code_interpreter.py](file:///d:/Works/openwebui_clone/tools/code_interpreter.py) thực hiện kết nối HTTP REST API tới Jupyter Gateway (`http://code-sandbox:8888`).
- [x] 2.2 Triển khai logic trong Custom Tool để khởi tạo/quản lý session, chạy mã Python, bắt lỗi ngoại lệ (exception) và trả về stdout/stderr.
- [x] 2.3 Triển khai logic phát hiện file ảnh đồ thị sinh ra trong thư mục shared volume `/tmp/outputs`, tự động trả về định dạng Markdown hiển thị ảnh dạng `/static/outputs/{filename}.png`.

## 3. Verification & Testing

- [x] 3.1 Viết bài test tự động bằng Playwright [ui-sandbox-interpreter.spec.ts](file:///d:/Works/openwebui_clone/tests/ui-sandbox-interpreter.spec.ts) để chạy mã Python mẫu (tính toán đơn giản và vẽ biểu đồ đồ thị) và xác nhận kết quả.
- [x] 3.2 Khởi chạy docker compose up để cập nhật cấu hình mới, chạy kiểm thử tự động Playwright và xác nhận kết quả thành công 100%.
