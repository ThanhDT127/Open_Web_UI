## Context

Toàn bộ kết luận dưới đây đến từ đối chiếu code + truy vấn DB thật, không phải suy đoán.

**Hai kỷ luật gom khác nhau trên cùng một bảng.** `mw_audit_log` 30 ngày có **264 dòng** nhưng chỉ **189 `rid` duy nhất** — 114 rid xuất hiện 1 lần, 75 rid xuất hiện 2 lần (cặp `pending` → `reconciled` của cùng một request).

| | `summary_v2.py` (tab Usage) | `analytics.py` (tab Chat Analytics) |
|---|---|---|
| Đơn vị đếm | `rid` duy nhất — `len(rid_status)` (`:290`), `.add(rid)` (`:254,266,274`) | **dòng** — `+= 1` (`:103,107,110,114`) |
| Trạng thái | last-status-per-rid (`:248`) | không đọc cột `status` |
| Truy vấn | 19 cột, có `rid` (`:61`) | 5 cột, **không lấy `rid`** (`:84`) |
| Kết quả | **189** | **264** (phồng 40%) |

`analytics.py` không cố tình đếm theo dòng — nó đếm theo dòng vì **không lấy `rid` ra khỏi DB**. Đây là thiếu sót lúc viết, không phải lựa chọn thiết kế.

**Bốn lỗi hiển thị đã xác minh trên dữ liệu thật:**

| Chỗ | Hiện tại | Nguyên nhân |
|---|---|---|
| `totals.requests` | `0` | `total_reqs = total_messages` (`:70`) ← `COUNT(id) FROM message`, bảng OW **rỗng 0 dòng** |
| `leaderboard[].chat_count` | `0` × 13 | `user_chat_counts` key theo `chat.user_id` = **UUID**, còn `u_id` từ `mw_audit_log` = **email** → `.get()` không bao giờ khớp (`:144`) |
| `leaderboard[].display_name` | trùng hệt email | `SELECT id, name FROM "user"` (`:133`) key theo UUID, tra bằng email |
| `hourly_activity` | tổng 264 | đếm dòng; request `pending` 14:59 + `reconciled` 15:01 bị tính vào **cả hai giờ** |

**Ràng buộc từ người dùng (anh Tuấn):**
- **Không xoá bất cứ thứ gì** khỏi tab Chat Analytics — người dùng vào đó phải xem được đủ, không phải nhảy qua lại giữa hai tab.
- `hourly_activity` giữ dạng **tổng**, không lấy trung bình.
- Tạm bỏ qua timezone — đang chạy đúng ở Việt Nam.

**Đã kiểm tra trước khi thiết kế:**
- `summary_v2.py` dùng `request` **đúng 2 chỗ**: khai báo tham số (`:110`) và `require_admin_or_session` (`:121`). 349 dòng còn lại là tính toán thuần.
- **Không có import vòng**: `summary_v2` chỉ import stdlib + fastapi + `config`, lazy-import `core.db` trong thân hàm. `analytics.py → summary_v2` là cạnh một chiều.
- Bảng `user` của Open WebUI có sẵn cột `email` với tên thật (`Trần Xuân Tuấn`, `Phạm VIệt Tùng`…).

## Goals / Non-Goals

**Goals:**
- Một hiện thực duy nhất biết cách gom `mw_audit_log`; hai tab không thể lệch nhau nữa.
- Tab Chat Analytics giữ **nguyên vẹn giao diện**, chỉ đổi số liệu từ sai sang đúng.
- Sửa 4 lỗi hiển thị đã nêu, không bỏ cột nào.
- Frontend `analytics.js` không phải sửa một dòng.

**Non-Goals:**
- Xoá thẻ/bảng/biểu đồ trùng với tab Usage — bị loại theo yêu cầu tự đủ thông tin.
- Sửa timezone, kể cả lỗi lệch 7 tiếng của đường dự phòng đọc file (xem Risks).
- Đụng cột `purpose` — móc nối chết, cần sửa Open WebUI mới dùng được.
- Đổi định nghĩa "active user" sang 12/13 — để Phase 4 xử lý ở tab Overview.
- Dọn phần dup còn lại của bad merge `2cb7510` (`main.py`, `auth.py`, `db.py`).

## Decisions

### D1 — Tách hàm thuần, KHÔNG để endpoint gọi endpoint

