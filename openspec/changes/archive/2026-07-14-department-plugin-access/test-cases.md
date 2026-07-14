# Test Cases: department-plugin-access

> Bám theo `specs/` của change này. Mỗi test case truy vết về requirement gốc.
> **Phương thức**: `unit` (pytest), `e2e` (Playwright), `manual` (thao tác tay + quan sát), `api` (curl/httpx).
> **Ưu tiên**: P1 = chặn release, P2 = quan trọng, P3 = nice-to-have.

## Môi trường & dữ liệu test chuẩn bị trước

| Mã | Hạng mục | Chi tiết |
|----|----------|----------|
| ENV-1 | User test | `test_marketing@congty.vn` (group `marketing`), `test_ketoan@congty.vn` (group `ke-toan-tai-chinh`), `test_it@congty.vn` (group `it`), `test_nogroup@congty.vn` (không group), 1 tài khoản admin |
| ENV-2 | Tài khoản ngoài | 2 tài khoản Microsoft 365 thật (tenant dev/công ty), 1 tài khoản GitHub, 1 tài khoản Google có Drive |
| ENV-3 | Hệ thống | Stack chạy đủ 10 container healthy; `.env` có OFFICE365/GITHUB/GOOGLE client id+secret; backup DB trước khi chạy nhóm seed |
| ENV-4 | Baseline | Chụp danh sách tool **và model** hiển thị của 1 user thường TRƯỚC khi seed (đối chiếu regression — xem TC-MDL-03) |
| ENV-5 | Chạy script seed | Host thường thiếu `requests` và không resolve được `open-webui`. Chạy trong container tạm trên network của stack (xem design.md → Migration Plan):<br>`docker run --rm --network oppen_web_ui_openwebui-network -v "$PWD":/repo -w /repo python:3.11-slim sh -c "pip install -q requests && python scripts/seed_department_access.py --url http://open-webui:8080"` |
| ENV-6 | Thứ tự phase | `groups → tools → models → grants`. Chạy `grants` trước `tools` sẽ ra `⚠ CHƯA CÓ trong workspace` (tool chưa tồn tại thì grant không gắn vào đâu) |

---

## 1. TC-GRP — Seed group phòng ban (specs/department-groups)

| ID | Ưu tiên | PT | Mô tả | Bước thực hiện | Kết quả mong đợi |
|----|---------|-----|-------|----------------|------------------|
| TC-GRP-01 | P1 | api | Seed lần đầu | DB chưa có group → chạy `seed_department_access.py` | Tạo đúng 8 group (`ban-lanh-dao`…`it`), mỗi group có description tiếng Việt + metadata `seeded-by`; script in danh sách đã tạo |
| TC-GRP-02 | P1 | api | Idempotent | Chạy lại script ngay sau TC-GRP-01 | Không tạo trùng (vẫn 8 rows), không sửa membership, exit 0 |
| TC-GRP-03 | P1 | api | Dry-run | Xóa 1 group rồi chạy `--dry-run` | In thao tác dự kiến (tạo lại 1 group), DB không đổi (vẫn 7) |
| TC-GRP-04 | P2 | api | Rollback an toàn | Gán 1 user vào group `marketing` → chạy `--rollback` | Group `marketing` được giữ + cảnh báo rõ tên; các group rỗng bị xóa |
| TC-GRP-05 | P2 | api | Rollback force | Chạy `--rollback --force` | Xóa toàn bộ group có metadata `seeded-by`, kể cả có thành viên; group tạo tay (không metadata) không bị đụng |
| TC-GRP-06 | P3 | api | Group tạo tay không bị ảnh hưởng | Tạo tay group `du-an-x` → chạy seed + rollback | `du-an-x` nguyên vẹn qua cả 2 thao tác |

## 2. TC-ACC — Phân quyền tool theo group (specs/department-tool-access)

