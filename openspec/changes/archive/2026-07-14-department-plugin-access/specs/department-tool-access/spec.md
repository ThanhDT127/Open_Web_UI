# department-tool-access Delta Specification

## ADDED Requirements

### Requirement: Phân quyền tool theo group phòng ban và theo user
Quyền dùng tool SHALL nằm hoàn toàn ở bảng `access_grant` của Open WebUI, với `principal_type` là `group` (phòng ban) hoặc `user` (ngoại lệ cá nhân): workspace tools qua `POST /api/v1/tools/id/{id}/access/update`, tool server connections (mcpo) qua `config.access_grants`. Tool không được cấp quyền cho principal nào MUST ở trạng thái private (chỉ admin thấy).

Model MUST NOT gate tool: không model nào mang `meta.toolIds`. User chọn model gốc bất kỳ rồi tự bật tool trong tool picker; Open WebUI lọc danh sách theo grant của user đó.

#### Scenario: User thấy đúng tool của phòng mình
- **WHEN** user thuộc group `marketing` mở danh sách tool khả dụng
- **THEN** user chỉ thấy các tool được cấp cho group `marketing` (và tool public toàn công ty), không thấy tool của phòng khác

#### Scenario: Ngoại lệ theo cá nhân
- **WHEN** admin cấp thêm một tool cho một user cụ thể (dashboard → Users → Edit User → mục Tool)
- **THEN** riêng user đó thấy và gọi được tool, các thành viên khác cùng group thì không

#### Scenario: Tool chưa gán quyền
- **WHEN** một tool server mới được thêm vào mcpo mà chưa gắn access_grants
- **THEN** chỉ admin nhìn thấy và gọi được tool server đó

#### Scenario: Chặn ở server, không chỉ ẩn trên UI
- **WHEN** user gọi thẳng API chat với `tool_ids` chứa tool họ không có quyền
- **THEN** Open WebUI (`utils/tools.py: get_tools`) kiểm tra `AccessGrants.has_access` và loại bỏ tool đó khỏi context, ghi log `Access denied to tool ...`

### Requirement: Bật/tắt tool ngay trong Edit Group và Edit User
Dashboard `llm-mw` SHALL cho admin bật/tắt từng tool ngay trong **Groups → Edit Group** và **Users → Edit User**, ghi vào chính bảng `access_grant` của Open WebUI. Open WebUI 0.9.6 chỉ biên tập được quyền tool từ phía *tool* và không có màn hình phân quyền theo user, nên UI này là nơi duy nhất phân quyền theo trục group/user.

Thao tác ghi MUST chỉ động đến đúng cặp `(tool, principal)` đang bật/tắt. Endpoint `POST /api/v1/tools/id/{id}/access/update` của Open WebUI xóa sạch grant của tool rồi ghi lại, nên MUST NOT dùng cho việc này — bật một tool cho một group sẽ thu hồi quyền của mọi group và user khác trên tool đó.

Modal Edit User SHALL phân biệt rõ quyền **kế thừa từ group** (hiển thị đã bật, khóa lại, ghi rõ group nào) với quyền **cấp riêng cho user** (bật/tắt được). Bỏ tick một quyền kế thừa không có tác dụng — phải sửa ở Edit Group — nên không được cho thao tác.

#### Scenario: Bật tool cho phòng ban
- **WHEN** admin mở Groups → Edit Group của một phòng ban, tick một tool và bấm Save
- **THEN** một grant `(tool, group, read)` được thêm vào `access_grant`, mọi thành viên phòng đó thấy tool trong tool picker, và grant của các group/user khác trên tool đó không đổi

#### Scenario: Cấp riêng cho một cá nhân
- **WHEN** admin mở Users → Edit User của một user đã map sang Open WebUI, tick một tool nằm ngoài chính sách phòng ban rồi Save
- **THEN** một grant `(tool, user, read)` được thêm, riêng user đó dùng được tool

#### Scenario: Không cho thu hồi nhầm quyền kế thừa
- **WHEN** admin mở Edit User của một user đang thuộc group có quyền dùng tool X
- **THEN** tool X hiện là đã bật, bị khóa, kèm nhãn tên group cấp quyền