Cắt `get_summary_v2` thành ba phần theo đúng ranh giới tự nhiên đã có:

```
_resolve_range(minutes, start, end, bucket)     ← pha 1 (:123-167)
    → (cutoff, end_time, bucket_size)

compute_usage_summary(cutoff, end_time, bucket_size)   ← pha 2+3 (:169-471)
    → dict          # thuần: không Request, không auth, không HTTP

get_summary_v2(request, …)                       ← chỉ còn vỏ
    auth → _resolve_range → compute_usage_summary → cắt [:20] → return
```

**Vì sao không gọi `get_summary_v2(request, …)` trực tiếp** (phương án đã cân nhắc kỹ và loại): tuy chạy được — nó là hàm thuần, không `async` — nhưng kéo theo truyền `Request`, chạy xác thực hai lần, ném `HTTPException` từ tầng tính toán, in thêm dòng log `[SUMMARY_V2]` mỗi lần mở Chat Analytics, và để lại nợ "endpoint gọi endpoint" phải trả sau.

**Cái phải trả cho lựa chọn này:** đây là refactor **di chuyển code, không sửa logic**, nhưng khối `:123-471` bị thụt lề lại nên `git diff` hiển thị ~349 dòng xoá + ~349 dòng thêm. Công cụ diff không phân biệt được "thụt lề lại" với "sửa nội dung", nên **không soát bằng mắt theo cách thường được**. Rủi ro này có thật và được xử lý riêng ở D9 — không bỏ qua, không giảm nhẹ.

**Loại bỏ:** để `analytics.py` tự sửa vòng lặp gom của nó thành đếm `rid`. Không đụng `summary_v2` chút nào, nhưng giữ nguyên **hai hiện thực song song** — không chữa nguyên nhân gốc, chỉ đồng bộ tạm hai bản sao rồi chờ chúng lệch lại.

### D2 — `analytics.py` map lại tên trường thay vì đổi frontend

Hai bên đặt tên khác nhau:

| | `analytics.py` | `summary_v2` |
|---|---|---|
| Khoá bucket | `"2026-07-15 15:00"` | `"2026-07-15T15:00:00"` |
| Trường | `period`, `requests` | `ts`, `requests_total` |

`analytics.py` chèn một lớp map mỏng khi định dạng. Đây **chính là** cơ chế giữ `analytics.js` bất động — đúng ràng buộc "không xoá gì, không bắt người dùng học lại giao diện".

### D3 — `bucket_size` truyền tường minh, không dùng `"auto"`

Hai bên đang chọn bucket theo hai quy tắc khác nhau:

| Khoảng | `summary_v2` | `analytics.py` |
|---|---|---|
| ≤ 1 giờ | minute | hour |
| 1 giờ – 1 ngày | hour | hour |
| 1 – 2 ngày | **hour** | **day** |
| > 2 ngày | day | day |

Khoảng mặc định 30 ngày thì cả hai đều `day` nên hiện chưa lệch. `analytics.py` sẽ **tự tính `bucket_size` theo quy tắc cũ của nó** (`minutes <= 1440`) rồi truyền vào, giữ nguyên cách chia bucket hiện tại. Thống nhất hai quy tắc là việc khác, không thuộc change này.

### D4 — Chuyển `[:20]` từ trong hàm gom ra ngoài endpoint

`summary_v2.py:464-465` cắt `breakdown_by_user[:20]` / `breakdown_by_model[:20]`. Tab Chat Analytics hiện hiển thị **toàn bộ** user (13 người). Nếu nó ăn thẳng danh sách đã cắt, khi vượt 20 user leaderboard sẽ **âm thầm mất dòng**.

`compute_usage_summary` trả danh sách đầy đủ; `get_summary_v2` cắt `[:20]` trước khi return để giữ nguyên hợp đồng API của nó. Bên gọi tự quyết định cắt hay không.

Đây là **thay đổi hành vi duy nhất bên trong khối được di chuyển** — mọi thứ khác chỉ đổi vị trí. Vì vậy nó phải xuất hiện như một trong số rất ít khác biệt còn lại sau khi lọc thụt lề ở D9; nếu thấy nhiều hơn thì có gì đó ngoài dự kiến.

### D5 — `hourly_activity` và `top_model` vào hàm dùng chung

