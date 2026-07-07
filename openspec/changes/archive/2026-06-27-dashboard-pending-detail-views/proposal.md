## Why

Hiện tại, Admin Dashboard chỉ hiển thị tổng số lượng request đang pending dưới dạng một con số đơn lẻ ở Usage Tab (`metricPending`). Khi xảy ra sự cố (mất kết nối mạng, người dùng tắt trình duyệt giữa chừng khi streaming, hoặc server Middleware/LLM sập), các request này sẽ bị kẹt vĩnh viễn trong trạng thái "pending" và được lưu lại trong bảng `mw_pending`. Admin thiếu giao diện (UI) để xem chi tiết các request này và đối soát (reconcile) hoặc xóa kẹt trực quan, dẫn đến việc quản trị bất tiện.

## What Changes

- **API hiển thị chi tiết**: Bổ sung endpoint `GET /v1/_mw/admin/pending` để trả về danh sách chi tiết các request đang pending từ database.
- **API xóa ép buộc**: Bổ sung endpoint `DELETE /v1/_mw/admin/pending/{request_id}` cho phép Admin dọn dẹp (Force Clear) trực tiếp request bị kẹt mà không cần đối soát qua LiteLLM.
- **Tương tác trên Card Pending**: Cho phép bấm trực tiếp vào Card **Pending** trên Dashboard để mở ra một Modal hiển thị chi tiết.
- **Modal quản lý chi tiết**: Thiết kế modal chứa bảng danh sách pending (Request ID, User ID, Model, Endpoint, Thời gian bắt đầu, Thời lượng đã trôi qua) kèm các nút thao tác nhanh:
  - **Reconcile (Đồng bộ)**: Đồng bộ chi phí và quota từ LiteLLM log rồi dọn dẹp.
  - **Force Clear (Xóa kẹt)**: Xóa ép buộc khỏi danh sách pending đối với các request chết.

## Capabilities

### New Capabilities
- `admin-pending-details-view`: Xem chi tiết và quản lý đối soát các request đang pending trong hệ thống.
- `admin-pending-force-clear`: Cho phép xóa ép buộc một request bị stuck ra khỏi danh sách pending mà không cần đối soát LiteLLM.

### Modified Capabilities

## Impact

- **Backend**:
  - Cập nhật router trong `llm-mw/api/admin.py` để bổ sung API lấy chi tiết pending và API force delete.
  - Cập nhật `llm-mw/main.py` để đăng ký các API endpoints mới.
- **Frontend**:
  - Cập nhật `llm-mw/dashboard/index.html` để thêm Modal overlay hiển thị bảng chi tiết pending và chỉnh sửa card Pending thành nút tương tác.
  - Cập nhật logic Javascript trong `llm-mw/dashboard/js/usage.js` (hoặc tạo file js mới) để fetch, render dữ liệu bảng và gọi các API tương tác.
