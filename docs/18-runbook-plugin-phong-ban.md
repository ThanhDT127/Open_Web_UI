# 18. Runbook — Thêm 1 plugin mới cho 1 phòng ban

Công thức lặp lại để mở một tool mới cho một phòng ban. Ví dụ xuyên suốt: mở **tool GitHub** cho phòng **Kỹ thuật/R&D**.

Bốn bước: **provider entry → tool file → access_grants → bundle**. Bước 1 chỉ cần khi tool gọi API bên ngoài dưới danh tính cá nhân của user (OAuth); tool nội bộ thì bỏ qua.

---

## Bước 1 — Provider entry (chỉ khi cần OAuth per-user)

Đăng ký ứng dụng OAuth ở nhà cung cấp (Google Cloud Console / GitHub Developer Settings / Azure AD), với redirect URI:

```
<MW_PUBLIC_URL>/v1/_mw/oauth/callback
```

Điền client id/secret vào `.env` (các biến OAuth **không** nằm trong `.env.example` — cấu hình tùy chọn, xem bảng biến dưới đây), rồi khai báo provider trong `llm-mw/api/oauth.py` → `PROVIDERS`:

```python
"github": {
    "auth_url": "https://github.com/login/oauth/authorize",
    "token_url": "https://github.com/login/oauth/access_token",
    "scopes": "repo read:user",          # least privilege — chỉ xin scope đang thực sự dùng
    "client_id_env": "GITHUB_CLIENT_ID",
    "client_secret_env": "GITHUB_CLIENT_SECRET",
},
```

> Provider có sẵn: `google_gmail`, `google_drive`, `github`, `office365`. Dùng lại thì không phải sửa code.

### Biến môi trường dùng chung cho MỌI luồng OAuth

| Biến | Bắt buộc | Mặc định | Ý nghĩa |
| --- | --- | --- | --- |
| `MW_PUBLIC_URL` | Có | `https://localhost:3000` | Origin công khai; redirect URI = `<MW_PUBLIC_URL>/v1/_mw/oauth/callback` |
| `MW_SECRET` | Có | (cảnh báo nếu để mặc định) | Ký `state` HMAC + `subkey_hash` |
| `WEBUI_SECRET_KEY` | **Có** | — | **Dùng chung với Open WebUI** để middleware xác minh cookie phiên `token` → biết user thật của trình duyệt. Phải bằng đúng giá trị Open WebUI đang dùng |
| `OPENWEBUI_SERVICE_KEY` (`SUBKEY_ADMIN`) | Có | — | Cho tool gọi `get_token` server-to-server theo danh tính user |

> **Bảo mật — bắt buộc:** danh tính gắn token lấy từ **phiên đăng nhập Open WebUI của chính trình duyệt** hoàn tất luồng (chống CSRF token-binding). Thiếu/không khớp `WEBUI_SECRET_KEY` ⇒ callback không xác minh được phiên ⇒ **mọi connect trả HTTP 400**. Không để `MW_SECRET`/`WEBUI_SECRET_KEY` ở giá trị mặc định trên môi trường thật.

### Biến môi trường theo từng tool (đặt cạnh tool tương ứng)

| Tool / provider | Biến | Ghi chú |
| --- | --- | --- |
| **Gmail** (`google_gmail_tool`) · **Drive** (`google_drive_tool`) | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Một OAuth client (Web) dùng chung cho cả Gmail + Drive; bật Gmail API + Drive API. Scopes cấp: `gmail.send`/`gmail.readonly`, `drive.readonly` |
| **GitHub** (`github_tool`) | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | GitHub OAuth App; callback = redirect URI trên; scopes `repo read:user`. Token GitHub **không hết hạn** (middleware lưu `expires_at = NULL`) |
| **Office 365** (MCP, không phải tool per-user) | `OFFICE365_CLIENT_ID`, `OFFICE365_CLIENT_SECRET`, `OFFICE365_TENANT_ID` | Azure AD app; scopes delegated: `Mail.Send`, `Mail.Read`, `Calendars.ReadWrite`, `Sites.Read.All`, `ChannelMessage.Send`, `offline_access`. `OFFICE365_TENANT_ID` mặc định `common`; đặt tenant-id công ty để khóa nội bộ (khuyến nghị). Hạ tầng OAuth giữ để bản MCP thật dùng lại |