- **`hourly_activity`**: đọc 100% từ `mw_audit_log`, không dính Open WebUI, và cần `rid` để hết đếm đôi → thuộc về hàm gom. Dùng `set` theo giờ rồi `len()`, y hệt kỷ luật của `timeseries_data`. Sửa luôn hai bệnh (phồng 40% + lem sang giờ bên cạnh) mà không viết logic mới.
- **`top_model`**: `user_data` (`:192-199`) chưa đếm model theo user. Thêm `"models": defaultdict(int)` và `+= 1` trong vòng lặp đang chạy. Bắt buộc phải làm — nếu không, cột `TOP MODEL` (hiện đang chạy đúng) sẽ mất, vi phạm ràng buộc "không xoá gì".

Tab Usage nhận thêm hai trường này nhưng không bắt buộc dùng — thuần bổ sung, tương thích ngược.

### D6 — Sửa `display_name` bằng cách đổi khoá join

`SELECT id, name FROM "user"` → `SELECT email, name FROM "user"`. Bảng `user` của Open WebUI có sẵn cột `email`, và `u_id` trong vòng lặp chính là email. Một từ.

**Loại bỏ:** giải UUID→email rồi mới tra tên — thừa, vì đã có sẵn cặp `email → name` trong cùng bảng.

### D7 — Sửa `chat_count` bằng chuỗi giải đã có, không dùng JOIN

Tái sử dụng chuỗi ở `analytics.py:255-274` (đang phục vụ `get_satisfaction_analytics`):

```
mw_users.openwebui_user_id → user_id (email)        # 11/12 user có map
   ↓ nếu thiếu (user đã xoá khỏi Open WebUI)
mw_audit_log.openwebui_user_id → user_id (email)    # dự phòng
```

**Loại bỏ:** `JOIN "user" u ON u.id = c.user_id` — đã thử, chỉ ra **7 user / 20 phiên** thay vì 9/24, tức mất 2 user đã xoá và 4 phiên của họ. Trái nguyên tắc dữ liệu lịch sử phải giữ nguyên cho user đã xoá. Chuỗi `mw_users → mw_audit_log` không phụ thuộc vòng đời user của Open WebUI nên không bị mất.

### D8 — Thứ tự triển khai để mỗi bước hệ thống vẫn chạy

```
1. Tách compute_usage_summary          → chưa ai gọi   → /summary BẤT BIẾN
2. Thêm hourly + top_model, chuyển [:20] ra ngoài → /summary BẤT BIẾN
3. analytics.py chuyển sang gọi hàm mới     → /analytics/chat đúng số
4. Sửa display_name                          → tên thật hiện ra
5. Sửa chat_count                            → tổng cột = Total Chats
```

Bước 1 và 2 **không thay đổi hành vi gì**. Nếu `/v1/_mw/summary` trả khác dù một chữ số thì dừng, không đi tiếp. Tách bước 1 khỏi bước 2 là cố ý: bước 1 thuần di chuyển, bước 2 thuần bổ sung — soát riêng từng loại dễ hơn soát một diff trộn cả hai.

### D9 — Quy trình soát diff của bước tách hàm

Đây là chỗ rủi ro tập trung. `git diff` mặc định **vô dụng** cho bước này vì thụt lề làm mọi dòng trông như bị sửa. Ba lớp kiểm chứng, chạy theo thứ tự, lớp sau bắt cái lớp trước bỏ lọt:

**Lớp 1 — Lọc thụt lề để lộ thay đổi thật**

```bash
git diff -w --ignore-blank-lines llm-mw/api/summary_v2.py
```

`-w` bỏ qua mọi khác biệt khoảng trắng, nên khối được di chuyển sẽ **biến mất khỏi diff**. Cái còn hiện ra phải **đúng và chỉ** gồm:
- dòng `def _resolve_range(...)` và `def compute_usage_summary(...)` mới
- dòng `return` mới ở cuối mỗi hàm
- thân `get_summary_v2` rút gọn
- phép cắt `[:20]` chuyển vị trí (D4)

Bất kỳ dòng nào khác xuất hiện = có sửa ngoài dự kiến → dừng, xem lại.

**Lớp 2 — So sánh thân hàm sau khi chuẩn hoá**

