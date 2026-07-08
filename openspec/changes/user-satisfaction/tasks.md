## 1. Backend API

- [x] 1.1 Thêm endpoint `/v1/_mw/admin/analytics/satisfaction` vào `llm-mw/api/analytics.py` (hoặc tạo một file route riêng `satisfaction.py`).
- [x] 1.2 Viết truy vấn SQL để lấy và tổng hợp tổng số feedback tích cực/tiêu cực, tính toán điểm CSAT, và gom nhóm theo `model_id`.
- [x] 1.3 Viết truy vấn SQL để lấy 50 phản hồi mới nhất (bao gồm bình luận, lý do và thông tin người dùng).
- [x] 1.4 Tích hợp logic `_time_boundaries` để API nhận diện đúng các tham số query `minutes` hoặc `start`/`end`.

## 2. Frontend Structure & Setup (Cấu trúc & Cài đặt Frontend)

- [x] 2.1 Thêm nút tab "⭐ Satisfaction" vào phần header trong `llm-mw/dashboard/index.html`.
- [x] 2.2 Thêm cấu trúc HTML tương ứng cho vùng chứa `div#satisfactionTab` trong `llm-mw/dashboard/index.html`.
- [x] 2.3 Tạo file `llm-mw/dashboard/js/satisfaction.js` để xử lý việc fetch dữ liệu CSAT và render lên giao diện (DOM).
- [x] 2.4 Cập nhật file `llm-mw/dashboard/js/main.js` để import `refreshSatisfaction` và export nó vào `window.dashboardAPI`.
- [x] 2.5 Cập nhật file `llm-mw/dashboard/js/tabs.js` để tự động gọi `refreshSatisfaction()` khi người dùng chọn tab Satisfaction.

## 3. Frontend Implementation & Integration (Triển khai & Tích hợp Frontend)

- [x] 3.1 Viết code render giao diện cho phần hiển thị điểm CSAT tổng quan và tổng lượt bình chọn trong `satisfaction.js`.
- [x] 3.2 Viết code render giao diện cho Bảng xếp hạng Model (Model Leaderboard table) trong `satisfaction.js`.
- [x] 3.3 Viết code render giao diện cho Luồng phản hồi gần đây (hiển thị bình luận, lý do và thông tin user) trong `satisfaction.js`.
- [x] 3.4 Đảm bảo hàm `window.dashboardAPI.refreshSatisfaction()` được gọi bên trong `setTimeRange` và `applyCustomRange` của `filters.js` để đồng bộ dữ liệu với bộ lọc thời gian chung.

## 4. Testing & Polish (Kiểm thử & Hoàn thiện)

- [x] 4.1 Kiểm tra để đảm bảo dữ liệu CSAT được tổng hợp chính xác cho nhiều khoảng thời gian khác nhau (1h, 24h, 7d).
- [x] 4.2 Kiểm tra bố cục (layout) và các style CSS cho tab Satisfaction để đảm bảo đồng bộ thẩm mỹ với toàn bộ dashboard.
- [x] 4.3 Đảm bảo không xảy ra lỗi SQL hoặc exception khi các trường thông tin người dùng bị thiếu (ví dụ: đối với người dùng đã bị xóa tài khoản).
