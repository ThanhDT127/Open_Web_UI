## Why

OpenWebUI cần chạy các đoạn mã Python (phân tích dữ liệu, vẽ biểu đồ, tính toán) một cách an toàn. Việc chạy trực tiếp trên host hoặc trong container chính có nguy cơ bảo mật lớn và không giới hạn được tài nguyên. Thiết lập một Sandbox cô lập bằng Jupyter Kernel Gateway giúp thực thi mã an toàn, kiểm soát tài nguyên và bảo vệ hệ thống.

## What Changes

- **Thêm dịch vụ Sandbox:** Cấu hình container Jupyter Kernel Gateway (`code-sandbox`) trong Docker Compose.
- **Cô lập mạng:** Tạo mạng nội bộ `openwebui-sandbox-network` cách ly hoàn toàn, chỉ cho phép outbound tới `pypi.org` để cài đặt thư viện cần thiết.
- **Giới hạn tài nguyên:** Đặt giới hạn cứng 512MB RAM, 1.0 CPU và mount root dưới dạng read-only, cấp 64MB tmpfs cho thư mục tạm `/tmp`.
- **Custom Code Interpreter Tool:** Tạo Custom Tool trong OpenWebUI để gửi mã Python sang Sandbox, nhận kết quả (văn bản/hình ảnh đồ thị) và lưu đồ thị vào thư mục static dùng chung để hiển thị trong chat.

## Capabilities

### New Capabilities
- `secure-code-sandbox`: Cung cấp môi trường thực thi mã Python độc lập, bảo mật và giới hạn tài nguyên cho AI, hỗ trợ xử lý và lưu trữ biểu đồ hình ảnh kết quả.

### Modified Capabilities
<!-- No modified capabilities -->

## Impact

- **Docker Compose:** Cấu hình mạng, volume và service mới trong `docker-compose.yml`.
- **OpenWebUI Tools:** Tạo tệp Custom Tool Python mới trong thư mục `tools/code_interpreter.py`.
