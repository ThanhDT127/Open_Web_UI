# Tasks — unify-group-aggregation (Phase 7a)

> Thứ tự các nhóm là **bắt buộc** (design D13). Mỗi nhóm xong thì hệ thống vẫn chạy được.
> **Nhóm 4 là bước duy nhất làm số hiển thị đổi** (Requests 264 → 189) — commit riêng, thông báo trước.

> **Cửa sổ dùng cho mọi phép đo/nghiệm thu dưới đây:** `2026-06-16T00:00:00+07:00` → `2026-07-15T23:59:59+07:00`.
> Ghi tường minh mũi giờ và biên cuối là bắt buộc — cùng dữ liệu, biên cuối `2026-07-15T00:00` cho `255/183` còn cuối ngày cho `264/189`.

## 1. Mở rộng hàm gom dùng chung (chưa ai đọc field mới — an toàn nhất)

- [x] 1.1 Trong `summary_v2.compute_usage_summary`, thu thập `latency_sum_ms` và `latency_sample_count` cho từng user từ list `latencies` đã có (`summary_v2.py:431-435`), thêm cả hai field vào mỗi dòng `breakdown_by_user`. **Không** thêm `avg_latency_ms` — nhóm tự chia, tránh làm tròn hai lần (design D5)
- [x] 1.2 Đổi `user_data[user_id]["models"]` từ `defaultdict(int)` sang `defaultdict(set)` chứa `rid`; cập nhật cả hai nhánh cộng (`:320` nhánh ok/reconciled và `:340` nhánh error) và chỗ suy ra `top_model` (`:437-438`) sang dùng `len()`
- [x] 1.3 Xuất phân bố model của từng user ra `breakdown_by_user` (số lượng theo rid duy nhất cho mỗi model), để nhóm gộp được thành `model_preferences` mà không cần đọc lại audit
- [x] 1.4 Thêm nhánh cho trạng thái `pending`: rid được `add` vào `user_data[user_id]["requests"]` nhưng **KHÔNG** cộng `cost_total` / `tokens_total` / `latencies`, và **KHÔNG** vào `requests_ok`. Hiện vòng lặp chỉ có `if ok/reconciled` … `elif error` mà không có `else` (`summary_v2.py:305-343`) nên rid `pending` không thuộc về ai (design D14)
- [x] 1.5 Đo `top_model` của toàn bộ user trước/sau thay đổi 1.2; ghi lại danh sách user có `top_model` đổi vào phần nghiệm thu — tác dụng lan có chủ ý sang tab Usage (design D6)
- [x] 1.6 Đo trước/sau cho ba tác dụng lan của 1.4 (design D14): (a) số request từng user trong bảng Top Users, (b) `error_rate_percent` từng user, (c) **tỷ lệ áp dụng ở tab Users** — `adoption.py:253` lấy `active_user_ids` từ `breakdown_by_user` nên người chỉ có request `pending` giờ được tính là có hoạt động
- [x] 1.7 Xác nhận sau 1.4, Σ số request của bảng Top Users **bằng** `totals.requests_total` (trước: `188` vs `189`)
- [x] 1.8 Xác nhận `breakdown_by_model` và `totals` **không đổi giá trị** (requirement "Existing model columns and totals are unchanged" của `dashboard-model-metrics` chỉ phủ `breakdown_by_model`, nhưng phải chứng minh là không vi phạm)
- [x] 1.9 Kiểm caller còn lại `api/analytics.py:121` (Chat Analytics). ⚠️ **Sửa so với bản viết ban đầu:** tab này **có** đọc `requests_total` theo user — `leaderboard[].request_count` (`analytics.py:158-168`) — nên `admin` cũng đổi 46 → 47 ở đây. Đúng hướng: trước đó Chat Analytics hiện tổng `189` nhưng cộng leaderboard ra `188`, giờ khớp. Ghi lại, không phải chặn

## 2. Đổi resolver thời gian (số KHÔNG đổi)

