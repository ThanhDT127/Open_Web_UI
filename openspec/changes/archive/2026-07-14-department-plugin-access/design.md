# Design: department-plugin-access

## Context

Stack Open WebUI 0.9.6 + middleware FastAPI phục vụ 200+ nhân viên. Hiện có 11 tool (5 MCP qua mcpo, 6 custom tool) hiển thị không phân biệt cho mọi user. DB `openwebui` đã có bảng `group`/`group_member` (0 rows) và cơ chế `access_grants` per-connection (`open_webui/utils/access_control.py: has_connection_access`) — mặc định rỗng = private/admin-only. Middleware đã có OAuth broker (`api/oauth.py` PROVIDERS registry: google_gmail, google_drive, github, office365) với flow connect/callback/get_token + auto-refresh, đang được `tools/google_gmail_tool.py` sử dụng làm mẫu per-user identity.

Ràng buộc: không fork/sửa mã nguồn Open WebUI (dùng image chính thức + Dockerfile overlay); mọi port internal đóng, chỉ Nginx :3000 mở; secrets qua `.env`.

## Goals / Non-Goals

**Goals:**
- Mỗi user chỉ nhìn thấy bộ tool đúng phòng ban của mình (3–6 tool/context) — giảm chọn sai tool.
- Action mang danh tính cá nhân (mail, lịch, Teams, GitHub, Drive) đứng tên user thật, truy vết được.
- Quy trình thêm plugin mới cho một phòng ban trở thành công thức lặp lại (provider entry + tool file + gắn access_grants + thêm vào bundle).
- Vá lỗ hổng CSRF trong OAuth `state`.

**Non-Goals:**
- Không tích hợp Canva/Figma (chưa có license) — chỉ chừa "khe cắm" trong bundle.
- Không đồng bộ membership từ nguồn nhân sự (HR/LDAP) — seed mẫu, gán tay qua admin UI.
- Không xây UI quản lý phân quyền riêng — dùng Admin UI/API sẵn có của Open WebUI.
- Không thay đổi cơ chế quota/audit hiện hành của middleware.

## Decisions

### D1. Phân quyền bằng cơ chế native của Open WebUI, seed qua Admin API
Dùng bảng `access_grant` sẵn có (0.9.6 đã migrate từ dict `access_control` sang bảng riêng), thao tác qua Admin API bằng script seed idempotent (`scripts/seed_department_access.py`) thay vì insert SQL trực tiếp. **Lý do**: API đi qua validation của Open WebUI, an toàn khi upgrade; SQL trực tiếp dễ vỡ theo schema (đã có tiền lệ schema quirks). **Alternative bị loại**: sửa mã nguồn Open WebUI — vi phạm ràng buộc không fork.

### D2. Trục phân quyền tool là GROUP + USER, model KHÔNG gate tool
Quyền dùng tool nằm hoàn toàn ở `access_grant` với `principal_type` = `group` (phòng ban) hoặc `user` (ngoại lệ cá nhân). Model không mang `meta.toolIds`: user chọn model gốc bất kỳ rồi tự bật tool trong tool picker, danh sách đã được Open WebUI lọc theo grant của họ.

**Lý do**: một trục quyền duy nhất, khớp cách admin tư duy ("phòng X được dùng tool nào") và biên tập được ngay trong UI native (Workspace → Tools → Access Control, chọn group hoặc user). Enforcement là thật chứ không chỉ ẩn/hiện: `utils/tools.py: get_tools()` kiểm tra lại `AccessGrants.has_access` cho từng `tool_id` lúc chạy và loại bỏ tool không có quyền.

**Thay thế D2 cũ** (bundle tool vào 5 "model preset trợ lý phòng ban"): preset ràng tool vào model, tạo trục quyền thứ hai chồng lên group và khiến admin tưởng quyền đi theo model. Nó chưa bao giờ là ranh giới quyền — `get_tools()` vẫn chặn theo grant — nên chỉ là lớp tiện dụng. 5 preset đã được gỡ bỏ hoàn toàn.