### Requirement: Ma trận phân quyền mặc định
Script seed SHALL áp ma trận quyền mặc định: nhóm tool dùng chung (export file, web search) public cho mọi user; `postgres` và `playwright` chỉ cấp cho `it` và `ky-thuat-rd`; `office365` cấp cho mọi group trừ khi admin thu hẹp; `github` cấp cho `it` và `ky-thuat-rd`; `google_drive` cấp cho mọi group phòng ban.

#### Scenario: Áp ma trận mặc định
- **WHEN** admin chạy script seed phần access_grants
- **THEN** từng tool/tool server được gắn đúng danh sách group theo ma trận, và script in bảng đối chiếu tool → groups để admin kiểm tra

### Requirement: Seed lại không được thu hồi quyền admin cấp tay
`POST /api/v1/tools/id/{id}/access/update` gọi `set_access_grants` — xóa sạch grant cũ rồi ghi lại. Script seed MUST giữ nguyên các grant `principal_type=user` (không phải wildcard `*`) đang có trong DB khi áp lại ma trận, để ngoại lệ cá nhân admin cấp trong UI không bị âm thầm thu hồi ở lần chạy sau.

#### Scenario: Chạy lại seed sau khi cấp quyền cá nhân
- **WHEN** admin cấp tool cho một user trong UI rồi chạy lại `--phase grants`
- **THEN** grant theo group được áp lại theo ma trận và grant theo user vẫn còn nguyên

### Requirement: Đồng bộ source tool từ repo vào Open WebUI
Open WebUI lưu source Python của tool trong DB (bảng `tool`/`function`, cột `content`) và KHÔNG nạp tool từ thư mục trên đĩa. Để repo là nguồn sự thật duy nhất, script seed SHALL đọc file trong `tools/` và đẩy lên qua Admin API (`POST /api/v1/tools/create` hoặc `/id/{id}/update`), thay cho việc copy-paste thủ công qua UI. Tool id MUST bằng tên file (không đuôi `.py`) để khớp ma trận phân quyền.

Script MUST idempotent: chỉ ghi đè khi source trong repo khác bản trong DB. Script SHALL bơm sẵn valves lấy từ `.env` (`SUBKEY_ADMIN`, `MW_BASE_URL`, `MW_PUBLIC_URL`) cho những tool có khai báo, và SHALL bật (`is_active`) các function, đặt `is_global` cho filter phê duyệt để nó áp dụng với mọi model.

#### Scenario: Import tool mới không cần thao tác tay
- **WHEN** admin thêm file `tools/<ten>.py` mới rồi chạy script seed phần tools
- **THEN** tool xuất hiện trong Workspace với đúng id, tên lấy từ frontmatter `title:`, valves đã điền sẵn, sẵn sàng gắn access_grants

#### Scenario: Sửa tool trong repo rồi đồng bộ lại
- **WHEN** admin sửa source một tool trong repo rồi chạy lại script
- **THEN** bản trong Open WebUI được cập nhật theo repo; tool không đổi source thì bỏ qua, không tạo bản trùng

### Requirement: Kiểm chứng phân quyền sau seed
Hệ thống SHALL có Playwright test xác minh: user thử nghiệm thuộc một group chỉ nhìn thấy bộ tool của group đó trong UI chat, và các toggle trong Edit Group / Edit User ghi thật vào `access_grant`.

#### Scenario: Test tự động phân quyền
- **WHEN** chạy bộ test Playwright với user test thuộc group `ke-toan-tai-chinh`
- **THEN** test pass khi danh sách tool hiển thị khớp ma trận và fail nếu lộ tool ngoài quyền

#### Scenario: Test tự động UI bật/tắt tool
- **WHEN** chạy `tests/dashboard-tool-access.spec.ts`
- **THEN** test lái UI thật: bật tool trong Edit Group → grant xuất hiện trong `access_grant`; tắt → grant biến mất mà các tool khác của group còn nguyên; Edit User hiện đúng tool kế thừa (khóa) và cấp riêng được
