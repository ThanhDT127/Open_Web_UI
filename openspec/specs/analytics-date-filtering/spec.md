## ADDED Requirements

### Requirement: Áp dụng bộ lọc thời gian toàn cục cho API Group Analytics
Hệ thống PHẢI đảm bảo rằng API Group Analytics (`/v1/_mw/admin/analytics/groups`) nhận và tuân thủ các tham số lọc thời gian chuẩn (`minutes`, `start`, `end`) được gửi từ giao diện dashboard, thay vì sử dụng độ trễ thời gian (date offset) được code cứng (hardcoded) như trước đây.

#### Scenario: Bộ lọc thời gian được áp dụng từ UI
- **WHEN** admin chọn một mốc thời gian cụ thể (ví dụ: Last 7 Days) trên giao diện dashboard
- **THEN** hệ thống gọi lại API Group Analytics kèm theo tham số thời gian đã chọn, và API lọc chính xác audit logs trong khoảng thời gian đó bằng cách sử dụng hàm `_time_boundaries`.