| ID | Ưu tiên | PT | Mô tả | Bước thực hiện | Kết quả mong đợi |
|----|---------|-----|-------|----------------|------------------|
| TC-ACC-01 | P1 | api | Áp ma trận mặc định | Chạy seed phần access_grants | Script in bảng tool → groups khớp ma trận trong spec; verify qua Admin API từng connection có access_grants đúng |
| TC-ACC-02 | P1 | e2e | User thấy đúng tool phòng mình | Login `test_marketing` → mở danh sách tool trong chat | Chỉ thấy tool của group `marketing` + tool public; KHÔNG thấy `postgres`, `playwright` |
| TC-ACC-03 | P1 | e2e | Cách ly chéo phòng ban | Login `test_ketoan` → so danh sách tool với `test_it` | Hai danh sách khác nhau đúng theo ma trận; `postgres` chỉ hiện với `test_it` |
| TC-ACC-04 | P1 | e2e | Default-private | Thêm 1 tool server mới vào mcpo, KHÔNG gán access_grants → login user thường | User không thấy; admin thấy |
| TC-ACC-05 | P1 | api | Chặn gọi trực tiếp (không chỉ ẩn UI) | Dùng token của `test_marketing` gọi API invoke tool `postgres` | Bị từ chối (403/404), không thực thi |
| TC-ACC-06 | P2 | e2e | User không group | Login `test_nogroup` | Chỉ thấy tool public (export, web search); mọi tool theo phòng ban ẩn |
| TC-ACC-07 | P2 | e2e | Thay đổi quyền có hiệu lực | Admin gỡ group `marketing` khỏi 1 tool → user refresh | Tool biến mất khỏi danh sách của `test_marketing` không cần restart |
| TC-ACC-08 | P3 | manual | Tool public toàn công ty | Cả 4 user test mở tool export file | Tất cả thấy và dùng được |
| TC-ACC-09 | P1 | api | Đồng bộ source tool từ repo | DB chưa có tool → chạy `--phase tools` | 5 workspace tool + 4 function được tạo với id = tên file; tên lấy từ frontmatter `title:`; valves `SUBKEY_ADMIN`/`MW_BASE_URL`/`MW_PUBLIC_URL` đã điền sẵn từ `.env` |
| TC-ACC-10 | P1 | api | Sửa tool trong repo → đồng bộ lại | Sửa 1 dòng trong `tools/github_tool.py` → chạy lại `--phase tools` | Chỉ `github_tool` báo "cập nhật source"; 4 tool còn lại báo "không đổi"; không tạo bản trùng |
| TC-ACC-11 | P1 | api | Idempotent phase tools | Chạy `--phase tools` 2 lần liên tiếp không sửa file | Lần 2 mọi tool/function đều báo "source không đổi", exit 0 |
| TC-ACC-12 | P2 | api | Filter phê duyệt là global | Sau `--phase tools`, kiểm tra `function` trong DB | `filter_approval_handler` có `is_active = true` VÀ `is_global = true` (nếu không, cổng phê duyệt không áp dụng cho model nào) |
| TC-ACC-13 | P1 | e2e | **Override theo user** | Admin cấp `github_tool` cho riêng `test_ketoan` (dashboard → Users → Edit User → mục Tool) | `test_ketoan` thấy và gọi được `github_tool`; các thành viên khác của `ke-toan-tai-chinh` vẫn KHÔNG thấy |
| TC-ACC-14 | P0 | api | **Seed lại không thu hồi quyền cấp tay** | Cấp tool cho 1 user trong UI → chạy lại `--phase grants` → kiểm tra `access_grant` | Row `principal_type='user'` VẪN CÒN. `set_access_grants` xóa-rồi-ghi-lại, nên thiếu `preserved_user_grants()` là mọi ngoại lệ cá nhân bị âm thầm thu hồi |
| TC-ACC-15 | P2 | api | Idempotent phase grants | Chạy `--phase grants` 2 lần | Lần 2 mọi dòng báo "không đổi" (kể cả tool có override user) |
| TC-ACC-16 | P0 | e2e | **Edit Group bật tool** | Dashboard → Groups → ✏️ Edit Group → tick tool → Save (`tests/dashboard-tool-access.spec.ts`) | Grant `(tool, group, read)` xuất hiện trong `access_grant`; chip tool hiện trong bảng |
| TC-ACC-17 | P0 | e2e | **Edit Group tắt tool không cuốn theo tool khác** | Bật rồi tắt `code_interpreter` cho `ke-toan-tai-chinh` | Grant biến mất; các tool khác của group (`google_gmail_tool`…) VẪN CÒN. Bảo vệ chống dùng nhầm `set_access_grants` (xóa-sạch-ghi-lại) |
| TC-ACC-18 | P0 | e2e | **Edit User: quyền kế thừa bị khóa** | Mở Edit User của user thuộc group có quyền tool X | Tool X hiện đã bật, `disabled`, kèm nhãn "từ &lt;group&gt;" — bỏ tick không có tác dụng nên không cho thao tác |
| TC-ACC-19 | P0 | e2e | **Edit User cấp riêng** | Tick một tool ngoài chính sách phòng ban trong Edit User → Save | `GET /tool-access/users/{id}` trả `direct=true`, `effective=true`; grant `(tool, user, read)` có trong DB |