> Bỏ trống client id của một provider ⇒ middleware chạy **nhánh mock** cho provider đó: flow connect/callback vẫn chạy nhưng token giả, gọi API thật trả 401. Tiện test luồng mà chưa cần app thật.

Restart middleware: `docker compose up -d --build middleware`

**Kiểm chứng**: trong trình duyệt **đang đăng nhập Open WebUI**, mở `<MW_PUBLIC_URL>/v1/_mw/oauth/connect?provider=<tên>` — phải nhảy sang màn hình đăng nhập của nhà cung cấp (không cần, và không còn nhận, tham số `openwebui_user_id`). Gọi bằng curl không kèm cookie phiên sẽ trả **401** — đúng thiết kế.

---

## Bước 2 — Tool file

Copy khuôn từ `tools/github_tool.py` (hoặc `google_gmail_tool.py`). Ba điểm bắt buộc:

1. **Lấy token của chính user** — không dùng key dùng chung:

```python
res = requests.get(
    f"{self.valves.MW_BASE_URL}/_mw/integrations/get_token",
    headers={"Authorization": f"Bearer {self.valves.SUBKEY_ADMIN}"},
    params={"provider": PROVIDER, "openwebui_user_id": __user__["id"]},
)
```

2. **Chưa kết nối (404) → trả link connect**, không thực hiện action:

```python
if res.status_code == 404:
    return self._connect_hint(__user__["id"])   # link /v1/_mw/oauth/connect?...
```

3. **Docstring tiếng Việt** cho từng hàm + `:param:` cho từng tham số — model đọc đúng chỗ này để quyết định gọi tool nào.

**Hành động gửi ra ngoài** (gửi mail, nhắn tin, tạo lịch mời người khác) phải đi qua cổng phê duyệt: tool đăng ký approval và trả `[PENDING_APPROVAL:<id>]`, rồi thêm nhánh thực thi trong `tools/filter_approval_handler.py` (xem nhánh `google_gmail_tool` làm mẫu). Hành động chỉ đọc thì chạy thẳng.

**Import vào Open WebUI — không copy-paste**: Open WebUI lưu source tool trong DB (bảng `tool`, cột `content`), **không đọc thư mục `tools/`**. Nhưng script seed đẩy file lên hộ bạn:

```python
# scripts/seed_department_access.py
WORKSPACE_TOOL_FILES = {
    ...
    "github_tool": "github_tool.py",   # tool id = tên file, không đuôi .py
}
```
```bash
python scripts/seed_department_access.py --phase tools
```

Script tạo mới nếu chưa có, cập nhật source nếu file trong repo đã đổi, và **bơm sẵn valves** (`SUBKEY_ADMIN`, `MW_BASE_URL`, `MW_PUBLIC_URL`) từ `.env` — khỏi điền tay trong UI. Sửa tool sau này chỉ cần sửa file rồi chạy lại phase này. Lưu ý phải bổ sung path tại WORKSPACE_TOOL_FILES trong scripts/seed_department_access.py

File `class Action`/`Filter`/`Pipe` là **function**, không phải tool: khai trong `FUNCTION_FILES` (script tự bật `is_active`, và đặt `is_global` cho filter phê duyệt để nó áp dụng với mọi model).

---

## Bước 3 — access_grants (phân quyền theo group)

Thêm tool vào ma trận trong `scripts/seed_department_access.py`:

```python
WORKSPACE_TOOL_MATRIX = {
    ...
    "github_tool": ["it", "ky-thuat-rd"],   # hoặc ALL_GROUPS / PUBLIC
}
```

- `PUBLIC` — mọi user đã đăng nhập
- `ALL_GROUPS` — 8 group phòng ban (user chưa vào group nào sẽ **không** thấy)
- `["slug", ...]` — chỉ các group liệt kê

Chạy seed (idempotent — chạy lại an toàn):

```bash
python scripts/seed_department_access.py --phase grants --dry-run   # xem bảng đối chiếu
python scripts/seed_department_access.py --phase grants
```

