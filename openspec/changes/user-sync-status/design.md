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

### Quyết định 2: Tích hợp Lazy Provisioning với tính năng Đồng bộ Chủ động (Proactive Sync)
- **Giải pháp**: Hệ thống cung cấp hai phương thức đồng bộ tài khoản:
  1. **Lazy Provisioning (Bị động)**: Middleware tự động tạo tài khoản, sinh subkey và cấp Quota mặc định (VD: $2) tại thời điểm người dùng chat lần đầu tiên (chỉ áp dụng nếu Admin đã duyệt `role = user` bên Open WebUI).
  2. **Proactive Sync (Chủ động)**: Admin sử dụng nút "Sync Now" trên bảng điều khiển User Sync Status để chủ động đẩy tài khoản sang Middleware *trước khi* người dùng bắt đầu chat.
- **Lý do lựa chọn**:
  - Tính linh hoạt cao: Proactive Sync cho phép Admin chủ động phân bổ Quota cao hơn (VD: $10 cho khách VIP) trước khi người dùng thực sự sử dụng hệ thống. Còn Lazy Provisioning đóng vai trò như một màng lưới an toàn (safety net) tự động hóa cho các người dùng thông thường, tiết kiệm thao tác thủ công.
  - Tiết kiệm tài nguyên: Dữ liệu (Subkey, Quota) chỉ được tạo ra khi thực sự cần thiết hoặc khi có chủ đích của Admin, ngăn chặn rác dữ liệu từ các tài khoản đăng ký ảo hoặc chưa duyệt.

### Quyết định 3: Thiết kế UI/UX Dashboard theo mô hình "Điều hướng sự chú ý" (Attention Directing)
- **Giải pháp**:
  - **Lược bỏ thông tin kỹ thuật**: Bảng dữ liệu không thiết kế các cột như `Subkey Hash`, `Middleware Subkey` hay nút `Rotate Key` tại giao diện chính, tuân thủ nguyên tắc Hộp đen (Blackbox).
  - **Giao diện co giãn (Scalable UI)**: Thiết kế Scrollable Container (giới hạn chiều cao) và Sticky Header (tiêu đề bám dính) cho tất cả các bảng.
  - **Thuật toán sắp xếp thông minh (Smart Sorting)**: Bảng Quota mặc định sắp xếp giảm dần theo **Tỷ lệ % Quota đã sử dụng**. Bảng Sync Status mặc định sắp xếp theo **Trọng số Ưu tiên lỗi**: `mismatch` (4) > `pending_ow_approval` (3) > `pending_sync` (2) > `orphan_middleware` (1) > `synced` (0).
- **Lý do lựa chọn**:
  - Giảm tải nhận thức (Cognitive Load), giúp Admin tập trung vào các tài khoản rủi ro (sắp hết hạn mức) hoặc các lỗi hệ thống cần xử lý ngay lập tức.
  - Đảm bảo bố cục trang hiển thị luôn ổn định ngay cả khi hệ thống mở rộng lên đến hàng ngàn người dùng.

## Risks / Trade-offs

- **[Trade-off] Rủi ro phân bổ sai Quota với luồng Lazy Provisioning**: Nếu Admin muốn cấp Quota đặc biệt cho một khách VIP nhưng quên sử dụng Proactive Sync trước, người đó sẽ bị hệ thống tự động gán mức Quota mặc định ($2) khi chat lần đầu.
  - *Mitigation*: Bảng "User Management" sử dụng thuật toán sắp xếp đẩy các tài khoản sắp cạn Quota lên đầu, giúp Admin nhanh chóng phát hiện và điều chỉnh lại Quota nếu người dùng VIP vô tình chạm ngưỡng $2 mặc định.
- **[Risk] Nâng cấp Open WebUI làm thay đổi cấu trúc bảng `"user"`** → khiến truy vấn kiểm tra chéo của Middleware bị lỗi.
  - *Mitigation*: Cố định phiên bản Open WebUI. Middleware chạy kiểm tra cấu trúc bảng (`email`, `role`, `name`) lúc startup; log CRITICAL và vô hiệu hóa đồng bộ nếu không khớp.
- **[Risk] Xung đột ghi đồng thời (Race Condition)**: Khi luồng Lazy Provisioning nhận nhiều request chat từ một user cùng một lúc.
  - *Mitigation*: Sử dụng `INSERT INTO mw_users ... ON CONFLICT (user_id) DO NOTHING` kèm theo Thread Lock ở mức FastAPI.
