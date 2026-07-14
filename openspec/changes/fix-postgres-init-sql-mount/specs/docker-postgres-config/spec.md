## ADDED Requirements

### Requirement: Cấu hình mount path cho pgvector init SQL
Dịch vụ postgres trong file [docker-compose.yml](file:///d:/Works/openwebui_clone/docker-compose.yml) MUST mount chính xác file khởi tạo SQL của pgvector từ thư mục `scripts/sql/` vào thư mục khởi tạo cơ sở dữ liệu của container.

#### Scenario: Kiểm tra đường dẫn volume mount của Postgres
- **WHEN** Hệ thống chạy lệnh `docker compose up` để khởi động các container dịch vụ
- **THEN** Container `openwebui-postgres` SHALL liên kết file host cục bộ tại đường dẫn `./scripts/sql/init_pgvector.sql` vào file `/docker-entrypoint-initdb.d/init.sql` trong container dưới dạng chỉ đọc (read-only)
