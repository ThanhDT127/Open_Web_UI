# Tasks — dashboard-group-scale (Phase 7b)

> Nền đã đúng nhờ 7a: `Σ nhóm == totals` trên mọi cửa sổ. Change này **chỉ cộng thêm**, không sửa cách tính.
> Mỗi nhóm task xong thì hệ thống vẫn chạy được; không nhóm nào làm đổi con số đã có.

> **Cửa sổ dùng cho mọi phép đo:** ghi tường minh **mũi giờ và biên cuối**. Cửa sổ cố định `2026-06-16T00:00:00+07:00` → `2026-07-15T23:59:59+07:00`; cửa sổ trượt 30 ngày là cái preset `30d` của dashboard gửi (`minutes=43200`) — **hai cái cho số khác nhau, cả hai đều đúng**.

## 1. Chỉ tiêu không cần truy vấn mới (backend)

- [x] 1.1 `compute_group_analytics`: thêm `cost_share_of_system_percent` mỗi nhóm = `total_cost / totals.cost_total_usd × 100`. Mẫu số lấy từ `totals` của cùng lời gọi `compute_usage_summary`, **không** phải `Σ` các dòng đang trả về (design D1, theo tiền lệ Phase 5). Guard chia cho 0
  - ⚠️ Trả **chưa làm tròn**. Làm tròn 1 chữ số từng dòng rồi cộng ra **99,9** chứ không phải 100 (đo thật: 48,3+36,0+12,6+2,6+0,4+0,0). Cùng bài học với chi phí ở 7a D15 — làm tròn đúng một lần, ở tầng hiển thị. Nhờ vậy tiêu chí nghiệm thu là **phép so bằng**, không phải dung sai
- [x] 1.2 Thêm `cost_per_member` = `total_cost / primary_member_count`, trả `None` khi mẫu số là 0 hoặc `None` — **không** trả `0`. Dòng "chưa quy được" trả `None` cho **cả** `primary_member_count`, `active_member_count`, `cost_per_member`, `cost_per_active_member`: nó không phải một đơn vị nên mọi chỉ tiêu trên đầu người đều không áp dụng, dù nó **có** người phát sinh chi phí (design D15)
- [x] 1.3 Thêm `active_member_count` = **giao** của {user có ≥1 request trong cửa sổ, lấy từ `breakdown_by_user`} ∩ {user có nhóm chính là nhóm này, lấy từ `ctx.user_primary_group`}. Phép giao là bắt buộc — người đã rời phòng vẫn còn lịch sử trong audit log, không giao thì `active` vượt `total` (design D3)
- [x] 1.4 Thêm `cost_per_active_member` = `total_cost / active_member_count`, `None` khi mẫu số 0. Giữ **cả hai** chỉ tiêu trên đầu người — chúng trả lời hai câu khác nhau và chênh lệch giữa chúng chính là tín hiệu adoption của phòng đó (design D4)
- [x] 1.5 Thêm vào payload cấp trên: `assigned_member_count` (Σ `primary_member_count` của **các phòng ban thật**), `provisioned_user_count` (số tài khoản `mw_users` chưa xoá — **mẫu số** của thẻ nhân sự, design D13) và `dept_cost_total` (Σ chi phí các phòng ban thật). Tính ở backend để frontend không phải tự lọc rồi lọc sai
- [x] 1.6 **Nghiệm thu 1.1–1.5** trên cửa sổ trượt 30 ngày, đối chiếu giá trị đã đo 2026-07-27:

  | Nhóm | share % | cost/member |
  |------|--------:|------------:|
  | Chưa quy được phòng ban | 48,3 | `None` |
  | Admin | 36,0 | 0.024123 |
  | R&D | 12,6 | 0.004215 |
  | DataCenter | 2,6 | 0.001771 |
  | DevOps | 0,4 | 0.000281 |
  | Marketing | 0,0 | `None` |
  | **Σ share** | **100,0** (chưa làm tròn; cộng bản đã làm tròn 1 chữ số ra 99,9) | |

