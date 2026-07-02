## ADDED Requirements

### Requirement: Cross-database Group Analytics Aggregation
Backend SHALL cung cấp API endpoint `/v1/_mw/admin/analytics/groups` tổng hợp chi phí, lượng tokens, độ trễ, và số lượng request từ `mw_audit_log` theo Primary Group của các users.

#### Scenario: Fetching group analytics data
- **WHEN** Admin gửi request GET tới `/v1/_mw/admin/analytics/groups` (có mang thông tin xác thực)
- **THEN** Backend trả về danh sách các Group kèm theo tổng số request, chi phí USD, tokens và tỷ lệ sử dụng model của mỗi Group

### Requirement: Automatic Primary Group Resolution
Khi thực hiện tổng hợp dữ liệu, API Backend SHALL tự động xác định Primary Group của một user dựa trên lịch sử gia nhập nhóm từ Open WebUI DB mà không yêu cầu cấu hình.

#### Scenario: User is in multiple Open WebUI groups
- **WHEN** user thuộc nhiều hơn 1 group trong bảng `group_member` của Open WebUI
- **THEN** Primary Group được lấy là group có giá trị `created_at` nhỏ nhất (nhóm gia nhập sớm nhất)

#### Scenario: User is in exactly one group
- **WHEN** user thuộc duy nhất 1 group
- **THEN** Group đó trở thành Primary Group

#### Scenario: User has no groups
- **WHEN** user không có bản ghi nào trong bảng `group_member`
- **THEN** Primary Group của user được định danh bằng nhãn "Uncategorized"

### Requirement: Group Analytics Dashboard UI
Hệ thống SHALL cung cấp tab "Group Analytics" trên Admin Dashboard để trực quan hóa dữ liệu chi phí và hành vi sử dụng model của các phòng ban.

#### Scenario: Viewing Top Spenders by Department
- **WHEN** Admin truy cập tab Group Analytics
- **THEN** Bảng xếp hạng chi phí theo phòng ban (Top Spenders) được hiển thị, sắp xếp theo tổng chi phí USD từ cao đến thấp

#### Scenario: Viewing Model Preferences by Department
- **WHEN** Admin xem thông tin phân tích
- **THEN** Tỷ lệ phân bổ phần trăm của các Model (vd: 60% GPT, 40% Claude) cho từng nhóm được hiển thị dưới dạng biểu đồ hoặc thanh bar CSS
