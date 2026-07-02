## ADDED Requirements

### Requirement: Default model access restriction
Hệ thống SHALL quy định danh sách các model mặc định được phép sử dụng cho người dùng mới thông qua biến cấu hình `DEFAULT_ALLOWED_MODELS`. Cơ chế wildcard mặc định `["*"]` MUST bị loại bỏ đối với tài khoản mới tạo hoặc đồng bộ.

#### Scenario: User registers and gets default model list
- **WHEN** một người dùng mới được tạo hoặc tự động đồng bộ định danh từ LDAP/SSO
- **THEN** trường `allowed_models` của người dùng đó trong cơ sở dữ liệu MUST được gán bằng giá trị của `DEFAULT_ALLOWED_MODELS` thay vì `["*"]`.

#### Scenario: User attempts to call an allowed model
- **WHEN** người dùng gửi yêu cầu chat sử dụng một model có tên trong `DEFAULT_ALLOWED_MODELS` (ví dụ: `gemini-auto`)
- **THEN** Middleware phê duyệt yêu cầu và chuyển tiếp request sang LiteLLM thành công.

#### Scenario: User attempts to call a restricted model
- **WHEN** người dùng gửi yêu cầu chat sử dụng một model đắt tiền không nằm trong `DEFAULT_ALLOWED_MODELS` (ví dụ: `chat-gpt-5.4`)
- **THEN** Middleware trả về lỗi HTTP 403 Forbidden ("Model not allowed") và chặn cuộc gọi.
