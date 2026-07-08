## ADDED Requirements

### Requirement: API Endpoint Satisfaction (Đánh giá mức độ hài lòng)
Middleware SHALL cung cấp một API endpoint (`/v1/_mw/admin/analytics/satisfaction`) để lấy dữ liệu tổng hợp về đánh giá của người dùng từ cơ sở dữ liệu của Open WebUI.

#### Scenario: Yêu cầu dữ liệu satisfaction với một khoảng thời gian cụ thể
- **WHEN** một admin gọi endpoint với các tham số query hợp lệ như `minutes` hoặc `start`/`end`
- **THEN** hệ thống SHALL trả về JSON chứa tổng số lượt đánh giá, điểm CSAT, bảng xếp hạng các model và các phản hồi chi tiết (comment/lý do) mới nhất trong khoảng thời gian đó.

### Requirement: Tổng hợp dữ liệu Feedback (Feedback Aggregation)
Middleware SHALL tổng hợp dữ liệu từ bảng `feedback`, ánh xạ `data->>rating = '1'` thành đánh giá tích cực (positive) và `data->>rating = '-1'` thành đánh giá tiêu cực (negative).

#### Scenario: Tổng hợp feedback theo từng model
- **WHEN** xây dựng bảng xếp hạng (leaderboard) các model
- **THEN** hệ thống SHALL nhóm các feedback theo `meta->>model_id`, tính toán tổng số lượt đánh giá tích cực và tổng số lượt đánh giá cho từng model, sau đó sắp xếp giảm dần theo tỷ lệ CSAT.

### Requirement: Tab Satisfaction trên Dashboard
Admin Dashboard SHALL bao gồm một tab chuyên biệt tên là "Satisfaction" (hoặc CSAT) để hiển thị trực quan các phân tích về đánh giá của người dùng.

#### Scenario: Xem tab Satisfaction
- **WHEN** admin bấm vào tab "Satisfaction"
- **THEN** dashboard SHALL hiển thị điểm CSAT tổng quan, bảng xếp hạng model, và một luồng (stream) các bình luận feedback mới nhất.

### Requirement: Tích hợp với Bộ lọc thời gian chung (Global Time Filter)
Phân tích User Satisfaction SHALL phản hồi lại bộ lọc khoảng thời gian chung (Time Range filter) nằm ở thanh menu bên (sidebar) của dashboard.

#### Scenario: Thay đổi bộ lọc khoảng thời gian
- **WHEN** admin chọn một khoảng thời gian khác (ví dụ: "Last 7d") khi đang ở tab Satisfaction
- **THEN** dashboard SHALL tự động làm mới điểm CSAT, bảng xếp hạng và các bình luận mới nhất để phản ánh đúng khung thời gian vừa chọn.
