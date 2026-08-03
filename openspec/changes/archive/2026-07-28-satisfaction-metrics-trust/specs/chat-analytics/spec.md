## MODIFIED Requirements

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
