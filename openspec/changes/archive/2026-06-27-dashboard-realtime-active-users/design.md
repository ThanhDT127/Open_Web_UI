## Context

Hệ thống hiện tại thu thập và đối soát quota người dùng dựa trên middleware kết nối PostgreSQL. Để nâng cao tính trực quan cho Admin Dashboard, chúng ta cần theo dõi số lượng người dùng hoạt động trong thời gian thực (Active Users) mà không gây ảnh hưởng lớn đến hiệu năng server (như việc liên tục gửi HTTP polling).

## Goals / Non-Goals

**Goals:**
- Hiển thị số lượng Active Users thời gian thực trên Admin Dashboard.
- Sử dụng kết nối Server-Sent Events (SSE) để tối ưu hóa hiệu năng truyền dữ liệu.
- Thiết lập cơ chế fallback khi PostgreSQL mất kết nối bằng cách đếm từ file log dự phòng.

**Non-Goals:**
- Theo dõi lịch sử chi tiết hành vi di chuyển chuột hoặc hoạt động chi tiết của từng user trên frontend (chỉ theo dõi dựa trên hoạt động gửi request).
- Đồng bộ danh sách người dùng với database của Open WebUI ở giai đoạn này.

## Decisions

### 1. Sử dụng Server-Sent Events (SSE) thay vì WebSockets hay Polling
- **Lựa chọn**: Sử dụng API `StreamingResponse` của FastAPI để tạo kết nối SSE.
- **Lý do**: SSE nhẹ nhàng, truyền một chiều từ Server về Client (phù hợp với việc chỉ đẩy số lượng active users), tự động kết nối lại khi đứt mạng qua đối tượng `EventSource` của trình duyệt. Nó đơn giản hơn WebSockets (không cần giao thức ws://) và tối ưu hơn Polling (tránh gửi hàng nghìn request lặp lại).
- **Lựa chọn thay thế**:
  - *Polling (2s/lần)*: Dễ làm nhưng tạo tải vô ích lên database và API server.
  - *WebSockets*: Quá phức tạp và dư thừa vì ta không cần truyền dữ liệu ngược từ Client lên Server qua kết nối này.

### 2. Công thức và Câu lệnh SQL xác định Active Users
- **Lựa chọn**: 
  1. Quét danh sách `user_id` độc bản đang nằm trong hàng chờ `mw_pending` (đang xử lý request).
  2. Quét danh sách `user_id` độc bản có request kết thúc thành công (`status` là `'ok'` hoặc `'reconciled'`) trong vòng 5 phút qua trong bảng `mw_audit_log`.
  3. Gộp 2 danh sách và đếm số lượng user độc bản.
- **SQL Query**:
  ```sql
  WITH active_pending AS (
      SELECT DISTINCT user_id FROM mw_pending
  ),
  active_recent AS (
      SELECT DISTINCT user_id FROM mw_audit_log 
      WHERE ts >= now() - interval '5 minutes' AND status IN ('ok', 'reconciled')
  )
  SELECT count(DISTINCT user_id) FROM (
      SELECT user_id FROM active_pending
      UNION
      SELECT user_id FROM active_recent
  ) combined;
  ```
- **Fallback (Khi mất kết nối DB)**:
  - Đọc và lấy ra các `user_id` độc bản từ file `pending.csv`.
  - Đọc ngược file `audit.jsonl` từ cuối lên, lọc ra các bản ghi có timestamp trong vòng 5 phút qua và trạng thái thành công, trích xuất `user_id` độc bản.
  - Gộp chung và trả về kết quả đếm.

### 3. Thiết kế luồng truyền nhận SSE
- Endpoint: `GET /v1/_mw/admin/active-users/stream`
- Trình tạo sự kiện (Generator):
  - Lần kết nối đầu tiên: Gửi ngay số lượng active users hiện tại.
  - Định kỳ mỗi 5 - 10 giây (hoặc khi có thay đổi trạng thái pending/audit log): Tính toán lại và đẩy số lượng mới nếu có thay đổi.
  - Gửi tín hiệu giữ nhịp (ping/keep-alive comment) để tránh bị Proxy/Nginx ngắt kết nối do chạy timeout.

## Risks / Trade-offs

- **[Risk] Kết nối SSE bị treo hoặc rò rỉ bộ nhớ (Connection leak)**
  - *Mitigation*: Phía backend cần lắng nghe tín hiệu ngắt kết nối từ Client (`await request.is_disconnected()`) để đóng Generator và dọn dẹp các luồng chạy ngầm ngay lập tức.
- **[Risk] Nginx ngắt kết nối do quá hạn (Timeout)**
  - *Mitigation*: Đảm bảo cấu hình HTTP Header `X-Accel-Buffering: no` và gửi định kỳ comment `: ping` để giữ cho kết nối luôn mở.
