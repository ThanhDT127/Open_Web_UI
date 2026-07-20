## Lý do (Why)

Quản trị viên cần cái nhìn tổng quan về cả hoạt động của người dùng và chi phí tài chính đi kèm. Hiện tại, Open WebUI chỉ theo dõi lượng chat (không biết chi phí), còn Middleware thì theo dõi chi phí (nhưng không có giao diện chat trực quan). Một Dashboard Chat Analytics hợp nhất sẽ cung cấp "một màn hình duy nhất" để hiểu cả hành vi chat (số lượng) và chi phí (tiền bạc).

## Thay đổi những gì (What Changes)

- Thêm trang "Chat Analytics" vào Middleware Admin Dashboard.
- Cung cấp số liệu tổng quát cho số lượng chat và tin nhắn (Lấy từ Database Open WebUI).
- Cung cấp số liệu tổng quát cho chi phí USD và lượng Token (Lấy từ Database Middleware).
- Trực quan hóa mức độ sử dụng và chi phí theo thời gian trên cùng một biểu đồ (dual-axis chart).
- Tạo Bảng xếp hạng (Leaderboards) cho Top Users (theo số tiền tiêu và lượng chat) và Top Models.
- Cho phép lọc dữ liệu theo thời gian (ví dụ: 24h, 7 ngày, 30 ngày).

## Chức năng (Capabilities)

### Chức năng mới
- `chat-analytics`: Tổng hợp và trực quan hóa lượng chat, lượng token tiêu thụ và chi phí trên Admin Dashboard.

### Chức năng thay đổi
- (Không có)

## Mức độ ảnh hưởng (Impact)

- **Backend:** Thêm API mới trong `llm-mw/api/` (ví dụ: `analytics.py`) để chạy các câu query gộp trên cả 2 kết nối `db_conn` và `db_ow_conn`.
- **Frontend:** Thêm các thành phần HTML/JS mới trên dashboard để vẽ biểu đồ (dùng Chart.js hoặc tương đương) và bảng xếp hạng.
- **Dependencies:** Có thể cần cài thêm một thư viện vẽ biểu đồ nhẹ gọn ở frontend.
