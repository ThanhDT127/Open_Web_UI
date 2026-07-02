## Why

Khi AI thực hiện các hành động nhạy cảm (như gửi email, xóa dữ liệu, chạy lệnh sandbox), hệ thống cần cơ chế kiểm duyệt của con người (Human-in-the-loop) trước khi thực hiện. Việc xây dựng giao diện Duyệt/Hủy trực quan ngay trong khung chat giúp người dùng kiểm soát hành động của AI một cách an toàn và tiện lợi.

## What Changes

- **Action Button UI:** Xây dựng Custom Action [action_approval_ui.py](file:///d:/Works/openwebui_clone/tools/action_approval_ui.py) để phát hiện thẻ chờ duyệt và hiển thị 2 nút bấm: **Duyệt (Approve)** và **Từ chối (Reject)** ngay dưới tin nhắn chat.
- **Filter Action Handler:** Xây dựng Custom Filter [filter_approval_handler.py](file:///d:/Works/openwebui_clone/tools/filter_approval_handler.py) để chặn lệnh phản hồi ẩn `/approve` hoặc `/reject` từ các nút bấm, cập nhật trạng thái duyệt và báo LLM tiếp tục xử lý tác vụ.
- **Lưu trữ trạng thái duyệt:** Lưu trữ trạng thái phê duyệt (Pending, Approved, Rejected) trong một bảng DB hoặc tệp dữ liệu tạm.

## Capabilities

### New Capabilities
- `tool-approval-ui`: Hỗ trợ luồng kiểm duyệt Human-in-the-loop trực quan cho các Custom Tools nhạy cảm bằng cách phối hợp Action (hiển thị UI nút bấm) và Filter (xử lý sự kiện click).

### Modified Capabilities
<!-- No modified capabilities -->

## Impact

- **OpenWebUI Tools:** Tạo 2 tệp Custom Tool mới trong thư mục `tools/action_approval_ui.py` và `tools/filter_approval_handler.py`.
