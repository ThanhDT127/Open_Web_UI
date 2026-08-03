# Proposal: department-plugin-access

## Why

Nền tảng đã tích lũy 11 tool/plugin (5 MCP server qua mcpo + 6 custom tool) nhưng chưa có phân quyền: mọi tool hiển thị cho mọi người, khiến (a) model chọn sai tool khi context chứa quá nhiều tool description, (b) không thể mở rộng plugin theo nhu cầu từng phòng ban (yêu cầu "đa ngành đa mảng"), và (c) các action cá nhân (gửi mail, nhắn Teams) qua office365 MCP đang chạy dưới **một danh tính chung** — không truy vết được ai làm gì. Đồng thời DB chưa có group nào (0 rows) dù schema `group`/`group_member` đã sẵn sàng, và cơ chế `access_grants` theo group đã có native trong Open WebUI 0.9.6.

## What Changes

- Seed bộ **group phòng ban mẫu** theo cơ cấu công ty điển hình (Ban lãnh đạo, Kinh doanh, Marketing, Kế toán – Tài chính, HCNS, Kỹ thuật/R&D, Sản xuất, IT) vào Open WebUI.
- Gắn **access_grants theo group phòng ban + override theo user** cho toàn bộ workspace tools và mcpo tool server connections; mặc định private, chỉ mở cho principal cần dùng. Đây là **trục phân quyền duy nhất** — model không gate tool.
- Bổ sung **tool office365 per-user** (mail/lịch/Teams/SharePoint) theo pattern gmail tool + OAuth broker; thu hẹp office365 MCP dùng chung tương ứng.
- Mở rộng provider `office365` trong OAuth broker: thêm scopes Calendars.ReadWrite, Sites.Read.All, ChannelMessage.Send.
- **Vá lỗ hổng CSRF** trong OAuth flow: tham số `state` plaintext (chứa user_id) đổi thành token ký HMAC + ngắn hạn.
- Bật **tool GitHub và Google Drive per-user** từ 2 provider đã có sẵn trong PROVIDERS registry.
- **Future work (ngoài scope)**: tích hợp Canva/Figma khi công ty có license; đồng bộ membership group từ nguồn nhân sự.

## Capabilities

### New Capabilities
- `department-groups`: Seed và quản lý bộ group phòng ban mẫu trong Open WebUI (bảng `group`/`group_member`), làm nền cho mọi phân quyền theo phòng ban.
- `department-tool-access`: Phân quyền hiển thị/sử dụng tool theo **group phòng ban và theo user** — bảng `access_grant` cho workspace tools và tool server connections (mcpo); nguyên tắc default-private. Biên tập bằng UI native của Open WebUI (Workspace → Tools → Access Control).
- `personal-integration-tools`: Bộ tool per-user (office365 mail/lịch/Teams/SharePoint, GitHub, Google Drive) dùng OAuth broker của middleware, mọi action đứng tên user thật.

### Modified Capabilities
- `oauth-click-to-connect`: (1) tham số `state` phải là token ký HMAC ngắn hạn thay vì plaintext user_id — chống gắn nhầm token qua CSRF; (2) provider office365 mở rộng scopes cho lịch/SharePoint/Teams.

## Impact

- **Middleware** (`llm-mw/api/oauth.py`, `llm-mw/api/integrations.py`): mở rộng PROVIDERS office365, cơ chế state ký HMAC.
- **Tools** (`tools/`): 3 tool mới (office365, github, google_drive) theo khuôn `google_gmail_tool.py`.
- **mcp_config.json / mcpo**: office365 MCP thu hẹp còn chức năng không mang danh tính cá nhân (hoặc gỡ bỏ).
- **Open WebUI admin data**: tạo groups, gắn access_grants (group + user) cho tools/tool servers, mở model gốc cho user thường — qua Admin API/script seed, không sửa mã nguồn Open WebUI.
- **Ops**: đăng ký app trên Azure AD/Entra ID tenant công ty (OFFICE365_CLIENT_ID/SECRET), cập nhật `.env`.
- **Docs**: cập nhật tài liệu 09 (user-management), 10 (user-guide), 12 (checklist tính năng).
