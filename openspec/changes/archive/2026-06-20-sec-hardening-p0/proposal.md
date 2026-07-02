## Why

Hệ thống hiện tại có các lỗ hổng bảo mật và mâu thuẫn cấu hình nghiêm trọng (P0) đe dọa trực tiếp đến an toàn dữ liệu và chi phí vận hành:
1. Thông tin subkey thô (plaintext subkeys) của người dùng được lưu trữ trực tiếp trong cơ sở dữ liệu và mã nguồn, có thể bị lộ nếu rò rỉ database.
2. MCP Postgres đang sử dụng quyền superuser với mật khẩu mặc định hardcoded trong file cấu hình công khai, có nguy cơ bị tấn công Prompt Injection để sửa/xóa cơ sở dữ liệu.
3. Cơ chế mặc định cấp quyền truy cập tất cả model (`["*"]`) cho người dùng mới đăng ký hoặc đồng bộ từ LDAP/SSO dẫn đến nguy cơ bùng nổ chi phí khi họ gọi các model Flagship đắt tiền.
4. Mâu thuẫn về giới hạn tải lên giữa Nginx và OpenWebUI làm đứt gãy trải nghiệm của người dùng khi làm việc với tệp RAG lớn.

## What Changes

- **Bảo mật thông tin Subkey:**
  - Loại bỏ hoàn toàn cột `subkey` (văn bản thô) khỏi bảng `mw_users`.
  - Chỉ lưu trữ, đối khớp và xác thực bằng `subkey_hash` (mã băm HMAC-SHA256).
  - Admin API sinh subkey mới chỉ hiển thị key thô một lần duy nhất khi tạo, sau đó chỉ lưu hash.
- **Bảo mật MCP Postgres:**
  - Tự động tạo role database read-only `mcp_readonly_user` khi khởi động database Middleware.
  - Sử dụng biến môi trường cho database credentials của MCP và sinh file cấu hình `mcp_config.json` thông qua tệp mẫu (template) kết hợp script build trước khi chạy stack.
- **Hạn chế Model mặc định cho User mới:**
  - Thay thế giá trị mặc định `["*"]` bằng danh sách `DEFAULT_ALLOWED_MODELS` (cấu hình trong `.env`, mặc định chỉ cho phép các auto-routing models giá tiêu chuẩn).
- **Khóa mật khẩu mặc định & Bảo mật Test:**
  - Loại bỏ mật khẩu mặc định `YOUR_DB_PASSWORD` trong docker-compose, yêu cầu bắt buộc cấu hình env password (fail fast nếu thiếu).
  - Chuyển thông tin tài khoản test Playwright mặc định sang biến môi trường.
- **Đồng bộ giới hạn dung lượng tải lên:**
  - Đồng bộ giới hạn tối đa của Nginx và OpenWebUI RAG ở mức **500MB** (thay vì Nginx 100MB và RAG 2GB lệch nhau).
- **Đính chính tài liệu RAG:**
  - Cập nhật tài liệu hướng dẫn ghi nhận chính xác Embeddings được gọi thông qua Gemini API (Cloud) chứ không phải local.

## Capabilities

### New Capabilities
- `subkey-security`: Quản lý và xác thực subkey của người dùng hoàn toàn bằng mã băm HMAC-SHA256, loại bỏ lưu trữ plaintext key thô.
- `mcp-security`: Cơ chế phân quyền read-only cho MCP Postgres và bảo mật credentials bằng tệp cấu hình sinh động thông qua template.
- `model-access-restriction`: Giới hạn danh sách model mặc định cho người dùng mới đăng ký hoặc đồng bộ bằng biến môi trường `DEFAULT_ALLOWED_MODELS` thay vì cấp quyền wildcard `["*"]`.
- `config-sync-and-ops`: Đồng bộ hóa cấu hình upload limit (500MB), loại bỏ default password fallback trong Docker và tests.

### Modified Capabilities
*Không có thay đổi về mặt yêu cầu nghiệp vụ đối với các capabilities hiện có.*

## Impact

- **Database:** Bảng `mw_users` sẽ bỏ cột `subkey` (plaintext) và chỉ truy vấn qua `subkey_hash`.
- **API Endpoints:** Middleware endpoints (/health, /v1/chat/completions, /v1/embeddings,...) xác thực hoàn toàn bằng hash. Admin API tạo/sửa user trả về subkey thô duy nhất một lần.
- **MCP Services:** MCP Postgres service sẽ chạy dưới quyền `mcp_readonly_user` và bị chặn tất cả các lệnh ghi dữ liệu.
- **Docker Compose & Nginx:** Yêu cầu cập nhật tệp `.env` với các mật khẩu bắt buộc và đồng bộ dung lượng request body.
- **Kiểm thử Playwright:** Yêu cầu chạy test với các biến môi trường cấu hình sẵn thay vì tài khoản mặc định.
