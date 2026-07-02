## Context

Hệ thống hiện tại lưu trữ lịch sử sử dụng (tokens, cost, models) ở database `middleware` (bảng `mw_audit_log`), trong khi thông tin nhóm người dùng lại nằm ở database `openwebui` (bảng `group`, `group_member`). Kiến trúc Middleware chỉ thiết lập kết nối Read-only sang `openwebui` DB. Để thực hiện phân bổ chi phí theo phòng ban (Chargeback), ta cần một cơ chế kết hợp dữ liệu chéo mà không làm thay đổi hay phụ thuộc vào mã nguồn của Open WebUI.

## Goals / Non-Goals

**Goals:**
- Xây dựng API tính toán chi phí, lượng tokens và độ trễ theo từng nhóm.
- Xác định tự động 1 nhóm chính (Primary Group / Cost Center) cho mỗi user theo nguyên tắc "Zero-Config" (Không can thiệp vào DB schema).
- Giao diện Admin Dashboard hiển thị biểu đồ và bảng xếp hạng chi phí theo nhóm rõ ràng.

**Non-Goals:**
- Không thay đổi mã nguồn, không thêm cột, không tạo bảng mới ở cả Open WebUI lẫn Middleware database.
- Không hỗ trợ phân cấp nhóm lồng nhau (Nested groups).
- Không chia đều chi phí (Split cost) cho nhiều group; 100% chi phí của 1 user sẽ tính vào 1 Primary Group duy nhất.

## Decisions

1. **Thuật toán giải quyết Primary Group (Quy tắc Thời gian - Cách A)**:
   - Hệ thống tự động tra cứu bảng `group_member` bên Open WebUI DB.
   - Group đầu tiên mà user được thêm vào (có `created_at` nhỏ nhất) mặc định trở thành Primary Group của user đó.
   - *Rationale (Lý do)*: Dựa trên thực tế vận hành, group đầu tiên user tham gia luôn là "Home Department". Nếu user chuyển phòng ban, Admin bắt buộc phải xóa user khỏi nhóm cũ và thêm vào nhóm mới ở Open WebUI. Hành động này tự động cập nhật `created_at` mới, khiến hệ thống Middleware nhận diện lại Primary Group một cách tự nhiên mà không cần chức năng Override thủ công.

2. **Cơ chế Cross-Database Join (Kết hợp dữ liệu In-Memory)**:
   - Thay vì dùng `dblink` phức tạp ở tầng CSDL, ta thực hiện gom nhóm ở tầng Python:
     - Bước 1: Lấy danh sách ánh xạ `user_id -> primary_group` từ Open WebUI.
     - Bước 2: Query dữ liệu tổng hợp từ `mw_audit_log` của Middleware theo `user_id`.
     - Bước 3: Dùng Python Dictionary để gộp (aggregate) kết quả từ Bước 2 theo các nhóm ở Bước 1.

## Risks / Trade-offs

- **Luân chuyển phòng ban tạm thời**: Nếu user được thêm vào nhóm tạm thời nhưng chưa rời nhóm chính, chi phí vẫn dồn vào nhóm cũ. Điều này chấp nhận được vì nhóm cũ mang tính chất "Department", còn nhóm tạm thời là "Project".
- **Memory Overhead**: Gom nhóm bằng Python trong RAM. Chấp nhận được với quy mô 200 - 5.000 users.
