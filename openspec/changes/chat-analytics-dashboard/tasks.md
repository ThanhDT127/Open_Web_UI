## 1. Backend API (Middleware)

- [x] 1.1 Tạo file module mới `llm-mw/api/analytics.py`.
- [x] 1.2 Viết hàm `_get_ow_usage(time_range)` để query số lượng tin nhắn và số lượng chat từ DB của Open WebUI (`db_ow_conn`).
- [x] 1.3 Viết hàm `_get_mw_cost(time_range)` để query số lượng token và chi phí USD từ DB của Middleware (`db_conn`).
- [x] 1.4 Mở endpoint `GET /v1/_mw/admin/analytics/chat` để gộp và trả về cả 2 tập dữ liệu trên (được gom nhóm theo thời gian, ví dụ: theo ngày).
- [x] 1.5 Đăng ký Router `analytics` vào trong file `llm-mw/main.py`.

## 2. Frontend (Dashboard)

- [x] 2.1 Thêm tab "Chat Analytics" vào `llm-mw/dashboard/index.html`.
- [x] 2.2 Xây dựng UI skeleton cho tab mới: các thẻ số liệu tổng quan (Chats, Messages, Tokens, Cost).
- [x] 2.3 Thêm bảng Leaderboard hiển thị Top Users theo cost.
- [x] 2.4 Tạo file `llm-mw/dashboard/js/analytics.js` để fetch data từ API vừa tạo.
- [x] 2.5 Sử dụng Chart.js (đã có sẵn) để vẽ biểu đồ line chart: Trục tung thứ nhất (Volume), Trục tung thứ hai (Cost USD).
- [x] 2.6 Tích hợp `analytics.js` vào file điều hướng `main.js`.

## 3. Bug Fixes (Phase 2)
- [x] 3.1 Fix B1+B2: Backend — JOIN bảng `user` (OW) để resolve UUID → email, merge đúng dữ liệu
- [x] 3.2 Fix B3: Frontend — Thêm time range filter riêng cho tab Analytics (24h/7d/30d/all)
- [x] 3.3 Fix B4: Backend — GROUP BY hour khi time_range=24h thay vì GROUP BY date

## 4. New Features (Phase 2)
- [x] 4.1 Backend — Thêm `_get_hourly_activity()` query (Hourly Activity)
- [x] 4.2 Backend — Thêm `_get_model_breakdown()` query (Model Breakdown)
- [x] 4.3 Backend — Thêm `active_users` count vào totals
- [x] 4.4 Frontend — Thêm Hourly Activity bar chart (giống OW Analytics)
- [x] 4.5 Frontend — Thêm Model Breakdown doughnut chart + Top Models table
- [x] 4.6 Frontend — Thêm Active Users metric card
- [x] 4.7 Frontend — Cải thiện Leaderboard (email/name, Cost Share %)