- [x] 2.1 Trong `api/group_analytics.py`, thay `from api.analytics import _time_boundaries` bằng `from api.summary_v2 import _resolve_range`; giữ mặc định `minutes=43200` ở signature để hành vi khi không truyền tham số không đổi. Truyền `bucket` **tường minh** (`"day"`), không để `"auto"` — tab Groups không dùng `timeseries` (design D16, theo tiền lệ D3 của `unify-audit-aggregation`)
- [x] 2.2 Áp cho cả hai endpoint (`get_group_analytics`, `get_group_users`); xác nhận `start`/`end` sai cú pháp và `start >= end` trả `HTTP 400` thay vì rơi về cửa sổ 30 ngày
- [x] 2.3 Kiểm frontend không bị ảnh hưởng: `group_analytics.js` gọi qua `buildRangeParams()` nên luôn truyền `start`/`end` hợp lệ

## 3. Đổi khung danh sách nhóm sang bảng `group` (nhóm cũ không đổi số)

- [x] 3.1 Lấy toàn bộ nhóm từ `SELECT id, name FROM "group"` làm khung kết quả, thay vì để `defaultdict` sinh khoá theo dòng audit
- [x] 3.2 Ghép số liệu sử dụng vào khung (LEFT JOIN theo nghĩa logic); nhóm không có dữ liệu trong cửa sổ trả `None` cho các chỉ số dẫn xuất để frontend hiện `—`
  - ⚠️ **Sai lệch so với kế hoạch:** `group_analytics.js:89` gọi `g.avg_latency_ms.toFixed(1)` nên `null` làm **crash** bảng. Kế hoạch xếp mọi việc frontend vào nhóm 7, nhưng như vậy nhóm 3 không deploy độc lập được — vi phạm chính nguyên tắc D13. Đã kéo riêng phần chống `null` của `avg_latency_ms` lên nhóm 3; phần hiện độ phủ latency vẫn ở 7.3
  - ➕ **Sửa thêm ngoài kế hoạch:** khối đọc Open WebUI trước đây bọc `except: pass`, nên OW lỗi thì `group_names` rỗng → **mọi dòng** rơi vào "chưa quy được phòng ban" và tổ chức trông như có 0 phòng ban. Cùng loại fail-open với task 5.3. Nay `_fetch_group_context()` raise `503`. Bắt buộc phải sửa ở nhóm này vì từ đây danh sách nhóm là **khung** của bảng
- [x] 3.3 Xác nhận nhóm `Marketing` (0 thành viên) xuất hiện trong bảng, và số lượng nhóm **không đổi** khi đổi cửa sổ thời gian từ 30 ngày xuống 1 giờ
- [x] 3.4 Tính sẵn `Counter(user_primary_group.values())` (số người có nhóm này là nhóm chính) và số người thuộc >1 nhóm — hai con số này cần cho nhóm 7 và cho 7b, và lấy được từ dữ liệu đã fetch, không thêm query
  - Xuất ra payload: `primary_member_count` mỗi nhóm (`None` cho dòng chưa quy được — nó không phải phòng ban), `department_count`, `multi_group_user_count`
  - Nghiệm thu: `department_count = 5` **giống nhau** ở cửa sổ 30 ngày và 1 giờ · `Marketing` hiện với `req=0, avg_latency_ms=null, members=0` · Σ requests vẫn `264` (nhóm 3 không đổi số) · `multi_group_user_count = 0`

## 4. ⚠️ Thay vòng gom bằng `compute_usage_summary` — BƯỚC LÀM SỐ ĐỔI