**Đánh đổi đã chấp nhận**: không còn giới hạn tool trong context theo preset, nên user thuộc nhiều group sẽ thấy nhiều tool hơn trong picker. Bù lại chính user chủ động chọn tool cho từng cuộc hội thoại — rủi ro "model chọn sai tool" chuyển thành lựa chọn có ý thức của người dùng.

### D2b. Nơi bật/tắt tool là Edit Group / Edit User của dashboard `llm-mw`

Admin bật/tắt tool ngay trong **Groups → ✏️ Edit Group** và **Users → ✏️ Edit User** của dashboard middleware. Backend ghi thẳng vào `access_grant` của Open WebUI (`llm-mw/core/tool_access.py`), là cùng bảng mà `get_tools()` kiểm lúc chạy — không sinh thêm trục quyền nào.

**Lý do không dùng UI native của Open WebUI**: nó chỉ biên tập được từ phía *tool* (Workspace → Tools → Access Control → thêm group/user), tức trả lời "tool này cho ai", trong khi admin tư duy ngược lại — "phòng ban / người này được dùng tool nào". Quan trọng hơn, Open WebUI **không có màn hình phân quyền theo user**: `UserUpdateForm` không có trường quyền nào, và `group.permissions` chỉ chứa quyền *năng lực* thô (`workspace.tools` = được tạo/sửa tool hay không), không phải danh sách tool được dùng. Muốn có toggle trong Edit Group/Edit User của Open WebUI thì phải fork frontend Svelte — vi phạm ràng buộc không fork (D1).

**Ghi có chủ đích, không xóa-sạch-ghi-lại**: `AccessGrants.set_access_grants` của Open WebUI (và endpoint `POST /api/v1/tools/id/{id}/access/update`) **xóa toàn bộ grant của tool rồi ghi lại**. Nếu dashboard dùng đường đó, bật/tắt một tool cho một group sẽ cuốn theo grant của mọi group và user khác trên tool đó. `core/tool_access.py` vì vậy INSERT/DELETE đúng cặp `(tool, principal)` đang thay đổi.

**Đánh đổi**: dashboard ghi trực tiếp vào DB `openwebui` (đã là pattern sẵn có: `core/identity.py`, `core/group_analytics.py`, `core/rag_health.py` đều đọc DB này). An toàn vì Open WebUI đọc `access_grant` tươi từ DB ở mỗi request, không cache.

### D3. Per-user identity qua OAuth broker middleware (pattern gmail), không qua mcpo
Tool github/drive/gmail viết theo khuôn `google_gmail_tool.py`: nhận `__user__` → `get_token` → gọi API ngoài bằng token của chính user. **Lý do**: mcpo chỉ có 1 cấu hình tĩnh = 1 danh tính chung, không audit được; broker đã có mã hóa AES-256 + auto-refresh chạy production với gmail. **Alternative bị loại**: mcpo với multi-user header injection — mcpo không hỗ trợ, phải fork.

> **Ngoại lệ: office365 KHÔNG áp D3.** `tools/office365_tool.py` đã bị **gỡ bỏ**; mảng Office 365 giao hẳn cho MCP server `office365` bên mentor. Quyết định của chủ dự án: mentor sở hữu và sẽ thay bằng bản thật, team không có quyền/dữ liệu Azure để tự quyết. Đánh đổi được chấp nhận có ý thức: MCP dùng **một danh tính chung** — đúng cái D3 muốn tránh — và bản hiện tại còn là **giả lập** (trả chuỗi cứng, không gọi Graph), nên đã cảnh báo rõ trong user guide. Chi tiết + điều kiện gỡ cảnh báo: `specs/personal-integration-tools/spec.md`, tasks mục 10.

### D4. Vá CSRF token-binding: danh tính lấy từ phiên tại callback + state ký + nonce double-submit

