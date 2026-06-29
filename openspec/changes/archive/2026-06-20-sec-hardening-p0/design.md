## Context

Hệ thống hiện tại có các lỗ hổng P0 về lưu trữ plaintext subkey, hardcoded DB credentials của MCP Postgres, cấu hình mặc định allowed_models có wildcard `["*"]` quá rộng, và mất đồng bộ upload limit giữa Nginx (100MB) và OpenWebUI (2GB).

Tài liệu thiết kế này đưa ra giải pháp kỹ thuật cụ thể để khắc phục toàn bộ vấn đề trên một cách an toàn nhất cho DB Postgres hiện tại.

## Goals / Non-Goals

**Goals:**
- Loại bỏ hoàn toàn plaintext subkey khỏi DB và API. Chỉ lưu trữ mã băm `subkey_hash`.
- Hardening MCP Postgres: sử dụng account read-only và nạp mật khẩu động qua template + env.
- Đổi mặc định `allowed_models` cho người dùng mới thành danh sách có kiểm soát cấu hình qua `DEFAULT_ALLOWED_MODELS` trong `.env`.
- Đồng bộ Nginx client body size và OpenWebUI RAG upload limit về 500MB.
- Loại bỏ các mật khẩu và tài khoản test mặc định (`YOUR_DB_PASSWORD`, `admin@example.com` trong tests).

**Non-Goals:**
- Nâng cấp RAG (Reranker, Citations) - để ở Phase 2.
- Thiết kế OAuth 2.0 Click-to-Connect - để ở Phase 2.
- Thiết kế hệ thống Code Sandbox - để ở Phase 3.

## Decisions

### 1. Database Migration cho `mw_users` (subkey_hash)
- **Quyết định:** Loại bỏ cột `subkey` (plaintext) khỏi bảng `mw_users` để tránh lưu trữ khóa thô.
- **Phương án thực hiện:**
  - Viết logic tự động trong [db.py](file:///d:/Works/openwebui_clone/llm-mw/core/db.py): khi khởi động DB pool, kiểm tra xem cột `subkey` có tồn tại không. Nếu có, thực hiện `ALTER TABLE mw_users DROP COLUMN subkey` (sau khi đã đảm bảo tất cả user hiện tại đều được backfill băm sang cột `subkey_hash` qua script).
  - Cập nhật tất cả các câu lệnh INSERT/UPDATE/SELECT trong [db.py](file:///d:/Works/openwebui_clone/llm-mw/core/db.py) và [auth.py](file:///d:/Works/openwebui_clone/llm-mw/core/auth.py) chỉ truy vấn và lưu trữ cột `subkey_hash`.
- **Lý do lựa chọn:** Đảm bảo an toàn 100% dữ liệu ngay cả khi DB bị leak.

### 2. Thiết lập Database User read-only cho MCP Postgres
- **Quyết định:** Tạo user `mcp_readonly_user` động trên database Middleware khi container khởi động.
- **Phương án thực hiện:**
  - Viết câu lệnh SQL `DO $$ ...` trong hàm `_create_tables()` của [db.py](file:///d:/Works/openwebui_clone/llm-mw/core/db.py) để tự tạo role `mcp_readonly_user` với mật khẩu được chỉ định qua biến môi trường `MCP_DATABASE_PASSWORD`.
  - Cấp các quyền SELECT tối giản trên public schema.
- **Lý do lựa chọn:** Tách biệt đặc quyền tối thiểu (least privilege) cho các MCP clients, bảo vệ DB trước các truy vấn phá hủy từ Prompt Injection.

### 3. Cơ chế sinh File cấu hình `mcp_config.json` động
- **Quyết định:** Sử dụng `mcp_config.template.json` trên host và viết script `scripts/generate_mcp_config.py` để biên dịch ra file thực tế tại thời điểm deploy.
- **Phương án thực hiện:**
  - Script python sẽ đọc `.env`, thay thế `${MCP_POSTGRES_PASSWORD}` hoặc `${POSTGRES_PASSWORD}` trong template và ghi đè ra `mcp_config.json`.
  - Thêm `mcp_config.json` vào `.gitignore`.
- **Lý do lựa chọn:** Giải quyết triệt để vấn đề credentials bị hardcode trong Git mà không cần thay đổi logic container `mcpo` gốc.

### 4. DEFAULT_ALLOWED_MODELS
- **Quyết định:** Thêm cấu hình mặc định mới qua env `DEFAULT_ALLOWED_MODELS` trong `.env`.
- **Phương án thực hiện:**
  - Thay thế fallback `["*"]` trong `config.py`, `auth.py`, `models.py` và `user_admin.py` bằng `DEFAULT_ALLOWED_MODELS` (mặc định trỏ về 5 auto-routing models tiêu chuẩn).
- **Lý do lựa chọn:** Giảm rủi ro bùng nổ chi phí khi có user mới đăng ký.

## Risks / Trade-offs

- **[Risk]** Lỗi mất kết nối đối với các client cũ chưa được cập nhật subkey_hash.
  - *Mitigation:* Chạy một hàm tự động băm (backfill) toàn bộ plaintext subkey hiện có sang `subkey_hash` trước khi drop cột `subkey`.
- **[Risk]** Nginx lỗi 413 (Payload Too Large) khi upload file lớn.
  - *Mitigation:* Tăng đồng thời `client_max_body_size 500M` của Nginx và `RAG_FILE_MAX_SIZE=500` của OpenWebUI.