Trích khối `:169-471` của bản gốc và thân `compute_usage_summary` của bản mới, bỏ khoảng trắng đầu dòng, rồi `diff`. Kết quả phải rỗng ngoài các thay đổi đã liệt kê ở Lớp 1. Đây là lưới an toàn cho trường hợp `-w` bỏ lọt (ví dụ dòng bị xoá hẳn thay vì thụt lề).

**Lớp 3 — Bất biến hành vi qua API**

Lưu response `/v1/_mw/summary?minutes=43200` trước khi sửa, `diff` sau mỗi bước. Đây là kiểm chứng cuối cùng và đáng tin nhất, vì nó không quan tâm code trông thế nào — chỉ quan tâm kết quả.

**Nguyên tắc:** cả ba lớp phải sạch mới đi tiếp. Lớp 3 sạch mà Lớp 1 bẩn vẫn là dấu hiệu xấu — nghĩa là có thay đổi chưa hiểu rõ, chỉ tình cờ không lộ ra ở khoảng dữ liệu đang test.

## Risks / Trade-offs

- **🔴 Rủi ro lớn nhất: refactor chạm lõi tab Usage, mà diff không soát được bằng mắt** → quy trình 3 lớp ở D9 (lọc thụt lề → so thân hàm chuẩn hoá → bất biến API). Các bất biến của `/v1/_mw/summary`: `requests_total=189`, `requests_ok=183`, `tokens_total=360907`, `cost_total_usd=0.067191`, `sum(timeseries)=189`, `sum(breakdown_by_user)=188`. Cả ba lớp phải sạch mới đi tiếp.
- **Tách bước 1 (di chuyển) khỏi bước 2 (bổ sung)** → nếu gộp, diff trộn hai loại thay đổi và Lớp 1 của D9 mất tác dụng. Phải commit/kiểm riêng từng bước.
- **Số trên màn hình nhảy** (`0 → 189`, biểu đồ giảm ~40%) → báo team trước; ghi lý do vào proposal để sau này tra được.
- **Leaderboard mất dòng khi > 20 user** → đã xử lý ở D4.
- **Bucket lệch ở khoảng 1-2 ngày** → đã xử lý ở D3 (truyền tường minh).
- **Lệch 7 tiếng giữa đường DB và đường dự phòng file** → **lỗi có sẵn, không do change này.** `_load_entries_from_db` trả datetime theo timezone phiên DB (`Asia/Ho_Chi_Minh`), còn `logging.py:209` ghi file bằng `datetime.now(tz=utc)`. `_get_bucket_key` dùng `strftime` nên **không quy đổi** — bucket theo tzinfo sẵn có. Khi DB sập, timeseries nhảy 7 tiếng, im lặng. Đang ngủ vì DB sống. Ghi backlog, không sửa trong change này (anh Tuấn đã chốt bỏ qua timezone). `ZoneInfo` được import mà không dùng ở **cả hai** file — nhiều khả năng là dấu vết của ý định xử lý chuyện này rồi bỏ dở.
- **Chat Analytics thừa hưởng dự phòng đọc file** → đây là **lợi**, không phải rủi ro: hiện nó không có dự phòng nào, DB chết là trắng số.

## Phát hiện khi cài đặt

Ba điều lộ ra lúc thực thi, đã xử lý — ghi lại để không ai đi "sửa" lại.

### `sum(chat_count)` = 20 chứ không phải `total_chats` = 24 — ĐÚNG, không sửa

24 phiên thuộc 9 UUID của Open WebUI. Bảy giải được ra email (20 phiên); hai UUID còn lại (`acfae7d4-…` 3 phiên, `5df78c8d-…` 1 phiên) **không tồn tại ở bất kỳ đâu**: không trong `mw_users`, không trong `mw_audit_log.openwebui_user_id`, và đã bị xoá khỏi bảng `user` của Open WebUI.

Nguyên nhân (anh Tuấn xác nhận): đây là những người bị **xoá cứng trước khi có chức năng soft delete**. Cột cầu nối `openwebui_user_id` cũng chỉ bắt đầu được ghi từ 28/06 (4.099 dòng audit trước đó là NULL).

Đã kiểm: `JOIN` thẳng bảng `user` của Open WebUI **cũng ra đúng 20** — nên đây không phải hệ quả của việc chọn `openwebui_user_id` làm cầu nối, mà là dữ liệu định danh chưa từng được lưu.