**Lỗ hổng thật (cập nhật sau review 2026-07-14):** bản vá ban đầu chỉ *ký HMAC* cho `state`
(payload chứa provider, user_id, exp, nonce) là **KHÔNG đủ**. `/connect` không cần auth và
sẽ cấp state ký hợp lệ cho bất kỳ `openwebui_user_id` nào; callback tin thẳng id trong state,
không ràng buộc phiên. Ký chỉ chống *sửa* state — nhưng kẻ tấn công đâu cần sửa: hắn xin một
state ký hợp lệ cho **id của chính hắn**, phishing nạn nhân hoàn tất consent → token Gmail của
nạn nhân bị lưu dưới tài khoản kẻ tấn công (hắn đọc mail nạn nhân qua tool). `nonce` sinh ra
nhưng `verify_state` không bao giờ đối chiếu ⇒ vô dụng. Đây là lỗi ở tầng thiết kế: chữ ký
không phải ranh giới cần thiết.

**Quyết định (fix triệt để):** danh tính gắn token **lấy từ phiên đăng nhập Open WebUI của
chính trình duyệt hoàn tất luồng tại `/callback`**, không lấy từ tham số client cung cấp.

1. **`/connect?provider=X`** (bỏ hẳn `openwebui_user_id`/`subkey` khỏi trục định danh trình
   duyệt): xác minh cookie `token` của Open WebUI → biết user; sinh `nonce`; đặt cookie
   `mw_oauth_nonce` (HttpOnly, Secure, SameSite=Lax, ≤10 phút); `state = b64(payload).hmac`
   với payload = {provider, nonce, exp}; redirect provider.
2. **`/callback`**: verify chữ ký + hạn `state` → verify `nonce` khớp cookie `mw_oauth_nonce`
   (double-submit) và chưa tiêu thụ → verify cookie phiên Open WebUI → suy ra `openwebui_user_id`
   → gắn token vào **chính user đó**; xóa cookie nonce (single-use). Sai bất kỳ bước nào ⇒ 400.

**Vì sao đóng được cả hai biến thể tấn công:**
- *Biến thể 1 — kẻ xấu gửi URL authorize dựng sẵn của provider*: nạn nhân bỏ qua `/connect`
  nên trình duyệt không có cookie `mw_oauth_nonce` khớp `state` ⇒ 400.
- *Biến thể 2 — kẻ xấu gửi link `/connect` mang id của hắn*: nạn nhân hoàn tất luồng, nhưng
  callback lấy danh tính từ **phiên của nạn nhân** ⇒ token gắn vào chính nạn nhân (vô hại),
  không vào tài khoản kẻ tấn công. Đây là điểm mà "ký state" hay "ticket cố định id" đều
  KHÔNG vá được, chỉ "danh tính-tại-callback-từ-phiên" mới vá được.

**Ràng buộc kèm theo:** Middleware phải xác minh được JWT cookie `token` của Open WebUI ⇒ cần
`WEBUI_SECRET_KEY` dùng chung (thêm vào env middleware). Đây là lý do bổ sung một requirement
"Xác thực phiên Open WebUI tại Middleware". Cookie `token` là HttpOnly + cùng origin `:3000` +
SameSite=Lax nên trình duyệt vẫn gửi kèm trên redirect GET từ provider về callback (đã xác minh
`routers/auths.py` của build 0.9.6 set cookie này). `MW_SECRET` vẫn dùng cho chữ ký `state`.

**Đường subkey (không phải trình duyệt):** luồng `?subkey=` cũ (test/CLI) không có phiên Open
WebUI. Nó bị loại khỏi trục định danh trình duyệt; nếu còn cần cho test thì để sau cổng service
key/admin, không phải đường mở cho trình duyệt user. `get_token` (server-to-server, dùng
`OPENWEBUI_SERVICE_KEY`) KHÔNG đổi.

**Alternative bị loại:**
- *Chỉ ký state* (bản cũ): không ràng phiên ⇒ không vá được (đã phân tích trên).
- *Ticket dùng một lần mã hóa id, mint server-side*: chặn được việc đổi id trong query nhưng
  vẫn thua biến thể 2 (id vẫn cố định trước khi nạn nhân consent). Không chọn.

