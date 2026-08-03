# Unify group aggregation (Phase 7a)

## Why

Tab Groups là tab dashboard **cuối cùng** còn tự gom `mw_audit_log` bằng vòng lặp riêng (`api/group_analytics.py`). Nó đếm **dòng** (`+= 1` mỗi row) trong khi mọi tab khác đếm **rid duy nhất** — cùng cửa sổ `2026-06-16T00:00:00+07:00 → 2026-07-15T23:59:59+07:00` trên dev cho **264 vs 189 requests, lệch 40%**. Đợt `unify-audit-aggregation` (2026-07-20) đã sửa việc này cho Chat Analytics nhưng **bỏ sót groups**: đọc lại `proposal.md`/`design.md` của change đó không có một chữ "group" nào.

Chi phí thì **hiện đang khớp tuyệt đối**: đo trực tiếp bằng SQL, cộng mọi dòng và cộng chỉ dòng `ok`/`reconciled` đều cho `0.067191` — vì các dòng thừa trên dev đều có `cost = 0`. Đó là "may mắn của dữ liệu dev" mà nguyên tắc thiết kế của dự án yêu cầu không được dựa vào: lên production, một dòng thừa mang tiền là lệch ngay.

> Con số `$0.0672` mà tab Groups đang hiện **không** phải bằng chứng lệch nguồn gom — nó là hệ quả của `round(stats["total_cost"], 4)` áp cho **từng nhóm** (`group_analytics.py:107`) rồi cộng các giá trị đã làm tròn. Đó là lỗi hiển thị riêng, và change này sửa luôn bằng cách trả 6 chữ số thập phân như `breakdown_by_user` vẫn làm.

Việc này **chặn cứng** Phase 7b: chỉ tiêu đầu bảng của 7b là `cost share % = chi phí phòng ÷ tổng hệ thống`, với tử số từ Groups (đếm dòng) và mẫu số từ Usage (đếm rid). Một phân số có tử và mẫu từ hai định nghĩa khác nhau thì không sửa được bằng làm tròn — và lãnh đạo sẽ **nhân ngược** con số phần trăm đó với tổng ở Overview để ra tiền.

Change này **chỉ sửa cho đúng, không thêm chỉ tiêu nào**. Làm ngược lại (công bố phần trăm trước, thống nhất nguồn sau) thì mọi con số vừa công bố sẽ đổi ở lần deploy kế tiếp.

## What Changes

**Nguồn gom**

- `group_analytics.py` gọi `compute_usage_summary` và gộp `breakdown_by_user` theo nhóm, thay vì tự duyệt `mw_audit_log`. Bỏ hai vòng gom trùng lặp (hai endpoint hiện là hai bản copy của cùng một vòng lặp, khác nhau chỉ ở điều kiện lọc).
- **BREAKING (số hiển thị đổi):** `total_requests` của tab Groups sẽ **tụt 264 → 189** trên dev. Đây là mục đích của change, không phải hồi quy — nhưng phải báo trước cho người xem dashboard, không để lặng lẽ.
- Tách hàm thuần `compute_group_analytics(cutoff, end_time, bucket_size)` — không nhận `Request`, không tự check auth, không raise HTTP. `export_report.py` gọi hàm này thay vì gọi hàm handler `get_group_analytics(request, ...)` như hiện tại.
- Đổi resolver thời gian từ `analytics._time_boundaries` (nuốt lỗi, rơi về 30 ngày) sang `summary_v2._resolve_range` (raise `400`) — nợ kỹ thuật #1 trong plan.

**Mở rộng hàm gom dùng chung** (`summary_v2.compute_usage_summary`)

- Thêm `latency_sum_ms` + `latency_sample_count` vào mỗi dòng `breakdown_by_user`. Cần cả hai vì P95 **không cộng lại được** từ P95 của từng người, nên trung bình trên tổng thời gian và tổng số mẫu là đường duy nhất tính latency theo nhóm.
- Đổi thống kê model từ đếm dòng (`models[model] += 1`) sang **đếm rid duy nhất**. Một request đi `error → reconciled` hiện bị đếm hai lần. **Tác dụng lan:** `top_model` của tab Usage có thể đổi với một số user — đổi theo hướng đúng hơn, và có chủ ý.
- **Đưa request `pending` vào sổ theo người.** Hiện `breakdown_by_user` chỉ nhận rid ở nhánh `ok`/`reconciled`/`error`, nên một request còn treo **không thuộc về ai** — `totals.requests_total` đếm nó (189) nhưng tổng theo người thì không (188). Lệch này đã có sẵn và đang hiện ra ở tab Usage: thẻ *Total Requests* `189` trong khi cộng bảng Top Users ra `188`. Đếm request `pending` vào người gọi nó (**không** cộng tiền/token vì chưa có số), để mọi tab cộng ra cùng một con số. **Tác dụng lan:** xem § Impact.

