## Why

Hiện tại, các phân tích sử dụng và chi phí (Usage & Cost Analytics) trên hệ thống chỉ ở góc nhìn cá nhân (User-centric). Đối với mô hình SaaS dành cho doanh nghiệp, ban quản trị cần góc nhìn theo phòng ban (Team-centric / Group-based) để thực hiện tính phí chéo (chargeback), theo dõi mức độ áp dụng AI (adoption) và cấu hình phân luồng model (routing). Sự kết hợp giữa cơ sở dữ liệu `group` của Open WebUI và `mw_audit_log` của Middleware là cần thiết để hiện thực hóa khả năng này.

## What Changes

- **Thuật toán xác định Primary Group tự động (Zero-Config)**: Xác định nhóm chính của một user bằng cách tự động lấy nhóm có thời gian tham gia sớm nhất (`created_at` nhỏ nhất) từ bảng `group_member` của Open WebUI (Cách A). Hệ thống không yêu cầu thêm bất kỳ cấu hình hay thay đổi schema nào.
- **Backend Analytics API**: Xây dựng endpoint `/v1/_mw/admin/analytics/groups` thực hiện truy vấn chéo (cross-database join) giữa bảng `group`, `group_member` (của Open WebUI) và `mw_audit_log` (của Middleware) để tính toán tổng chi phí, lượng request, và xu hướng sử dụng model theo nhóm.
- **Giao diện Group Analytics**: Thêm tab "Group Analytics" vào Admin Dashboard, cung cấp biểu đồ và bảng xếp hạng chi phí/model theo phòng ban.

## Capabilities

### New Capabilities
- `group-analytics`: Cung cấp khả năng theo dõi và thống kê chi phí, hiệu suất, hành vi sử dụng model theo nhóm (phòng ban). Tích hợp sẵn cơ chế nhận diện tự động nhóm chính (Primary Group) của người dùng dựa trên dữ liệu lịch sử tham gia nhóm.

### Modified Capabilities
- (Không có thay đổi đặc tả cho các tính năng hiện tại)

## Impact

- **Backend API**: Thêm các truy vấn kết hợp giữa hai pool kết nối `db_conn` (Middleware) và `db_ow_conn` (Open WebUI). Không có tác động thay đổi DB Schema.
- **Frontend Layer**: Thay đổi cấu trúc Dashboard tab, bổ sung component biểu đồ nhóm.
