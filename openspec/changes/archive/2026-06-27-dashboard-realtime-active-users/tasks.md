## 1. Backend API Implementation

- [x] 1.1 Viết hàm API `stream_active_users` (SSE) trong file [admin.py](file:///c:/RangDonk/Oppen_Web_UI/llm-mw/api/admin.py) hoặc file mới. Thiết lập generator tính toán số user độc bản trong `mw_pending` và `mw_audit_log` (5 phút gần nhất).
- [x] 1.2 Viết logic fallback đọc file `pending.csv` và `audit.jsonl` khi mất kết nối PostgreSQL.
- [x] 1.3 Đăng ký tuyến đường `GET /v1/_mw/admin/active-users/stream` trong file [main.py](file:///c:/RangDonk/Oppen_Web_UI/llm-mw/main.py) có bảo vệ bởi `require_admin_or_session`.

## 2. Frontend Layout & CSS Styling

- [x] 2.1 Thêm Card "Active Users" (`#cardActiveUsers`) vào khu vực metrics của tab Usage trong file [index.html](file:///c:/RangDonk/Oppen_Web_UI/llm-mw/dashboard/index.html).
- [x] 2.2 Định nghĩa CSS cho Card mới và chấm tròn xanh lá biểu thị trạng thái "Real-time" trong file [dashboard.css](file:///c:/RangDonk/Oppen_Web_UI/llm-mw/dashboard/css/dashboard.css).


## 3. Frontend Client Logic (Javascript)

- [x] 3.1 Tạo file Javascript mới `llm-mw/dashboard/js/active_users.js` để khởi tạo kết nối `EventSource` lắng nghe sự kiện từ backend và cập nhật giá trị vào `#metricActiveUsers`.
- [x] 3.2 Import và kích hoạt kết nối `EventSource` khi dashboard được khởi tạo trong file [main.js](file:///c:/RangDonk/Oppen_Web_UI/llm-mw/dashboard/js/main.js).


## 4. Kiểm thử & Xác thực (Verification)

- [x] 4.1 Gửi request test kết nối SSE endpoint bằng `curl` và kiểm tra cấu trúc gói tin trả về.
- [x] 4.2 Truy cập giao diện Admin Dashboard và xác nhận Card Active Users tự động tăng/giảm thời gian thực khi thực hiện gửi request chat mới từ một tab khác.
