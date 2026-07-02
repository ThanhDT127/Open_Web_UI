## 1. Middleware Database & Security Setup

- [x] 1.1 Thêm bảng `mw_user_integrations` vào `_SCHEMA_SQL` trong [db.py](file:///d:/Works/openwebui_clone/llm-mw/core/db.py).
- [x] 1.2 Viết module mã hóa/giải mã AES-256 [crypto.py](file:///d:/Works/openwebui_clone/llm-mw/utils/crypto.py) sử dụng `cryptography.fernet` với khóa `MW_SECRET`.
- [x] 1.3 Tạo các unit test python cho module mã hóa để xác nhận việc mã hóa/giải mã hoạt động chính xác.

## 2. API Endpoints Implementation

- [x] 2.1 Viết các endpoint khởi chạy OAuth `/v1/_mw/oauth/connect` và callback `/v1/_mw/oauth/callback` trong [oauth.py](file:///d:/Works/openwebui_clone/llm-mw/api/oauth.py).
- [x] 2.2 Viết endpoint lấy token sạch và tự động refresh `/v1/_mw/integrations/get_token` trong [integrations.py](file:///d:/Works/openwebui_clone/llm-mw/api/integrations.py).
- [x] 2.3 Đăng ký các route mới trong tệp [main.py](file:///d:/Works/openwebui_clone/llm-mw/main.py).

## 3. Custom OpenWebUI Tool & Verification

- [x] 3.1 Viết Custom Tool [google_gmail_tool.py](file:///d:/Works/openwebui_clone/tools/google_gmail_tool.py) gửi mail, tích hợp kiểm tra token từ Middleware API.
- [x] 3.2 Viết script test tự động bằng Playwright [ui-oauth-integrations.spec.ts](file:///d:/Works/openwebui_clone/tests/ui-oauth-integrations.spec.ts) để verify API và luồng check OAuth.
- [x] 3.3 Chạy kiểm thử tự động Playwright bằng lệnh `npx playwright test tests/ui-oauth-integrations.spec.ts` và xác nhận kết quả thành công 100%.
