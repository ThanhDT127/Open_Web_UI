## 1. Backend API Changes

- [x] 1.1 Tái sử dụng (Reuse) hàm `_time_boundaries` từ `api.analytics` vào trong `api/group_analytics.py` (chỉ import và dùng, tuyệt đối không viết lại logic parse ngày giờ). Sửa chữ ký hàm `get_group_analytics` để nhận `minutes`, `start`, `end`.
- [x] 1.2 Tận dụng lại logic truy vấn (query) có sẵn của hàm `get_group_analytics`, copy và tạo ra một hàm mới `get_group_users(...)` để lấy quota nhóm theo từng user. Kế thừa toàn bộ cơ chế lọc `_time_boundaries`.
- [x] 1.3 Đăng ký route mới `/v1/_mw/admin/analytics/groups/{group_id}/users` trong file `main.py` (chỉ thêm đúng 1 dòng khai báo route, không sửa các route khác).

## 2. Frontend JS Changes

- [x] 2.1 Giữ nguyên khung của hàm `fetchData` trong `dashboard/js/group_analytics.js`, chỉ tái sử dụng cách lấy giá trị từ biến `currentTimeRange` (giống cách làm bên `analytics.js`) để gắn thêm tham số `minutes`, `start`, `end` vào chuỗi gọi API.
- [x] 2.2 Tận dụng lại các hàm `setTimeRange` và `applyCustomRange` trong `dashboard/js/filters.js` bằng cách chỉ bổ sung thêm duy nhất 1 dòng gọi `window.dashboardAPI.refreshGroups()` vào những chỗ đang gọi `refreshAnalytics()`. Tuyệt đối không thay đổi logic đang có.
- [x] 2.3 Gắn thêm sự kiện `onClick` vào thẻ `<tr>` (table row) trong `group_analytics.js` mà không làm thay đổi các class hay attributes hiện tại của dòng đó.
- [x] 2.4 Viết logic DOM insertion ngắn gọn nhất có thể để chèn bảng phụ xuống dưới. Tái sử dụng (Reuse) triệt để các CSS class (như `max-height`, `overflow-y-auto`) từ bảng User Quota Management để tạo thanh cuộn, không viết CSS mới.