- [x] 1.7 **Bất biến bắt buộc:** `active_member_count <= primary_member_count` cho mọi nhóm **có `group_id`** × **mọi** cửa sổ (dòng chưa quy được trả `None` cho cả hai nên không áp dụng). Kiểm ít nhất 4 cửa sổ gồm một cửa sổ rỗng (1 giờ) và một cửa sổ toàn bộ dữ liệu
- [x] 1.8 Xác nhận **không con số cũ nào đổi**: `total_requests`, `total_cost`, `avg_latency_ms`, `latency_sample_count`, `model_preferences`, `department_count`, `multi_group_user_count` giữ nguyên giá trị trước/sau

  **✅ Kết quả nhóm 1 (2026-07-27)** — mọi giá trị khớp dự đoán, và 3 bất biến pass trên **4 cửa sổ** (1 giờ rỗng · 30 ngày · cố định · toàn bộ):

  | Bất biến | Kết quả |
  |---|---|
  | `Σ cost_share_of_system_percent == 100` (chưa làm tròn) | ✅ `100.0` **tuyệt đối** cả 4 cửa sổ |
  | `active_member_count <= primary_member_count` (nhóm có `group_id`) | ✅ cả 4 cửa sổ |
  | Dòng "chưa quy được" trả `None` cho **cả 4** chỉ tiêu đầu người | ✅ cả 4 cửa sổ |

  Thẻ: `department_count 5` · `assigned_member_count 5` / `provisioned_user_count 12` · `dept_cost_total 0.034606` → **`$0.006921`** mỗi phòng ban.

  ⚠️ **Sửa hai lần mới đúng, cả hai đều là bài học làm tròn của 7a lặp lại:**
  1. Trả share **đã** làm tròn 1 chữ số → cộng ra `99,9`. Đổi sang trả thô.
  2. Mẫu số lấy `totals.cost_total_usd` — con số đó **đã `round(..., 6)`**. Mẫu số đã làm tròn chia cho tử số thô làm tổng lệch `100.000537`. Đổi sang cộng `cost_usd_raw` từ `breakdown_by_user` (chính là population total, chưa làm tròn) → khớp tuyệt đối. Xem design D1

## 2. Quota trong drill-down (backend, cần truy vấn mới)

- [x] 2.1 Đọc quota **theo lô**: một `SELECT user_id, quota, deleted_at FROM mw_users` cho toàn bộ danh sách drill-down, theo mẫu `adoption.py:_quota_histogram` (Phase 4)
- [x] 2.2 ⚠️ **TUYỆT ĐỐI KHÔNG** gọi `get_current_quota_user` (`core/alerting.py`) cho từng dòng — hàm đó **reset kỳ quota như side-effect**, nên một lần render trang sẽ sửa dữ liệu quota của tới 200 người. Ghi cảnh báo này thành comment ngay tại chỗ đọc quota (design D6)
- [x] 2.3 Tính phần trăm bằng **đúng công thức** `get_user_quota_status` đang dùng, để người sắp bị cảnh báo quota và người hiển thị gần 100% ở đây là cùng một người
- [x] 2.4 Ba trạng thái hiển thị, **không được gộp** (design D5):
  - không có bản ghi `mw_users` (định danh hệ thống, tài khoản đã xoá khỏi OW) → `None` + lý do
  - `deleted_at IS NOT NULL` → `None` + lý do "tài khoản đã xoá"
  - `limit_cost_usd <= 0` → cờ **"không giới hạn"** riêng, **KHÔNG** dùng `None` — tra được và câu trả lời là vô hạn
- [x] 2.5 `compute_group_users`: thêm `cost_share_of_group_percent` = chi phí thành viên / tổng chi phí nhóm đang mở (mẫu số là **nhóm**, không phải hệ thống). Tên field nói rõ mẫu số, không dùng lại tên của bảng nhóm (design D14). Guard chia cho 0
- [x] 2.6 **Nghiệm thu:** Σ `cost_share_of_group_percent` của các thành viên trong một nhóm = 100% · `admin` và `dinhthinhan18111971@gmail.com` (không có `mw_users`) ra trạng thái "không tra được" · nếu dev có user `limit <= 0` thì ra "không giới hạn"
  - ✅ Σ tỷ trọng trong phòng = **100,0 tuyệt đối** cho **mọi** nhóm có chi phí
  - ⚠️ **Sửa dự đoán:** `admin` ra `unlimited`, KHÔNG phải `no_account` — nó **có** tài khoản `mw_users` (nên có quota, `limit <= 0`) nhưng **không** có tài khoản Open WebUI (nên không có phòng ban). Hai hệ định danh khác nhau; `no_account` đúng cho `dinhthinhan18111971`, `pvt123`, `testuser`
  - ➕ **Phát hiện ngoài kế hoạch:** `get_current_quota_user` không chỉ có side-effect — nó còn **áp reset kỳ quota** trước khi trả số. Đọc thô `mw_users.quota` nên có thể ra số của **kỳ đã hết**. Đã xử lý read-only: so `quota.period_start` với `period_anchor_ms()`; kỳ đã hết thì `used` hiệu dụng = 0. Không ghi gì
  - ✅ **Chứng minh được logic này có chạy** (dev có 4 user kỳ đã hết, 2 trong đó đủ số liệu để phân biệt):

    | user | kỳ | `period_start` | % báo cáo | % nếu **thiếu** check |
    |---|---|---|---:|---:|
    | `donk@gmail.com` | weekly | 07/07 | **0.0** | 0.0201 |
    | `tranxuanbang@gmail.com` | monthly | 28/06 | **0.0** | 0.0314 |
    | `tranxuantuan1522005` | monthly | 01/07 *(còn hiệu lực)* | **0.6689** | 0.6689 |

    Thiếu check này thì bảng hiện phần trăm của **kỳ trước** như thể là kỳ hiện tại
