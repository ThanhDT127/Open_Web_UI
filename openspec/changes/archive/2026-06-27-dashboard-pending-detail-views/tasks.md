## 1. Backend API Implementation

- [x] 1.1 Tạo hàm API `list_pending` và `force_remove_pending` trong file [admin.py](file:///c:/RangDonk/Oppen_Web_UI/llm-mw/api/admin.py) với xác thực `require_admin_or_session`.
- [x] 1.2 Đăng ký 2 API mới trong file [main.py](file:///c:/RangDonk/Oppen_Web_UI/llm-mw/main.py):
  - `GET /v1/_mw/admin/pending`
  - `DELETE /v1/_mw/admin/pending/{request_id}`

## 2. Giao diện Frontend Layout

- [x] 2.1 Cập nhật card hiển thị Pending (`#metricPending`) trong file [index.html](file:///c:/RangDonk/Oppen_Web_UI/llm-mw/dashboard/index.html) để hỗ trợ click mở Modal và thay đổi thuộc tính CSS (thêm pointer cursor và hover background).
- [x] 2.2 Thêm Modal HTML cấu trúc `#pendingModal` trong [index.html](file:///c:/RangDonk/Oppen_Web_UI/llm-mw/dashboard/index.html) chứa:
  - Header với tiêu đề "Active Pending Requests" và nút đóng ✕.
  - Body chứa bảng danh sách pending (Request ID, User, Model, Endpoint, Time, Actions).
  - Footer chứa nút đóng hoặc nút dọn dẹp hàng loạt.

## 3. Frontend Logic (Javascript)

- [x] 3.1 Viết logic xử lý sự kiện click Card, gọi API lấy danh sách, tính toán thời gian Elapsed (trôi qua bao lâu) và render động dữ liệu bảng trong file [usage.js](file:///c:/RangDonk/Oppen_Web_UI/llm-mw/dashboard/js/usage.js) (hoặc tạo file js mới).
- [x] 3.2 Viết hàm gọi API đối soát (`POST /admin/reconcile`) và API xóa ép buộc (`DELETE /v1/_mw/admin/pending/{id}`) khi người dùng click vào các nút tương ứng.
- [x] 3.3 Đồng bộ lại danh sách pending trên giao diện sau khi đối soát hoặc xóa kẹt thành công.

## 4. Kiểm thử & Xác thực (Verification)

- [x] 4.1 Tạo dữ liệu kẹt giả lập trong PostgreSQL:
  ```sql
  INSERT INTO mw_pending (request_id, user_id, ts) VALUES ('test-stuck-rid-123', 'admin', 1774880900);
  INSERT INTO mw_audit_log (ts, rid, user_id, endpoint, model, status) VALUES (now(), 'test-stuck-rid-123', 'admin', '/v1/chat/completions', 'gemini-2.5-flash', 'pending');
  ```
- [x] 4.2 Mở Admin Dashboard, bấm vào Card Pending, kiểm tra bảng dữ liệu hiển thị đúng thông tin của record giả lập.
- [x] 4.3 Nhấn nút **Force Clear** (thùng rác), kiểm tra xem dòng đó có biến mất khỏi giao diện và database hay không.
