# Tasks: department-plugin-access

## 1. Spike & nền tảng phân quyền

- [x] 1.1 Spike: xác minh Admin API của Open WebUI 0.9.6 cho phép tạo group, gán access_control cho tool/model, gán access_grants cho tool server connection (curl với admin token; ghi kết quả vào design.md Open Questions)
- [x] 1.2 Viết `scripts/seed_department_access.py` — phần tạo 8 group phòng ban mẫu (idempotent, `--dry-run`, `--rollback`, metadata `seeded-by`)
- [x] 1.3 Chạy seed group trên môi trường thật, xác nhận 8 group trong bảng `group`

## 2. Phân quyền tool & tool server

- [x] 2.1 Bổ sung phần access_grants vào script seed: áp ma trận tool → groups mặc định cho 5 mcpo server và 6 workspace tool, in bảng đối chiếu
- [x] 2.2 Chạy seed access_grants, kiểm tra tay: user test thuộc 1 group chỉ thấy đúng bộ tool
- [x] 2.3 Viết Playwright test phân quyền (user test group `ke-toan-tai-chinh` không thấy tool ngoài ma trận)

## 3. ~~Trợ lý phòng ban (model presets)~~ — ĐÃ GỠ BỎ

Hướng preset bị loại bỏ hoàn toàn (xem D2 mới trong design.md): nó ràng tool vào model,
tạo trục quyền thứ hai chồng lên group và khiến admin tưởng quyền đi theo model.
Quyền tool nay chỉ nằm ở `access_grant` theo group + user.

- [x] 3.1 Gỡ 5 preset khỏi DB (`--phase presets --rollback`) và khỏi script seed (`ASSISTANT_PRESETS`, `seed_presets`, phase `presets`)
- [x] 3.2 Vá bug chí mạng trong `rollback_presets`: lọc model chỉ theo tag `seeded-by` mà thiếu điều kiện `base_model_id` ⇒ sẽ **xóa luôn 20 model gốc** (chúng mang cùng tag). Nay lọc `and m.get("base_model_id")`, đối xứng với `rollback_base_models`
- [x] 3.3 Đặt `tool_export_all` thành `is_global: True` — trước đây nó hiện ra nhờ `meta.actionIds` của preset; preset mất thì không model nào tham chiếu ⇒ nút Xuất file biến mất
- [x] 3.4 Xóa `tests/department-assistants.spec.ts` (test bundle preset không còn đối tượng)

## 4. Vá bảo mật OAuth state (làm trước khi mở rộng OAuth)

- [x] 4.1 ~~Implement state HMAC trong `llm-mw/api/oauth.py`~~ — **CHƯA ĐỦ, xem mục 11**. Bản HMAC-only không vá được CSRF token-binding thật (design D4 cập nhật): `/connect` không auth vẫn cấp state ký cho id bất kỳ, callback không ràng phiên. Chữ ký + exp được GIỮ LẠI như một lớp, nhưng trục vá thật là danh tính-tại-callback-từ-phiên.
- [x] 4.2 Unit test sign/verify: state hợp lệ, hết hạn, sai chữ ký, bị sửa payload (`llm-mw/test_oauth_state.py` — 6 test, pass trong container)
- [x] 4.3 Regression test flow gmail tool end-to-end sau khi đổi state — `llm-mw/test_gmail_oauth_flow.py` (6 test, chạy thật qua middleware, nhánh OAuth mock): chưa kết nối → link connect; connect → state ký hợp lệ; callback chặn state giả (400, không lưu token); callback lưu token đúng `subkey_hash` của user; get_token trả token đúng user; đã kết nối → tool tạo PENDING_APPROVAL. **Phát hiện + vá 1 bug chặn**: `get_token` chỉ cho tra token theo `openwebui_user_id` khi caller có `role == "admin"`, nhưng tài khoản dịch vụ trong `users.json` không mang role đó → mọi tool đọc token dưới hash của tài khoản dịch vụ (dùng chung danh tính, trái D3). Nay ủy quyền theo service key (`OPENWEBUI_SERVICE_KEY`) thay vì role.

