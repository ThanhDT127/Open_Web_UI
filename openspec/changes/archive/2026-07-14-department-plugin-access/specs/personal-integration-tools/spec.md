# personal-integration-tools Delta Specification

## ADDED Requirements

### Requirement: Office365 do MCP phụ trách, không có tool per-user
Mảng Office 365 SHALL do MCP server `office365` phụ trách; hệ thống MUST NOT có custom tool per-user cho office365. `tools/office365_tool.py` đã bị gỡ bỏ cùng nhánh thực thi phê duyệt `_execute_office365` trong `filter_approval_handler.py`, và `office365_tool` bị loại khỏi `WORKSPACE_TOOL_MATRIX` / `WORKSPACE_TOOL_FILES`.

**Bối cảnh quyết định (đảo ngược D3 cho riêng office365)**: MCP `office365` hiện tại (`scripts/office365_mcp.py`) là **bản giả lập** do phía mentor cung cấp — mọi hàm trả chuỗi cứng (`outlook_send_email` → `"Email sent ... (Simulated Outlook)"`), không gọi Microsoft Graph. Mentor sở hữu mảng này và sẽ thay bằng bản thật; team không có quyền/dữ liệu Azure để tự quyết. Chạy song song hai bản Office365 (một per-user thật, một giả lập) gây nhầm lẫn lớn hơn lợi ích, nên giữ một đường duy nhất.

Hạ tầng OAuth `office365` (provider trong `PROVIDERS`, scopes, `refresh_send_scope`, biến `OFFICE365_*`) SHALL được giữ lại — bản thật của mentor nhiều khả năng cần, và gỡ đi là phá bỏ công việc đã hoàn thành mà không thu được gì.

#### Scenario: Không còn tool office365 per-user
- **WHEN** user bất kỳ (kể cả admin) mở tool picker
- **THEN** không có `office365_tool`; chỉ có `server:office365` (MCP)

#### Scenario: Seed lại không dựng lại tool đã gỡ
- **WHEN** chạy `--phase tools` và `--phase grants`
- **THEN** `office365_tool` không được tạo lại và không nhận grant nào; `tests/department-tool-access.spec.ts` liệt kê `office365_tool` trong `MUST_NOT_SEE` để chặn hồi quy

### Requirement: Tool GitHub và Google Drive per-user
Hệ thống SHALL cung cấp 2 custom tool dùng provider `github` và `google_drive` sẵn có trong PROVIDERS registry: GitHub (liệt kê repo, đọc issue/PR, tìm code) và Google Drive (tìm kiếm, đọc nội dung file), đều theo cơ chế get_token per-user.

#### Scenario: Đọc issue GitHub bằng token cá nhân
- **WHEN** user đã kết nối GitHub yêu cầu "tóm tắt issue đang mở của repo X"
- **THEN** tool truy cập bằng token của user đó (chỉ thấy repo user có quyền) và trả về tóm tắt

### Requirement: Cảnh báo rõ MCP office365 là bản giả lập
Chừng nào `scripts/office365_mcp.py` còn trả dữ liệu giả, tài liệu người dùng (`docs/10-user-guide-vi.md`) MUST cảnh báo rõ rằng Office 365 **báo thành công nhưng không thực hiện gì** — không gửi mail, không tạo lịch, không nhắn Teams — và mail/file đọc ra là **dữ liệu mẫu bịa sẵn**, không phải hộp thư thật. Người dùng cần gửi mail thật MUST được chỉ sang Gmail.

**Lý do**: rủi ro lớn nhất của bản giả lập không phải là nó không chạy, mà là nó **nói dối một cách thuyết phục**. User nhờ "gửi mail cho khách hàng" và nhận được "Đã gửi thành công" trong khi không có mail nào rời khỏi hệ thống — hỏng im lặng, phát hiện muộn.

#### Scenario: User được cảnh báo trước khi tin kết quả
- **WHEN** user đọc mục công cụ theo phòng ban trong user guide
- **THEN** Office 365 mang nhãn cảnh báo và nêu rõ nó không gửi/tạo gì thật, kèm chỉ dẫn dùng Gmail để gửi mail thật

#### Scenario: Mentor thay bản thật
- **WHEN** MCP office365 được thay bằng bản gọi Microsoft Graph thật
- **THEN** gỡ cảnh báo khỏi `docs/10`, `docs/12`; xem lại quyết định về danh tính (MCP dùng chung 1 danh tính — trái D3) trước khi mở cho user
