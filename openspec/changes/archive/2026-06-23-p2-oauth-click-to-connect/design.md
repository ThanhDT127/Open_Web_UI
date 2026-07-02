## Context

OpenWebUI chạy độc lập với tài khoản người dùng, không cho phép lưu trữ riêng credentials cho từng nhân viên để sử dụng cho MCP tools. Chúng ta thiết kế cổng OAuth 2.0 tập trung tại Middleware, nơi quản lý vòng đời token, thực hiện làm mới (refresh token) và mã hóa an toàn.

## Goals / Non-Goals

**Goals:**
- Tạo bảng cơ sở dữ liệu `mw_user_integrations` trong PostgreSQL.
- Tạo module mã hóa `crypto.py` trong `llm-mw/utils/` sử dụng AES-256.
- Tạo endpoints `/v1/_mw/oauth/connect` và `/v1/_mw/oauth/callback` trong Middleware.
- Tạo endpoint `/v1/_mw/integrations/get_token` để trả về token sạch cho OpenWebUI Custom Tools.

**Non-Goals:**
- Không lưu trữ credentials dưới dạng plaintext.
- Không thay đổi mã nguồn Svelte/TypeScript gốc của OpenWebUI.

## Decisions

### Mã hóa Token bằng AES-256 (CBC/GCM)
- **Lựa chọn:** Dùng thư viện `cryptography` của Python để thực hiện mã hóa AES-256. Khóa mã hóa `MW_SECRET` được lấy từ tệp `.env`.
- **Lý do:** Đảm bảo tính toàn vẹn và bảo mật dữ liệu của người dùng cuối. Ngay cả khi database bị tấn công SQL Injection hoặc lộ tệp backup, dữ liệu token vẫn được an toàn.

### Click-to-Connect URL trong Tool Response
- **Lựa chọn:** Khi tool phát hiện chưa có token, nó trả về nội dung Markdown có chứa thẻ link trỏ tới endpoint `/v1/_mw/oauth/connect?provider={provider}&subkey={subkey}`.
- **Lý do:** Điều này cung cấp trải nghiệm click-to-connect trực quan ngay trong khung chat mà không cần sửa đổi mã nguồn frontend của OpenWebUI.

## Risks / Trade-offs

- **[Risk] Hết hạn Token (Token Expiry):** Google/GitHub Access Tokens có thời hạn ngắn (thường là 1 giờ).
  - *Mitigation:* Lưu trữ cả `refresh_token` và tự động gọi API làm mới (refresh flow) trong endpoint `/v1/_mw/integrations/get_token` nếu token hiện tại hết hạn hoặc chuẩn bị hết hạn (trong vòng 5 phút).
