## Yêu cầu BỔ SUNG (ADDED Requirements)

### Requirement: API Endpoint Phân tích hợp nhất
Hệ thống PHẢI cung cấp một API endpoint (`GET /v1/_mw/admin/analytics/chat`) trả về số liệu thống kê gộp từ cả Database của Open WebUI và Database của Middleware.

#### Scenario: Yêu cầu lấy phân tích trong 24 giờ
- **WHEN** Admin gửi request yêu cầu lấy analytics với tham số `time_range=24h`
- **THEN** Hệ thống trả về tổng số lượng chat, số lượng tin nhắn, số lượng token, và tổng chi phí USD trong 24 giờ qua, được gom nhóm theo từng giờ.

### Requirement: Các biểu đồ chi tiết (Detailed Charts)
Hệ thống PHẢI cung cấp đa dạng các biểu đồ để phân tích sâu hơn về hành vi người dùng và chi phí mô hình.

#### Scenario: Phân tích theo giờ và theo mô hình
- **WHEN** Admin xem tab Analytics
- **THEN** Hệ thống hiển thị:
  1. Biểu đồ **Hourly Activity (0h-23h)** cho biết số lượng request phân bố theo các giờ trong ngày (giống Open WebUI Analytics).
  2. Biểu đồ **Model Breakdown** (Doughnut chart) và bảng **Top Models** cho biết tỷ trọng chi phí và số lượng request của từng loại AI model.
  3. Biểu đồ **Daily Trend** (Dual-axis line chart) so sánh số lượng request và chi phí USD theo từng ngày.
  4. Metric hiển thị **Active Users** (số lượng người dùng duy nhất đã hoạt động).
  5. Bảng **Top Users Leaderboard** hiển thị Email/Name của người dùng thay vì UUID, kèm theo tỷ lệ phần trăm (Cost Share) của người dùng đó trên tổng chi phí.
  6. **Bộ lọc thời gian (Time Filter)** riêng biệt (24h, 7d, 30d, All Time) dành riêng cho tab Analytics, hoạt động độc lập với bộ lọc của các tab khác.
