## ADDED Requirements

### Requirement: Isolated Sandbox Provisioning
Hệ thống MUST khởi chạy một container Jupyter Kernel Gateway (`code-sandbox`) được cách ly mạng hoàn toàn (chỉ cho phép outbound tới `pypi.org` để cài đặt thư viện). Container MUST được cấu hình giới hạn tài nguyên: RAM tối đa 512MB, CPU tối đa 1.0, root filesystem dạng read-only, và cấp 64MB tmpfs cho thư mục ghi file tạm `/tmp`.

#### Scenario: Docker compose starts sandbox successfully
- **WHEN** hệ thống Docker Compose khởi chạy
- **THEN** dịch vụ `code-sandbox` được kích hoạt với đầy đủ các cấu hình giới hạn CPU, RAM, read-only filesystem và network policy như mô tả.

### Requirement: Code Execution API
Custom Tool trong OpenWebUI SHALL gửi mã Python đến REST API của Jupyter Kernel Gateway bên trong sandbox để thực thi và nhận lại kết quả.

#### Scenario: Run simple python calculation
- **WHEN** AI hoặc người dùng gửi một đoạn mã Python tính toán (ví dụ: `print(2 + 2)`) đến Custom Tool
- **THEN** Custom Tool gửi mã sang sandbox, nhận lại kết quả stdout `4` và hiển thị kết quả trong chat.

### Requirement: Chart Image Static Serving
Khi mã Python sinh ra hình ảnh biểu đồ đồ thị (ví dụ: PNG qua matplotlib), Custom Tool SHALL trích xuất, lưu trữ hình ảnh vào thư mục static dùng chung và trả về đường dẫn Markdown tương ứng để hiển thị ảnh trực tiếp trong giao diện chat.

#### Scenario: Plotting a chart and display in chat
- **WHEN** mã Python vẽ đồ thị matplotlib được chạy trong sandbox và lưu lại thành file ảnh
- **THEN** Custom Tool sao chép file ảnh này sang thư mục static dùng chung của OpenWebUI và trả về đường dẫn Markdown hiển thị ảnh dạng `/static/outputs/{filename}.png`.
