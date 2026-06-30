## Context

Hiện tại, cấu trúc người dùng của Open WebUI (CSDL `openwebui`, bảng `"user"`) và thông tin hạn ngạch/khóa phụ của Middleware (CSDL `middleware`, bảng `mw_users`) hoàn toàn decoupled. 

Hệ thống đang cấu hình đăng ký tài khoản cục bộ (Local Signup) với vai trò mặc định là `pending` (`DEFAULT_USER_ROLE=pending` trong `docker-compose.yml`), yêu cầu Admin phê duyệt thủ công chuyển sang `user`/`admin` mới được kích hoạt. Middleware chưa tự động nhận biết tài khoản được duyệt này, dẫn đến lỗi chặn quyền truy cập khi họ gọi tin nhắn chat. Cần có thiết kế kỹ thuật để kết nối và tự động đồng bộ hóa thông tin người dùng chéo CSDL dựa trên trạng thái phê duyệt thực tế của Admin.

## Goals / Non-Goals

**Goals:**
- Tạo một kết nối database chỉ đọc (Read-only Connection Pool) từ Middleware sang DB `openwebui`.
- Thiết lập cơ chế Lazy Provisioning trong luồng xác thực: khi nhận được request từ một người dùng mới (chưa có trong `mw_users` nhưng đã được Admin phê duyệt hoạt động bên bảng `"user"` của Open WebUI), Middleware sẽ tự động tạo bản ghi `mw_users` tương ứng, sinh subkey và áp dụng hạn ngạch mặc định.
- Cải tiến API và giao diện Dashboard để Quản trị viên đối chiếu chênh lệch tài khoản giữa hai DB (Sync Status View).
- Hỗ trợ API phản hồi khóa subkey của người dùng để Open WebUI có thể tự động lấy và tiêm (inject) vào thiết lập cá nhân của người dùng đó.

**Non-Goals:**
- Middleware tuyệt đối KHÔNG thực hiện ghi chéo (Write) hoặc thay đổi cấu trúc bảng của DB `openwebui` (chỉ duy trì kết nối read-only).
- Không hỗ trợ đồng bộ hoặc đăng ký tài khoản bằng số điện thoại.

## Decisions

### Quyết định 1: Lựa chọn kết nối trực tiếp chỉ đọc (Option A) thay vì API Bridge (Option B)
- **Giải pháp**: Middleware cấu hình thêm connection pool thứ hai kết nối trực tiếp đến DB `openwebui` (chung instance PostgreSQL với Middleware nhưng khác database).
- **Lý do lựa chọn**:
  - Do cả 2 database nằm chung một cụm (PostgreSQL container), kết nối trực tiếp qua Pool cực kỳ nhanh (< 10ms) và ổn định.
  - Giúp viết các câu truy vấn JOIN trực tiếp hoặc kiểm tra nhanh mà không cần fork/sửa mã nguồn gốc của Open WebUI để mở thêm API.
  - Option B (API Bridge) sẽ yêu cầu sửa đổi sâu backend Open WebUI, tăng độ phức tạp khi nâng cấp bảo trì.

### Quyết định 2: Sử dụng luồng Lazy Provisioning (On-demand) kết hợp với Cơ chế Duyệt thủ công hiện tại
- **Giải pháp**: Middleware tự động đồng bộ tài khoản tại thời điểm người dùng phát sinh request đầu tiên, nhưng **chỉ thực hiện đối với các tài khoản đã được Admin phê duyệt** (cột `role` là `user` hoặc `admin` bên Open WebUI). Các tài khoản mới đăng ký đang ở trạng thái `pending` hoặc bị khóa `banned` sẽ bị Middleware chặn ngay từ luồng xác thực.
- **Lý do lựa chọn**:
  - Tối ưu luồng quản lý: Admin chỉ cần phê duyệt tài khoản một lần duy nhất trên giao diện Open WebUI; khi người dùng thực hiện chat lần đầu sau khi duyệt, Middleware sẽ tự động khởi tạo subkey và quota mà không cần Admin thao tác thủ công trên Middleware DB.
  - Sẵn sàng cho tương lai: Dễ dàng chuyển dịch sang tự động hóa 100% khi cấu hình SSO/AD trong tương lai (khi đó `DEFAULT_USER_ROLE` sẽ được cấu hình thành `user`).
  - Tiết kiệm tài nguyên: Tránh tạo dữ liệu rác cho các tài khoản đăng ký nhưng chưa được duyệt hoặc chưa bao giờ sử dụng.
  - Giảm thiểu overhead IO quét toàn bộ bảng định kỳ.

## Risks / Trade-offs

- **[Risk] Nâng cấp Open WebUI làm thay đổi cấu trúc bảng `"user"`** → khiến truy vấn kiểm tra chéo của Middleware bị lỗi.
  - *Mitigation*: Cố định phiên bản Open WebUI ở `v0.9.5`. Đồng thời, Middleware sẽ chạy một câu lệnh SQL kiểm tra sự tồn tại của các cột cần thiết (`email`, `role`, `name` của bảng `"user"`) tại thời điểm startup; nếu không khớp cấu trúc mong đợi, Middleware sẽ ghi log lỗi CRITICAL và tạm ngừng chức năng đồng bộ chéo.
- **[Risk] Xung đột ghi đồng thời (Race Condition) khi người dùng mới gửi nhiều request chat cùng lúc** → dẫn đến ghi trùng lặp user trong `mw_users`.
  - *Mitigation*: Sử dụng cấu trúc `INSERT INTO mw_users ... ON CONFLICT (user_id) DO NOTHING` ở mức DB, đồng thời bao bọc bằng Thread Lock ở mức ứng dụng FastAPI của Middleware.
