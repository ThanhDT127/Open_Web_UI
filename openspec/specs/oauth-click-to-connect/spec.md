# oauth-click-to-connect Specification

## Purpose
TBD - created by archiving change p2-oauth-click-to-connect. Update Purpose after archive.
## Requirements
### Requirement: Middleware Database Storage for Tokens
The Middleware database SHALL store user OAuth tokens securely in a table `mw_user_integrations` and encrypt the `access_token` and `refresh_token` using AES-256 with the secret key `MW_SECRET`.

#### Scenario: Successfully storing credentials
- **WHEN** the OAuth callback exchanges a code for tokens
- **THEN** the system encrypts the tokens and saves them in the database associated with the user's subkey hash

### Requirement: OAuth Authorization Flow Endpoints
The Middleware SHALL expose a redirection endpoint `/v1/_mw/oauth/connect` to start the OAuth flow for supported providers (Google Workspace, GitHub, Microsoft Office 365) and a callback endpoint `/v1/_mw/oauth/callback` to handle the authorization response.

Danh tính mà token được gắn vào MUST được suy ra từ **phiên đăng nhập Open WebUI của chính trình duyệt hoàn tất luồng** (cookie `token` do Open WebUI phát, xác minh bằng `WEBUI_SECRET_KEY` dùng chung), KHÔNG lấy từ tham số `openwebui_user_id`/`subkey` do client cung cấp trên endpoint truy cập được bằng trình duyệt. `/connect` MUST NOT còn nhận `openwebui_user_id`/`subkey` làm trục định danh cho luồng trình duyệt.

Tham số `state` MUST là token ký HMAC-SHA256 bằng `MW_SECRET`, chứa provider, một `nonce` ngẫu nhiên và thời hạn tối đa 10 phút. `/connect` MUST đặt cookie `mw_oauth_nonce` (HttpOnly, Secure, SameSite=Lax, hết hạn ≤ 10 phút) mang chính `nonce` đó. Callback MUST xác minh: (1) chữ ký + thời hạn của `state`; (2) `nonce` trong `state` khớp cookie `mw_oauth_nonce` (double-submit); (3) trình duyệt có phiên Open WebUI hợp lệ. Sai bất kỳ điều kiện nào MUST trả HTTP 400 và MUST NOT trao đổi code hay lưu token. Callback MUST xóa cookie `mw_oauth_nonce` khi thành công — luồng dùng một lần: gọi lại trong cùng trình duyệt không còn cookie khớp ⇒ bị từ chối; kèm hạn 10 phút của `state` giới hạn cửa sổ replay.

#### Scenario: User initiates OAuth connection
- **WHEN** một user đã đăng nhập Open WebUI mở `/v1/_mw/oauth/connect?provider=google_gmail` từ trong trình duyệt của mình
- **THEN** Middleware đặt cookie `mw_oauth_nonce` và redirect tới màn hình consent chính thức của provider với `state` là token đã ký chứa `nonce` đó

#### Scenario: Token gắn đúng người hoàn tất luồng
- **WHEN** callback nhận code hợp lệ, `state` + cookie `nonce` khớp, và trình duyệt mang phiên Open WebUI của user U
- **THEN** Middleware đổi code lấy token và lưu dưới `subkey_hash` của **U** (suy ra từ phiên), bất kể tham số nào từng xuất hiện ở `/connect`

#### Scenario: Chặn CSRF token-binding — provider URL dựng sẵn
- **WHEN** kẻ tấn công gửi nạn nhân một URL authorize dựng sẵn của provider (bỏ qua `/connect`), nạn nhân consent và bị redirect về callback
- **THEN** trình duyệt nạn nhân không có cookie `mw_oauth_nonce` khớp `state` → Middleware trả HTTP 400, không trao đổi code, không lưu token

#### Scenario: Chặn CSRF token-binding — link /connect mang id người khác
- **WHEN** nạn nhân bị lừa mở một link `/connect` do kẻ tấn công tạo rồi hoàn tất consent
- **THEN** token được gắn vào **chính nạn nhân** (danh tính lấy từ phiên trình duyệt nạn nhân), không vào tài khoản kẻ tấn công — kẻ tấn công không thu được gì

#### Scenario: Chặn replay link connect
- **WHEN** callback được gọi lại trong cùng trình duyệt sau khi đã hoàn tất (cookie `mw_oauth_nonce` đã bị xóa), hoặc `state` đã quá hạn, hoặc chữ ký sai
- **THEN** Middleware trả HTTP 400, không trao đổi code và không lưu bất kỳ token nào

