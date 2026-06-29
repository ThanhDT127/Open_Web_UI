## Context

Khi AI thực hiện các hành động nhạy cảm (như gửi email hoặc chạy lệnh sandbox nguy hiểm), hệ thống cần một cơ chế Human-in-the-loop (con người kiểm duyệt) trước khi thực thi thực tế. Việc tích hợp cơ chế này trực tiếp trong OpenWebUI mà không thay đổi mã nguồn Svelte frontend yêu cầu sử dụng kết hợp Custom Action (để hiển thị UI xác nhận phê duyệt) và Custom Filter (để chặn lệnh duyệt và thực thi tác vụ).

## Goals / Non-Goals

**Goals:**
- Thiết lập bảng lưu trữ trạng thái phê duyệt trong database PostgreSQL.
- Xây dựng các API middleware để đăng ký, lấy thông tin và cập nhật trạng thái phê duyệt.
- Tích hợp luồng phê duyệt vào Custom Gmail Tool (khi gửi email, tạm dừng và đăng ký yêu cầu phê duyệt).
- Xây dựng Custom Action `action_approval_ui.py` để hiển thị hộp thoại xác nhận phê duyệt (Approve/Reject) thông qua JavaScript injection (`__event_call__` execute).
- Xây dựng Custom Filter `filter_approval_handler.py` để chặn lệnh `/approve` hoặc `/reject`, thực thi tác vụ tương ứng (gửi email thực tế sau khi được duyệt) và trả kết quả cho LLM.

**Non-Goals:**
- Sửa đổi trực tiếp mã nguồn Frontend (TypeScript/Svelte) của OpenWebUI.
- Triển khai phê duyệt cho tất cả các tool không nhạy cảm (chỉ áp dụng cho Gmail hoặc các tool được đánh dấu nhạy cảm).

## Decisions

### 1. Database Schema cho Approvals
Chúng ta sẽ tạo bảng `mw_tool_approvals` trong cơ sở dữ liệu PostgreSQL của Middleware.

```sql
CREATE TABLE IF NOT EXISTS mw_tool_approvals (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    tool_name   TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    payload     JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);
```

*Alternative Considered:* Lưu trạng thái trong memory cache hoặc Redis.
*Rationale:* PostgreSQL đảm bảo tính bền vững (persistence) và tính nhất quán của dữ liệu phê duyệt, giúp lưu vết audit trail đầy đủ và không bị mất khi khởi động lại các container.

### 2. Middleware API Endpoints
Chúng ta sẽ thêm các endpoint sau vào `llm-mw`:
- `POST /v1/_mw/approvals`: Tạo mới yêu cầu phê duyệt ở trạng thái `pending`.
- `GET /v1/_mw/approvals/<approval_id>`: Lấy chi tiết yêu cầu phê duyệt.
- `POST /v1/_mw/approvals/<approval_id>/status`: Cập nhật trạng thái (`approved` hoặc `rejected`).

### 3. OpenWebUI Action & Filter Flow
- **Bước 1 (Tool request):** Khi LLM gọi `send_gmail`, tool sẽ kiểm tra xem đã có trạng thái được phê duyệt chưa. Nếu chưa, tool sẽ tạo một yêu cầu duyệt qua API middleware, lưu payload email (`recipient`, `subject`, `body`) và trả về chuỗi `[PENDING_APPROVAL:gmail_send_<uuid>]`.
- **Bước 2 (Action Button UI):** Custom Action hiển thị một nút dưới tin nhắn. Khi người dùng click hoặc tin nhắn chứa mã chờ duyệt, Action kích hoạt một modal UI đẹp mắt bằng JS Injection. Modal có hai nút "Duyệt" và "Từ chối".
- **Bước 3 (Command submission):** Khi người dùng click nút Duyệt hoặc Từ chối trên modal, JS sẽ gọi API cập nhật trạng thái middleware thành `approved` / `rejected`, sau đó gửi tin nhắn `/approve <id>` hoặc `/reject <id>` vào khung chat.
- **Bước 4 (Filter Intercept & Execute):** Custom Filter (inlet) chặn tin nhắn `/approve <id>` hoặc `/reject <id>`.
  - Nếu duyệt: Filter lấy payload từ middleware, thực hiện gửi email thật qua Gmail API bằng OAuth token của người dùng, cập nhật kết quả gửi email thành công/thất bại và thế chỗ nội dung chat bằng kết quả đó để gửi cho LLM.
  - Nếu từ chối: Filter cập nhật và thế chỗ nội dung chat bằng thông báo từ chối.

## Risks / Trade-offs

- **[Risk]** Người dùng vô tình đóng modal hoặc không duyệt.
  - *Mitigation:* Yêu cầu sẽ ở trạng thái `pending` vô thời hạn. Người dùng có thể click lại nút Action dưới tin nhắn bất kỳ lúc nào để mở lại modal duyệt.
- **[Risk]** Lộ thông tin nhạy cảm trong payload.
  - *Mitigation:* Bảng database nằm trong mạng nội bộ PostgreSQL và chỉ truy cập được qua các API được bảo vệ bằng Bearer admin token.
