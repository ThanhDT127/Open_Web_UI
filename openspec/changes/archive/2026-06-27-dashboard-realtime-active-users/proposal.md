## Why

Hiện tại, quản trị viên (Admin) của hệ thống Middleware chỉ có thể xem thống kê tĩnh dựa trên bộ lọc thời gian và các request đã hoàn thành. Hệ thống chưa có tính năng theo dõi lượng người dùng hoạt động theo thời gian thực (Real-time Active Users). Điều này gây khó khăn trong việc giám sát tải thực tế của hệ thống, phát hiện các trường hợp spam request hoặc rò rỉ API key trong thời gian thực mà không cần F5 tải lại trang liên tục.

## What Changes

- **Thêm chỉ số Active Users**: Bổ sung card hiển thị số lượng người dùng đang hoạt động thực tế trên Dashboard (Usage Tab).
- **Cập nhật Backend**: Xây dựng API stream truyền dữ liệu thời gian thực dạng Server-Sent Events (SSE) để truyền lượng Active Users về Dashboard.
- **Cập nhật Frontend**: Kết nối EventSource trong Javascript Dashboard để hiển thị trực quan theo thời gian thực, tự động tăng/giảm số lượng người dùng đang hoạt động.
- **Cơ chế Fallback**: Hỗ trợ đếm từ file `pending.csv` và `audit.jsonl` khi mất kết nối cơ sở dữ liệu PostgreSQL.

## Capabilities

### New Capabilities
- `dashboard-realtime-active-users`: Cung cấp tính năng đếm và hiển thị số lượng người dùng hoạt động thời gian thực (Real-time Active Users) trên Admin Dashboard sử dụng kết nối SSE.

### Modified Capabilities

## Impact

- **Mã nguồn Backend**: Bổ sung endpoint trong `llm-mw/api/admin.py` hoặc file mới và đăng ký định tuyến trong `llm-mw/main.py`.
- **Mã nguồn Frontend**: Cập nhật file HTML `index.html`, style CSS và thêm logic kết nối SSE trong file Javascript mới `active_users.js` (hoặc tích hợp vào file hiện có).
- **Hiệu năng**: Tạo kết nối duy trì (persistent connection) nhẹ qua SSE thay vì Polling liên tục.
