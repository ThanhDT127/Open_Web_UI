## ADDED Requirements

### Requirement: Admin có thể click vào một nhóm để xem chi tiết (drill-down) hạn mức sử dụng của người dùng trong nhóm đó
Hệ thống PHẢI cung cấp một API và giao diện UI cho phép quản trị viên xem chi tiết hạn mức (quota) đã sử dụng của từng người dùng thuộc một nhóm cụ thể. Dữ liệu này phải được áp dụng cùng bộ lọc thời gian đang được thiết lập trên toàn cục của dashboard. Bảng dữ liệu phụ (chứa danh sách users) PHẢI tái sử dụng cơ chế cuộn chuột (scroll) giống với bảng User Quota Management để tránh làm giao diện bị kéo giãn quá mức khi một nhóm có quá nhiều thành viên.

#### Scenario: Xem chi tiết (drill-down) thành công qua giao diện UI
- **WHEN** admin click vào một dòng nhóm (group row) trong bảng Group Analytics
- **THEN** hệ thống gọi API lấy dữ liệu phân tích từng người dùng cho nhóm đó và mở rộng một bảng phụ (dạng accordion) hiển thị các chỉ số sử dụng của từng người dùng trong khoảng thời gian đã chọn.

#### Scenario: Cuộn chuột trên danh sách user đông đúc
- **WHEN** bảng phụ mở ra một danh sách chứa rất nhiều người dùng (users)
- **THEN** bảng phụ sẽ hiển thị thanh cuộn chuột (scroll bar) bên trong một vùng không gian giới hạn chiều cao (max-height), tái sử dụng class CSS của bảng User Quota Management.