## 3. TC-MDL — Model gốc & bất biến "model không gate tool"

> Thay cho TC-AST (trợ lý phòng ban) — 5 preset đã gỡ bỏ, xem D2 trong design.md.
> Các case model gốc bên dưới vẫn giữ nguyên giá trị hồi quy.

| ID | Ưu tiên | PT | Mô tả | Bước thực hiện | Kết quả mong đợi |
|----|---------|-----|-------|----------------|------------------|
| TC-MDL-01 | P1 | api | **Model không gate tool** (bất biến cốt lõi) | `SELECT count(*) FROM model WHERE meta::json->>'toolIds' NOT IN (NULL,'[]')` | Trả về **0**. Bất kỳ model nào mang `toolIds` là đã tái lập gate theo model — vi phạm D2 |
| TC-MDL-02 | P1 | api | **Không tool nào public** | `SELECT count(*) FROM access_grant WHERE resource_type='tool' AND principal_id='*'` | Trả về **0** (default-private). Wildcard chỉ được phép trên MCP server `fetch` / `sequential-thinking` |
| TC-MDL-03 | P1 | e2e | **Model AI gốc không bị mất** (hồi quy) | Sau khi chạy đủ 4 phase, login `test_it` → mở ô chọn model | Thấy đủ **20 model AI gốc** (5 auto + 15 `chat-*`) |
| TC-MDL-04 | P0 | api | **Rollback lọc theo `seeded-by` phải kèm `base_model_id`** (bẫy đã sập 1 lần) | Bất kỳ code nào xóa model theo tag `seeded-by` MUST kiểm tra thêm `base_model_id`. Chạy `--rollback --dry-run` trước mọi lần rollback | Model gốc (`base_model_id IS NULL`) và preset (`IS NOT NULL`) **mang cùng tag** `seeded-by`. Lọc thiếu ⇒ xóa sạch 20 model gốc, user thường không còn model nào để chat |
| TC-MDL-05 | P2 | api | Model không dùng để chat bị loại | Sau `--phase models`, liệt kê bảng `model` where `base_model_id IS NULL` | Không có model `img-*`, embedding hay rerank nào được mở cho user |
| TC-MDL-06 | P1 | api | Idempotent phase models | Chạy `--phase models` 2 lần | Lần 2 báo "mở mới 0, cập nhật quyền 0, không đổi 20"; không lỗi "model id is already registered" |
| TC-MDL-07 | P1 | e2e | Nút Xuất file còn sống sau khi gỡ preset | Login user bất kỳ, chat 1 câu | Action "Xuất file" hiện dưới câu trả lời (nhờ `tool_export_all.is_global = true`, trước đây do `meta.actionIds` của preset) |

## 4. TC-SEC — OAuth session-binding / chống CSRF token-binding (specs/oauth-click-to-connect)

Trục vá là **danh tính-tại-callback-từ-phiên Open WebUI** + `nonce` double-submit cookie +
state ký/exp (design D4 cập nhật). Danh tính KHÔNG còn đến từ tham số client ở `/connect`.

