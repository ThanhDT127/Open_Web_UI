## ADDED Requirements

### Requirement: Tự động khởi tạo lười người dùng (Lazy Provisioning)
Middleware hệ thống MUST tự động kiểm tra chéo và khởi tạo người dùng trong cơ sở dữ liệu `middleware` (bảng `mw_users`) khi có yêu cầu xác thực hoặc truy vấn thông tin từ một tài khoản người dùng chưa tồn tại trong Middleware nhưng có tài khoản đang hoạt động (active) trong DB `openwebui` (bảng `"user"`).

#### Scenario: Khởi tạo thành công cho người dùng hợp lệ
- **WHEN** Người dùng hợp lệ có email `nhanvien@example.com` (đã đăng nhập SSO và hoạt động trên Open WebUI) gửi yêu cầu chat đầu tiên hoặc gọi endpoint truy vấn hạn mức
- **THEN** Middleware SHALL kiểm tra chéo DB `openwebui`, tự động khởi tạo người dùng trong bảng `mw_users` với quota mặc định và sinh subkey mới, sau đó phản hồi thành công yêu cầu

#### Scenario: Từ chối yêu cầu cho người dùng không tồn tại hoặc bị khóa
- **WHEN** Một yêu cầu mang email hoặc subkey không hợp lệ, không tồn tại hoặc bị khóa (role = 'banned' hoặc 'pending') trong DB `openwebui` gửi yêu cầu xác thực
- **THEN** Middleware SHALL từ chối yêu cầu và trả về mã lỗi thích hợp (401 Unauthorized hoặc 403 Forbidden)

### Requirement: Giao diện so sánh trạng thái đồng bộ tài khoản chéo CSDL
Hệ thống SHALL cung cấp một giao diện (Dashboard) dành cho Admin để đối chiếu danh sách tài khoản giữa DB `openwebui` và DB `middleware`, liệt kê rõ các trường hợp lệch đồng bộ hoặc khóa tài khoản.

#### Scenario: Hiển thị đúng danh sách lệch đồng bộ
- **WHEN** Admin mở tab Users trên Dashboard quản lý và chọn chế độ Sync Status
- **THEN** Hệ thống SHALL hiển thị danh sách tất cả các tài khoản đang bị lệch trạng thái (ví dụ: có bên Open WebUI nhưng chưa có subkey bên Middleware, hoặc bị khóa lệch trạng thái hoạt động) kèm theo tùy chọn "Đồng bộ ngay" (Sync Now)

### Requirement: Đồng bộ thủ công cấp phát bản ghi user đầy đủ như Lazy Provisioning
Endpoint đồng bộ thủ công (`POST /v1/_mw/admin/users/sync-now`, nút "Sync Now") MUST tạo bản ghi user có cấu trúc giống hệt Lazy Provisioning — bao gồm subkey_hash và quota mặc định (đọc từ cấu hình `provisioning.default_quota` trong Settings) — thay vì chèn bản ghi trần với quota rỗng `{}` (vốn khiến user không bị giới hạn chi tiêu).

#### Scenario: Sync Now tạo user mới với quota mặc định
- **WHEN** Admin bấm Sync Now cho một user có trong Open WebUI nhưng chưa tồn tại trong `mw_users`
- **THEN** Middleware SHALL tạo bản ghi với subkey_hash mới, `allowed_models = ["*"]` và quota mặc định đầy đủ (period, limit_cost_usd, timezone, period_start, các bộ đếm used_* = 0)

#### Scenario: Sync Now tự sửa bản ghi quota hỏng
- **WHEN** Admin bấm Sync Now cho một user đã tồn tại nhưng quota bị hỏng (thiếu trường `period` — chỉ có thể sinh ra từ lỗi chèn trần trước đây) hoặc thiếu subkey_hash
- **THEN** Middleware SHALL backfill quota mặc định và/hoặc subkey_hash cho bản ghi đó

#### Scenario: Sync Now không đụng vào quota hợp lệ
- **WHEN** Admin bấm Sync Now cho một user đã có quota hợp lệ (có trường `period`)
- **THEN** Middleware SHALL giữ nguyên toàn bộ quota (giới hạn và bộ đếm used_*), chỉ cập nhật role, trạng thái active và openwebui_user_id

### Requirement: Đồng bộ trạng thái khóa tài khoản
Khi trạng thái của một tài khoản bị thay đổi thành không hoạt động (role = 'banned' hoặc 'pending') trong DB `openwebui` bởi Admin, hệ thống MUST lập tức vô hiệu hóa subkey tương ứng bên Middleware để chặn cuộc gọi API.

#### Scenario: Vô hiệu hóa subkey tức thời
- **WHEN** Admin chuyển trạng thái người dùng `nhanvien@example.com` thành Banned hoặc Pending trong trang quản trị Open WebUI
- **THEN** Middleware SHALL cập nhật trạng thái `active = false` tương ứng bên bảng `mw_users` và chặn ngay lập tức các yêu cầu chat sử dụng subkey cũ của người dùng này
