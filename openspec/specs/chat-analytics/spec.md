# chat-analytics Specification

## Purpose
TBD - created by archiving change chat-analytics-dashboard. Update Purpose after archive.
## Requirements
### Requirement: API Endpoint Phân tích hợp nhất
Hệ thống SHALL cung cấp một API endpoint (`GET /v1/_mw/admin/analytics/chat`) trả về số liệu thống kê gộp từ cả Database của Open WebUI và Database của Middleware.

Endpoint này SHALL giải mã khoảng thời gian bằng **cùng một bộ giải mã** với các endpoint phân tích khác, và SHALL trả lỗi `400` khi tham số thời gian không hợp lệ. Endpoint SHALL NOT âm thầm thay một khoảng thời gian không hợp lệ bằng khoảng mặc định — làm vậy khiến cùng một tham số sai cho ra hai hành vi khác nhau giữa các tab, và người đọc không có cách nào biết mình đang nhìn khoảng thời gian nào.

Việc chọn độ rộng bucket của biểu đồ SHALL giữ nguyên cách neo theo tham số `minutes` của endpoint này, không chuyển sang cơ chế tự suy ra bucket của bộ giải mã dùng chung.

#### Scenario: Yêu cầu lấy phân tích trong 24 giờ
- **WHEN** Admin gửi request yêu cầu lấy analytics với tham số `time_range=24h`
- **THEN** Hệ thống trả về tổng số lượng chat, số lượng tin nhắn, số lượng token, và tổng chi phí USD trong 24 giờ qua, được gom nhóm theo từng giờ.

#### Scenario: Tham số thời gian sai định dạng
- **WHEN** request mang `start` hoặc `end` không phải định dạng ISO hợp lệ
- **THEN** endpoint trả `400` kèm mô tả lỗi, thay vì trả dữ liệu của khoảng mặc định 30 ngày

#### Scenario: Khoảng thời gian đảo ngược
- **WHEN** request mang `start` lớn hơn hoặc bằng `end`
- **THEN** endpoint trả `400`, thay vì trả kết quả rỗng của một khoảng âm

#### Scenario: Độ rộng bucket không đổi sau khi thống nhất bộ giải mã
- **WHEN** Admin xem tab Analytics với khoảng thời gian từ 24 giờ trở xuống
- **THEN** biểu đồ vẫn gom theo giờ như trước, không chuyển sang gom theo ngày

### Requirement: Các biểu đồ chi tiết (Detailed Charts)
Hệ thống SHALL cung cấp đa dạng các biểu đồ để phân tích sâu hơn về hành vi người dùng và chi phí mô hình.

#### Scenario: Phân tích theo giờ và theo mô hình
- **WHEN** Admin xem tab Analytics
- **THEN** Hệ thống hiển thị:
  1. Biểu đồ **Hourly Activity (0h-23h)** cho biết số lượng request phân bố theo các giờ trong ngày (giống Open WebUI Analytics).
  2. Biểu đồ **Model Breakdown** (Doughnut chart) và bảng **Top Models** cho biết tỷ trọng chi phí và số lượng request của từng loại AI model.
  3. Biểu đồ **Daily Trend** (Dual-axis line chart) so sánh số lượng request và chi phí USD theo từng ngày.
  4. Metric hiển thị **Active Users** (số lượng người dùng duy nhất đã hoạt động).
  5. Bảng **Top Users Leaderboard** hiển thị Email/Name của người dùng thay vì UUID, kèm theo tỷ lệ phần trăm (Cost Share) của người dùng đó trên tổng chi phí.
  6. **Bộ lọc thời gian (Time Filter)** riêng biệt (24h, 7d, 30d, All Time) dành riêng cho tab Analytics, hoạt động độc lập với bộ lọc của các tab khác.