| ID | Ưu tiên | PT | Mô tả | Bước thực hiện | Kết quả mong đợi |
|----|---------|-----|-------|----------------|------------------|
| TC-SEC-01 | P1 | unit | Sign/verify state hợp lệ | Tạo state {provider, nonce, exp} → verify ngay | Verify pass, giải mã đúng provider + nonce |
| TC-SEC-02 | P1 | unit | State hết hạn | Tạo state exp quá khứ (mock +11 phút) → verify | Verify fail, lý do "expired" |
| TC-SEC-03 | P1 | unit | Sai chữ ký / sửa payload | Sửa 1 ký tự chữ ký hoặc payload → verify | Verify fail |
| TC-SEC-04 | P1 | unit | Verify cookie phiên Open WebUI | JWT `token` hợp lệ / sai chữ ký / hết hạn / thiếu | Hợp lệ → trả openwebui_user_id; còn lại → coi như chưa đăng nhập |
| TC-SEC-05 | P1 | api | Callback thiếu cookie nonce | GET `/callback?code=x&state=<hợp lệ>` không kèm cookie `mw_oauth_nonce` | HTTP 400; không row mới `mw_user_integrations`; không gọi token_url (kiểm log) |
| TC-SEC-06 | P1 | api | **Biến thể 1 — provider URL dựng sẵn** | Kẻ tấn công đưa nạn nhân URL authorize dựng sẵn (bỏ qua `/connect`); nạn nhân consent → callback không có cookie nonce | HTTP 400; không lưu token |
| TC-SEC-07 | P1 | api | **Biến thể 2 — link /connect mang id kẻ tấn công** | Nạn nhân (có phiên Open WebUI của chính mình) mở link `/connect` kẻ tấn công tạo → hoàn tất consent | Token gắn vào **chính nạn nhân** (theo phiên), KHÔNG vào tài khoản kẻ tấn công |
| TC-SEC-08 | P1 | api | Chống replay (cookie single-use) | Hoàn tất 1 luồng hợp lệ (cookie nonce bị xóa); gọi lại callback trong cùng trình duyệt (không còn cookie nonce) | Lần 2 trả HTTP 400 (thiếu cookie khớp) |
| TC-SEC-09 | P1 | api | Callback không phiên Open WebUI | Hoàn tất luồng trong trình duyệt chưa đăng nhập Open WebUI | HTTP 400 + hướng dẫn đăng nhập; không lưu token |
| TC-SEC-10 | P1 | e2e | Regression gmail flow | User thật đăng nhập Open WebUI → bấm connect gmail (link chỉ có `?provider=`) → gửi 1 mail | Toàn flow chạy; token gắn đúng user; link connect không còn `openwebui_user_id` |
| TC-SEC-11 | P2 | api | State format cũ bị từ chối | Callback với state kiểu cũ `provider:ow_user_id:<id>` | HTTP 400 |

## 5. TC-O365 — Office365 per-user (specs/personal-integration-tools)

| ID | Ưu tiên | PT | Mô tả | Bước thực hiện | Kết quả mong đợi |
|----|---------|-----|-------|----------------|------------------|
| TC-O365-01 | P1 | e2e | Chưa kết nối → nhận link | User chưa connect gọi tool office365 "đọc mail mới" | Tool trả link connect + hướng dẫn tiếng Việt; không action nào chạy |
| TC-O365-02 | P1 | manual | Connect flow đầy đủ | Bấm link → đăng nhập M365 → consent | Consent liệt kê đúng 5 scopes; redirect về callback báo thành công; token mã hóa trong `mw_user_integrations` |
| TC-O365-03 | P1 | manual | Mail đứng tên user thật | User A gửi mail cho user B qua tool | Mail đến từ địa chỉ user A; có trong Sent Items của A |
| TC-O365-04 | P1 | manual | Cách ly danh tính 2 user | User A và B cùng gửi mail qua tool | Mỗi mail đứng đúng tên từng người; không lẫn token |
| TC-O365-05 | P2 | manual | Lịch + Teams + SharePoint | Lần lượt: tạo event, gửi tin Teams, tìm file SharePoint | Event trong calendar cá nhân; tin nhắn đứng tên user; kết quả tìm đúng quyền truy cập của user |
| TC-O365-06 | P1 | api | Auto-refresh token | Set `expires_at` quá khứ trong DB → gọi tool | Middleware tự refresh, action thành công, `expires_at` mới trong DB |
| TC-O365-07 | P2 | manual | Token bị thu hồi | Revoke consent trên portal Microsoft → gọi tool | Tool báo cần kết nối lại kèm link (không crash, không lộ lỗi thô) |
| TC-O365-08 | P1 | manual | Migration MCP: hết đường danh tính chung | Sau khi gỡ send-actions khỏi MCP: yêu cầu model "gửi mail" trong chat có cả 2 đường | Chỉ tool per-user được gọi; MCP office365 không còn expose `outlook_send_email`/`teams_send_message` (verify qua `curl mcpo:8015/office365/openapi.json`) |