### D7. Cấu hình OAuth chuyển từ `.env.example` sang hướng dẫn cài đặt
Gỡ khối biến OAuth Click-to-Connect khỏi `.env.example`, đưa vào spec hướng dẫn cài đặt
(`specs/oauth-click-to-connect`, requirement "Cấu hình OAuth nằm trong hướng dẫn cài đặt") và
tài liệu vận hành. **Lý do**: đây là cấu hình tích hợp *tùy chọn* cần bối cảnh (đăng ký app ở
provider, redirect URI, khóa tenant, nhánh mock). `.env.example` nên tối giản + trỏ tới hướng
dẫn; bảng biến trong spec là nguồn sự thật. **Đánh đổi**: người deploy không thấy sẵn biến
trong `.env.example` — bù lại bằng dòng trỏ rõ ràng và hướng dẫn đầy đủ từng bước.

### D5. Scopes office365 mở rộng theo nhu cầu thực, không xin thừa
Thêm `Calendars.ReadWrite`, `Sites.Read.All`, `ChannelMessage.Send` (delegated). Không xin `Mail.ReadWrite`, `Files.ReadWrite.All` cho tới khi có use case. **Lý do**: least privilege; consent screen ít scope dễ được user chấp nhận và IT phê duyệt.

### D6. Danh sách group mẫu cố định trong script seed
8 group: `ban-lanh-dao`, `kinh-doanh`, `marketing`, `ke-toan-tai-chinh`, `hcns`, `ky-thuat-rd`, `san-xuat`, `it`. Script seed idempotent (tồn tại thì bỏ qua), có flag `--dry-run`. Membership gán tay bởi admin.

## Risks / Trade-offs

- [Admin API của Open WebUI 0.9.6 có thể không expose đủ endpoint tạo group/gán access_grants] → Spike task đầu tiên xác minh bằng curl; fallback: insert SQL có kiểm soát trong transaction, đối chiếu model SQLAlchemy trong container.
- [User thuộc nhiều phòng ban thấy nhiều tool trong picker] → chấp nhận: user tự chọn tool cho từng hội thoại, không nhồi hết vào context. Nếu về sau thực sự phiền, xử lý bằng cách siết ma trận group chứ không dựng lại lớp preset.
- [Seed lại `--phase grants` có thể xóa mất grant admin cấp tay cho cá nhân trong UI] → `update_tool_access` gọi `set_access_grants` (xóa sạch rồi ghi lại), nên `seed_grants` GIỮ LẠI mọi grant `principal_type=user` không phải wildcard (`preserved_user_grants()`). Wildcard `*` vẫn do ma trận quản.
- [Đăng ký Azure AD app phụ thuộc IT công ty (ngoài team)] → tách task ops riêng, các tool code xong test bằng tenant dev/mock trước.
- [Gỡ chức năng khỏi office365 MCP làm gián đoạn user đang dùng] → migration: bật tool per-user trước, thông báo, gỡ MCP sau 2 tuần.
- [Session-binding làm hỏng link connect cũ đã gửi] → chấp nhận, link connect vốn dùng một lần; ngoài ra `nonce` nay single-use nên link cũ vô hiệu là đúng thiết kế.
- [Callback cần cookie phiên Open WebUI ⇒ hỏng nếu user hoàn tất luồng ở trình duyệt khác/chưa đăng nhập] → trả 400 kèm hướng dẫn đăng nhập rồi kết nối lại; luồng chuẩn (bấm link trong Open WebUI) luôn cùng trình duyệt nên không vướng.
- [Residual: chưa đóng nếu nạn nhân tự đăng nhập Open WebUI *bằng chính tài khoản kẻ tấn công* rồi mới consent] → ngoài phạm vi (khi đó nạn nhân đã có credential kẻ tấn công, không còn là CSRF token-binding); không xử lý.

## Migration Plan

