## Why

Hiện tại, các bộ lọc Ngày/Giờ trên dashboard không được áp dụng cho tab Group Analytics, dẫn đến việc báo cáo dữ liệu bị ngắt kết nối và luôn ở trạng thái tĩnh (mặc định 30 ngày). Thêm vào đó, mặc dù Group Analytics hiển thị được tổng chi phí của từng phòng ban, nhưng các quản trị viên (admin) lại đang thiếu khả năng "xem chi tiết" (drill down) vào một nhóm cụ thể để biết chính xác từng cá nhân trong nhóm đó đã tiêu thụ bao nhiêu. Điều này là cực kỳ quan trọng cho việc kiểm toán và phân bổ chi phí chính xác.

## What Changes

- Sửa đổi API `/v1/_mw/admin/analytics/groups` hiện tại để nó nhận các tham số lọc ngày/giờ chuẩn (`minutes`, `start`, `end`) thay vì bị fix cứng ở mức `days=30`.
- Tạo một API mới `/v1/_mw/admin/analytics/groups/{group_id}/users` để lấy dữ liệu sử dụng hạn mức (quota) của từng người dùng riêng biệt bên trong một nhóm (group) được chỉ định.
- Triển khai thay đổi giao diện (UI) trong bảng Group Analytics: cho phép click vào dòng của một nhóm để mở rộng (expand) ra một bảng phụ (sub-table) dạng accordion, hiển thị chi tiết quota của từng người dùng trong nhóm đó.
- Kết nối với biến toàn cục `currentTimeRange` từ file `filters.js` để đảm bảo mỗi khi thay đổi bộ lọc thời gian, giao diện Group Analytics sẽ tự động load lại dữ liệu mới.

## Capabilities

### New Capabilities
- `group-drill-down`: Khả năng kiểm tra chi tiết lượng quota tiêu thụ của từng người dùng bên trong một nhóm tổ chức cụ thể, thông qua giao diện accordion và API chuyên dụng.

### Modified Capabilities
- `analytics-date-filtering`: Cập nhật logic lấy dữ liệu phân tích nhóm hiện tại để tuân thủ các ràng buộc về lọc thời gian toàn cục đang được sử dụng xuyên suốt trên dashboard.

## Impact

- **Affected APIs**: `api/group_analytics.py` (chỉnh sửa một endpoint có sẵn, thêm một endpoint mới).
- **Affected Frontend JS**: `dashboard/js/group_analytics.js` (cấu trúc tham số cho API, chèn HTML động cho bảng phụ, sự kiện click), `dashboard/js/filters.js` (gọi hàm refresh cho tab group).
- **Dependencies**: Backend sẽ tái sử dụng hàm hỗ trợ `_time_boundaries` từ `api.analytics` để đảm bảo tính nhất quán trong việc parse thời gian. Không cần thay đổi schema database.