**Sửa lỗi phát hiện khi khảo sát**

- **Drill-down lệch bảng cha (bug đang ngủ):** bảng cha dùng nhóm chính (`DISTINCT ON (u.email) ORDER BY created_at ASC`), drill-down dùng **mọi membership** (`WHERE gm.group_id = %s`). Khi có người thuộc 2 nhóm thì `Σ drill-down ≠ dòng bảng cha`, và cost share % của thành viên ở 7b sẽ ra `>100%`. Cho cả hai dùng cùng một map nhóm chính.
- **Fail-open ở nhánh uncategorized:** `group_analytics.py:203-217` query OW lần hai rồi bọc `except: pass` — query lỗi thì **không lọc ai cả**, drill-down trả về toàn bộ user hệ thống dán nhãn uncategorized. Bỏ hẳn query lần hai (đã có map nhóm trong tay).
- **Nhóm không có traffic hiện vô hình:** `group_stats` là `defaultdict` chỉ sinh khoá khi gặp dòng audit, nên nhóm `Marketing` (0 thành viên) chưa bao giờ xuất hiện trong bảng. Lấy danh sách nhóm từ bảng `group` của Open WebUI làm khung (LEFT JOIN) thay vì suy ra từ audit rows. Nhóm không có dữ liệu hiện `—`, theo tiền lệ `runway_days` của Phase 6.
- **`avg_latency_ms` sai hệ thống:** hiện chia `Σ latency ÷ Σ dòng`, mà dòng `pending` không có `latency_ms` vẫn nằm trong mẫu số ⇒ luôn thấp hơn thực tế. Chia tổng thời gian cho số mẫu thật, và **hiện `latency_sample_count` lên UI** vì latency chỉ phủ ~62% request thành công (toàn bộ dòng `reconciled` không ghi `latency_ms`).
- **Chi phí trả về 6 chữ số thập phân** thay vì `round(..., 4)` từng nhóm. Làm tròn từng nhóm rồi cộng thì tổng không bao giờ khớp `totals.cost_total_usd`, nên không kiểm chứng được bằng phép so bằng.

**Nhãn**

- Đổi nhãn dòng `Uncategorized` → **"Chưa quy được phòng ban"**. Bằng chứng dev: 155/264 dòng thuộc rổ này, nhưng chỉ **20 dòng (13%)** là nhân viên có tài khoản Open WebUI chưa được gán phòng; **134 dòng (87%)** là định danh **không có tài khoản OW nào** — `admin` (64 dòng, không phải email, là định danh hệ thống) và `dinhthinhan18111971@gmail.com` (62 dòng, đã bị xóa bên OW nên `ON DELETE CASCADE` xóa luôn membership). Nhãn "chưa gán" ngụ ý sẽ gán được nếu admin siêng hơn — sai với 87% của con số.
- Sửa nhãn tương ứng trong `export_report.py:313` (đang hardcode `"Uncategorized"`), để Excel và dashboard không gọi khác tên cho cùng một dòng.
- Chú thích **"Chi phí phân bổ theo cơ cấu tổ chức HIỆN TẠI"** trên tab: bảng `group_member` của OW chỉ lưu trạng thái hiện tại, còn `mw_audit_log` là lịch sử bất biến — nên người chuyển phòng mang **toàn bộ** lịch sử sang phòng mới, và báo cáo một tháng quá khứ sẽ đổi số sau khi có người chuyển phòng.
- Cảnh báo **"⚠️ N người thuộc nhiều nhóm — chi phí tính vào nhóm vào sớm nhất"** khi phát hiện đa nhóm. Giữ nguyên quy tắc nhóm chính, chỉ biến lỗi im lặng thành lỗi nhìn thấy được.
- Đổi nhãn cột **"Thành viên"** ở một trong hai chỗ: bảng Groups đếm người có nhóm này là **nhóm chính**, còn section Tool Access ngay bên dưới đếm **toàn bộ membership** (`core/tool_access.py:85`). Hai con số khác nhau cùng tên trên một màn hình.
- Biểu đồ doughnut: gán màu xám nhạt cho dòng "chưa quy được phòng ban" và đẩy nó xuống cuối legend, để 4 phòng ban thật đọc thành một bộ.

## Capabilities

### New Capabilities

Không có. Change này sửa hành vi của capability đã tồn tại, không giới thiệu năng lực mới.

### Modified Capabilities

