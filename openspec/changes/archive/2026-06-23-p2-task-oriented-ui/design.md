## Context

Giao diện mặc định của OpenWebUI không có màn hình chia tác vụ rõ ràng. Do container của OpenWebUI được compile sẵn, chúng ta sẽ tùy biến trang chủ thông qua các công cụ Custom CSS và Chat Suggestions tích hợp trong trang quản trị Admin Panel.

## Goals / Non-Goals

**Goals:**
- Tạo tệp `task_cards_styling.css` chứa định dạng giao diện grid 2x2, gradient background, icons, hover animations cho suggestions.
- Tạo cấu hình JSON chứa nội dung gợi ý kích hoạt tương ứng cho 4 tác vụ map với model chuyên trách.

**Non-Goals:**
- Không sửa đổi mã nguồn Svelte/TypeScript gốc của OpenWebUI.

## Decisions

### Tùy biến CSS trực tiếp trong Admin
- **Lựa chọn:** Tiêm CSS tùy biến thông qua Admin Settings -> Interface -> Custom CSS.
- **Lý do:** Đây là cơ chế chính thức của OpenWebUI để tùy biến UI mà không cần fork code. CSS này được lưu trong database SQLite/Postgres của OpenWebUI và áp dụng cho toàn bộ người dùng.

## Risks / Trade-offs

- **[Risk] Nâng cấp OpenWebUI làm thay đổi class:** Nếu OpenWebUI nâng cấp cấu trúc HTML và class name, Custom CSS này có thể bị mất tác dụng hoặc vỡ giao diện.
  - *Mitigation:* Chúng ta lưu trữ đoạn CSS này trong thư mục `fuction UI/task_cards_styling.css` để Admin có thể dễ dàng sửa đổi và cập nhật nếu cần.
