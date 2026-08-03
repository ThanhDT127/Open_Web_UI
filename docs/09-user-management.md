# Hướng dẫn Quản lý Người dùng

## Tổng quan

LLM Middleware bao gồm hệ thống quản lý người dùng toàn diện với RBAC (Role-Based Access Control), quản lý vòng đời khóa API, và audit trail cho các thao tác quản trị.

## Schema Người dùng

Mỗi user trong bảng `mw_users` (PostgreSQL) có cấu trúc sau:

```json
{
  "user_id": "admin",
  "role": "admin",  // admin | manager | user
  "subkey_hash": "...",  // Chỉ lưu hash, plaintext không bao giờ lưu lâu dài
  "active": true,
  "allowed_models": ["*"],
  "quota": {
    "period": "monthly",
    "timezone": "Asia/Ho_Chi_Minh",
    "limit_tokens": 0,
    "limit_cost_usd": 0,
    "limit_image_requests": 0,
    "used_tokens": 0,
    "used_cost_usd": 0.0,
    "used_image_requests": 0
  }
}
```

### Vai trò (Roles)

- **admin**: Toàn quyền truy cập các endpoint quản trị (quản lý user)
- **manager**: (Dự kiến) Quyền admin chỉ đọc
- **user**: Người dùng API tiêu chuẩn với giới hạn quota

## Migration

Để thêm RBAC cho users.json hiện có:

```bash
python scripts/migrate_users_rbac.py
```

Script này sẽ:
1. Sao lưu users.json hiện tại
2. Thêm trường 'role' (user đầu tiên nhận 'admin', còn lại nhận 'user')
3. Xác thực và lưu

## Các Endpoint Quản trị

Tất cả endpoint yêu cầu xác thực admin (cookie session hoặc header X-Admin-Key).

### Danh sách Người dùng

```bash
GET /v1/_mw/admin/users
```

**Phản hồi:**
```json
{
  "users": [
    {
      "user_id": "admin",
      "role": "admin",
      "active": true,
      "allowed_models": ["*"],
      "quota": {...}
    }
  ],
  "total": 2
}
```

**Lưu ý:** Các khóa và hash được ẩn khỏi phản hồi.

---

### Tạo Người dùng

```bash
POST /v1/_mw/admin/users
Content-Type: application/json

{
  "user_id": "new_user",
  "role": "user",
  "allowed_models": ["chat-gemini-2.5-flash", "chat-gpt-5"],
  "limit_tokens": 100000,
  "limit_cost_usd": 5.0,
  "limit_image_requests": 50,
  "period": "monthly",
  "timezone": "Asia/Ho_Chi_Minh"
}
```

**Phản hồi:**
```json
{
  "message": "User created successfully",
  "user": {...},
  "subkey": "sk_abc123...",  // Chỉ hiển thị 1 LẦN DUY NHẤT!
  "warning": "Save this subkey securely. It will not be shown again."
}
```

**QUAN TRỌNG:** Sao chép subkey ngay lập tức. Không thể khôi phục sau này.

---

### Cập nhật Người dùng

```bash
PATCH /v1/_mw/admin/users/{user_id}
Content-Type: application/json

{
  "role": "manager",
  "active": true,
  "allowed_models": ["*"],
  "limit_cost_usd": 10.0
}
```

**Phản hồi:**
```json
{
  "message": "User updated successfully",
  "user": {...},
  "changes": {
    "role": "manager",
    "limit_cost_usd": 10.0
  }
}
```

**Các trường:** Tất cả đều tùy chọn. Chỉ các trường được cung cấp mới được cập nhật.

---

### Xoay vòng Khóa (Rotate Key)

```bash
POST /v1/_mw/admin/users/{user_id}/rotate_key
```

**Phản hồi:**
```json
{
  "message": "Key rotated successfully",
  "user_id": "user1",
  "subkey": "sk_new_key_xyz...",  // Chỉ hiển thị 1 LẦN DUY NHẤT!
  "warning": "Save this subkey securely. The old key is now invalid."
}
```

**QUAN TRỌNG:** Khóa cũ bị vô hiệu hóa ngay lập tức.

---

### Xóa Người dùng

```bash
DELETE /v1/_mw/admin/users/{user_id}
```

**Phản hồi:**
```json
{
  "message": "User alice deleted",
  "user_id": "alice"
}
```

**QUAN TRỌNG:**
- Xóa là vĩnh viễn - xóa khỏi cả DB và bản sao lưu JSON
- Không cho phép tự xóa (admin không thể xóa chính mình)
- Yêu cầu xác nhận 2 lần trên giao diện Dashboard

