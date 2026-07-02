# config-sync-and-ops Specification

## Purpose
TBD - created by archiving change sec-hardening-p0. Update Purpose after archive.
## Requirements
### Requirement: Docker Compose fail-fast configuration
Hệ thống SHALL cấu hình docker-compose để từ chối chạy (fail fast) nếu thiếu các biến môi trường mật khẩu bí mật (Postgres password, LiteLLM keys) trong tệp `.env`. Mật khẩu mặc định thô `YOUR_DB_PASSWORD` MUST bị loại bỏ khỏi mọi giá trị mặc định của docker-compose.

#### Scenario: Running docker-compose without password env variable
- **WHEN** Admin chạy lệnh `docker compose up` mà chưa cấu hình biến `POSTGRES_PASSWORD` trong tệp `.env`
- **THEN** Docker Compose dừng tiến trình lập tức và trả về lỗi thông báo thiếu biến môi trường bắt buộc.

### Requirement: Secure test credentials
Hệ thống SHALL loại bỏ các tài khoản và mật khẩu kiểm thử mặc định thô (`admin@example.com` / `Testcus1234`) ra khỏi mã nguồn kiểm thử. Các kiểm thử tự động MUST sử dụng các biến môi trường cấu hình sẵn.

#### Scenario: Running Playwright tests in CI/CD or local
- **WHEN** tiến trình CI/CD kích hoạt chạy kiểm thử Playwright
- **THEN** test runner đọc thông tin đăng nhập từ `process.env.TEST_ADMIN_EMAIL` và `TEST_ADMIN_PASSWORD` (nếu thiếu, kiểm thử MUST dừng và báo lỗi cấu hình).

### Requirement: Synchronized upload limit
Hệ thống SHALL đồng bộ giới hạn dung lượng tải lên tối đa ở cả Nginx (`client_max_body_size`) và OpenWebUI (`RAG_FILE_MAX_SIZE`) ở mức **500MB**.

#### Scenario: Uploading a file within 500MB limit
- **WHEN** user tải lên tệp tài liệu dung lượng 150MB
- **THEN** Nginx cho phép request đi qua và OpenWebUI tiếp nhận tệp để thực hiện trích xuất dữ liệu thành công.