- [x] 2.7 Kiểm **không có side-effect**: chụp `mw_users.quota` trước, gọi drill-down 3 lần, chụp lại — không bản ghi nào đổi. ✅ `no_side_effect: true` sau 4 lượt gọi toàn bộ 6 nhóm

## 3. Scorecard 3 thẻ (frontend)

- [x] 3.1 Chèn cụm 3 thẻ **lên đầu** tab Groups, nhãn theo design D12: **Số phòng ban** (`department_count`) · **Nhân sự đã có phòng ban** (`assigned_member_count / provisioned_user_count`, dạng `N / M` — design D13) · **Chi phí bình quân mỗi phòng ban** (`dept_cost_total / department_count`)
- [x] 3.2 Giữ nguyên section "🔧 Phân quyền Tool theo phòng ban" — không di chuyển, không đổi nội dung (Phase 0)
- [x] 3.3 Chú thích **bắt buộc** ngay dưới cụm thẻ: *"Hệ thống có N phòng ban. Ba số trên chỉ tính người đã được gán phòng ban — phần còn lại nằm ở dòng **Chưa quy được phòng ban** trong bảng dưới. ⓘ"*
- [x] 3.4 Tooltip ở ⓘ: *"Dòng đó gồm ba loại: nhân viên chưa được thêm vào phòng ban nào · tài khoản đã bị xóa khỏi Open WebUI (lịch sử chi phí vẫn được giữ) · định danh hệ thống không phải người dùng (ví dụ `admin`). Vì vậy tổng chi phí trong bảng sẽ lớn hơn N phòng ban cộng lại."*
- [x] 3.5 **Nghiệm thu chú thích, không chỉ nghiệm thu số.** Trên dev, dòng chưa quy được chiếm **48% tổng chi tiêu**: cộng cột chi phí trong bảng ra `0.0670` chia 5 = `0.0134`, trong khi thẻ hiện `0.006921` — **gấp đôi**. Chú thích là thứ duy nhất giải thích khoảng cách đó, nên nó phải có mặt mới coi là xong
- [x] 3.6 Kỳ vọng dev (cửa sổ trượt 30 ngày): *Số phòng ban* `5` · *Nhân sự đã có phòng ban* `5 / 12` · *Chi phí bình quân mỗi phòng ban* `$0.006921`

## 4. Cột mới trong bảng Groups (frontend)

- [x] 4.1 Thêm cột **"Nhân sự phòng"** (`primary_member_count`) — **KHÔNG** đặt tên "Thành viên". Section Tool Access cùng tab đã dùng chữ đó cho phép đếm khác (mọi membership). Dòng "chưa quy được" hiện `—` (design D8 + D12). ⚠️ 7a đề xuất *"Thuộc phòng này"*; D12 đổi vì đó là cụm tính từ, khó đọc với người chưa theo dõi Phase 7
- [x] 4.2 Thêm cột **"Tỷ trọng chi phí"**, **"Chi phí / nhân sự"** và **"Chi phí / người có dùng"** — tên dùng chung chữ *nhân sự* với cột 4.1 để người đọc thấy ngay cái nào chia cho cái nào. Tiền hiển thị qua `usd4()` export từ `metrics_registry.js`, **không** viết `toFixed(4)` thẳng
- [x] 4.3 ⚠️ Sửa `colspan` — **8 chỗ, không phải 10**:
  - **7 chỗ trong `dashboard/js/group_analytics.js`**: dòng `105`, `133`, `164`, `183`, `197`, `214`, `235` (tại thời điểm 7a archive)
  - **1 chỗ trong `dashboard/index.html`**: dòng `570`, thuộc `tbody id="groupAnalyticsTable"`
  - ⛔ **KHÔNG đụng** hai `colspan="7"` còn lại của `index.html` (dòng `797` `tbody id="syncTable"`, dòng `1129` `tbody id="logsResults"`) — chúng thuộc bảng khác, sửa vào là hỏng tab khác
