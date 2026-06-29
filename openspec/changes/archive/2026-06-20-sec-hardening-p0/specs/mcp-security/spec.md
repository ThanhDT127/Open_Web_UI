## ADDED Requirements

### Requirement: Postgres MCP read-only privileges
Hệ thống SHALL tạo và cấu hình một DB user read-only `mcp_readonly_user` cho Postgres MCP server. User này MUST chỉ được phép thực hiện câu lệnh SELECT trên schema public và không được phép ghi hay sửa đổi cơ sở dữ liệu.

#### Scenario: Running a safe SELECT query via MCP
- **WHEN** AI Agent thực thi công cụ MCP Postgres để chạy câu lệnh `SELECT * FROM mw_prices`
- **THEN** hệ thống trả về kết quả truy vấn thành công.

#### Scenario: Running a destructive query via MCP
- **WHEN** AI Agent thực thi công cụ MCP Postgres để chạy câu lệnh `DROP TABLE mw_users` hoặc `DELETE FROM mw_users`
- **THEN** Postgres DB trả về lỗi từ chối quyền truy cập (Permission Denied) và chặn đứng hành động phá hủy dữ liệu.

### Requirement: Dynamic MCP configuration generation
Hệ thống SHALL lưu trữ cấu hình MCP trong tệp mẫu `mcp_config.template.json` có chứa placeholder cho mật khẩu. Tệp cấu hình thực tế `mcp_config.json` MUST được sinh tự động bằng script Python kết hợp biến môi trường và MUST nằm trong danh sách bỏ qua của Git (.gitignore).

#### Scenario: Deploying MCP server
- **WHEN** quản trị viên khởi chạy stack thông qua docker-compose
- **THEN** script Python chạy trước để điền mật khẩu từ env vào `mcp_config.json` và container `mcpo` nạp tệp cấu hình động này an toàn.
