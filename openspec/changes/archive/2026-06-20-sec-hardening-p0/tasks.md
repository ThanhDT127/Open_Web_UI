## 1. Thiết lập Git & Môi trường

- [x] 1.1 Sửa đổi `.gitignore` để bỏ qua đúng tệp `llm-mw/data/users.json`, `llm-mw/data/users.local.json`, `llm-mw/data/backup/` và `mcp_config.json`.
- [x] 1.2 Chạy lệnh git cache để xóa `users.json` khỏi Git tracking (`git rm --cached llm-mw/data/users.json`).

## 2. Bảo mật thông tin Subkey (Băm mật khẩu)

- [x] 2.1 Cập nhật `_SCHEMA_SQL` của bảng `mw_users` trong `llm-mw/core/db.py` để loại bỏ cột `subkey` (plaintext).
- [x] 2.2 Viết đoạn SQL tự động di trú (Migration) trong `_create_tables()` của `llm-mw/core/db.py` để thực hiện `ALTER TABLE mw_users DROP COLUMN IF EXISTS subkey` sau khi đã backfill dữ liệu băm.
- [x] 2.3 Cập nhật các hàm `_load_users_db`, `_save_users_db`, `create_user_db`, `get_user_by_id_db`, `get_user_by_openwebui_id_db` và `_row_to_user_dict` trong `llm-mw/core/db.py` để loại bỏ cột `subkey`.
- [x] 2.4 Sửa đổi `llm-mw/core/auth.py`: Hàm `_find_user_db` chỉ đối khớp bằng `subkey_hash`, loại bỏ so sánh bằng `subkey` thô.
- [x] 2.5 Sửa đổi `llm-mw/api/user_admin.py` tại endpoint `create_user` và `rotate_user_key`: chỉ sinh subkey thô và trả về cho client duy nhất một lần trong API response, chỉ lưu hash vào database.

## 3. Hardening Postgres MCP Server

- [x] 3.1 Viết đoạn SQL tự động tạo role database read-only `mcp_readonly_user` trong hàm `_create_tables()` của `llm-mw/core/db.py` với mật khẩu lấy từ biến môi trường `MCP_DATABASE_PASSWORD`.
- [x] 3.2 Cấp các quyền tối giản `SELECT ON ALL TABLES` cho `mcp_readonly_user` trên database Middleware.
- [x] 3.3 Tạo tệp cấu hình mẫu `mcp_config.template.json` ở thư mục gốc của dự án chứa placeholder `${MCP_POSTGRES_PASSWORD}` cho Postgres connection.
- [x] 3.4 Viết script Python `scripts/generate_mcp_config.py` đọc tệp `.env` và thay thế placeholder để sinh ra tệp cấu hình thực tế `mcp_config.json` khi chạy stack.

## 4. Giới Hạn Model Mặc Định (DEFAULT_ALLOWED_MODELS)

- [x] 4.1 Thêm biến môi trường `DEFAULT_ALLOWED_MODELS` vào [config.py](file:///d:/Works/openwebui_clone/llm-mw/config.py) với giá trị mặc định là danh sách các auto-routing models.
- [x] 4.2 Cập nhật `llm-mw/core/auth.py` và `llm-mw/api/models.py` thay thế giá trị mặc định `["*"]` bằng `DEFAULT_ALLOWED_MODELS`.
- [x] 4.3 Cập nhật `llm-mw/api/user_admin.py` thay thế default allowed models của `CreateUserRequest` và `UpdateUserRequest` bằng `DEFAULT_ALLOWED_MODELS`.

## 5. Khóa mật khẩu mặc định & Bảo mật Test

- [x] 5.1 Sửa đổi [docker-compose.yml](file:///d:/Works/openwebui_clone/docker-compose.yml): loại bỏ hoàn toàn default fallback password `YOUR_DB_PASSWORD`, dùng định dạng bắt buộc env `${POSTGRES_PASSWORD:?Required}`.
- [x] 5.2 Sửa đổi các tệp kiểm thử `tests/auth.spec.ts` và `tests/rag.spec.ts` loại bỏ default test credentials (`admin@example.com` / `Testcus1234`), thay bằng đọc từ env và báo lỗi nếu thiếu.

## 6. Đồng Bộ Upload Limits & Cập nhật Tài liệu

- [x] 6.1 Cập nhật `nginx/nginx.conf`: sửa `client_max_body_size` thành `500M`.
- [x] 6.2 Cập nhật `docker-compose.yml`: sửa `RAG_FILE_MAX_SIZE=500` cho open-webui service.
- [x] 6.3 Sửa đổi tài liệu hướng dẫn RAG trong `docs/` làm rõ việc embedding được thực hiện thông qua Gemini API (Cloud) dưới sự kiểm soát của Middleware.

## 7. Xác Minh & Kiểm Thử

- [x] 7.1 Chạy lệnh `docker compose config` kiểm tra cú pháp và tính bắt buộc của các biến môi trường mật khẩu trong `.env`.
- [x] 7.2 Chạy script biên dịch toàn bộ code Python của Middleware để kiểm tra lỗi cú pháp.
- [x] 7.3 Xác minh băm subkey: kiểm tra DB Postgres xem cột `subkey` đã bị drop chưa và đăng nhập thử bằng key mới.
- [x] 7.4 Xác minh phân quyền MCP Postgres: Chạy lệnh SELECT qua tool MCP Postgres thành công, và chạy câu lệnh DROP/DELETE bị từ chối quyền (Permission Denied).