---

### Tắt Tài khoản (Disable)

```bash
POST /v1/_mw/admin/users/{user_id}/disable
```

**Phản hồi:**
```json
{
  "message": "User user1 disabled successfully",
  "user": {...}
}
```

Người dùng bị tắt không thể xác thực (trả về 403 Forbidden).

---

### Bật lại Tài khoản (Enable)

```bash
POST /v1/_mw/admin/users/{user_id}/enable
```

**Phản hồi:**
```json
{
  "message": "User user1 enabled successfully",
  "user": {...}
}
```

---

## Giao diện Quản lý trên Dashboard

Quản lý người dùng đầy đủ có sẵn tại Dashboard Admin `https://openwebui.example.com:51122/dashboard` > tab **Users**.

### Các Thao tác

| STT | Thao tác      | Nút        | Mô tả                                   |
| --- | ------------- | ---------- | --------------------------------------- |
| 01  | **Thêm user** | Add User   | Tạo user mới với subkey tự sinh         |
| 02  | **Sửa user**  | Edit       | Sửa quota, models, role, period, active |
| 03  | **Xóa user**  | Delete     | Xóa user (xác nhận 2 lần)               |
| 04  | **Xoay khóa** | Rotate Key | Vô hiệu khóa cũ, tạo khóa mới           |
| 05  | **Bật/Tắt**   | Toggle     | Bật/tắt tài khoản (403 khi bị tắt)      |

### Hiển thị Subkey

- Sau khi **Tạo** hoặc **Xoay khóa**, popup hiển thị subkey dạng plaintext
- Admin phải sao chép ngay lập tức - sẽ **KHÔNG** hiển thị lại
- Bảng Dashboard chỉ hiển thị hash đã ẩn (`abc...xyz`)
- Subkeys được hash bằng HMAC-SHA256 sử dụng `MW_SECRET`

---

### Nhật ký Kiểm toán Quản trị (Admin Audit Trail)

```bash
GET /v1/_mw/admin/audit?minutes=1440
```

**Phản hồi:**
```json
{
  "audit_trail": [
    {
      "ts": "2026-01-07T16:19:45.123456+00:00",
      "actor": "admin_session",
      "action": "create_user",
      "target_user": "new_user",
      "changes": {"role": "user", "allowed_models": ["*"]},
      "status": "ok",
      "ip": "127.0.0.1",
      "user_agent": "curl/7.68.0"
    }
  ],
  "total": 10
}
```

**Tham số truy vấn:**
- `minutes`: Khoảng thời gian (mặc định: 1440 = 24 giờ)
- `start` / `end`: Chuỗi ISO datetime cho khoảng tùy chỉnh

## File Nhật ký Kiểm toán

Các thao tác quản trị được ghi vào `logs/admin_audit.jsonl` (rotating, tối đa 20MB, 5 bản sao lưu).

Mỗi bản ghi bao gồm:
- `ts`: Thời gian (ISO UTC)
- `actor`: Định danh phiên admin
- `action`: Thao tác thực hiện (create_user, update_user, rotate_key, disable_user, enable_user)
- `target_user`: User ID bị ảnh hưởng
- `changes`: Tóm tắt các thay đổi
- `status`: ok | error
- `ip`: Địa chỉ IP client
- `user_agent`: User agent client

## Nhóm Phòng ban & Phân quyền Tool

Từ change `department-plugin-access`, quyền dùng tool được cấp **theo group phòng ban** thay vì mở cho mọi user. Nguyên tắc: **mặc định private** — tool không có `access_grants` thì chỉ admin thấy.

### 8 group phòng ban mẫu

| Slug                | Phòng ban                  |
| ------------------- | -------------------------- |
| `ban-lanh-dao`      | Ban lãnh đạo               |
| `kinh-doanh`        | Kinh doanh                 |
| `marketing`         | Marketing                  |
| `ke-toan-tai-chinh` | Kế toán – Tài chính        |
| `hcns`              | Hành chính – Nhân sự       |
| `ky-thuat-rd`       | Kỹ thuật / R&D             |
| `san-xuat`          | Sản xuất                   |
| `it`                | IT                         |

Group được tạo bằng script seed (idempotent, chạy lại an toàn):

```bash
python scripts/seed_department_access.py --dry-run     # xem trước, không ghi
python scripts/seed_department_access.py               # chạy đủ 5 phase
python scripts/seed_department_access.py --phase tools # chỉ 1 phase
python scripts/seed_department_access.py --rollback    # gỡ những gì script đã tạo
```