- [x] 4.1 Tách hàm thuần `compute_group_analytics(cutoff, end_time, bucket_size)` — không nhận `Request`, không auth, không raise HTTP (design D1)
- [x] 4.2 Trong hàm thuần: gọi `compute_usage_summary`, gộp `breakdown_by_user` theo nhóm chính; bỏ hoàn toàn vòng `SELECT ... FROM mw_audit_log` và vòng `for row in cur.fetchall()` của `get_group_analytics` (`group_analytics.py:55-87`)
- [x] 4.3 Tính `avg_latency_ms` của nhóm bằng `Σ(latency_sum_ms_i) / Σ(latency_sample_count_i)`; trả kèm tổng `latency_sample_count` của nhóm
- [x] 4.4 Gộp `model_preferences` của nhóm từ phân bố model theo rid (task 1.3); giữ nguyên hình dạng `[{model, count, percentage}]`
- [x] 4.5 Map tên field về đúng hợp đồng cũ mà frontend đang đọc — `total_requests` / `total_cost` / `total_tokens` / `avg_latency_ms` / `model_preferences` — **không đổi frontend** (design D2)
- [x] 4.6 Trả `total_cost` **chưa làm tròn**, bỏ `round(..., 4)` từng nhóm (`group_analytics.py:107`); làm tròn đúng một lần ở tầng hiển thị (design D15)
  - ⚠️ **Sửa hai lần mới đúng.** Bản đầu trả 6 chữ số → đo trên toàn bộ dữ liệu (4101 request) thấy lệch `0.000001`: `totals` làm tròn **một** lần ở cuối, còn nhóm cộng các giá trị **đã** làm tròn của từng user. Thêm `cost_usd_raw` vào `breakdown_by_user` thì cửa sổ lớn khớp nhưng cửa sổ nhỏ lại lệch — vì payload vẫn `round(..., 6)` **từng nhóm**. Bỏ hẳn việc làm tròn trong payload mới hết
  - Sai số **tăng theo số phần tử được cộng**: 6 chữ số × 200 user (quy mô production) dồn tới chữ số thập phân **thứ 4** — chữ số cuối mà `usd4()` hiển thị. Trên dev 13 user thì nằm ở chữ số thứ 6 nên không thấy — đúng loại "may mắn dữ liệu dev"
  - ✅ Đối chiếu lại **10 cửa sổ** (1g · 6g · 24g · 7n · 30n · 90n · cố định 16/06-15/07 · 1 ngày 15/07 · toàn bộ từ 2020 · cửa sổ tương lai rỗng) × 3 nguồn độc lập (SQL thô · `totals` · Σ nhóm): **khớp tuyệt đối cả request, chi phí và tokens ở cả 10**
- [x] 4.10 Frontend format tiền qua formatter dùng chung `usd4` (export từ `metrics_registry.js`) thay vì `toFixed(4)` viết thẳng ở 3 chỗ trong `group_analytics.js`. Export hàm formatter chứ **không** đăng ký cột bảng thành metric — spec `dashboard-model-metrics` đã chốt chỉ scorecard mới vào registry
- [x] 4.7 Endpoint `get_group_analytics` chỉ còn: auth → `_resolve_range` → gọi hàm thuần → trả kết quả
- [x] 4.8 **Nghiệm thu bắt buộc.** Tiêu chí chính là **bất biến**, không phải con số cụ thể:

  > `Σ requests các nhóm == totals.requests_total` và `Σ chi phí các nhóm == totals.cost_total_usd`, **trên bất kỳ cửa sổ nào**.

  Phát biểu theo bất biến vì con số tuyệt đối phụ thuộc cửa sổ và sẽ mục theo thời gian. ⚠️ **Cửa sổ nghiệm thu ở đầu file là khoảng CỐ ĐỊNH, phải nhập bằng custom range** — preset `30d` trên dashboard là cửa sổ **trượt** kết thúc ở hôm nay nên cho số khác, và cả hai đều đúng. Đã kiểm bất biến trên **hai** cửa sổ khác nhau:

  | Cửa sổ | Σ nhóm | `totals.requests_total` | Σ cost nhóm | `totals.cost_total_usd` |
  |---|---:|---:|---:|---:|
  | Cố định `16/06→15/07 +07` | 189 | 189 ✓ | 0.067191 | 0.067191 ✓ |
  | Trượt `30d` (preset dashboard) | 186 | 186 ✓ | 0.066959 | 0.066959 ✓ |

  Con số cụ thể cho cửa sổ cố định — bốn nguồn phải cho cùng một số request:

  | Nguồn                                  | Trước | Sau |
  |----------------------------------------|------:|----:|
  | Tab Groups (Σ các nhóm)                |   264 | 189 |
  | `totals.requests_total`                |   189 | 189 |
  | Σ bảng Top Users tab Usage             |   188 | 189 |
  | `count(DISTINCT rid)` bằng SQL          |   189 | 189 |

  Và `Σ chi phí các nhóm == totals.cost_total_usd` bằng **phép so bằng tuyệt đối** (khả thi nhờ 4.6). Giá trị hiện tại: `0.067191`

  **✅ Kết quả đo 2026-07-27:** `Σ group requests = 189 == totals.requests_total = 189` · `Σ group cost = 0.067191 == totals.cost_total_usd = 0.067191`, **sai số 0.0** · `department_count = 5` · `multi_group_user_count = 0`

  Chi tiết từng nhóm — lưu ý **avg latency tăng 2–2,5 lần** vì mẫu số giờ là số mẫu latency thật, không phải mọi dòng audit (design D5):

  | Nhóm                   | Req trước | Req sau | Avg latency trước | Avg latency sau | Mẫu latency |
  |------------------------|----------:|--------:|------------------:|----------------:|------------:|
  | Chưa quy được phòng ban |       155 |     111 |          2 341,57 |        5 499,15 |          66 |
  | Admin                  |        71 |      51 |          2 779,71 |        6 366,43 |          31 |
  | R&D                    |        26 |      18 |          3 500,50 |        9 101,31 |          10 |
  | DevOps                 |         8 |       6 |          7 375,56 |       14 751,12 |           4 |
  | DataCenter             |         4 |       3 |          4 893,18 |        9 786,35 |           2 |
  | Marketing              |         0 |       0 |                 — |               — |           0 |
  | **Σ**                  |   **264** | **189** |                   |                 |             |
