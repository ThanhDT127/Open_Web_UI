# Kế hoạch Implement Chỉ tiêu Dashboard

**Nguồn:** `docs/dashboard_metrics_catalog_gdocs.md` (catalog đầy đủ, các mục `[+]`) + `docs/dashboard_prototype_prompt.md` + `docs/dashboard_prototype_prompt_addendum.md` (v1) + `docs/dashboard_prototype_prompt_addendum_v2.md` (v2, đã leader duyệt hình dạng qua prototype `docs/Total_users_model_etc.html`).

**Trước khi build UI cho bất kỳ phase nào:** xem `docs/dashboard_frontend_harvest.md` — đã đối chiếu CSS/JS của prototype (`index_exaple.html`) với code thật (`dashboard.css`, `charts.js`...), phân loại cái gì dùng lại được, cái gì cần snippet mới, cái gì KHÔNG được copy — tránh làm lại phần đã có sẵn.

**Nguyên tắc TÁI DÙNG (áp cho cả backend, không chỉ frontend):** trước khi viết query/aggregation mới, tra xem vòng lặp/dict/hàm nào đã gom sẵn dữ liệu đó rồi **mở rộng nó**, đừng nhân bản. Rất nhiều chỉ tiêu `[+]` thực chất chỉ là "index khác trên mảng đã sort" hoặc "chia hai con số đã query" — không phải logic mới. Pointer reuse cụ thể đã ghi trong từng phase bên dưới; nếu một phase không có pointer, vẫn nên `grep` hàm/dict liên quan trong `api/summary_v2.py`, `api/analytics.py`, `core/*.py` trước khi code.

**Cách dùng:** tick `[x]` khi chỉ tiêu đã lên production (không phải khi mock/prototype xong). Mỗi phase tương ứng 1 OpenSpec change (tên đề xuất trong ngoặc) — tạo change khi bắt đầu phase đó, không tạo trước.

**Thứ tự phase theo phụ thuộc kỹ thuật:** hạ tầng so sánh kỳ (Phase 2) là nền cho gần như mọi phase sau, nên đứng sớm dù không phải chỉ tiêu "nhìn thấy" đầu tiên.

---

## Phase 0 — Đối chiếu code thật (`llm-mw/dashboard/index.html`) trước khi implement

Đọc trực tiếp dashboard đang chạy production + prototype `index_exaple.html`, phát hiện vài lệch pha giữa catalog/prototype và code thật cần xử lý trước, không phải chỉ tiêu mới:

- [ ] ⚠️ **Tab `📚 Knowledge` bị catalog/prototype bỏ sót hoàn toàn.** Dashboard thật có tab riêng `knowledgeTab` (Inventory & Growth, KB Value Matrix — Star/Needs Tuning/Dead Knowledge/Unproven, Governance — Reclaimable/Duplicate Files/Owner Concentration) — không nằm trong bất kỳ mục nào của `dashboard_metrics_catalog_gdocs.md` §3.7, và **thanh tab trong `index_exaple.html` không có nút Knowledge** (chỉ còn Overview·Usage·Providers·Access·Users·Logs·RAG Health·Groups·Chat·Satisfaction·Prices·Settings — 12 tab, thiếu Knowledge). Khi implement Phase 1 (thêm Overview + Providers), **phải giữ nguyên tab Knowledge trong thanh tab thật** — đừng áp y nguyên danh sách 12 tab của prototype.
- [ ] Prototype dùng cấu trúc DOM/class khác code thật (`section.panel` + `data-tab` + `.tab-btn` của Open Design, thay vì `div.tab-content` + `button.tab` + `window.dashboardAPI.switchTab()` của dashboard thật). Khi implement, chuyển ý tưởng/label/ngưỡng màu từ prototype sang đúng pattern `.metric-card`/`.insight-banner`/`.tabs` hiện có trong `dashboard.css` — không copy nguyên khối HTML của prototype.
- [ ] Tab mới (Overview, Providers) cần theo đúng convention hiện có: id dạng `overviewTab`/`providersTab`, nút tab gọi `window.dashboardAPI.switchTab(event, 'overview')`, và một namespace JS riêng theo mẫu `window.groupAnalyticsAPI`/`window.ragHealthAPI`/`window.settingsAPI` đã dùng cho các tab khác (vd. `window.overviewAPI`, `window.providersAPI`).
- [x] Nhãn `📩 Total Requests` ở tab Chat Analytics — **ĐÃ SỬA 2026-07-20** (change `unify-audit-aggregation`), nhưng **theo hướng ngược với đề xuất ban đầu**.
  > **Đề xuất cũ (đã loại):** đổi nhãn thành *"✉️ Tổng số tin nhắn"* cho khớp giá trị.
  > **Đã làm:** giữ nhãn, **sửa giá trị cho khớp nhãn**. `total_reqs` nay lấy từ `mw_audit_log` (đếm `rid` duy nhất) thay vì `COUNT(id) FROM message` của Open WebUI.
  >
  > Điều tra khi implement cho thấy đề xuất cũ dựa trên chẩn đoán chưa tới nơi: bảng `message` của Open WebUI **rỗng hoàn toàn** (phiên bản này lưu tin nhắn trong JSON `chat.chat`), nên thẻ **luôn hiện `0`**, không phải "hiện số tin nhắn". Đổi nhãn sang "Tổng số tin nhắn" sẽ chỉ đặt tên đúng cho một con số vĩnh viễn bằng 0.
  >
  > 🚫 Nhãn hiện tại **đã đúng** (189 request thật, khớp tab Usage). Đừng đổi lại. Xem thêm mục "Bẫy trùng nhãn" ở Phase 11.
