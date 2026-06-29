## Why

OpenWebUI không hỗ trợ lưu trữ thông tin đăng nhập/token OAuth riêng biệt cho từng người dùng trong các Custom Tools. Việc này dẫn đến việc người dùng không thể tích hợp tài khoản Gmail, Drive, GitHub cá nhân vào các tác vụ của AI. Việc xây dựng luồng OAuth 2.0 Click-to-Connect ở mức Middleware sẽ giải quyết triệt để bài toán này một cách an toàn và cung cấp trải nghiệm chuyên nghiệp cho người dùng doanh nghiệp.

## What Changes

- **Bảng cơ sở dữ liệu lưu trữ tokens:** Tạo bảng `mw_user_integrations` trong PostgreSQL để lưu trữ trạng thái OAuth của từng người dùng (định danh bằng băm subkey).
- **Mã hóa Token:** Sử dụng AES-256 để mã hóa `access_token` và `refresh_token` trước khi lưu vào DB.
- **Cổng xác thực OAuth Middleware:** Xây dựng endpoint `/v1/_mw/oauth/connect` để chuyển hướng người dùng sang trang đăng nhập Google/GitHub và `/v1/_mw/oauth/callback` để tiếp nhận ủy quyền, cập nhật token.
- **API lấy Token sạch:** Xây dựng endpoint `/v1/_mw/integrations/get_token` dành cho các Custom Tools gọi lấy token sạch sau khi kiểm tra subkey hợp lệ.
- **Custom Gmail Tool:** Tạo công cụ mẫu gửi email, kiểm tra kết nối tài khoản và hiển thị link Connect nếu chưa liên kết.

## Capabilities

### New Capabilities
- `oauth-click-to-connect`: Tích hợp các luồng OAuth 2.0 per-user, lưu trữ mã hóa token an toàn trong Middleware database và kết nối các MCP tools.

### Modified Capabilities
<!-- No modified capabilities -->

## Impact

- **llm-mw (Middleware):** Thay đổi DB schema, bổ sung các route oauth/integrations và module mã hóa.
- **open-webui:** Tải custom Gmail Tool (Python class) vào giao diện để sử dụng.