### 1. Deploy middleware mới
Session-binding OAuth (danh tính-tại-callback + nonce double-submit + state ký) + scopes
office365 + fix `expires_at`. Backward compatible với token đã lưu. **Bắt buộc**: chia sẻ
`WEBUI_SECRET_KEY` cho service middleware (xem hướng dẫn cài đặt) để callback xác minh được
cookie phiên Open WebUI; thiếu nó thì mọi luồng connect trình duyệt trả 400.

```bash
docker compose up -d --build middleware
```

### 2. Chạy script seed (5 phase, đúng thứ tự)

Xác thực: `OPENWEBUI_ADMIN_TOKEN`, hoặc `TEST_ADMIN_EMAIL`/`TEST_ADMIN_PASSWORD` trong `.env`.

```bash
python scripts/seed_department_access.py --dry-run      # xem trước toàn bộ, không ghi
python scripts/seed_department_access.py                # chạy đủ 5 phase
python scripts/seed_department_access.py --phase tools  # chỉ 1 phase
```

Máy host thường không có `requests` và không gọi được `open-webui` qua tên service. Chạy trong container tạm trên network của stack:

```bash
docker run --rm --network oppen_web_ui_openwebui-network -v "$PWD":/repo -w /repo \
  python:3.11-slim sh -c "pip install -q requests && \
  python scripts/seed_department_access.py --url http://open-webui:8080"
```

| Phase | Làm gì | Vì sao bắt buộc |
| --- | --- | --- |
| `groups` | Tạo 8 group phòng ban | Nền cho mọi access_grants |
| `tools` | Đẩy source từ `tools/` lên Open WebUI (create/update), bơm valves từ `.env`, bật function, đặt `is_global` cho filter phê duyệt | Open WebUI lưu tool trong DB, KHÔNG đọc thư mục — không có phase này thì phải copy-paste tay |
| `models` | Tạo dòng cấu hình + grants public cho 5 model auto và 15 model `chat-*` | `get_filtered_models` chỉ cho user thường thấy model **có dòng trong bảng `model`** — bỏ qua phase này thì user **mất sạch model AI, không còn gì để chat** |
| `grants` | Gắn access_grants theo ma trận tool → group (+ override theo user) | Nguyên tắc default-private |

Phase `tools` phải chạy **trước** `grants`: tool chưa tồn tại thì grants không gắn vào đâu (script cảnh báo `⚠ CHƯA CÓ trong workspace`).

Model **không** gate tool (xem D2) nên không có phase `presets`.

### 3. Gán thành viên group
Admin → Settings → Groups → thêm user vào group phòng ban (gán tay; xem Future Work về đồng bộ HR).

### 4. Đăng ký OAuth app rồi test per-user
Điền `GITHUB_CLIENT_ID` / `GOOGLE_CLIENT_ID` / `OFFICE365_CLIENT_ID` + secret vào `.env`, build lại middleware. Thiếu client id ⇒ middleware chạy nhánh **mock**: flow connect/callback vẫn chạy nhưng token giả, gọi API thật trả 401.

### 5. Gỡ chức năng khỏi office365 MCP
`scripts/office365_mcp.py` thực chất là **server giả lập** (trả chuỗi hardcode "Simulated Outlook", không gửi mail thật) — nên "2 tuần chạy song song" không bảo vệ ai; gỡ ngay khi `office365_tool` lên là đúng, vì để lại thì model báo "đã gửi mail" trong khi không có mail nào được gửi.

### Rollback

```bash
python scripts/seed_department_access.py --rollback --dry-run   # xem trước
python scripts/seed_department_access.py --rollback             # gỡ grants → model gốc → tool → group
python scripts/seed_department_access.py --rollback --force     # xóa cả group đã có thành viên
```

Script chỉ gỡ những gì chính nó tạo (tag `seeded-by`; riêng tool nhận diện theo `WORKSPACE_TOOL_FILES`). Function KHÔNG bị xóa — chúng là hạ tầng chung. Middleware revert bằng image tag trước.

## Future Work

Ngoài scope change này, ghi lại để không rơi:

- **Tích hợp Canva / Figma cho Marketing** — chờ công ty mua license. Khi có: đăng ký OAuth app, thêm provider entry, viết tool theo runbook (docs/18), cắm vào bundle "Trợ lý Marketing" (hiện đã chừa khe: bundle mới có web search + image generation). Canva Connect API và Figma REST API đều hỗ trợ OAuth per-user nên dùng lại nguyên broker sẵn có, không phải sửa middleware.
- **Đồng bộ membership group từ nguồn nhân sự** — hiện admin gán tay từng user vào group qua Admin UI, không bền khi có 200+ nhân viên và biến động nhân sự. Hướng: job đồng bộ định kỳ từ HR/AD (Azure AD group đã có sẵn nếu khóa tenant ở task 5.2) → map sang group Open WebUI qua `POST /api/v1/groups/id/{id}/users/add|remove`. Cần chốt nguồn dữ liệu nhân sự trước.
- **Liệt kê team/kênh Teams theo tên** — `send_teams_message` hiện bắt user tự cung cấp `team_id` + `channel_id` vì spec chốt least-privilege không xin `Team.ReadBasic.All`/`Channel.ReadBasic.All`. Nếu UX này gây vướng, xin thêm 2 scope đọc đó rồi bổ sung hàm resolve theo tên.
- **Rà soát tool ngoài ma trận** — script seed cảnh báo (không tự sửa) các workspace tool không nằm trong `WORKSPACE_TOOL_MATRIX`. Cần một lần rà soát thủ công sau khi import đủ tool.

## Open Questions

- ~~Admin API tạo group có sẵn trong 0.9.6 hay phải qua SQL? (spike task 1.1)~~ **ĐÃ XÁC MINH (spike 2026-07-13, chạy trực tiếp trên môi trường đang chạy):**
  - **Groups**: `POST /api/v1/groups/create` (GroupForm: `name`, `description`, `permissions`, `data`) hoạt động — tạo/xóa thành công qua API. Trường `data` (JSON) persist → dùng `data["seeded-by"]` làm tag rollback (cột `meta` có trong DB nhưng KHÔNG expose qua GroupForm). API tự thêm `data.config.share = "members"`. Xóa: `DELETE /api/v1/groups/id/{id}/delete`; thành viên: `POST /api/v1/groups/id/{id}/users/add|remove`.
  - **Workspace tools/models**: build này đã migrate từ `access_control` dict sang bảng `access_grant` (resource_type: tool/model/knowledge/...; principal_type: user/group/`*`; permission: read/write). Endpoint chuyên dụng: `POST /api/v1/tools/id/{id}/access/update` và `POST /api/v1/models/model/access/update` nhận `access_grants: [{principal_type, principal_id, permission}]`. Tạo preset: `POST /api/v1/models/create` (ModelForm có `access_grants`).
  - **Tool server connections**: `GET/POST /api/v1/configs/tool_servers` với `TOOL_SERVER_CONNECTIONS[].config.access_grants`; `has_connection_access` (utils/access_control): thiếu/rỗng = private admin-only → đúng nguyên tắc default-private. Không cần fallback SQL.
  - **Phát hiện lệch môi trường**: DB hiện tại KHÔNG còn tool server connection nào (config chỉ có key `ui`) và bảng `tool` rỗng — 11 tool trong proposal không còn sau lần reset/cleanup DB. mcpo đang chạy 4 server tại `http://mcpo:8015/{playwright,fetch,postgres,sequential-thinking}`; server `office365` **fail khi khởi động** trong mcpo (xem logs). → Script seed phải TẠO connections mcpo (kèm access_grants) chứ không chỉ patch grants; phần grants cho workspace tool chỉ áp cho tool id có thật trong DB, cảnh báo tool vắng mặt.
- Tenant Azure AD: dùng `common` như hiện tại hay khóa về tenant công ty (`login.microsoftonline.com/<tenant-id>`)? Khuyến nghị khóa tenant — chờ IT xác nhận tenant-id.