- [x] 4.9 Commit riêng nhóm này, message nêu rõ số trước/sau; thông báo cho người xem dashboard trước khi deploy
  - Commit `ff814fe` (`... requests 264 -> 189`). Deploy **dev** đã làm (`docker compose restart middleware`); thông báo cho người xem là việc của lần deploy **production**, chưa tới
  - ⚠️ Lưu ý vận hành: `uvicorn` chạy `--workers 4` **không có `--reload`**, nên `docker cp` file vào container **không** làm code có hiệu lực. Phải restart. Chỉ `dashboard/` là bind-mount nên JS/HTML thì live ngay

## 9. Nghiệm thu live qua HTTP (sau restart)

- [x] 9.1 `GET /v1/_mw/admin/analytics/groups` → `200`; `Σ requests = 189 == totals.requests_total`; `Σ cost = 0.067191 == totals.cost_total_usd`; `department_count = 5`; `multi_group_user_count = 0`; 6 dòng (5 phòng + 1 chưa quy được)
- [x] 9.2 Drill-down live cho **cả 6 nhóm** → mọi dòng khớp dòng cha cả request và chi phí
- [x] 9.3 Đường lỗi: range sai cú pháp → `400` · range đảo ngược → `400` · không auth → `403`
- [x] 9.4 Excel export → `200`, 29 554 bytes, 7 sheet. Sheet "Phòng ban" khớp API từng dòng (tên + request), Σ `189`, `Marketing` có ô latency **rỗng** thay vì `0`
- [x] 9.5 Tab bị lan vẫn `200`: `/summary` · `/analytics/chat` · `/adoption` · `/providers`
- [x] 9.6 Tab Usage: `totals.requests_total = 189` **==** Σ bảng Top Users `189` (trước change lệch 1) — lỗi D14 đã hết trên live
- [x] 9.7 Field mới ra tới payload: `cost_usd_raw`, `latency_sum_ms`, `latency_sample_count`, `model_counts`
- [x] 9.8 Adoption sau D14: `active_users 13 / provisioned 12 → 83.3%` — **không đổi** so với baseline, vì `admin` vốn đã có request khác
- [x] 9.9 Nghiệm thu trên trình duyệt: chú thích phòng ban, ô latency, miếng doughnut xám xếp cuối legend, drill-down khi bấm dòng
  - ✅ Anh Tuấn xác nhận bằng ảnh chụp 27/07: *"Hệ thống có **5** phòng ban"* · nhãn **"Chưa quy được phòng ban"** · **108** request (trước 151) · độ phủ latency hiện trong ô · legend có **Marketing** và miếng **xám xếp cuối** · drill-down cộng ra **đúng 108 request và $0.0324** = dòng cha (trước lệch 33–44%)
  - Trong drill-down thấy đúng 2 trong 3 loại của rổ "chưa quy được": tài khoản đã xoá khỏi OW (`dinhthinhan18111971`, tên rơi về email) và định danh hệ thống (`admin`)
  - ⚠️ **Phát hiện lúc deploy:** ảnh chụp **lần đầu** ra số cũ vì `docker cp` không phải deploy — `llm-mw/Dockerfile:18` `COPY api/ ./api/` nướng code vào **image**, nên container tạo lại từ image là mất hết. Phải `docker compose build middleware && docker compose up -d middleware`. Chỉ `dashboard/` bind-mount nên JS/HTML live ngay sau F5
  - Ảnh chụp còn hiện `(64 mẫu)`; sau đó đã đổi thành `(64/108 req)` — cần F5 lại để thấy