## 6. GitHub & Google Drive per-userx

- [x] 6.1 Viết `tools/github_tool.py` (list repo, đọc issue/PR, tìm code) dùng provider `github` sẵn có — 4 hàm chỉ-đọc: `list_my_repos`, `list_issues`, `read_issue`, `search_code`
- [x] 6.2 Viết `tools/google_drive_tool.py` (tìm kiếm, đọc file) dùng provider `google_drive` sẵn có — `search_drive_files`, `read_drive_file` (tự export Google Docs/Sheets/Slides sang văn bản; scope `drive.readonly` sẵn có là đủ)
- [x] 6.3 Import 2 tool, gắn quyền theo ma trận (github → `it`, `ky-thuat-rd`), thêm vào bundle tương ứng, test với user đã connect — ĐÃ XONG import + grants + bundle; CÒN LẠI test với user đã connect, chặn bởi việc chưa đăng ký OAuth app GitHub/Google (thiếu `GITHUB_CLIENT_ID`, `GOOGLE_CLIENT_ID` ⇒ middleware chạy nhánh mock)

## 7. Tài liệu & bàn giao

- [x] 7.1 Cập nhật docs 09 (user-management: group + phân quyền tool), 10 (user-guide: cách kết nối tài khoản, dùng trợ lý phòng ban), 12 (checklist tính năng)
- [x] 7.2 Viết runbook ngắn cho admin: thêm 1 plugin mới cho 1 phòng ban theo công thức (provider entry → tool file → access_grants → bundle) — `docs/18-runbook-plugin-phong-ban.md`
- [x] 7.3 Ghi mục Future Work: Canva/Figma (chờ license), đồng bộ membership từ HR — mục "Future Work" trong design.md (thêm: liệt kê team/kênh Teams theo tên, rà soát tool ngoài ma trận)

## 8. Vá lỗi phát sinh khi vận hành thật (bổ sung sau khi seed lên môi trường)

- [x] 8.1 Phase `tools` trong script seed: đẩy source từ `tools/` trong repo lên Open WebUI qua Admin API (create/update, idempotent theo nội dung), bơm valves từ `.env`, bật function + đặt `is_global` cho filter phê duyệt — Open WebUI lưu tool trong DB chứ không đọc thư mục, trước đây phải copy-paste tay qua UI
- [x] 8.2 Phase `models`: **vá lỗi user thường mất sạch model AI**. Nguyên nhân: `utils/models.py: get_filtered_models` chỉ hiện cho user thường model **có dòng trong bảng `model`**; model gốc đến từ connection nên không có dòng nào ⇒ "chưa cấu hình" ⇒ admin-only. Phase này tạo dòng cấu hình + access_grants public cho 5 model auto + 15 model `chat-*` (loại `img-*`/embedding/rerank)
- [x] 8.3 ~~Siết phạm vi trợ lý theo group~~ — không còn đối tượng sau khi gỡ preset (xem mục 3)
- [x] 8.4 Vá `expires_at` cho provider không trả `expires_in` (GitHub OAuth App): trước đây mặc định 3600s ⇒ sau 1 giờ `get_token` coi là hết hạn, không có refresh token ⇒ bắt user kết nối lại dù token còn dùng tốt vĩnh viễn. Nay lưu `expires_at = NULL`
- [x] 8.5 **Xóa gate tool theo model + lỗ hổng public**: `scripts/inject_p2_components.py` gắn tool vào model bằng so khớp chuỗi tên (`if 'gemini' in model_id or 'gpt' in ... or 'claude' in ...`) và cấp `principal_id: "*"` (public cho mọi user) khi tạo tool; `scripts/inject_tool_servers.py` ghi **SQL thẳng** vào bảng `config` (trái nguyên tắc "mọi thao tác qua Admin API"), hardcode `"*"` cho 12 MCP server và **ghi đè trọn** `tool_server.connections` ⇒ xóa sạch grant theo group do `seed_grants` đặt. Cả hai script đã bị `seed_department_access.py` thay thế hoàn toàn và không còn nơi nào tham chiếu ⇒ **đã xóa**
- [x] 8.6 `seed_grants` giữ lại grant `principal_type=user` khi seed lại: `update_tool_access` gọi `set_access_grants` (xóa sạch rồi ghi lại) nên mỗi lần chạy `--phase grants` sẽ âm thầm thu hồi mọi ngoại lệ cá nhân admin cấp trong UI. Nay `preserved_user_grants()` giữ nguyên các grant đó

