## Why

Dashboard hiện tại chỉ có export CSV cơ bản trong tab Logs (chỉ export trang hiện tại, 8 cột). Admin không có cách nào tải một báo cáo tổng hợp toàn diện bao gồm usage, costs, groups, satisfaction, và chi tiết audit log. Khi cần gửi báo cáo cho manager hoặc lưu trữ compliance, admin phải screenshot từng tab hoặc copy paste thủ công.

Với 200 users doanh nghiệp, admin cần **1 nút bấm → 1 file báo cáo đầy đủ** để review và forward cho stakeholders.

## What Changes

- **Thêm backend endpoint** `GET /v1/_mw/export/report` tổng hợp dữ liệu từ cả MW DB và OW DB, trả về file Excel (.xlsx) multi-sheet hoặc CSV
- **Thêm nút "📥 Export Report"** trên header Dashboard, mở modal chọn format (Excel/CSV) và time range (dùng time range đang chọn trên dashboard)
- **Thêm dependency `openpyxl`** vào requirements.txt để generate Excel file server-side
- **Excel output gồm 7 sheets**: Summary, Top Users, Top Models, Groups, Chat Analytics, Satisfaction, Raw Audit Log
- **CSV output**: export raw audit log dạng streaming (cho nhu cầu import data)

## Capabilities

### New Capabilities
- `report-export`: Backend API endpoint và logic tổng hợp dữ liệu từ nhiều nguồn (mw_audit_log, mw_users, OW chat/message/feedback/group) để generate file Excel multi-sheet hoặc CSV streaming. Dashboard UI modal cho admin download.

### Modified Capabilities
_(Không có capability hiện tại nào bị thay đổi requirement — export Logs hiện có trong logs.js vẫn giữ nguyên)_

## Impact

- **Backend**: Thêm file `api/export_report.py`, thêm route trong `main.py`
- **Frontend**: Thêm file `dashboard/js/export.js`, thêm nút và modal trong `dashboard/index.html`, style trong `dashboard/css/dashboard.css`
- **Dependencies**: Thêm `openpyxl` vào `requirements.txt` và `Dockerfile`
- **DB queries**: Tái sử dụng logic từ `summary.py`, `analytics.py`, `group_analytics.py`, `audit_query.py` — không thêm table/index mới
- **Auth**: Dùng `require_admin_or_session` hiện có — chỉ admin access