- [ ] Tab Groups thật có sẵn section "🔧 Phân quyền Tool theo phòng ban" (không phải metric, là cấu hình tool-per-group) — khi thêm scorecard/cột mới ở Phase 7, giữ nguyên section này, chỉ chèn thêm ở đầu tab.
- [ ] Tab Settings đã có sẵn form "💳 API Budgets" (`budgetOpenAI`, `budgetGemini`, `budgetXai`, `budgetAnthropic`, `budgetDeepseek`) — Phase 6 (Providers budget) đọc từ đây, không cần tạo thêm UI cấu hình ngân sách mới.

---

## Phase 1 — Overview tab shell & thẻ inventory (`dashboard-overview-cards`) — ✅ HOÀN THÀNH 2026-07-19

Dựng shell trước để leader thấy hình dạng thật sớm — nhưng **2/6 thẻ Overview không có số thật ngay**, vì phụ thuộc Phase 4 (chưa làm sớm hơn được: adoption rate cần logic đếm user hoạt động theo range, khác hẳn "Active Users (realtime)" SSE hiện có).

- [x] Tab `🎯 Overview` mới — giữ nguyên tab Knowledge khi chèn tab mới vào thanh tab (xem Phase 0). *Kết quả: 12 tab, có cả `overview` lẫn `knowledge`; theo đúng convention `overviewTab` / `switchTab(event,'overview')` / `window.overviewAPI`.*
- [x] 4 thẻ ra số thật ngay trong phase này: **Chi phí tháng này** (Cost MTD — tái dùng dữ liệu Usage) · **Mức hài lòng** (CSAT — tái dùng dữ liệu Satisfaction) · **Sức khỏe hệ thống** (error rate + P95 — tái dùng Usage; dòng uptime để trống/ẩn tới khi Phase 10 expose `/health`) · **Mức tập trung chi phí** (Pareto top 10% — độc lập với phase khác, nhưng **dùng chung 1 lần** với Pareto ở Phase 4: tính server-side trên toàn bộ user, xem cảnh báo `[:20]` ở Phase 4 — làm ở phase nào trước thì phase kia reuse, đừng viết 2 lần). *Kết quả: `top10_pct_cost_share` đã có trong `summary_v2.totals`, tính trên toàn population trước khi cắt `[:20]` — Phase 4 reuse thẳng, không viết lại.*
- [x] 2 thẻ tạm placeholder cho tới khi Phase 4 xong: **Tỷ lệ sử dụng** (adoption rate) · **Chi phí / người dùng thật** (cần "active users theo range", không phải realtime SSE). *Kết quả: `ovCardAdoption` / `ovCardCpu`, hiển thị `—` + hint "chờ Phase 4".*
- [x] Thẻ `Total Users` ở tab Users — đếm từ `mw_users` chưa xóa. *Kết quả: `metricTotalUsers`. Leader yêu cầu giữ thẻ này riêng dù trùng thông tin với badge.*
- [x] Badge tab Users. ⚠️ **Chốt khác plan:** plan viết `Đã dùng: 127 · Tổng: 186`, thực tế làm **`Đang bật: X · Tổng: Y`**. Lý do: `X` là số user **chưa bị disable**, KHÔNG phải "đã dùng" — gọi nó "Đã dùng" sẽ tái tạo đúng lỗi mislabel mà Phase 0 đang đi sửa. Con số "đã dùng" thật cần logic adoption của Phase 4.

