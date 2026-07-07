## Ngữ cảnh (Context)

Hệ thống hiện tại đang thiếu một giao diện hợp nhất để Admin theo dõi cả mức độ sử dụng AI (số lượng chat/tin nhắn) và chi phí AI (Tiền USD/Token). Open WebUI có sẵn trang Analytics để đo lượng dùng nhưng không biết giá tiền. Middleware thì theo dõi tiền trong `mw_audit_log` nhưng lại không có giao diện thân thiện.

## Mục tiêu / Ngoài phạm vi

**Mục tiêu:**
- Cung cấp một dashboard hợp nhất hiển thị cả mức sử dụng (từ Open WebUI) và chi phí (từ Middleware).
- Cho phép lọc theo khoảng thời gian (24h, 7 ngày, 30 ngày).
- Hiển thị Bảng xếp hạng top users (theo số tiền và số lượng chat).

**Ngoài phạm vi (Non-Goals):**
- KHÔNG cố gắng khớp chính xác một `chat_id` bên Open WebUI với một dòng chi phí bên Middleware (Phương pháp Decoupled analytics).
- KHÔNG xây dựng lại toàn bộ trang Analytics có sẵn của Open WebUI; chúng ta chỉ mang những chỉ số quan trọng (số đếm) sang để hiển thị cạnh chi phí.

## Quyết định thiết kế (Decisions)

1. **Phân tích Độc lập (Decoupled Analytics - Không cố khớp Chat ID):**
   - *Quyết định:* Không cố gắng can thiệp để nhét `chat_id` từ Open WebUI vào bảng `mw_audit_log` của Middleware.
   - *Lý do:* Việc cố gắng liên kết các request API độc lập (stateless) với các phiên chat (stateful) rất dễ lỗi và đòi hỏi phải sửa core của Open WebUI. Thay vào đó, ta gom nhóm cả 2 tập dữ liệu theo `user_id` và `timestamp`. Cách này vẫn giải quyết được bài toán (biết ai tiêu bao nhiêu, khi nào) mà không gây gánh nặng kỹ thuật.
2. **Lớp API Tổng hợp (API Aggregation Layer):**
   - *Quyết định:* Xây dựng endpoint mới `GET /v1/_mw/admin/analytics/chat` trên Middleware.
   - *Lý do:* Middleware hiện đã có sẵn kết nối Read-Only (`db_ow_conn`) tới DB của Open WebUI và DB của chính nó (`db_conn`). Endpoint này sẽ chạy lệnh `GROUP BY` trên cả 2 DB và trả về một file JSON gộp chung.
3. **Triển khai Giao diện (UI Implementation):**
   - *Quyết định:* Tích hợp Chart.js vào Middleware Admin Dashboard hiện tại (`dashboard/index.html`).
   - *Lý do:* Tránh việc phải dùng công cụ bên ngoài như Grafana, giữ nguyên trải nghiệm "All-in-one" (tất cả trong một) tự host.

## Rủi ro / Đánh đổi (Risks / Trade-offs)

- [Rủi ro] **Hiệu suất query gom nhóm trên DB lớn:** Chạy lệnh `GROUP BY` trên hàng triệu dòng trong bảng `mw_audit_log` hoặc `message` có thể bị chậm.
  - *Khắc phục:* Đảm bảo đã đánh index cho cột `timestamp` và `user_id` ở cả 2 database. Trong Phiên bản 1 (V1), ta sẽ dựa vào tốc độ aggregation gốc của DB. Nếu sau này bị nghẽn, ta sẽ tính đến phương án chạy Cron jobs để tính toán trước.