**Vì sao không sửa được:** leaderboard dựng từ `mw_audit_log`; hai người này không có dòng nào ở đó, nên **không có ô nào để điền 4 phiên chat vào**, kể cả nếu biết họ là ai. `sum(chat_count)` và `total_chats` đếm hai tập khác nhau và không bắt buộc bằng nhau.

**Vết tích này đóng, không lớn thêm:** soft delete giữ nguyên dòng `mw_users` cùng `openwebui_user_id`, và helper `_resolve_ow_ids_to_emails` cố ý **không lọc `deleted_at`** — nên user bị xoá mềm về sau vẫn giữ đủ số phiên chat lịch sử.

### `breakdown_by_*` = 188 trong khi `requests_total` = 189 — kế thừa, đúng

`summary_v2` chỉ gom rid có trạng thái `ok`/`reconciled`/`error` vào `breakdown_by_*`, bỏ rid chỉ có `pending`. Mốc gốc tab Usage cũng là `189/189/188/188`. Chat Analytics giờ khớp từng con số. Rid gây lệch là `test-stuck-rid-123` (model `gemini-2.5-flash`, kẹt `pending` từ 27/06) — cũng là lý do bảng model từ 5 xuống 4 dòng, tức hội tụ đúng chứ không mất dữ liệu.

### Bốn lỗi tự gây ra, phát hiện và sửa qua ba vòng review

| Vòng | Lỗi | Xử lý |
|---|---|---|
| 1 | `get_satisfaction_analytics` vẫn giữ **bản sao inline** của chuỗi giải định danh → đúng anti-pattern mà change này đi chữa | Gộp về `_resolve_ow_ids_to_emails`, xoá 15 dòng trùng |
| 2 | **Mất giới hạn `leaderboard[:50]`** khi thay khối code (thứ tự sắp xếp vẫn đúng nhờ kế thừa `breakdown_by_user.sort(cost desc)`) | Khôi phục phép cắt |
| 2 | **Lỗi gom bị nuốt im lặng**: `compute_usage_summary` trả `{"error": …}` mà không log; `analytics.py` mất `logger.error` vốn có → phép gom hỏng thì **cả hai tab về 0 không dấu vết**, đúng loại bug change này đi chữa | Thêm log ở cả hai tầng; thay `except: pass` trần khi tra tên user bằng `logger.error` |
| 3 | **`top_model` bất nhất ở nhánh lỗi**: nhánh `status == "error"` có ghi `model_data[model]` nhưng KHÔNG ghi `user_data[…]["models"]` → user mà mọi request đều lỗi sẽ báo `top_model="unknown"` trong khi bảng model vẫn liệt kê model đó. Code cũ của `analytics.py` đếm mọi dòng kể cả lỗi | Thêm đếm model ở nhánh lỗi cho khớp |

Vòng 3 quét thêm: consumer khác của `summary_v2` (`export_report`, `main.py`), biến mồ côi, rò rỉ `defaultdict` vào JSON, smoke test 7 endpoint — **không ra thêm vấn đề**. Bốn biến mồ côi còn lại trong `summary_v2` (`is_image_model`, `is_audio_model`, `is_video_model`, `source`) đã **có sẵn trong bản gốc**, nằm trong khối được di chuyển nguyên vẹn.

## Migration Plan

Thuần bổ sung, không migration DB, không breaking. Triển khai theo D8, rồi `docker compose up -d --build middleware` (code Python nằm trong image, `reload=False`).

Mỗi bước ở D8 nên là **một commit riêng** — vừa để Lớp 1 của D9 soát được, vừa để rollback từng nấc nếu cần.

Rollback: hoàn nguyên `analytics.py` về bản tự gom; `summary_v2` giữ hàm đã tách vẫn chạy bình thường vì `get_summary_v2` không đổi hợp đồng API.

## Open Questions

- Có nên thống nhất luôn quy tắc chọn `bucket_size` giữa hai endpoint không? D3 cố ý giữ nguyên khác biệt để không đổi hành vi; nhưng về lâu dài hai quy tắc song song vẫn là mầm lệch.
- `hourly_activity` bổ sung vào `/v1/_mw/summary` — tab Usage có muốn hiển thị nó không, hay chỉ để đó cho Chat Analytics dùng? Không chặn change này.