- `group-analytics`: nguồn gom đổi sang `compute_usage_summary` (đơn vị đếm là rid duy nhất, chỉ `ok`/`reconciled` mới cộng tiền/token) · nhãn `Uncategorized` → "Chưa quy được phòng ban" và định nghĩa rổ đó gồm 3 loại · `avg_latency_ms` tính trên số mẫu thật kèm `latency_sample_count` · phần trăm model đếm theo rid duy nhất · khung danh sách nhóm lấy từ bảng `group` · range không hợp lệ trả `400` thay vì lặng lẽ về 30 ngày · quy tắc nhóm chính giữ nguyên (`created_at` cũ nhất) nhưng bổ sung yêu cầu cảnh báo khi có người thuộc nhiều nhóm.
- `group-drill-down`: bổ sung yêu cầu drill-down dùng **cùng một định nghĩa thành viên** với bảng cha (nhóm chính), để `Σ drill-down` luôn khớp dòng cha · nhánh "chưa quy được phòng ban" không được fail-open khi truy vấn Open WebUI lỗi.

## Impact

**Backend**

| File                                | Thay đổi                                                                     |
|-------------------------------------|------------------------------------------------------------------------------|
| `llm-mw/api/group_analytics.py`     | Viết lại cả hai endpoint quanh `compute_usage_summary`; tách hàm thuần        |
| `llm-mw/api/summary_v2.py`          | Thêm `latency_sum_ms` · `latency_sample_count` vào `breakdown_by_user`; model đếm theo rid; rid `pending` vào sổ theo người |
| `llm-mw/api/export_report.py`       | `_collect_groups` gọi hàm thuần, bỏ `except: pass`; sửa nhãn sheet Phòng ban  |

**Frontend**

| File                                        | Thay đổi                                                     |
|---------------------------------------------|--------------------------------------------------------------|
| `llm-mw/dashboard/js/group_analytics.js`    | `colspan="7"` nằm ở **7 chỗ** — sửa hết; màu xám doughnut; hiện độ phủ latency |
| `llm-mw/dashboard/index.html`               | Chú thích "cơ cấu hiện tại"; cảnh báo đa nhóm; đổi nhãn cột Thành viên |

**Lan sang tab khác** — tất cả là hệ quả của việc sửa hàm gom dùng chung, có chủ ý, ghi trong `design.md`

| Nơi bị ảnh hưởng                              | Đổi gì                                                                                          |
|-----------------------------------------------|-------------------------------------------------------------------------------------------------|
| Tab **Usage** — bảng Top Users                | `top_model` của một số user có thể đổi (đếm model theo rid). Số request tăng đúng bằng số request `pending` của user đó, và tổng bảng khớp thẻ *Total Requests* |
| Tab **Usage** — `error_rate_percent` theo user | Mẫu số giờ gồm cả request `pending` ⇒ tỷ lệ lỗi từng user giảm nhẹ                              |
| Tab **Chat Analytics** — leaderboard      | `request_count` đọc `requests_total` theo user (`analytics.py:158-168`), nên cũng tăng đúng bằng số request `pending`. Đúng hướng: tab này trước đó hiện tổng `189` nhưng cộng leaderboard ra `188` |
| Tab **Users** — tỷ lệ áp dụng (`adoption.py`) | `active_user_ids` lấy từ `breakdown_by_user`, nên người trong kỳ **chỉ có** request `pending` giờ được tính là có hoạt động. Đúng bản chất (họ có gửi request) nhưng làm tỷ lệ áp dụng nhích lên — **phải đo trước/sau**. *Đo trên dev: không đổi (13 → 13), vì `admin` vốn đã có request khác* |
| **Excel export**                              | Số ở sheet "Phòng ban" tự khớp dashboard, vì `export_report.py` đang tái dùng chứ không tự gom — không phải sửa hai chỗ |

**Không đụng tới**

- Section "🔧 Phân quyền Tool theo phòng ban" — giữ nguyên theo Phase 0, chỉ đổi nhãn cột "Thành viên" nếu chọn đổi ở phía đó.
- `core/tool_access.py` logic cấp quyền · `core/alerting.py` · CHECK 1 (quota per-user).

**Non-goals** (thuộc `dashboard-group-scale` / Phase 7b)

- Cost share % hai cấp (phòng/hệ thống, thành viên/phòng)
- `Cost / total_members` · `Cost / active_members`
- % hạn mức quota trong drill-down thành viên
- Scorecard 3 thẻ (Số đơn vị · Tổng thành viên · TB chi phí/đơn vị) — **và chú thích + tooltip đi kèm scorecard**, vì scorecard chưa tồn tại ở change này
- Badge KT/CK cho "TB chi phí/đơn vị". Lưu ý tab Groups **chưa có** cơ chế fetch 3 cửa sổ song song như Usage/Overview — đó là phần việc thật của 7b, không phải "chỉ khai báo thêm một dòng registry" như plan ghi.
