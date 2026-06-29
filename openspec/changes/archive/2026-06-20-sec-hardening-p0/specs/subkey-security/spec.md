## ADDED Requirements

### Requirement: Hashed subkey authentication
Hệ thống SHALL chỉ sử dụng mã băm HMAC-SHA256 của subkey để xác thực người dùng. Cột `subkey` chứa văn bản thô (plaintext) MUST bị xóa khỏi bảng `mw_users` trong cơ sở dữ liệu.

#### Scenario: Client authenticates with a valid subkey
- **WHEN** client gửi yêu cầu HTTP với subkey hợp lệ trong Header `Authorization: Bearer <subkey>`
- **THEN** hệ thống băm subkey này bằng `MW_SECRET` và so khớp thành công với `subkey_hash` trong database để xác thực người dùng.

#### Scenario: Client authenticates with an invalid subkey
- **WHEN** client gửi yêu cầu với subkey sai hoặc chưa được đăng ký
- **THEN** hệ thống trả về lỗi HTTP 401 Unauthorized và từ chối xử lý.

### Requirement: Secure subkey generation
Khi Admin tạo người dùng mới hoặc rotate key của người dùng, hệ thống SHALL chỉ hiển thị subkey thô duy nhất một lần trong phản hồi API. Hệ thống MUST chỉ lưu trữ `subkey_hash` vào cơ sở dữ liệu.

#### Scenario: Admin creates a new user
- **WHEN** Admin gửi yêu cầu POST tạo user mới
- **THEN** hệ thống sinh key thô, trả về cho Admin, băm key này và chỉ lưu `subkey_hash` vào Postgres DB. Cột `subkey` thô trong DB MUST bỏ trống.