- [x] 4.4 Chỉ tiêu không tính được hiện `—` **kèm tooltip lý do**, không hiện `0` (design D11). `—` trơ đọc ra như lỗi dữ liệu; `—` có lý do đọc ra như một câu trả lời
- [x] 4.5 Cột mới trong drill-down: **"Tỷ trọng trong phòng"** và **"Đã dùng hạn mức (kỳ này)"**; đổi nhãn cột chi phí sẵn có thành **"Chi tiêu (khoảng đang xem)"**. Hai cột cuối phải mang mốc thời gian trong nhãn vì chúng ở **hai trục thời gian khác nhau** (design D7 + D12)

## 5. Badge so kỳ KT/CK

- [x] 5.1 Khai báo **3 thẻ scorecard** trong `metrics_registry.js`. Cột bảng **KHÔNG** khai báo — spec `dashboard-model-metrics` đã chốt chỉ scorecard mới vào registry (design D9)
- [x] 5.2 Dựng cơ chế lấy **3 cửa sổ song song** (hiện tại · KT · CK) cho tab Groups
  - ⚠️ **Design D10 của tôi cũng nói quá.** Plan ghi "chỉ khai báo thêm một dòng registry" là sai (registry chỉ mô tả cách hiển thị), nhưng tôi lại viết "phải dựng cơ chế" — cũng không đúng: `compare_data.loadCompare()` **đã là helper dùng chung**, 4 tab đang gọi (`usage.js`, `overview.js`, `adoption.js`, `analytics.js`). Tab Groups chỉ **chưa gọi** nó. Việc thật: viết một hàm `_pickDeptAvg()` rút chỉ tiêu ra khỏi payload mỗi cửa sổ, rồi gọi `loadCompare` + `renderDelta`. Khoảng 20 dòng, không phải dựng hạ tầng
- [x] 5.3 Badge **chỉ** gắn cho *Chi phí bình quân mỗi phòng ban*. *Số phòng ban* và *Nhân sự đã có phòng ban* là snapshot cơ cấu tổ chức, không có trục thời gian → **chặn so kỳ**, giống các thẻ roster đã bị chặn ở Phase 4
- [x] 5.4 Nghiệm thu: đổi cửa sổ thì *Chi phí bình quân mỗi phòng ban* đổi và badge cập nhật; *Số phòng ban* **không** đổi
  - 🔴 **Lỗi tìm được khi test, đã sửa.** `_pickDeptAvg` trả `0` cho cửa sổ không có chi phí phòng ban nào, thay vì `null`. Docstring của `compare_data.loadCompare` yêu cầu `null` đúng cho ca này: *"SHOULD return null when the window holds no data at all — that is what makes the badge show '—' instead of a fake zero change"*. Trả `0` thì badge tính `0.006921` so với `0` — chia cho 0 khoác áo phần trăm
  - Cả **hai** cửa sổ quá khứ đều rỗng trên dev: KT `28/05→27/06` và CK `27/06/2025→27/07/2025`. Toàn bộ chi tiêu của phòng ban nằm trong 30 ngày gần nhất, nên không sửa thì badge sẽ hiện một mức tăng bịa ra thay vì `—` trung thực
  - Sau sửa: `current 0.006921` · KT `null` · CK `null` → badge hiện `—`

## 6. Nghiệm thu tổng thể

- [x] 6.1 Đối chiếu nhiều cửa sổ (1 giờ rỗng · 30 ngày · cố định 16/06-15/07 · toàn bộ): Σ `cost_share_of_system_percent` = 100% · `active <= total` trên mọi nhóm **có `group_id`** · không nhóm nào chia cho 0
  - ✅ Thêm 3 cửa sổ biên (rỗng 1 giờ · tương lai · 1 giây): không crash, 5 dòng phòng ban vẫn đủ, mọi tỷ trọng = 0, drill-down 0 người
  - 📝 **Một kỳ vọng test của tôi SAI, không phải code sai:** tôi assert `cost_per_member is None` cho mọi nhóm ở cửa sổ rỗng. Thực tế phòng ban có nhân sự trả `0.0` — và đó **đúng**: phòng có 1 người tiêu $0 thì chi phí/người thật sự là $0, khác hẳn chia cho 0. Chỉ `Marketing` (0 nhân sự) mới trả `None`. Giữ code, sửa kỳ vọng