Script xác thực qua `OPENWEBUI_ADMIN_TOKEN`, hoặc `TEST_ADMIN_EMAIL`/`TEST_ADMIN_PASSWORD` trong `.env`.

**4 phase, chạy theo thứ tự:**

| Phase | Làm gì |
| --- | --- |
| `groups` | Tạo 8 group phòng ban |
| `tools` | **Đẩy source từ `tools/` trong repo lên Open WebUI** — Open WebUI lưu tool trong DB chứ không đọc thư mục, nên đây là cách thay cho copy-paste qua UI. Bơm luôn valves từ `.env`, bật function, đặt filter phê duyệt thành global |
| `models` | Mở model AI gốc cho user thường (xem cảnh báo dưới) |
| `grants` | Gắn access_grants theo ma trận tool → group (+ override theo user) |

> ⚠️ **Vì sao cần phase `models`**: Open WebUI 0.9.6 (`utils/models.py: get_filtered_models`) chỉ cho user thường thấy model **có dòng cấu hình trong bảng `model`**; model nào không có dòng bị coi là "chưa cấu hình quyền" và **chỉ admin thấy**. Model gốc đến từ connection tới middleware nên không có dòng nào → nếu bỏ qua phase này, user đăng nhập vào sẽ **mất sạch model AI, không còn gì để chat**. Phase `models` tạo dòng cấu hình + grants public cho 5 model auto và 15 model `chat-*` (bỏ `img-*`/embedding/rerank vì không dùng để chat).

Chạy script từ máy có `requests`, hoặc trong container tạm trên cùng network:

```bash
docker run --rm --network oppen_web_ui_openwebui-network -v "$PWD":/repo -w /repo \
  python:3.11-slim sh -c "pip install -q requests && \
  python scripts/seed_department_access.py --url http://open-webui:8080"
```

**Gán thành viên vào group**: Admin → Settings → Groups → chọn group → thêm user (làm tay; chưa đồng bộ từ HR).

### Ma trận tool → group (mặc định)

| Tool                                   | Được cấp cho                    |
| -------------------------------------- | ------------------------------- |
| `fetch`, `sequential-thinking` (mcpo)  | Mọi user (public)               |
| `postgres`, `playwright` (mcpo)        | `it`, `ky-thuat-rd`             |
| `office365` (mcpo)                     | Mọi group phòng ban             |
| `google_gmail_tool`, `google_drive_tool` | Mọi group phòng ban           |
| `github_tool`                          | `it`, `ky-thuat-rd`             |
| `code_interpreter`                     | `it`, `ky-thuat-rd`             |

Sửa ma trận trong `scripts/seed_department_access.py` (`MCPO_SERVER_MATRIX`, `WORKSPACE_TOOL_MATRIX`) rồi chạy lại script — hoặc bật/tắt trực tiếp trong dashboard (**Groups → Edit Group**, **Users → Edit User**).

> **Office365 do MCP phụ trách.** Mảng Office 365 hiện chỉ có MCP server `office365` (`server:office365` trong tool picker) — bản do mentor cung cấp, sẽ thay bằng bản thật sau. Tool Python `office365_tool.py` **đã gỡ bỏ** để tránh hai bản chạy song song.
>
> Grant của MCP server **không nằm trong bảng `access_grant`** mà nhúng trong JSON `config.tool_server.connections[].config.access_grants`, nên **không bật/tắt được từ Edit Group / Edit User** — chỉ sửa qua `MCPO_SERVER_MATRIX` trong script seed.

### Trục phân quyền: GROUP + USER (model không liên quan)

Quyền dùng tool nằm **hoàn toàn** ở bảng `access_grant` của Open WebUI, cấp cho:

- **Group** (phòng ban) — trục chính, theo ma trận ở trên.
- **User** — ngoại lệ cho cá nhân, cấp thêm ngoài chính sách group.

**Model KHÔNG gate tool.** User chọn model AI gốc bất kỳ (cả 20 model đều public), rồi **tự bật tool** trong tool picker của khung chat — danh sách tool đã được lọc sẵn theo quyền của họ. Không có "trợ lý phòng ban" hay preset nào ràng tool vào model nữa.

> Đây là điểm từng gây hiểu nhầm: trước kia có 5 model preset "Trợ lý" mang sẵn `meta.toolIds`, khiến admin tưởng quyền tool đi theo model. Thực ra không phải — 5 preset đó **đã được gỡ bỏ hoàn toàn**.

**Bật/tắt tool ở đâu** — trong dashboard middleware, theo đúng trục quyền:

| Cần làm | Vào đâu |
|---|---|
| Đổi tool của cả một phòng ban | Tab **Groups** → bảng *Phân quyền Tool theo phòng ban* → ✏️ **Edit Group** |
| Cấp thêm tool cho riêng một người | Tab **Users** → ✏️ **Edit User** → mục **🔧 Tool được phép dùng** |

Quyền có hiệu lực ngay, không cần restart. Trong Edit User, tool user đã có **qua group** hiện là đã bật nhưng **khóa** kèm nhãn tên group — muốn thu hồi thì sửa ở Edit Group. Mục Tool chỉ hiện với user đã map sang Open WebUI (`openwebui_user_id`), vì quyền gắn vào tài khoản Open WebUI chứ không phải tài khoản middleware.

> **Vì sao không dùng UI của Open WebUI?** Open WebUI chỉ cho biên tập quyền từ phía *tool* (Workspace → Tools → Access Control), tức trả lời "tool này cho ai" — ngược với cách admin tư duy. Và nó **không có màn hình phân quyền theo user** nào cả: `group.permissions` chỉ chứa quyền năng lực thô (được tạo/sửa tool hay không), không phải danh sách tool được dùng.

> Grant cấp tay cho user **không bị mất** khi chạy lại `--phase grants`: script giữ nguyên mọi grant `principal_type=user` đang có (`preserved_user_grants()`). Chỉ grant theo group mới bị áp lại theo ma trận — nên nếu sửa quyền group trong UI, nhớ cập nhật `WORKSPACE_TOOL_MATRIX` cho khớp.

**Enforcement là thật, không chỉ ẩn/hiện UI**: `utils/tools.py: get_tools()` kiểm tra lại quyền cho từng tool ngay lúc chạy — gọi thẳng API với `tool_ids` không có quyền vẫn bị loại khỏi context (log `Access denied to tool ...`).

Thêm plugin mới cho một phòng ban: xem [Runbook 18](18-runbook-plugin-phong-ban.md).

## Thực hành Bảo mật Tốt nhất

1. **Lưu trữ Khóa:**
   - Không bao giờ ghi log hoặc hiển thị subkey ngoại trừ khi tạo/xoay
   - Chỉ lưu hash (HMAC-SHA256) trong database
   - Sử dụng biến môi trường `MW_SECRET` làm salt hash

2. **Xoay vòng Khóa:**
   - Xoay khóa định kỳ (ví dụ: mỗi 90 ngày)
   - Xoay ngay lập tức nếu khóa bị lộ
   - Khóa cũ bị vô hiệu hóa tức thì

3. **RBAC:**
   - Cấp vai trò 'admin' hạn chế
   - Dùng vai trò 'user' cho người dùng API
   - Tương lai: vai trò 'manager' cho quyền admin chỉ đọc

4. **Nhật ký Kiểm toán:**
   - Rà soát admin_audit.jsonl định kỳ
   - Giám sát các thao tác admin trái phép
   - Đối chiếu với địa chỉ IP để điều tra

## Ví dụ

### Tạo User qua curl

```bash
curl -X POST http://localhost:5000/v1/_mw/admin/users \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "role": "user",
    "allowed_models": ["chat-gemini-2.5-flash"],
    "limit_cost_usd": 5.0,
    "period": "monthly"
  }'
```

### Xoay Khóa qua curl

```bash
curl -X POST http://localhost:5000/v1/_mw/admin/users/alice/rotate_key \
  -H "X-Admin-Key: $ADMIN_KEY"
```

### Tắt User qua curl

```bash
curl -X POST http://localhost:5000/v1/_mw/admin/users/alice/disable \
  -H "X-Admin-Key: $ADMIN_KEY"
```

## Xử lý Sự cố

### Lỗi: "Invalid admin key or session"

**Giải pháp:**
- Với curl: Dùng `-H "X-Admin-Key: $ADMIN_KEY"`
- Với dashboard: Đăng nhập bằng admin key để lấy session cookie

### Lỗi: "User already exists"

**Giải pháp:** User ID phải là duy nhất. Chọn user_id khác hoặc cập nhật user hiện có.

### Mất khóa, không xác thực được

**Giải pháp:** Admin phải xoay khóa và cung cấp khóa mới. Khóa cũ không thể khôi phục.

### Không tìm thấy nhật ký kiểm toán

**Giải pháp:** Nhật ký kiểm toán admin được tạo khi có thao tác admin đầu tiên. Đường dẫn file: `logs/admin_audit.jsonl`
