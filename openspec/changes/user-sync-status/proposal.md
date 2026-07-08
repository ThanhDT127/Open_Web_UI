## Why

Hiện tại, cơ sở dữ liệu người dùng của Open WebUI (bảng `"user"` trong DB `openwebui`) và cơ sở dữ liệu hạn mức của Middleware (bảng `mw_users` trong DB `middleware`) hoạt động độc lập và chưa có cơ chế đồng bộ tự động. Khi người dùng mới đăng nhập hệ thống lần đầu thông qua SSO (hoặc đăng ký thông thường), thông tin của họ chỉ tồn tại bên Open WebUI DB; Middleware không có thông tin này nên sẽ chặn mọi yêu cầu chat và báo lỗi xác thực. Việc phát triển tính năng "User Sync Status" với cơ chế tự động khởi tạo lười (Lazy Provisioning) giúp đồng bộ hóa tức thời tài khoản người dùng, đảm bảo trải nghiệm sử dụng mượt mà không bị ngắt quãng.

## What Changes

- **Bổ sung kết nối chéo CSDL**: Middleware sẽ thiết lập thêm một Read-only database connection pool kết nối tới DB `openwebui` trên cùng máy chủ PostgreSQL.
- **Tự động khởi tạo tài khoản (Lazy Provisioning)**: Khi nhận được yêu cầu xác thực hoặc truy vấn hạn mức từ một người dùng chưa tồn tại trong Middleware DB, Middleware sẽ tự động kiểm tra chéo thông tin sang Open WebUI DB. Nếu người dùng tồn tại và đang hoạt động, Middleware sẽ tự động tạo bản ghi mới trong bảng `mw_users`, cấp hạn mức quota mặc định và sinh khóa phụ ẩn (subkey).
- **Cơ chế tiêm khóa (Subkey Injection)**: Cung cấp API để Open WebUI tự động lấy subkey mới tạo của người dùng và lưu vào cài đặt cá nhân, loại bỏ thao tác copy-paste thủ công của Admin.
- **Giám sát đồng bộ (Sync Status Dashboard)**: Bổ sung giao diện và API cho phép Quản trị viên (Admin) theo dõi trạng thái đồng bộ tài khoản giữa hai cơ sở dữ liệu, hiển thị cảnh báo đỏ khi phát hiện lệch tài khoản và hỗ trợ nút bấm đồng bộ nhanh thủ công.
- **Giao diện Quản trị Thông minh (Intelligent Dashboard)**: Áp dụng cơ chế điều hướng sự chú ý (Attention Directing) bằng cách sắp xếp tài khoản theo % Quota đã sử dụng và mức độ ưu tiên của trạng thái đồng bộ. Tối ưu hóa không gian hiển thị bằng Scrollable Table, Sticky Header.

## Capabilities

### New Capabilities

- `user-sync-status`: Cung cấp khả năng tự động đồng bộ hóa tài khoản người dùng, tự sinh khóa phụ subkey và cấp phát quota mặc định theo nhu cầu (on-demand), cùng với giao diện quản lý trạng thái đồng bộ chéo CSDL cho Admin.

### Modified Capabilities

*(Không có)*

## Impact

- **Database Layer**: `llm-mw/core/db.py` sẽ khởi tạo thêm connection pool phụ kết nối đến DB `openwebui`.
- **Authentication Layer**: `llm-mw/core/auth.py` và luồng xác thực `require_user` sẽ bổ sung bước kiểm tra chéo và tự tạo user nếu chưa tồn tại.
- **API Layer**: Cập nhật endpoint `/v1/_mw/quota-status` và `/v1/_mw/admin/users` để hỗ trợ cơ chế tự cấp khóa và thống kê trạng thái đồng bộ chéo.
- **Frontend Dashboard**: Bổ sung giao diện so sánh trạng thái tài khoản trên admin dashboard.