- [x] 6.2 Drill-down: Σ share thành viên = 100% cho mọi nhóm có chi phí
- [x] 6.3 ⚠️ **Deploy đúng cách:** `docker compose build middleware && docker compose up -d middleware`. **`docker cp` KHÔNG phải deploy** — `llm-mw/Dockerfile:18` `COPY api/ ./api/` nướng code vào image, nên container tạo lại từ image là mất hết. Chỉ `dashboard/` bind-mount nên JS/HTML live ngay sau F5. Bài học từ 7a
- [x] 6.4 Nghiệm thu trên trình duyệt: 3 thẻ + chú thích + tooltip · cột "Nhân sự phòng" · share % cộng ra 100 · drill-down có quota với đủ 3 trạng thái · badge chỉ trên một thẻ
  - Đo 2026-07-28 trên Chrome, `http://localhost:5000/dashboard` (không qua nginx — nginx đang chết vì thiếu `fullchain.pem`, lỗi có sẵn). Cửa sổ `Last 30d`: thẻ `5` · `5 / 12` + "Còn 7 tài khoản chưa được gán phòng ban" · `$0.0069` = `0.03460576 / 5`. Bảng **10 header / 10 ô mỗi dòng**, share hiển thị cộng đúng `100.0`. Drill-down `colspan=10`, đủ **3** trạng thái hạn mức: `—` (`no_account`, có tooltip) · `Không giới hạn` (`unlimited`) · `0.0%`/số thật (`ok`). Badge KT/CK hiện `–` ở **cả** cửa sổ rỗng lẫn 30 ngày (hai kỳ quá khứ đều rỗng trên dev) — đúng, không bịa mức tăng. Không có lỗi console.
  - ⚠️ Trạng thái thứ tư `deleted` **chưa từng chạy**: `select … from mw_users` cho **0 dòng soft-deleted**. Ba tài khoản `dinhthinhan18111971` `pvt123` `testuser` rơi vào `no_account` vì **không có** dòng `mw_users`. Nhánh `deleted` mới chỉ được đọc bằng mắt.
  - Bảng rộng hơn khung **111px** ở 1187px; `.table-container` có `overflow-x: auto` nên cuộn ngang được và `body` không tràn. Đây là hệ quả của 4 cột mới — trả lại cột UUID sẽ làm nó tệ hơn đáng kể.
- [x] 6.5 Xác nhận **tab khác không đổi số**: ✅ `/summary` `189` / `0.067191` · `/adoption` `13/12 → 83.3%` · `/admin/analytics/chat` `200` · `/providers` `200` · Excel `200`, 29 554 bytes — tất cả giữ nguyên giá trị trước 7b

## 7. Đồng bộ tài liệu

- [x] 7.1 Cập nhật `docs/dashboard_metrics_implementation_plan.md` §7b — đánh dấu xong, ghi số nghiệm thu kèm cửa sổ **có mũi giờ**
  - Ghi cửa sổ là **trượt** (`minutes=43200`, đo `2026-07-28T08:19+07:00`) và nói rõ vì sao 27/07 ra `186` còn 28/07 ra `182` — bất biến mới là thứ nghiệm thu, không phải con số. Đồng thời tick dòng "Groups — TB chi phí/đơn vị" ở §Phase 2 và dòng nghiệm thu trình duyệt ở §7a.
  - Thêm **nợ kỹ thuật #4 và #5** (lỗi khôi phục phiên khi F5 · chỉ 3 module JS được cache-bust) — cả hai đều có sẵn, phát hiện khi nghiệm thu, ngoài phạm vi Phase 7.
- [x] 7.2 Sửa lại con số `colspan` trong plan: **8 chỗ (7 JS + 1 HTML)**, không phải 10. Ghi rõ hai `colspan="7"` còn lại của `index.html` thuộc bảng khác
  - Dòng này trong plan đã đúng sẵn; bổ sung thêm một bẫy nữa: `colspan="10"` ở `topModelsTable` **vốn đã là 10 từ trước**, không phải do đợt này — `git diff` xác nhận `index.html` chỉ đổi đúng một chỗ.
- [x] 7.3 `openspec validate dashboard-group-scale --strict` rồi `openspec archive`. ⚠️ Nếu archive báo lỗi giữa chừng, **kiểm `git status` trước khi chạy lại** — 7a gặp trường hợp công cụ in "Aborted. No files were changed" nhưng thực tế đã ghi một file