## 9. UI bật/tắt tool tại Edit Group & Edit User (dashboard llm-mw)

- [x] 9.1 `llm-mw/core/tool_access.py`: đọc/ghi `access_grant` của Open WebUI theo trục group và user. Ghi **có chủ đích từng dòng** (INSERT/DELETE đúng cặp `(tool, principal)`), KHÔNG dùng `POST /api/v1/tools/id/{id}/access/update` vì endpoint đó gọi `set_access_grants` — xóa sạch grant của tool rồi ghi lại ⇒ bật một tool cho một group sẽ cuốn theo grant của mọi group/user khác trên tool đó
- [x] 9.2 `llm-mw/api/tool_access.py` + route trong `main.py`: `GET/PUT /v1/_mw/admin/tool-access/{groups,users}/{id}` (guard `require_admin_or_session`, ghi audit trail)
- [x] 9.3 Dashboard: tab Groups thêm bảng "Phân quyền Tool theo phòng ban" + modal **Edit Group** với toggle từng tool; modal **Edit User** thêm mục Tool — quyền kế thừa từ group hiện là đã bật + **khóa** (bỏ tick không có tác dụng, phải sửa ở Edit Group), quyền cấp riêng thì bật/tắt được
- [x] 9.4 Playwright `tests/dashboard-tool-access.spec.ts` (4 test): lái UI thật, đối chiếu xuống `access_grant` — bật/tắt tool cho group, cấp riêng cho user, không cho thu hồi nhầm quyền kế thừa

### Bug có sẵn phát hiện khi dựng UI (dashboard trước đó KHÔNG chạy được)

- [x] 9.5 `dashboard/js/main.js` lỗi cú pháp — merge lỗi làm `import { refreshAnalytics }` khai hai lần (`SyntaxError: Identifier already declared`) và thiếu dấu phẩy trong destructuring ⇒ **toàn bộ module JS không nạp được**, `window.dashboardAPI` không bao giờ được tạo, mọi nút bấm là no-op. Đã dọn trùng lặp
- [x] 9.6 `dashboard/index.html` lỗi cú pháp trong `<script>` stub — `deletePrice` thiếu dấu phẩy trước khối lặp `refreshUsage` ⇒ `SyntaxError` ngay cả với stub
- [x] 9.7 `dashboard/index.html` **thiếu thẻ đóng `</div>`**: `<div class="metric-card interactive">` bị lặp hai lần (một cái không bao giờ đóng) ⇒ nó nuốt phần còn lại của trang, khiến **cả 9 tab kia trở thành con của `#usageTab`** và bị `display:none` theo nó khi chuyển tab ⇒ dashboard chỉ từng hiện được tab Usage. Đã sửa; cây DOM nay cân bằng, 10 tab đều là con trực tiếp của `#dashboard`
- [x] 9.8 `dashboard/js/notifications.js` poll `/admin/notifications/unread` ngay lúc tải trang (chưa có cookie) ⇒ 403 ⇒ handler 403 đá người dùng về màn login kèm "Session expired", **ghi đè cả phiên vừa đăng nhập thành công**. Nay chỉ poll sau khi đã đăng nhập (`startNotifications()` gọi từ `startDashboard()`)

## 11. Vá triệt để CSRF token-binding OAuth (session binding) — phát hiện khi review 2026-07-14

