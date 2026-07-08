## 1. Backend Core & API

- [x] 1.1 Viết hàm logic `resolve_primary_group()`: Truy vấn bảng `group_member` từ kết nối Open WebUI DB để trích xuất group cũ nhất (theo `created_at`) cho mỗi user.
- [x] 1.2 Xây dựng thuật toán In-Memory Join: Lấy danh sách ánh xạ `user_id -> primary_group` đã lọc ở trên, sau đó gộp với kết quả truy vấn tổng (`cost`, `tokens`) từ `mw_audit_log` của Middleware.
- [x] 1.3 Tạo endpoint `GET /v1/_mw/admin/analytics/groups` trả về chuỗi JSON chứa phân tích nhóm (tổng chi phí, request, độ trễ trung bình, tỷ trọng sử dụng model).

## 2. Frontend: Group Analytics Dashboard

- [x] 2.1 Thiết kế và chèn UI tab "Group Analytics" vào file `llm-mw/dashboard/index.html`.
- [x] 2.2 Viết logic JavaScript mới (ví dụ: `group_analytics.js`) để fetch dữ liệu từ API `/v1/_mw/admin/analytics/groups`.
- [x] 2.3 Tích hợp thư viện biểu đồ hoặc HTML/CSS để hiển thị trực quan "Bảng xếp hạng Top Spenders" và "Tỷ lệ Model Preferences" theo từng phòng ban.
- [x] 2.4 Cập nhật thanh điều hướng `tabs.js` để Admin có thể click mở tab Group Analytics.