## 5. Đồng nhất drill-down với bảng cha (sửa bug đang ngủ)

- [x] 5.1 `get_group_users` dùng **cùng** map nhóm chính với bảng cha, thay `SELECT u.email WHERE gm.group_id = %s` (`group_analytics.py:136-141`) — user thuộc 2 nhóm chỉ xuất hiện ở drill-down của nhóm gia nhập sớm hơn (design D7)
- [x] 5.2 Bỏ hẳn khối query Open WebUI lần thứ hai cho nhánh uncategorized (`group_analytics.py:203-217`) cùng với `except: pass` — map nhóm chính đã đủ để suy ra tập này
- [x] 5.3 Cho nhánh "chưa quy được phòng ban" **báo lỗi** khi truy vấn Open WebUI thất bại, thay vì trả về danh sách chưa lọc (hết fail-open)
- [x] 5.4 Drill-down lấy số liệu từ hàm thuần dùng chung, không tự duyệt `mw_audit_log`; bỏ vòng gom trùng lặp ở `group_analytics.py:160-200`
- [x] 5.5 Kiểm chứng: Σ chi phí các dòng drill-down của một nhóm == chi phí nhóm đó ở bảng cha, cho **mọi** nhóm kể cả "chưa quy được phòng ban"
- [x] 5.6 Kiểm chứng: số request của một user trong drill-down == số request của user đó trên bảng Top Users của tab Usage, cùng cửa sổ — **chỉ so được với user nằm trong 20 dòng** mà `get_summary_v2` trả về (`summary_v2.py:606-609` cắt `[:20]`); muốn kiểm toàn bộ thì so với payload đầy đủ của `compute_usage_summary`
- [x] 5.7 Kiểm user đã bị xóa khỏi Open WebUI (`dinhthinhan18111971@gmail.com` trên dev) vẫn còn lịch sử trong drill-down, tên hiển thị rơi về định danh gốc
- [x] 5.8 Commit riêng nhóm này, tách khỏi nhóm 4

  **✅ Nghiệm thu nhóm 5** — 4 cửa sổ (cố định 16/06-15/07 · 30 ngày · toàn bộ · 1 giờ rỗng), **mọi dòng khớp cả request và chi phí**:

  | Nhóm | cha req | con req | cha cost | con cost |
  |---|---:|---:|---:|---:|
  | Chưa quy được phòng ban | 111 | 111 | 0.032586 | 0.032586 |
  | Admin | 51 | 51 | 0.024123 | 0.024123 |
  | R&D | 18 | 18 | 0.008431 | 0.008431 |
  | DataCenter | 3 | 3 | 0.001771 | 0.001771 |
  | DevOps | 6 | 6 | 0.000281 | 0.000281 |
  | Marketing | 0 | 0 | 0.000000 | 0.000000 |

  Trước nhóm 5 các cặp này lệch 33–44% (Admin 51 vs 71, R&D 18 vs 26).

  - **Phân hoạch đúng:** không user nào xuất hiện ở hai nhóm, không user nào bị bỏ rơi — kiểm trên cả 4 cửa sổ
  - **5.6:** số request từng user trong drill-down khớp `breakdown_by_user` cho **toàn bộ** user (so với payload đầy đủ, không qua endpoint bị cắt `[:20]`)
  - **5.7:** `dinhthinhan18111971@gmail.com` (đã xóa khỏi OW) còn 44 request, tên rơi về email · `admin` (định danh hệ thống) còn 47 request · user còn tài khoản hiện tên thật ("Hà Mạnh Thế")
  - **Chia cho 0:** user không có mẫu latency (`pvt123`, `testuser`) trả `avg_latency_ms: null`, không crash
  - ➕ Dọn kèm: bỏ `import time`, `List`, `Tuple`, `db_conn` — không còn dùng sau khi hết tự đọc `mw_audit_log`