> Ma trận trong repo là **chính sách mặc định**. Sửa quyền hằng ngày thì làm trong UI: Dashboard middleware → tab **Groups** → bảng *Phân quyền Tool theo phòng ban* → ✏️ **Edit Group** → tick/bỏ tick tool → Save. Hai đường ghi vào cùng bảng `access_grant`, nhưng chạy lại `--phase grants` sẽ **kéo group về đúng ma trận** — thay đổi trong UI mà không cập nhật ma trận sẽ mất ở lần seed sau. (Grant theo *user* thì không bị đụng — xem Bước 4.)

> Nguyên tắc **default-private**: tool không có `access_grants` thì chỉ admin thấy. Không cần "khóa" gì thêm.

**Kiểm chứng**: đăng nhập bằng user thuộc group được cấp → thấy tool; user ngoài group → không thấy.

---

## Bước 4 — (Tuỳ chọn) Cấp thêm cho một cá nhân

Ma trận ở Bước 3 cấp theo **group**. Nếu cần cho riêng một người dùng tool nằm ngoài chính sách phòng ban:

**Cách 1 — trong UI (thường dùng):** Dashboard middleware → tab **Users** → ✏️ Edit User → mục **🔧 Tool được phép dùng** → tick tool → Save.

> Tool user đã có **qua group** hiện là đã bật nhưng **khóa**, kèm nhãn tên group. Muốn thu hồi thì sửa ở **Groups → ✏️ Edit Group**, không phải ở đây.
>
> Mục Tool chỉ hiện với user đã **map sang Open WebUI** (`openwebui_user_id`) — quyền gắn vào tài khoản Open WebUI, không phải tài khoản middleware. User chưa map thì dùng nút **Sync Now** ở bảng sync status.

**Cách 2 — khai trong repo** (nếu muốn versioned): thêm vào `USER_TOOL_OVERRIDES` trong file seed rồi chạy `--phase grants`.

```python
USER_TOOL_OVERRIDES = {
    "github_tool": ["an.nv@oppen.vn"],
}
```

> Hai cách không giẫm chân nhau: `seed_grants` **giữ nguyên** mọi grant `principal_type=user` đã có trong DB khi áp lại ma trận (`preserved_user_grants()`), nên quyền cấp tay trong UI không bị thu hồi ở lần seed sau.

**Không cần gắn tool vào model.** Model không gate tool: user chọn model AI gốc bất kỳ rồi tự bật tool trong tool picker của khung chat, danh sách đã lọc theo quyền của họ.

**Kiểm chứng**: đăng nhập bằng user được cấp → mở tool picker trong chat → thấy tool; user khác cùng group → không thấy.

---

## Rollback

```bash
python scripts/seed_department_access.py --rollback --dry-run   # xem trước
python scripts/seed_department_access.py --rollback             # gỡ grants + model gốc + tool + group script đã tạo
```

> ⚠️ Luôn chạy `--dry-run` trước. Model gốc và preset (nếu có) **mang cùng tag** `seeded-by`, nên bất kỳ đoạn rollback nào lọc theo tag mà quên điều kiện `base_model_id` sẽ **xóa sạch 20 model AI gốc** — user thường sẽ không còn model nào để chat.

Script chỉ gỡ những gì chính nó tạo (nhận diện qua tag `seeded-by: department-plugin-access`); group đã có thành viên được giữ lại trừ khi thêm `--force`.

---

## Checklist nhanh

- [ ] Provider có trong `PROVIDERS` (nếu cần OAuth), client id/secret đã vào `.env`
- [ ] Tool file lấy token theo `__user__`, xử lý nhánh 404 → link connect
- [ ] Hành động gửi ra ngoài đi qua approval + có nhánh thực thi trong filter
- [ ] Tool khai trong `WORKSPACE_TOOL_FILES`, đã chạy `--phase tools`
- [ ] Tool có trong `WORKSPACE_TOOL_MATRIX`, đã chạy `--phase grants`
- [ ] Test bằng 1 user thuộc group **và** 1 user ngoài group (user ngoài group phải KHÔNG thấy tool)

---

## Liên quan

- [09 — Quản lý người dùng](09-user-management.md): danh sách group, ma trận tool → group, cách cấp quyền cho cá nhân
- [10 — Hướng dẫn sử dụng](10-user-guide-vi.md): user kết nối tài khoản và bật tool trong chat thế nào
