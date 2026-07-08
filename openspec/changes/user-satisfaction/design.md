## Context (Bối cảnh)

Nền tảng Open WebUI lưu trữ các đánh giá của người dùng về câu trả lời của mô hình AI, bao gồm xếp hạng (thumbs up/down) và phản hồi định tính (bình luận và lý do) vào bảng `feedback`. Tuy nhiên, các admin hiện tại chưa có công cụ để xem dữ liệu này trên dashboard. Việc xây dựng một dashboard theo dõi Mức độ hài lòng của người dùng (CSAT) sẽ cung cấp cho admin những thông tin hữu ích về hiệu suất của các mô hình và trải nghiệm của người dùng.

## Goals / Non-Goals (Mục tiêu / Ngoài phạm vi)

**Goals (Mục tiêu):**
- Cung cấp một giao diện tổng hợp dữ liệu phản hồi của người dùng trong một khoảng thời gian cụ thể.
- Tính toán điểm số CSAT tổng quan dựa trên số lượt đánh giá tích cực (thumbs up) so với tổng số lượt đánh giá.
- Tạo một bảng xếp hạng (leaderboard) các mô hình theo điểm số CSAT trung bình.
- Hiển thị một luồng (feed) các bình luận và phản hồi định tính mới nhất để giúp debug các câu trả lời kém chất lượng của mô hình.
- Tích hợp liền mạch với cơ chế lọc thời gian chung (global time filter) hiện có trên admin dashboard.

**Non-Goals (Ngoài phạm vi):**
- Thay đổi cách Open WebUI frontend đang thu thập phản hồi.
- Ghi đè hoặc chỉnh sửa dữ liệu phản hồi (chỉ xây dựng giao diện read-only cho admins).
- Xử lý ngôn ngữ tự nhiên (NLP) phức tạp hoặc phân tích cảm xúc (sentiment analysis) trên phần text của phản hồi.

## Decisions (Các quyết định thiết kế)

**1. Data Aggregation via SQL vs Application Logic (Tổng hợp dữ liệu bằng SQL hay Code):**
- **Quyết định:** Thực hiện việc tổng hợp (aggregation) trực tiếp trong PostgreSQL.
- **Lý do:** Cấu trúc bảng `feedback` rất đơn giản và phù hợp với các truy vấn tổng hợp của SQL. Sử dụng SQL (`COUNT`, `GROUP BY model_id`) cho hiệu năng tốt hơn nhiều so với việc tải toàn bộ dữ liệu lên bộ nhớ của Python, đặc biệt với các khoảng thời gian lớn như "All Time".

**2. API Endpoint Structure (Cấu trúc API Endpoint):**
- **Quyết định:** Tạo một endpoint chuyên biệt `/v1/_mw/admin/analytics/satisfaction` bên trong file `api/analytics.py`.
- **Lý do:** Cách này giúp nhóm logic CSAT cùng với endpoint `/chat` analytics hiện có, đồng thời dễ dàng tái sử dụng logic lọc ranh giới thời gian (`_time_boundaries`) đã được thiết lập sẵn trong `summary.py` và `analytics.py`.

**3. Frontend Integration (Tích hợp Frontend):**
- **Quyết định:** Thêm một tab mới tên là "Satisfaction" trên giao diện. Với bố cục hiện tại, việc thêm một tab chuyên biệt "⭐ Satisfaction" sẽ gọn gàng hơn và tuân theo mẫu kiến trúc chung giống như các tab "Chat Analytics" và "Usage".
- **Lý do:** Cô lập logic hiển thị CSAT khỏi các biểu đồ phân tích lưu lượng chat, tạo ra một không gian riêng cho bảng xếp hạng và các bình luận gần đây mà không làm lộn xộn các biểu đồ đã có.

## Risks / Trade-offs (Rủi ro / Sự đánh đổi)

- **Rủi ro: Hiệu năng phân tích trường JSON (JSON Field Parsing Performance)**
  - **Trade-off/Mitigation (Giảm thiểu):** Các cột `data` và `meta` trong bảng `feedback` có kiểu dữ liệu là JSON/JSONB. Query trực tiếp vào các trường bên trong JSON có thể bị chậm nếu không được đánh index. Tuy nhiên, với lượng truy cập của admin dashboard, đây chưa phải là nút thắt cổ chai (bottleneck) ngay lập tức. Chúng ta sẽ sử dụng giới hạn như `LIMIT 50` cho các truy vấn lấy phản hồi gần nhất để tránh việc quét toàn bộ bảng (full-table scans).
  
- **Rủi ro: Dữ liệu người dùng bị đứt gãy (Disconnected User Data)**
  - **Trade-off/Mitigation (Giảm thiểu):** Có thể một feedback đang liên kết với một user ID đã bị xóa khỏi hệ thống. Chúng ta sẽ sử dụng `LEFT JOIN` với bảng `user` để đảm bảo các feedback này không bị rớt mất khỏi kết quả tổng hợp ngay cả khi record của người dùng không còn tồn tại.