## 6. TC-GH / TC-GD — GitHub & Google Drive per-user

| ID | Ưu tiên | PT | Mô tả | Bước thực hiện | Kết quả mong đợi |
|----|---------|-----|-------|----------------|------------------|
| TC-GH-01 | P1 | e2e | Chưa connect → link | User chưa connect GitHub gọi tool | Trả link connect provider `github` |
| TC-GH-02 | P1 | manual | Đọc issue bằng token cá nhân | Connect → "tóm tắt issue đang mở của repo X" (repo private user có quyền) | Trả đúng nội dung; repo user KHÔNG có quyền → tool báo không truy cập được |
| TC-GH-03 | P2 | e2e | Phân quyền hiển thị | `test_marketing` không thấy tool GitHub; `test_it` thấy | Khớp ma trận (github → `it`, `ky-thuat-rd`) |
| TC-GD-01 | P1 | manual | Drive tìm + đọc file | Connect Google → "tìm file kế hoạch Q3 trong Drive của tôi" | Kết quả từ Drive của chính user; scope read-only (không sửa/xóa được) |
| TC-GD-02 | P2 | manual | Cách ly dữ liệu | 2 user cùng tìm 1 tên file | Mỗi người chỉ nhận kết quả từ Drive của mình |

## 7. TC-REG — Regression toàn hệ thống

| ID | Ưu tiên | PT | Mô tả | Bước thực hiện | Kết quả mong đợi |
|----|---------|-----|-------|----------------|------------------|
| TC-REG-01 | P1 | manual | Middleware ổn định sau deploy | `docker ps` + logs 10 phút sau deploy | healthy; 0 worker died; 0 FILE-ONLY; 0 deadlock |
| TC-REG-02 | P1 | e2e | Tool cũ không hỏng | Chạy export Excel/PDF/Word + web search + 1 chat thường | Hoạt động như baseline ENV-4 |
| TC-REG-03 | P1 | api | Quota & audit không đổi | User chat 3 request → check `mw_audit_log` | Đủ 3 dòng log user/model/token/cost như trước |
| TC-REG-04 | P2 | e2e | Admin bypass | Login admin | Thấy toàn bộ tool bất kể access_grants |
| TC-REG-05 | P2 | manual | Gmail tool sống sau mọi thay đổi | Gửi 1 mail qua gmail tool ở cuối đợt test | Thành công (chốt regression OAuth broker) |

---

## Tiêu chí hoàn thành (Definition of Done)

- 100% test P1 pass; P2 pass ≥ 90% (fail phải có ticket theo dõi); P3 ghi nhận.
- Bộ e2e (TC-ACC-02/03/04, TC-MDL-03, TC-SEC-07, TC-GH-01) tự động hóa bằng Playwright, đưa vào `tests/`.
- Bộ unit TC-SEC-01→04, 09 đưa vào `llm-mw/` chạy bằng pytest.
- Kết quả từng lượt chạy ghi vào `test-results/` theo mẫu hiện hành của dự án.

## Truy vết specs

| Nhóm TC | Requirement gốc |
|---------|-----------------|
| TC-GRP | department-groups: Seed bộ group mẫu; Rollback group đã seed |
| TC-ACC | department-tool-access: Phân quyền theo group; Ma trận mặc định; Đồng bộ source tool từ repo; Kiểm chứng sau seed |
| TC-MDL | Model gốc vẫn chọn được sau seed; model KHÔNG gate tool (không `meta.toolIds`); không tool nào public; rollback không xóa nhầm model gốc |
| TC-SEC | oauth-click-to-connect (MODIFIED): OAuth Flow Endpoints (state HMAC) |
| TC-O365, TC-GH, TC-GD | personal-integration-tools: office365/GitHub/Drive per-user; Thu hẹp MCP |
| TC-REG | Bảo toàn hành vi hệ thống hiện hữu |