#### Scenario: Trình duyệt chưa đăng nhập Open WebUI
- **WHEN** callback được hoàn tất trong một trình duyệt không có phiên Open WebUI hợp lệ
- **THEN** Middleware trả HTTP 400 kèm hướng dẫn đăng nhập Open WebUI trước rồi kết nối lại, không lưu token

### Requirement: Integration Token Verification in Tools
The Custom Tools in OpenWebUI SHALL check for existing and active user OAuth connections by calling the Middleware API `/v1/_mw/integrations/get_token` with the user's subkey, and return a connection request message if the connection is missing or expired.

#### Scenario: Running Gmail Tool without active connection
- **WHEN** the user runs the Gmail Tool but has not authorized their Gmail account
- **THEN** the tool returns a markdown message showing a secure link to connect their account via `/v1/_mw/oauth/connect`

### Requirement: Office365 Provider Scopes
Provider `office365` trong PROVIDERS registry SHALL yêu cầu các delegated scopes: `Mail.Send`, `Mail.Read`, `Calendars.ReadWrite`, `Sites.Read.All`, `ChannelMessage.Send` (kèm `offline_access` để nhận refresh token). Hệ thống MUST NOT yêu cầu scope ghi rộng hơn khi chưa có use case tương ứng.

#### Scenario: Consent screen hiển thị đủ scopes mới
- **WHEN** user bắt đầu flow connect office365
- **THEN** màn hình consent của Microsoft liệt kê đúng 5 scopes trên và token nhận về dùng được cho mail, lịch, SharePoint đọc, Teams gửi tin

### Requirement: Xác thực phiên Open WebUI tại Middleware
Middleware SHALL xác minh cookie phiên `token` của Open WebUI (JWT ký bằng `WEBUI_SECRET_KEY`) để lấy `openwebui_user_id` của trình duyệt gọi tới. `WEBUI_SECRET_KEY` MUST được chia sẻ cho service middleware qua biến môi trường. Việc xác minh MUST kiểm chữ ký và thời hạn; token thiếu, sai chữ ký hoặc hết hạn MUST bị coi là chưa đăng nhập.

Cơ chế này CHỈ dùng để suy ra danh tính cho luồng OAuth khởi tạo từ trình duyệt; nó MUST NOT thay thế cơ chế `OPENWEBUI_SERVICE_KEY` mà các tool dùng để gọi `get_token` server-to-server.

#### Scenario: Suy ra danh tính từ phiên hợp lệ
- **WHEN** một request tới `/connect` hoặc `/callback` kèm cookie `token` hợp lệ của user U
- **THEN** Middleware xác định caller là U và dùng U làm chủ thể gắn token

#### Scenario: Cookie phiên không hợp lệ
- **WHEN** cookie `token` thiếu, sai chữ ký hoặc hết hạn
- **THEN** Middleware coi như chưa đăng nhập và từ chối luồng OAuth trình duyệt với HTTP 400

### Requirement: Cấu hình OAuth nằm trong runbook theo từng tool, không trong .env.example
Biến môi trường của OAuth Click-to-Connect SHALL được tài liệu hóa trong **runbook `docs/18`** — biến dùng chung (`MW_PUBLIC_URL`, `MW_SECRET`, `WEBUI_SECRET_KEY`, `OPENWEBUI_SERVICE_KEY`) ở phần chung, còn client id/secret (+ tenant) của mỗi provider SHALL đặt **cạnh tool tương ứng** trong runbook. `.env.example` MUST NOT chứa khối biến OAuth Click-to-Connect; thay vào đó SHALL có một dòng trỏ tới `docs/18`.

**Lý do**: các biến này là cấu hình tích hợp tùy chọn cần bối cảnh (đăng ký app ở provider, redirect URI, khóa tenant, nhánh mock khi bỏ trống). Đặt biến cạnh đúng tool trong runbook giúp người thêm plugin thấy ngay cần gì cho tool đó; nhồi vào `.env.example` khiến người deploy tưởng bắt buộc và thiếu bối cảnh.

#### Scenario: .env.example không còn khối OAuth
- **WHEN** người deploy mở `.env.example`
- **THEN** không thấy biến OAuth Click-to-Connect nào; thấy một dòng trỏ tới `docs/18` để cấu hình tích hợp per-user

#### Scenario: Runbook nêu đủ biến theo từng tool để bật một provider
- **WHEN** admin làm theo `docs/18` để bật GitHub per-user
- **THEN** runbook nêu ngay cạnh tool GitHub: `GITHUB_CLIENT_ID/SECRET`, redirect URI `<MW_PUBLIC_URL>/v1/_mw/oauth/callback`, scopes; phần chung nêu `WEBUI_SECRET_KEY` bắt buộc; và nêu rõ bỏ trống client id ⇒ nhánh mock (token giả, API thật trả 401)