**Hai mục đã chuyển sang phase khác** (không bỏ, chỉ đổi chỗ cho đúng phụ thuộc):

- ➡️ **Thẻ `Total Models`** → **Phase 6**, vì tab Providers chưa tồn tại trong dashboard thật.
- ➡️ **Đường tham chiếu trên DAU chart** → **Phase 4**, vì tab Users chưa có DAU chart nào để gắn, và chuỗi DAU thật cần field backend mới (đúng phần việc Phase 4).

## Phase 2 — Hạ tầng so sánh kỳ CK/KT (`dashboard-period-compare`)

Phạm vi đã phình theo quyết định leader (#9): áp cho mọi chỉ tiêu có trục thời gian, trên mọi tab — không chỉ Usage.

> **Cập nhật 2026-07-20 — kế hoạch backend bên dưới đã bị thay bằng phương án frontend. `llm-mw/api/` không đổi một dòng nào.**
>
> Mọi endpoint dashboard **vốn đã nhận `start`/`end` tuyệt đối** (6 module, 12 endpoint). Hỏi backend về một kỳ quá khứ chỉ là một request thường. Nên frontend tự tính 3 cửa sổ rồi gọi song song, thay vì thêm `compare=1` vào 6 module.
>
> Việc này làm **toàn bộ khối backend bên dưới biến mất**: không cần `_aggregate()` dùng chung, không cần lo backward-compat cho `export_report.py`, không cần hợp nhất 5 resolver range đang phân kỳ. Lưu ý "epoch giây vs datetime" ở gạch đầu dòng thứ 2 cũng tự hết vì mỗi endpoint vẫn tự parse `start`/`end` như nó vẫn làm. Đổi lại: 2 request song song và một ít payload thừa — đo thật là **~6,1 KB mỗi lần đổi range**, không đáng kể.
>
> Không khoá đường về: cùng ~20 dòng số học đó port sang Python bất cứ lúc nào, khi export cần CK/KT.

- [x] ~~Helper `_aggregate(start, end)` dùng chung~~ → thay bằng `dashboard/js/period_compare.js` (số học thuần, không import, unit-test bằng Node trần)
- [x] ~~Áp helper vào `summary_v2.py` / `analytics.py` / `group_analytics.py` / `access_logs.py`~~ → **không cần**, xem ghi chú trên
- [x] Nguồn chân lý cho khoảng thời gian ở frontend: `buildRangeParams()` trong `filters.js`, thay 11 chỗ tự dựng `URLSearchParams` mỗi chỗ tự gọi `Date.now()`
- [x] ~~Param `compare=1` + quy tắc cửa sổ CK (1h→lùi 24h · 1d→lùi 7d · 7d→lùi 28d · custom→chu kỳ lịch nhỏ nhất bao range)~~
  > **Luật cũ đã bị thay.** Nó không phủ được nút `6h`/`30d`, không có câu trả lời cho khoảng tuỳ ý, và **dùng sai thuật ngữ**: "cùng kỳ" trong nghiệp vụ Việt Nam mặc định là cùng kỳ *năm trước*, không phải một bước lùi ngắn. Luật mới gồm đúng hai dòng, phủ mọi trường hợp, không bảng tra:
  > - `KT = [start − Δ, start)` với `Δ = end − start`
  > - `CK = [start − 1 năm, end − 1 năm]`, kẹp `29/02 → 28/02` khi năm đích không nhuận
  >
  > Khớp Power BI `SAMEPERIODLASTYEAR`, GA4 "Same period last year", Adobe Analytics. Lịch đọc theo **giờ Việt Nam (UTC+7)** — chỉ ảnh hưởng luật kẹp, nhưng ở đó nó quyết định trọn 24 tiếng.
- [x] ~~Quy tắc ẩn CK linh hoạt (không có dữ liệu / chồng lấn KT >80% / chênh lệch không đáng kể)~~
  > **Đã xoá luật "chồng lấn KT > 80%"** — nó suy ra từ mô hình shift cũ vừa bị thay, nên không còn nền. Khảo sát GA4 và Adobe: **không công cụ nào chặn cửa sổ chồng lấn**. Thay bằng minh bạch: badge **luôn in mốc thật** của cửa sổ đang so. Chỉ giữ đúng một điều kiện ẩn: **không có dữ liệu → `CK: —`** mờ.
- [x] Component frontend `.delta-badge` — 2 dòng CK/KT, màu theo ngữ cảnh + biến thể `d-neutral`
- [x] Registry khai báo (`dashboard/js/metrics_registry.js`): nhãn, formatter, kiểu delta, cực tính, cờ chặn — **không có trong kế hoạch gốc**, thêm vào vì Phase 11 (Việt hoá nhãn) nhờ đó thành sửa một cột thay vì ~30 chỗ
- [x] Wire vào 6 thẻ tab Usage (Requests, Cost, Tokens, P95, Error Rate, Billable)

### Wiring theo tab (phụ thuộc chỉ tiêu gốc đã tồn tại — có thể làm dần, không chặn nhau)

- [x] Overview — **3 thẻ, không phải 6**: Sức khỏe hệ thống, Mức hài lòng, Mức tập trung chi phí. "Chi phí tháng này" cố ý bỏ qua range toàn cục (tự neo mùng 1) nên bị chặn so sánh; "Tỷ lệ sử dụng" và "Chi phí/người dùng thật" là placeholder Phase 4, chưa có dữ liệu
- [ ] Usage — Unit Economics (avg cost/request, cost/1k tokens, avg tokens/request) — phụ thuộc Phase 3
- [ ] Providers — thẻ "Đã tiêu" khớp Total Cost — phụ thuộc Phase 6
- [ ] Groups — TB chi phí/đơn vị — phụ thuộc Phase 7
- [x] Chat Analytics — **chỉ Requests / Tokens / Cost**. `Chats` và `Active users` **bị chặn so sánh vĩnh viễn**: nguồn là bảng `chat` của Open WebUI, mà **người dùng xoá được**, nên cửa sổ càng lùi xa càng bị xói mòn — so kỳ sẽ luôn nghiêng về "quá khứ thấp hơn hiện tại" một cách có hệ thống, và **lên vận hành thật thì tệ hơn** chứ không đỡ hơn. Muốn cứu `Active users` thì lấy `COUNT(DISTINCT user_id)` từ `mw_audit_log` (bất biến, đủ lịch sử) — nhưng đó là định nghĩa khác nên phải đổi nhãn, không thay ngầm
- [ ] Satisfaction (CSAT khớp Overview, Coverage) — phụ thuộc Phase 8
- [ ] Users — Adoption rate, Tài khoản ngủ (xanh khi giảm), Cấp mới trong kỳ (`d-neutral`)
- [ ] Access — Failed logins, 401/403 rate, Unique IPs (`d-neutral`) — phụ thuộc Phase 10
- [ ] Logs — Thao tác 7d (`d-neutral`), Nhạy cảm — phụ thuộc Phase 10
- [ ] RAG Health — Embedding calls, Citation hit-rate, % chat dùng KB — phụ thuộc Phase 9

---

## Phase 3 — Request/Call: các lăng kính còn thiếu (`dashboard-request-lens`)

Chủ yếu thêm field/tính toán vào `totals` của `compute_usage_summary` (`summary_v2.py`), không bảng mới, không param, không đổi shape. Chỉ tiêu dẫn xuất tính server-side để badge so kỳ Phase 2 tự chạy.

- [x] Throughput (RPM) & peak — `rpm_avg` + `rpm_peak` **cùng đơn vị req/phút** (peak = bucket bận nhất chuẩn hoá về phút) + `rpm_peak_bucket` báo độ phân giải
- [x] P50 / P99 / Max latency — hàm `_pct(p)` dùng lại `all_latencies` đã `.sort()` (chỗ tính P95), cùng guard `idx<n else [-1]`
- [x] Avg tokens/request & tỷ lệ in:out — thêm accumulator `total_tokens_in/out`; `avg_tokens_per_request` chia **`requests_ok`**
- [x] Avg cost/request, cost/1k tokens — `cost_per_request = total_cost/requests_ok` (mẫu số **request thành công**, vì tử số chỉ gồm request thành công); `cost_per_1k_tokens = total_cost/total_tokens×1000`
- [x] Pending: tổng đang kẹt (`pending_open_count`) + tuổi kẹt lâu nhất (`pending_oldest_age_sec` = `now − min(ts)`; `mw_pending.ts` là epoch giây) — snapshot toàn bảng nên **chặn so kỳ**
- [ ] ~~Admin Ops — đếm request `/admin/*`~~ → **non-goal.** `/admin/*` không nằm trong `mw_audit_log` (chỉ 5 handler AI gọi `init_audit_state`, có allowlist). Thuộc lăng kính Access/Ops (Phase 10), nguồn `mw_request_log` (`access_logs.py` đã aggregate sẵn)
- [ ] ~~Error breakdown theo `error_type`~~ → **non-goal.** Lỗi có 2 bản chất khác nguồn: *vận hành provider-side* (trong `mw_audit_log`, cùng tập Error Rate %) vs *chính sách* auth/quota/validation (bị chặn trước `init_audit_state` → thuộc `mw_request_log`/Access). Không trộn một thẻ. (Taxonomy `auth/quota/provider/system` trong ghi chú cũ **không khớp** giá trị thật trong DB: `upstream`/`connection`/`upstream_error`)

## Phase 4 — User/Account: mức độ áp dụng — ✅ HOÀN THÀNH 2026-07-23 (change `dashboard-adoption`)

Câu hỏi cốt lõi của hệ nội bộ ([[internal-rag-chatbot-adoption-not-growth]]) — ưu tiên cao theo catalog §5. Endpoint mới `GET /v1/_mw/adoption` (module `api/adoption.py`), reuse `compute_usage_summary`; frontend `dashboard/js/adoption.js` trên tab Users + gỡ 2 placeholder Overview. **Nghiệm thu live 2026-07-23:** adoption 83.3%, 2 tài khoản ngủ, histogram 11+1, Pareto 61.2% — mọi bất biến pass.

- [x] Nhân viên mới được cấp tài khoản / kỳ — `new_accounts_in_period`. **Không lọc `deleted_at`** (chống xói mòn kỳ quá khứ; xóa mềm giữ dòng nên đếm đủ). Nhãn "cấp mới", không phải "tuyển mới".
- [x] Tỷ lệ áp dụng: đã dùng / đã cấp — tử số = active-in-range **giao roster hiện tại** (KHÔNG lấy thẳng `len(breakdown_by_user)`: gồm cả user đã xóa còn hoạt động → sẽ vượt 100%; live thật 13/12=108% → giao kéo về 83.3%); mẫu số = `mw_users` chưa xóa.
- [x] Danh sách tài khoản "ngủ" (chưa từng dùng / ngừng > 30 ngày) — hiệu tập hợp `mw_users` ∩ `max(ts)/user`. **Nút nhắc đào tạo: NON-GOAL** (bảng read-only, để phase sau).
- [x] Chuỗi User hoạt động theo ngày/tuần (DAU/WAU). **Lệch plan (D2):** KHÔNG thêm set user/bucket vào `compute_usage_summary` — WAU cần nguồn theo *tập* ngày nên dùng query gom `(ngày,user)` riêng (ép `AT TIME ZONE 'Asia/Ho_Chi_Minh'`), giữ hàm gom dùng chung bất biến.
- [x] **Đường tham chiếu ngang trên DAU chart = tổng tài khoản đã cấp** *(chuyển từ Phase 1)* — plugin `afterDatasetsDraw` inline trong `adoption.js` (không cần thư viện annotation).
- [x] Pareto: top 10% user = ?% chi phí — đọc thẳng `top10_pct_cost_share` + `breakdown_by_user` full từ `compute_usage_summary`, **0 backend mới**.
- [x] Phân phối mức dùng quota (histogram 0-25/25-50/50-75/75-90/>90 + **bucket "không giới hạn"** riêng cho `limit ≤ 0`) — bulk-read `quota`, công thức như `get_user_quota_status`.

## Phase 5 — Model: tỷ trọng & đơn giá (change `dashboard-model-lens`)

- [x] **Cost share % + unique users theo model** — ✅ HOÀN THÀNH 2026-07-24 (change `dashboard-model-lens`). Thêm 2 field vào `breakdown_by_model` (`summary_v2.py`): `cost_share_percent` = `stats["cost_total"]/total_cost` (tính trên tổng global **trước** cắt `[:20]` → an toàn) + `unique_users` (thêm `set` vào `model_data`, `.add(user_id)` ở cả 2 nhánh ok+error). Render 2 cột vào bảng Top Models tab Usage. Nghiệm thu live: Σ share=100.1, embedding 80%CP/2 người vs deepseek-flash 17%/13 người.
  - **`$/request` per model đã có sẵn** từ trước (`usage.js`, `avgCost = cost_usd/requests_total`) — không làm lại.
  - **Non-goal:** `blended cost/1k tokens` (jargon trùng `$/req`); `request_share_percent` (fast-follow tùy chọn — đã có `$/req` cho tín hiệu đắt/rẻ); giữ bảng gọn.
- [ ] ❓ **Chờ leader quyết** — ghép CSAT với cost/request theo model (rủi ro: khớp sai tên model giữa 2 DB). **Non-goal của `dashboard-model-lens`** — tách quyết định riêng vì cần bảng ánh xạ tên model 2 DB (cùng loại lỗi định danh [[chat-analytics-id-mismatch]]).

## Phase 6 — Provider: ngân sách chủ động (change `dashboard-provider-budget`) — ✅ CODE XONG 2026-07-25, chờ deploy

**Đổi mô hình khi implement:** không phải "ngân sách tháng reset" mà là **credit trả trước** (admin nạp tiền vào billing account, chia cho user, cạn thì nạp thêm — không reset lịch). Gán chi phí theo **billing account** (nơi trả tiền thật) suy từ LiteLLM `/model/info`, không theo prefix brand.

- [x] **Attribution dùng chung** `core/provider_attribution.py` — map `alias→billing account` từ `/model/info` (litellm_config.yaml không mount cho MW); nhánh catch-all `other` → Σ luôn khớp total (test live: 0.4479=0.4479). Dùng chung dashboard + alert CHECK 2.
- [x] **Endpoint** `GET /v1/_mw/providers` — mỗi account: đã nạp / đã tiêu (từ nạp) / còn lại / **runway (dự kiến cạn)** thay cho "projected cuối tháng"; guard min-days + burn=0. Burn-rate chỉ tính ngầm, không hiện cột.
- [x] **Tab Providers** — scorecard 4 thẻ (Nhà cung cấp · Tổng còn lại · Tổng đã tiêu · **Total Models**) + bảng credit. Tab theo credit hiện tại, không theo bộ lọc thời gian.
- [x] **Total Models** — reuse chính call `/model/info` (24 model); LiteLLM không chứa `*-auto` (MW inject) nên **không trừ 5**, chỉ lọc phòng thủ.
- [x] **Settings** — 6 ô billing account, nút **Nạp thêm** (carry-forward `deposited=remaining+amount`, đóng dấu `funded_at`) vs **Sửa** (giữ `funded_at`, reuse `update_alert_config` deep-merge).
- [x] **Alert CHECK 2** đổi nghĩa "sắp cạn credit → nạp thêm", bỏ `date_trunc('month')`, dedup theo funding epoch. **CHECK 1 (quota-user) không đụng.**
- [x] Mock $800/$644 chỉ ở prototype, code thật (Overview thẻ #1) đã dùng số thật — no-op.
- [ ] **Chờ deploy:** rebuild container middleware để phục vụ route mới + nghiệm thu end-to-end trên trình duyệt.

## Phase 7 — Group/Phòng ban: chuẩn hóa theo quy mô

- [ ] Cost share % — phòng / tổng hệ thống
- [ ] Cost share % — thành viên / tổng phòng (trong drill-down)
- [ ] Cost / total_members
- [ ] Cost / active_members
- [ ] % hạn mức kỳ quota hiện tại trong drill-down thành viên — `get_group_users` (`group_analytics.py:116`) đã xác nhận chỉ query OW + `mw_audit_log`, chưa đụng `mw_users`. Cần thêm query sang `mw_users` (hoặc gọi `get_user_quota_status` — hàm nằm ở `core/alerting.py`, cũng được `api/quota_status.py` bọc lại thành endpoint). Dán nhãn rõ 2 cột: *Chi tiêu (khoảng đang xem)* vs *% hạn mức (kỳ quota hiện tại)*
- [ ] Tab Groups — scorecard 3 thẻ (Số đơn vị, Tổng thành viên, TB chi phí/đơn vị)

## Phase 8 — Feedback/Satisfaction

- [ ] Feedback coverage rate (% tin nhắn được đánh giá / tổng tin nhắn) — **Reuse:** mẫu số `total_messages` đã query trong `analytics.py` (`get_chat_analytics`, COUNT bảng `message`); tử số là feedback total đã có trong `get_satisfaction_analytics` (`totals.total`). Coverage chỉ là phép chia 2 con số đã tồn tại (2 hàm khác nhau — quyết định gộp hay gọi chéo)
- [ ] Xu hướng CSAT theo thời gian (line chart theo tuần)
- [ ] ❓ **Chờ leader quyết** ([[dashboard-scope-no-nlp-content-analysis]]) — Negative reason breakdown (`GROUP BY reason WHERE rating=-1`, enum có sẵn, không phải NLP) — giữ nguyên hiện trạng (chỉ feed thô) nếu leader từ chối. **Reuse nếu duyệt:** chỉ cần thêm `GROUP BY reason` ở backend — bảng dịch `reason`→tiếng Việt đã có sẵn ở `dashboard/js/satisfaction.js:115-121`, không phải làm lại phần nhãn frontend

## Phase 9 — RAG/Knowledge

- [ ] % chat dùng KB (coverage) — số cuộc chat có đính kèm tài liệu / tổng chat — **Reuse:** `core/rag_health.py:182 query_retrieval_health` đã phát hiện & đếm chat có `<source id>` tag (KB-attached) cho hit-rate; tử số dùng lại con số attached này, mẫu số (tổng chat) lấy từ `analytics.py`

## Phase 10 — Vận hành: System health, Cost anomaly, Access/security, Audit

- [ ] Expose `/health` (uptime, LiteLLM status, disk free) lên dashboard — đã xác nhận sẵn ở `api/health.py` (`uptime_seconds`, `status["litellm"]` = ok/degraded/error, `disk_free_gb`), đăng ký tại `main.py:176`; dòng uptime ở thẻ Overview #4 (Phase 1) chờ mục này để hết placeholder
- [ ] Expose P95 toàn hệ thống — đã tính sẵn trong access summary (`access_logs.py:185`, `p95_latency_ms`)
- [ ] Cost anomaly alert (>2× daily avg) — cảnh báo cấp dashboard-wide, khác ngưỡng ngân sách theo từng provider ở Phase 6. **Reuse:** `timeseries_data` (`summary_v2.py:184`) đã cộng `cost_total` theo bucket ngày/giờ → so từng ngày với trung bình chuỗi, không query lại
- [ ] Unique IP count (lưu ý: cần parse `X-Forwarded-For` nếu chạy sau reverse-proxy)
- [ ] Failed login count — reuse `by_status` (nt.): đếm request vào endpoint login trả 403
- [ ] 401/403 rate — **Reuse:** `access_logs.py:76` đã gom `by_status` (dict đếm theo status code) + `requests_total`. Rate = `(by_status[401]+by_status[403]) / requests_total` — không quét lại log
- [ ] Admin Audit Trail — dashboard gọi endpoint có sẵn (`user_admin.py:416` `get_admin_audit`, route `/v1/_mw/admin/audit`, đọc file `admin_audit.jsonl`, hiện trả `{audit_trail, total}` dạng list thô theo thời gian). Việc cần thêm: nhóm theo loại thao tác + đếm theo admin, highlight thao tác nhạy cảm (delete_user, rotate_key, sửa quota) — có thể làm ở frontend từ list thô, hoặc thêm aggregation ở endpoint

## Phase 11 — Việt hóa nhãn scorecard (cosmetic, provisional)

Quyết định #12 trong addendum v2 **chưa được anh Tuấn xác nhận cuối** — chỉ làm sau khi confirm, tách riêng khỏi các phase trên vì thuần đổi label, rủi ro thấp nhưng chạm nhiều file.

- [ ] ❓ **Chờ xác nhận cuối** — áp bảng mapping tên tiếng Việt (Total Requests → Tổng số requests AI, v.v.) lên mọi scorecard, giữ nguyên tên cột bảng/chart bằng tiếng Anh
- [ ] ~~⚠️ **Bẫy trùng nhãn**~~ — **BẪY NÀY KHÔNG CÒN.** Vẫn có 2 thẻ cùng ghi "Total Requests" (tab Usage + tab Chat Analytics), nhưng từ change `unify-audit-aggregation` (2026-07-20) **cả hai đo đúng cùng một thứ và ra cùng một số** (cùng đếm `rid` duy nhất từ `mw_audit_log`). Map **cả hai** về *Tổng số requests AI* là đúng.
  > 🚫 **ĐỪNG đổi thẻ Chat Analytics thành *"Tổng số tin nhắn"*** như bản plan cũ hướng dẫn. Hướng dẫn đó viết khi thẻ này còn đọc `COUNT(id) FROM message` của Open WebUI (bảng rỗng → luôn hiện `0`). Cách sửa đã chọn là **sửa giá trị cho khớp nhãn**, không phải đổi nhãn cho khớp giá trị sai. Đổi thành "Tổng số tin nhắn" bây giờ sẽ làm nhãn **sai trở lại** — con số đó là số request, không phải số tin nhắn.

---

## Theo dõi riêng — câu hỏi còn treo (không tự quyết khi implement)

- [ ] Negative reason breakdown — đưa vào catalog hay giữ nguyên hiện trạng? (Phase 8)
- [ ] CSAT ghép cost/request theo model — có nên thêm? (Phase 5)
- [ ] Mapping tên tiếng Việt — xác nhận cuối cùng? (Phase 11)
- [ ] Tab Knowledge (Inventory & Growth, KB Value Matrix, Governance) chưa từng nằm trong phạm vi catalog này — nếu leader muốn mở rộng chỉ tiêu cho tab này, cần một vòng catalog riêng (Phase 0 chỉ đảm bảo không làm mất tab, không mở rộng chỉ tiêu cho nó)

---

## Nợ kỹ thuật — phát hiện khi làm Phase 2, **cố ý không sửa**

Ba khoản dưới đây đều nằm ngoài phạm vi Phase 2 và đều đã được cân nhắc rồi quyết định để lại. Ghi ở đây để phase sau khỏi phải điều tra lại từ đầu.

**1. Năm resolver khoảng thời gian phân kỳ nhau ở backend.** `summary_v2._resolve_range` `raise 400` khi parse hỏng, còn `analytics._time_boundaries` **nuốt lặng lỗi rồi rơi về mặc định 30 ngày** — cùng một tham số sai cho ra hai hành vi khác hẳn. `access_logs` thì chứa một bản copy-paste của `_resolve_range`.
*Vì sao để lại:* Phase 2 khiến chúng **không còn chạy** — `buildRangeParams()` luôn phát `start`/`end` tuyệt đối nên mọi resolver đều đi nhánh "đã có mốc". Đó là hàng rào chính. Nhưng nếu về sau có caller nào bỏ `start`/`end` thì sự phân kỳ quay lại ngay, **âm thầm**: tab đó sẽ hiển thị 30 ngày trong khi tab khác báo lỗi.

**2. Thẻ Cost MTD định nghĩa "tháng này" lệch 7 tiếng so với cảnh báo ngân sách.** `overview.js` neo mùng 1 bằng `Date.UTC`, còn cảnh báo ngân sách neo `date_trunc('month', now())` ở Postgres chạy `TZ: Asia/Ho_Chi_Minh`.
*Vì sao để lại:* lỗi có sẵn, không do Phase 2. **Nhưng Phase 6 sẽ đặt hai con số đó cạnh nhau trên cùng màn hình**, và lúc ấy chúng sẽ lệch nhau vào 7 tiếng đầu mỗi tháng mà không ai biết vì sao. Sửa ở Phase 6, đừng để tới lúc có người báo bug.

**3. `leaderboard[].chat_count` luôn = 0 do lệch định danh.** `user_chat_counts` key theo `chat.user_id` = **UUID** của Open WebUI, còn vòng lặp tra bằng `mw_audit_log.user_id` = **email** → `.get()` không bao giờ khớp.
*Vì sao để lại:* cần JOIN bảng `user` của OW hoặc dùng `mw_users.openwebui_user_id`; là một change riêng. *(Bug anh em của nó — `totals.requests` đọc `COUNT(*) FROM message` trên bảng rỗng — thì **đã được sửa**, giờ lấy từ `mw_audit_log`.)*