## 6. Excel export dùng hàm thuần

- [x] 6.1 `export_report._collect_groups` (`export_report.py:148-160`) gọi `compute_group_analytics(cutoff, end_time, bucket_size)` thay vì gọi hàm handler `get_group_analytics(request, ...)`; bỏ tham số `request`
- [x] 6.2 Bỏ `except Exception: pass` — lỗi phải nổi lên, không để sheet "Phòng ban" ghi "Dữ liệu nhóm không khả dụng" trong khi file Excel vẫn xuất bình thường (design D12)
- [x] 6.3 Đổi nhãn `g.get("group_name", "Uncategorized")` (`export_report.py:313`) sang nhãn mới, để Excel và dashboard không gọi khác tên cho cùng một dòng
- [x] 6.4 Xuất một file Excel thật, đối chiếu sheet "Phòng ban" với bảng trên dashboard: từng dòng khớp cả requests, cost, tokens và avg latency
  - ✅ Sheet và dashboard giờ đọc **cùng một list** từ `compute_group_analytics` → thứ tự dòng và mọi giá trị khớp theo cấu trúc, Σ requests `189 == 189`. Nhãn "Chưa quy được phòng ban" lấy từ API, không hardcode
  - Chi phí làm tròn 6 số **tại ô Excel** (tầng hiển thị), payload để thô — cùng nguyên tắc với `usd4()` ở dashboard
  - Nhóm không có traffic ghi ô latency **rỗng** thay vì `0` (`Marketing`)

## 7. Frontend: nhãn, độ phủ, cảnh báo, màu

- [x] 7.1 Đổi nhãn dòng `Uncategorized` → **"Chưa quy được phòng ban"** trong `group_analytics.js` (giữ dòng trong bảng, không ẩn)
- [x] 7.2 Sửa **đủ 7 chỗ** `colspan="7"` trong `group_analytics.js` nếu số cột đổi — các dòng `50`, `72`, `103`, `122`, `136`, `153`, `174`. Sót một chỗ là bảng lệch
  - **Không cần sửa:** 7a không thêm cột nào. Cột "Thành viên" là task 7.7 đang bị chặn, còn độ phủ latency (7.3) nằm **trong** ô latency sẵn có chứ không thành cột riêng. Đã đếm lại: `<thead>` vẫn 7 `<th>`, `colspan="7"` ở 7 chỗ JS + 3 chỗ HTML đều còn đúng. Ghi lại để 7b biết phải sửa 10 chỗ khi thêm cột
- [x] 7.3 Hiện `latency_sample_count` cạnh giá trị độ trễ trung bình (dạng số mẫu hoặc tooltip), vì latency chỉ phủ ~62% request thành công; nhóm không có mẫu nào hiện `—`
  - Dạng **`5564.4 (64/108 req)`**, phần trong ngoặc màu mờ + `title` giải thích vì sao thiếu. Nhóm không có số đo hiện `—` kèm tooltip, không hiện `0`
  - ⚠️ Bản đầu viết `(64 mẫu)` — **"mẫu" là từ thống kê**, người đọc dashboard phải dịch trong đầu. Đổi sang dạng phân số `64/108 req`: không cần từ chuyên môn, và tự nói ra điều quan trọng nhất là con số **không dựa trên toàn bộ request**. Dạng phần trăm `(59%)` quét nhanh hơn nhưng mất con số tuyệt đối