Bản HMAC-only (mục 4) chưa vá được lỗ hổng thật: `/connect` không auth vẫn cấp state ký cho id
bất kỳ, callback tin id trong state, không ràng phiên ⇒ kẻ xấu gắn token nạn nhân vào tài khoản
mình. Fix: danh tính gắn token lấy từ phiên Open WebUI tại callback (xem design D4 cập nhật).

- [x] 11.1 `llm-mw`: hàm `resolve_openwebui_session` xác minh cookie phiên `token` của Open WebUI (JWT HS256 ký `WEBUI_SECRET_KEY`, bỏ qua `alg` header ⇒ miễn nhiễm alg-confusion) → trả `openwebui_user_id`; kiểm chữ ký + hạn; thiếu/sai/hết hạn ⇒ "". Thêm `WEBUI_SECRET_KEY` vào `config.py` + env service middleware trong `docker-compose.yml` (đã xác nhận set trong container, len=26)
- [x] 11.2 `llm-mw/api/oauth.py` `/connect`: bỏ `openwebui_user_id`/`subkey`; xác minh phiên Open WebUI (thiếu ⇒ 401); sinh `nonce`, đặt cookie `mw_oauth_nonce` (HttpOnly, Secure, SameSite=Lax, ≤10 phút, path hẹp); `state` ký = {provider, nonce, exp}; redirect provider
- [x] 11.3 `llm-mw/api/oauth.py` `/callback`: verify chữ ký+hạn `state` → `nonce` khớp cookie double-submit → verify cookie phiên Open WebUI → gắn token vào user suy ra từ phiên; xóa cookie nonce (single-use); mọi bước sai ⇒ 400 (không trao đổi code, không lưu token). Đã xóa hẳn nhánh subkey + bug hash `hashlib.sha256` cũ
- [x] 11.4 `tools/*_tool.py` (gmail, github, drive): bỏ `&openwebui_user_id=` khỏi link connect trong `_connect_hint` — link chỉ còn `?provider=`
- [x] 11.5 `llm-mw/test_oauth_state.py` (9 test, PASS trong container): state ký/exp/tamper + `resolve_openwebui_session` (hợp lệ/sai chữ ký/hết hạn/thiếu cookie/secret rỗng). `test_gmail_oauth_flow.py` viết lại theo session-binding: (a) connect không phiên⇒401; (b) thiếu cookie nonce (biến thể 1)⇒400; (c) không phiên⇒400; (d) state giả⇒400; (e) link không lộ user_id — 5 gate PASS. Happy-path (callback lưu token + get_token + single-use replay⇒400) verify qua provider mock office365 (google/github có cred thật nên không mock-exchange được)
- [x] 11.6 Verify e2e qua nginx `:3000` thật: `/connect?...&openwebui_user_id=<bất kỳ>` không phiên ⇒ **401** (trước fix là 307 redirect Google cho id bất kỳ); `/callback` state giả ⇒ **400**. Biến thể 1 (URL provider dựng sẵn, không cookie nonce)⇒400; happy-path office365 mock gắn token đúng user theo phiên

## 12. Chuyển cấu hình OAuth từ .env.example sang runbook docs/18, đặt env cạnh từng tool (D7)

- [x] 12.1 Gỡ khối "OAuth Click-to-Connect" khỏi `.env.example`; thay bằng 1 dòng trỏ tới `docs/18`
- [x] 12.2 Gộp cấu hình OAuth vào runbook `docs/18` Bước 1: bảng biến dùng chung (`MW_PUBLIC_URL`, `MW_SECRET`, `WEBUI_SECRET_KEY`, `OPENWEBUI_SERVICE_KEY`) + bảng biến theo từng tool (Google→Gmail/Drive, GitHub, Office365 + tenant); redirect URI, scopes, nhánh mock; cập nhật lệnh kiểm chứng (cần phiên Open WebUI, bỏ `openwebui_user_id`). Không tạo `docs/19`
- [x] 12.3 Kiểm chéo (grep): không còn `openwebui_user_id={` trong `docs/`/`tools/`; `.env.example` không còn client id vars, chỉ còn dòng trỏ `docs/18`; không tồn tại `docs/19`
