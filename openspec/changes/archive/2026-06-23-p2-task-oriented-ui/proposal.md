## Why

Trang chủ mặc định của OpenWebUI ở dạng khung chat trống đơn giản, chưa tối ưu cho các luồng công việc tự động chuyên sâu trong doanh nghiệp (như hỏi tài liệu, cào web, phân tích file). Việc chuyển đổi trang chủ thành giao diện thẻ tác vụ (Task-oriented UI) giúp định hướng công việc rõ ràng hơn cho nhân viên và tối ưu hóa việc phân chia model LLM/Prompt chuyên trách.

## What Changes

- **Bổ sung giao diện thẻ tác vụ (Task-oriented UI):** Thiết kế lại trang chủ OpenWebUI mặc định thành các thẻ công việc lớn ("Hỏi tài liệu", "Nghiên cứu web", "Phân tích file", "Tạo biểu mẫu") sử dụng CSS Injection.
- **Tích hợp Custom Suggestions cấu hình sẵn:** Cài đặt 4 Suggestions tương ứng với 4 tác vụ lớn, click vào sẽ tự kích hoạt model/prompt chuyên dụng.

## Capabilities

### New Capabilities
- `task-oriented-ui`: Định nghĩa cấu hình thẻ tác vụ trang chủ sử dụng Chat Suggestions và phong cách CSS Injection bản xứ.

### Modified Capabilities
<!-- No modified capabilities -->

## Impact

- **open-webui:** Tải cấu hình CSS tùy biến và dữ liệu Suggestions vào cơ sở dữ liệu OpenWebUI.
- **fuction UI/ (Workspace):** Tạo các tệp lưu trữ static CSS và cấu hình JSON để backup/import.