- [x] 7.4 Thêm chú thích trên tab: *"Chi phí phân bổ theo cơ cấu tổ chức HIỆN TẠI. Người chuyển phòng sẽ mang toàn bộ lịch sử sang phòng mới."* (design D9)
- [x] 7.5 Thêm cảnh báo khi có người thuộc >1 nhóm: *"⚠️ N người thuộc nhiều nhóm — chi phí tính vào nhóm vào sớm nhất"*, dùng con số từ task 3.4 (design D10)
- [x] 7.6 Biểu đồ doughnut: nhận diện dòng không có `group_id` rồi **override** sang màu trung tính, và đẩy xuống cuối chú giải. KHÔNG thêm màu xám vào cuối mảng palette — bảng sort theo chi phí giảm dần nên dòng đó nằm index 0 và sẽ ăn màu `#3b82f6` (design D11)
- [x] 7.7 Đổi nhãn cột "Thành viên" ở một trong hai chỗ — bảng Groups (đếm nhóm chính) vs section Tool Access (`core/tool_access.py:85`, đếm toàn bộ membership). **Chốt phía nào trước khi làm** — xem Open Question 1 trong `design.md`
  - **Đã chốt: giữ nguyên "Thành viên" ở Tool Access, cột mới của 7b đặt là "Thuộc phòng này".** 7a **không sửa code** — cột trùng chữ chưa tồn tại, nó chỉ xuất hiện khi 7b thêm cột. Quyết định đã ghi vào `design.md` Open Question 1 và vào plan §7b
  - Đã xác minh Phase 7 **không đụng** tool access: 6 file thay đổi trong cả 5 commit đều không phải `core/tool_access.py` hay `api/tool_access.py`; và grep xác nhận tool access **không** dùng khái niệm nhóm chính (`DISTINCT ON` / `created_at ASC` không xuất hiện) — nó quyết định ai thấy tool bằng **mọi** membership (`tool_access.py:218-226`). Hai đường tách biệt hoàn toàn
- [x] 7.8 Giữ nguyên section "🔧 Phân quyền Tool theo phòng ban" theo Phase 0 — không di chuyển, không đổi logic

## 8. Đồng bộ tài liệu

- [x] 8.1 Cập nhật `docs/dashboard_metrics_implementation_plan.md` §Phase 7 — đánh dấu phần 7a xong, ghi rõ con số 264 → 189, cửa sổ nghiệm thu **kèm mũi giờ và biên cuối**, và ngày nghiệm thu
- [x] 8.2 Ghi vào plan tác dụng lan của D14 sang tab Users (tỷ lệ áp dụng nhích lên) kèm số liệu trước/sau, để lần sau không ai truy ngược sai nguyên nhân
- [x] 8.3 Ghi vào plan: tab Groups **chưa có** cơ chế fetch 3 cửa sổ song song cho badge KT/CK — sửa lại dòng "🟢 chỉ khai báo thêm một dòng registry" vì nó sai, đó là việc thật của 7b
- [ ] 8.4 `openspec validate unify-group-aggregation --strict` và `openspec archive unify-group-aggregation` sau khi nghiệm thu

## 10. Latency đếm theo request, không theo dòng

- [x] 10.1 `user_data["latencies"]` và `model_data["latencies"]` đổi từ `list` (append mỗi dòng) sang `dict[rid] = latency` — một request đóng góp tối đa **một** số đo, để tử số của `(N/M req)` cùng đơn vị với mẫu số
- [x] 10.2 Cập nhật 5 chỗ đọc: `all_latencies.extend(...)` · p95 theo user · p95 theo model · `sum(...)` cho `latency_sum_ms` · `len(...)` cho `latency_sample_count` — dùng `.values()` ở chỗ cần giá trị, không phải khoá
- [x] 10.3 **Không con số nào được đổi** (dữ liệu hiện tại đã 1 request = 1 dòng latency). Đo trước/sau: `totals` · `breakdown_by_model` · `breakdown_by_user` — **cả ba không có field nào đổi**
- [x] 10.4 Nghiệm thu live sau rebuild: mọi nhóm có `N ≤ M` — `64/108` · `31/51` · `10/18` · `2/3` · `4/6` · `0/0`

  **Vì sao sửa dù số không đổi:** đây là sửa để bất biến được **cấu trúc bảo đảm** chứ không nhờ dữ liệu may mắn. Trước đó tử số đếm dòng còn mẫu số đếm request; hôm nay trùng nhau, nhưng nếu sau này có luồng ghi `latency_ms` ở cả bước `ok` lẫn bước đối soát thì màn hình sẽ hiện phân số kiểu `120/108` mà không ai truy được nguồn.

  **Nợ ghi lại cho sau:** trung bình không phải thống kê chuẩn cho latency — phân bố latency có đuôi dài nên ngành dùng p50/p95/p99, và tab Usage của chính dashboard này cũng dùng p95. Tab Groups giữ trung bình vì p95 **không cộng lại được** từ p95 của từng người (design D5). Muốn p95 theo nhóm thì hàm gom phải giữ lại danh sách latency thô — cân nhắc ở 7b hoặc sau.
