## Context

Hệ thống lưu trữ các request đang xử lý trong bảng `mw_pending` (định nghĩa trong `llm-mw/core/db.py`). Khi một request streaming hoặc gọi LLM diễn ra, Middleware ghi nhận log `status='pending'` trong `mw_audit_log` và thêm một bản ghi vào `mw_pending`. Khi kết thúc hoặc lỗi, Middleware xóa bản ghi đó đi.

Thiết kế này sẽ cung cấp API và giao diện UI giúp QTV kiểm tra danh sách này trực quan, đối soát thủ công hoặc xóa ép buộc (Force Clear) các bản ghi bị kẹt.

## Goals / Non-Goals

**Goals:**
- Xây dựng API `GET /v1/_mw/admin/pending` lấy danh sách chi tiết các request pending.
- Xây dựng API `DELETE /v1/_mw/admin/pending/{request_id}` để dọn dẹp ép buộc khi đối soát tự động không khả thi.
- Tích hợp giao diện hiển thị danh sách này dưới dạng Modal trên Admin Dashboard.
- Hỗ trợ các nút hành động "Reconcile" (Đồng bộ) và "Force Clear" (Xóa kẹt) trực quan trên từng dòng.

**Non-Goals:**
- Không thay đổi cách thức hoạt động tự động của hàm `append_pending` và `remove_pending` ở lõi xử lý chat.
- Không truy vấn cơ sở dữ liệu Open WebUI để lấy thông tin email/tên hiển thị của người dùng nhằm duy trì tính độc lập hoàn toàn của Middleware DB (chỉ hiển thị `user_id` của Middleware).

## Decisions

### 1. Vị trí đặt API Router
- **Lựa chọn**: Tích hợp các API mới trực tiếp vào file `llm-mw/api/admin.py` và tái sử dụng hàm `remove_pending` trong file `llm-mw/core/cost.py`.
- **Lý do**: File `admin.py` đã chứa endpoint `/admin/reconcile`, việc tích hợp chung giúp gom các nghiệp vụ quản trị dọn dẹp hệ thống vào một nơi, tránh tạo thêm file Python mới làm loãng cấu trúc.

### 2. Thiết kế API lấy danh sách Pending (SQL JOIN)
Để hiển thị đầy đủ thông tin hữu ích cho QTV (Model gì, Endpoint nào, User nào), API sẽ chạy câu lệnh SQL kết hợp bảng `mw_pending` và `mw_audit_log` (nơi lưu vết ban đầu lúc request mới bắt đầu):
```sql
SELECT p.request_id, p.user_id, p.ts as started_at, a.model, a.endpoint
FROM mw_pending p
LEFT JOIN (
    SELECT DISTINCT ON (rid) rid, model, endpoint
    FROM mw_audit_log
    WHERE status = 'pending'
    ORDER BY rid, ts DESC
) a ON p.request_id = a.rid
ORDER BY p.ts DESC;
```

### 3. Thêm chức năng Xóa Ép buộc (Force Clear)
- **Lựa chọn**: Hỗ trợ API `DELETE` để gọi thẳng hàm `remove_pending` xóa cứng dòng kẹt khỏi database và file CSV dự phòng.
- **Lý do**: Endpoint `/admin/reconcile` hiện tại phụ thuộc vào việc LiteLLM phải ghi nhận log. Nếu LiteLLM không có log (do lỗi mạng trước khi tới proxy hoặc proxy bị crash), API này trả về 404 và từ chối xóa request. Force Clear giải quyết triệt để vấn đề này.

## Risks / Trade-offs

- **[Risk]** Force Clear xóa mất bản ghi đang chạy thực tế khi người dùng đang stream bình thường.
  - **Mitigation**: Hiển thị rõ thời gian kẹt (Elapsed time) và chỉ khuyên dùng Force Clear cho các request đã chạy quá 10 phút.
