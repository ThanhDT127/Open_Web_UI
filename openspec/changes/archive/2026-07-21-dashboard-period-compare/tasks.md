## 1. Nguồn chân lý cho khoảng thời gian (refactor giữ nguyên hành vi)

> Bước rủi ro duy nhất của change — chạm 11 tab đang chạy tốt nhưng **chưa thêm tính năng nào**. Làm trọn và nghiệm thu xong mới sang nhóm 2, để nếu phải lùi thì revert riêng nhóm này.

- [x] 1.1 `filters.js`: `currentTimeRange` mang `start`/`end` **tuyệt đối**, resolve một lần mỗi chu kỳ refresh thay vì để mỗi caller tự lấy `Date.now()`; preset (`minutes`) quy đổi ngay tại chỗ resolve. Range vẫn phải cuộn theo thời gian thật giữa các chu kỳ.
- [x] 1.2 Viết `buildRangeParams(extra = {})` dùng chung, phát `start`/`end` tuyệt đối + gộp param riêng của từng tab (giữ đúng hành vi tham số phụ mà `raghealth.js`/`knowledge.js` đang có).
- [x] 1.3 Chuyển `raghealth.js`, `knowledge.js`, `export.js` sang `buildRangeParams()` — 3 file này vốn đã tự quy đổi sang tuyệt đối bằng 8 dòng giống hệt nhau nên rủi ro thấp nhất; xoá phần trùng lặp.
- [x] 1.4 Chuyển `usage.js`, `overview.js`.
- [x] 1.5 Chuyển `analytics.js`, `satisfaction.js`, `group_analytics.js`.
- [x] 1.6 Chuyển `access.js`, `logs.js`.
- [x] 1.7 Regression thủ công: mở lần lượt từng tab ở cả 5 preset lẫn một custom range, đối chiếu số hiển thị **không đổi** so với trước refactor.
  > **Tầng API** (chạy trong container `middleware`): 9/9 endpoint trả **cùng số** giữa dạng cũ `?minutes=60` và dạng mới `?start&end&minutes` — `summary`, `access_summary`, `analytics/chat`, `analytics/satisfaction`, `analytics/groups`, `rag-health/ingestion`, `rag-health/retrieval`, `knowledge-analytics/inventory`, `audit/query`. `access_summary` lệch 2 đơn vị là do nó **đếm chính request của mình**; kiểm lại với cửa sổ cố định thì ổn định (`156` = `156`), còn `minutes=60` thì tự tăng (`158`→`159`).
  > **Tầng UI** (Playwright trên `http://localhost:5000/dashboard`): 6 cấu hình khoảng (5 preset + 1 custom) × 12 tab = **72 lượt render, 0 lỗi mới**. Số lỗi console/page đứng yên ở đúng 1 trong suốt quá trình, và lỗi đó là **có sẵn**, không do change này — xem 7.5.
  > **Import graph**: kiểm tĩnh 143 named import trên 24 module → không có import gãy.
- [x] 1.8 Kiểm chéo cửa sổ dùng chung: mở tab Usage rồi chuyển sang Overview trong cùng một chu kỳ → hai tab phải gọi đúng cùng `start`/`end` (xem Network) và hiển thị cùng số ở chỉ tiêu trùng.
  > Đo trên Playwright: 149 request `/v1/_mw/*`, trong đó 93 mang `start`/`end`. Ở custom range, **15 request trải 10 endpoint khác nhau dùng đúng 1 cửa sổ duy nhất** (`summary`, `analytics/chat`, `analytics/satisfaction`, `analytics/groups`, `access_summary`, `audit/query`, `rag-health/{ingestion,retrieval}`, `knowledge-analytics/{inventory,kb-value}`). Trước refactor mỗi chỗ tự gọi `Date.now()` nên không có bảo đảm này.

## 2. Luật kỳ

- [x] 2.1 Tạo `dashboard/js/period_compare.js`; hàm tính kỳ trước: `[start − Δ, start)` với `Δ = end − start`, số học thuần, không làm tròn về biên lịch.
- [x] 2.2 Hàm tính cùng kỳ năm trước: trừ đúng 1 năm giữ nguyên tháng/ngày/giờ/phút; kẹp `29/02 → 28/02` khi năm đích không nhuận (**không** tràn sang `01/03`).
- [x] 2.3 Hàm phát hiện lệch độ dài giữa cửa sổ so sánh và cửa sổ hiện tại (phục vụ dấu ⚠️ ca năm nhuận).
- [x] 2.4 Test Playwright cho các ca biên, theo mẫu `tests/dashboard-tool-access.spec.ts`: custom range lẻ phút (`05/03 14:23 → 18/03 09:47` → KT `20/02 18:59 → 05/03 14:23`); biên rơi đúng `29/02/2028` → CK `28/02/2027`; range đè `29/02` → CK ngắn hơn 1 ngày và bị đánh dấu; **và ca lệch múi giờ**: mốc `29/02/2028 05:00` giờ VN (= `28/02` theo UTC) vẫn phải kẹp → CK `28/02/2027 05:00` giờ VN, không phải `01/03/2027`.
  > `tests/dashboard-period-compare.spec.ts` — **9 test, pass 9/9**. Hai việc phải làm để bộ test chạy lại được (cả 11 spec có sẵn cũng đang hỏng vì hai lý do này): (1) `npm install` trong `tests/` — `node_modules` chưa từng được cài; browser chromium thì đã có sẵn trong cache nên không phải tải. (2) `playwright.config.ts` chốt cứng `webServer.url` vào `localhost:3000`, khiến toàn bộ suite từ chối chạy khi nginx hỏng — kể cả test không mở trình duyệt; đã sửa cho nó bám `BASE_URL` như `use.baseURL` vẫn làm. Chạy: `BASE_URL=http://localhost:5000/dashboard npx playwright test`.

## 3. Registry, render và CSS

- [x] 3.1 Áp **giờ Việt Nam (UTC+7)** cho cả hai chỗ theo D9: chuỗi mốc in trong badge, và lịch dùng để đánh giá luật kẹp `29/02` ở 2.2. Không dùng `Date.UTC` (tiền lệ ở `overview.js:72` là khoản nợ, không phải mẫu để theo).
- [x] 3.2 Tạo `dashboard/js/metrics_registry.js`: khai báo cho các chỉ tiêu trong phạm vi change (6 thẻ Usage + thẻ Overview và Chat Analytics được wiring ở nhóm 5–6), mỗi mục gồm nhãn, formatter, kiểu delta, cực tính, cờ so sánh.
- [x] 3.3 Ba kiểu delta: tương đối (`%`), điểm phần trăm, tuyệt đối — mỗi chỉ tiêu tự khai, không suy từ kiểu dữ liệu.
- [x] 3.4 Cực tính màu: tăng-là-tốt / tăng-là-xấu / trung tính; màu lấy từ khai báo chứ không từ dấu của con số.
- [x] 3.5 Cờ chặn so sánh cho chỉ tiêu không thuộc phạm vi khoảng thời gian; **bắt buộc chặn `pending_open_count`** (nguồn `_get_global_pending_count()` không nhận tham số thời gian nên trả cùng giá trị ở cả 3 cửa sổ), cùng các thẻ inventory/cấu hình.
  > Chặn hiện có **5 mục**: `pending_open_count`, `usage_missing_calls`, `cost_mtd_usd`, `chats`, `active_users` — mỗi mục kèm `blockedReason` viết rõ lý do, để người sau đọc được vì sao chứ không tưởng là bỏ sót. Xem khảo sát nguồn ở đầu nhóm 6.
  > Cờ chặn có hiệu lực ở **cả `computeDelta()` lẫn `renderDelta()`**. Ban đầu chỉ chặn ở tầng render, nên gọi thẳng `computeDelta('chats', 24, 0)` vẫn ra `▲ +24` — đi vòng được cái chặn. Với loại lỗi "đúng số học nhưng sai bản chất" thì hàng rào không được phép có cửa sau.
- [x] 3.6 `renderDelta()` sinh markup badge: KT trước, CK sau; mỗi dòng gồm mũi tên, delta, **mốc thật của cửa sổ được so**, và giá trị tuyệt đối.
- [x] 3.7 Xử lý thiếu dữ liệu và mẫu số bằng 0: không có dữ liệu → `CK: —` kiểu mờ, không mũi tên không `%`; mẫu số `0` → in thay đổi tuyệt đối, **tuyệt đối không** in phần trăm.
- [x] 3.8 Dấu ⚠️ + tooltip giải thích khi hai cửa sổ lệch độ dài.
- [x] 3.9 Thêm CSS vào `dashboard.css`: `.delta-badge`, `.delta-line`, `.d-green`, `.d-red`, `.d-dim`, `.d-neutral`, `.delta-abs` theo snippet `docs/dashboard_frontend_harvest.md` §2E (đã xác minh các class này chưa tồn tại — không đụng class cũ).

## 4. Tầng tải dữ liệu so sánh

- [x] 4.1 Gọi song song 2 cửa sổ quá khứ (`Promise.all`) trên chính endpoint hiện có, dùng `start`/`end` tuyệt đối — không thêm param mới, không sửa backend.
  > `dashboard/js/compare_data.js`. Tách khỏi `period_compare.js` có chủ đích: file kia phải giữ thuần số học ngày tháng, không import gì, để chạy test được bằng Node trần. `loadCompare()` trả `{kt, ck}`, mỗi bên gồm `totals` + `window` + `lengthMismatch`. Fetch hỏng thì badge in `—` chứ không kéo sập thẻ.
- [x] 4.2 Cache theo khoá `(module, start, end)`; đổi global range thì invalidate và nạp lại một lần.
  > Khoá `${path}|${start}|${end}`, cache lưu **Promise** chứ không lưu kết quả nên hai thẻ gọi cùng lúc chỉ tốn một request. Invalidate qua sự kiện `range:changed` do `filters.js` phát — dùng sự kiện thay vì gọi trực tiếp để hai module không import vòng vào nhau.
- [x] 4.3 Xác minh poll định kỳ 15s (`main.js:139`) **không** phát thêm request so sánh nào: đổi range → đếm request; đợi qua vài chu kỳ poll → số request so sánh không tăng.
  > Đo bằng Playwright: đổi sang 30d → đúng **2** request so sánh; đợi 40s (~2 chu kỳ poll, tổng `/summary` tăng 3 → 6) → vẫn **2**. Cơ chế là ghim `anchorWindow`, chỉ làm mới khi đổi range, không làm mới theo tick.
- [x] 4.4 Đo payload thực tế của 2 request quá khứ, rồi **chốt quyết định** có cần `totals_only=1` hay không (câu treo #3 trong `design.md`). Nếu không cần thì ghi lại số đo để khỏi bàn lại.
  > **Chốt: KHÔNG cần.** `/v1/_mw/summary` trung bình **4.2 KB/request** → hai cửa sổ so sánh **~6.1 KB**, phát một lần mỗi lần đổi range. Thêm param backend để tiết kiệm 6 KB là không đáng. Đã ghi vào `design.md` § Open Questions.

## 5. Wiring tab Usage — điểm chốt hình dạng với leader

- [x] 5.1 Gắn badge cho 6 thẻ tab Usage: Requests, Cost, Tokens, P95, Error Rate, Billable.
  > `usage.js`: `_COMPARE_CARDS` liệt kê 7 mục — 6 thẻ trong phạm vi **cộng** `metricPending`, cố ý để lại nhằm chứng minh cờ chặn của registry thật sự chạy chứ không phải chỉ khai báo suông. `_renderCompare()` gọi kiểu fire-and-forget nên so sánh chậm không giữ chân số hiện tại.
- [x] 5.2 **Chốt quyết định + dựng fixture mock CK** (câu treo #1 trong `design.md`): dữ liệu năm trước hiện rỗng (`mw_audit_log` có dòng đầu tiên **04/05/2026**, đã đo trên DB 2026-07-20) nên CK sẽ là `—` cho tới ~05/2027; cần mock để trình được hình dạng đầy đủ. Quyết định nơi đặt và cách bật (cờ dev-only / file seed).
  > **Chốt cuối: KHÔNG mock gì cả — CK để `—` cho tới khi có dữ liệu thật (~05/2027).** Mã mock đã gỡ hết khỏi `compare_data.js` và `metrics_registry.js`.
  > Đường đi tới quyết định này đáng ghi lại, vì nó bác chính giả định của task: (1) bản đầu nhân tỉ lệ cả hai bên → bật cờ là KT `3.907` **thật** bị thay bằng `203` bịa, vứt đi đúng nửa badge đang nói thật và che mất cú sụt `−95%`; (2) sửa thành chỉ đắp CK khi CK rỗng, gắn nhãn `[MOCK]`; (3) rồi bỏ hẳn.
  > Lý do bỏ hẳn: **KT đã có dữ liệu thật**, nên badge vốn đã trình được đầy đủ hình dạng (mũi tên, màu theo cực tính, mốc cửa sổ, giá trị tuyệt đối, ba kiểu delta) mà không cần bịa dòng nào. Mock chỉ còn thêm được một dòng thứ hai — đổi lại là rủi ro một ảnh chụp màn hình bị đọc thành sự thật. Không đáng.
  > `CK: —` mờ **chính là hành vi đúng** đang được spec yêu cầu (3.7), không phải tính năng còn dở.
- [x] 5.3 Rà lại theo spec: đủ 6 badge, mốc in tường minh, màu đúng cực tính, thẻ bị chặn so sánh thì không có badge.
  > Nghiệm thu Playwright (spec tạm, đã xoá sau khi chạy): **6/6 thẻ** có badge 2 dòng đúng thứ tự KT → CK; `metricPending` **không** có badge. Mock 30d in ra `▼ −6.9% · KT: 21/05/2026 18:29 – 20/06/2026 18:29 (203)` và `▲ +18% · CK: 20/06/2025 – 20/07/2025 (160)`; Error Rate ra `−0.2 điểm %` đúng kiểu delta `pp`. Hai lỗi thật lộ ra và đã sửa: (1) `formatVnWindow` nuốt mất năm khiến cửa sổ CK 2025 đọc **y hệt** cửa sổ hiện tại — nay luôn in năm; (2) delta bằng 0 in ra một chữ `0` trơ trọi cạnh giá trị tuyệt đối, nay in `không đổi`. Console sạch (chỉ còn tiếng ồn SSE do chính test điều hướng làm đứt luồng).
- [ ] 5.4 Trình leader chốt hình dạng. ~~**Không làm nhóm 6 trước khi có phản hồi** — sửa 6 thẻ rẻ hơn sửa 30 thẻ.~~
  > **Chốt chặn đã bỏ 2026-07-20; việc trình leader thì CHƯA làm — đây là việc của người, không phải của code.**
  > Lý do bỏ chặn: lập luận "sửa 6 thẻ rẻ hơn sửa 30 thẻ" bị chính khảo sát ở nhóm 6 bác bỏ — nhóm 6 hoá ra chỉ có **6 badge** (3 Overview + 3 Chat Analytics), không phải 30. Và hình dạng nằm gọn trong `renderDelta()` + registry, nên leader đổi ý thì vẫn là sửa **một hàm**, không phải 12 chỗ gọi. Đúng thứ D4/D5 sinh ra để bảo đảm.
  > Khi trình: mở `localhost:5000/dashboard` → **Last 30d**, và nói rõ một câu — *số của cửa sổ KT là đợt tự test RAG trước khi Hung sửa, không phải sử dụng thật*. Không có nó thì `▼ −95%` đọc thành "người dùng bỏ hệ thống", trong khi người dùng thật đã **tăng từ 1 lên 13**.

## 6. Wiring Overview và Chat Analytics

> **Khảo sát nguồn dữ liệu đã làm trước, 2026-07-20 — đọc trước khi gắn badge.**
> Bài học: câu hỏi "chỉ tiêu này so kỳ được không" có **hai** vế, không phải một.
> (1) *Có nằm trong phạm vi khoảng thời gian không?* — `pending_open_count` gãy ở đây, câu SQL không có điều kiện thời gian.
> (2) *Nguồn có đủ lịch sử và có bất biến không?* — vế này ban đầu bỏ sót. `chats`/`active_users` gãy ở đây: câu SQL lọc thời gian hoàn toàn đúng, nhưng **dữ liệu không tồn tại**. Nguy hiểm hơn vế 1 vì vế 1 in ra `không đổi` mãi mãi (nhìn là biết vô lý) còn vế 2 in ra `▼ −100%` (trông y như một cú sụt thật).
>
> Số đo: `mw_audit_log` `04/05/2026 → 15/07/2026` (4.229 dòng, **bất biến**); bảng `chat` của Open WebUI `28/06/2026 → 15/07/2026` (24 dòng, **người dùng xoá được**). Cùng một response `/analytics/chat` mà hai nửa có lịch sử dài ngắn khác nhau.
>
> Đã đối chiếu số liệu lịch sử với người vận hành: `−95%` request và `−40 điểm %` lỗi ở cửa sổ KT là **thật và giải thích được** — một đợt tự test RAG của `admin` (2.920 request, 1.762 lỗi, dồn trong 7 ngày 01–07/06) trước khi Hung sửa xong. Badge dựng lại đúng câu chuyện đó từ ba con số độc lập, nên đây là **bằng chứng nghiệm thu**, không phải lỗi. Đã cân nhắc rồi **bỏ** ý tưởng "mốc dữ liệu tin cậy": đó là đặc thù dữ liệu dev, lên vận hành thật thì tự tan — dựng cơ chế rào là làm quá.

- [x] 6.1 Gắn badge cho các thẻ tab Overview thuộc phạm vi.
  > Nghiệm thu: 3/3 thẻ có badge 2 dòng; ⭐ Mức hài lòng ra `KT: −` **đúng** — cửa sổ KT có `total: 0` lượt đánh giá. Đây là ca chứng minh guard vế-2 hoạt động: `csat_percent` ở cửa sổ đó trả về `0`, nên nếu đọc thẳng thì badge sẽ in `▲ +80 điểm %`, một cú cải thiện hoàn toàn bịa. Guard `total > 0` chặn đúng chỗ.
  > 📊 Mức tập trung chi phí ra `▲ +8.3 điểm %` (52,9% → 61,2%), tô **đỏ** theo cực tính `down-good`.
  > 💸 Chi phí tháng này: **không** có badge ✔.
  > **Phạm vi thật là 3 thẻ, không phải 6.** Badge được: 🩺 Sức khỏe hệ thống (`error_rate_percent`, qua `getLastSummary()`), ⭐ Mức hài lòng (`csat_percent`), 📊 Mức tập trung chi phí (`top10_pct_cost_share`).
  > Không badge được: 💸 Chi phí tháng này — cố ý **bỏ qua range toàn cục**, tự tính từ mùng 1 (`overview.js:64`), nên anchor chung sẽ so nhầm hai khoảng khác nhau → đã khai `cost_mtd_usd` là `compare: false`. 📈 Tỷ lệ sử dụng và 👤 Chi phí/người dùng thật là **placeholder Phase 4**: `<div class="metric-value">—</div>` không có `id`, không có dữ liệu.
- [x] 6.2 Gắn badge cho tab Chat Analytics.
  > Nghiệm thu: 3/3 badge ra số; `analyticsTotalChats` và `analyticsActiveUsers` **không** có badge ✔ (vẫn liệt kê trong `_COMPARE_CARDS` để cái chặn được *thực thi* chứ không phải được *giả định*).
  > Endpoint này đặt tên khác `/summary` (`requests` vs `requests_total`…). Đã **chuẩn hoá trong hàm `pick`** thay vì khai chỉ tiêu hai lần trong registry — một chỉ tiêu phải có đúng một khai báo, nếu không hai tab hiển thị nó sẽ trôi khỏi nhau về định dạng hoặc màu, đúng thứ registry sinh ra để ngăn.
  > Chỉ 3 trong 5 chỉ tiêu badge được: `requests`, `tokens`, `cost_usd` (đều từ `mw_audit_log`). `chats` và `active_users` **đã khai `compare: false`** — nguồn cho phép xoá nên cửa sổ càng lùi xa càng bị xói mòn, có hệ thống, và lên vận hành thật thì **tệ hơn** chứ không đỡ hơn.
  > Ba chỉ tiêu badge được có giá trị **trùng khít** tab Usage (`189` / `360.907` / `$0,0672`) → 6.3 coi như đã có sẵn bằng chứng.
  > Nếu sau này muốn cứu `active_users`: `mw_audit_log` có `user_id`, nên `COUNT(DISTINCT)` cho ra một chỉ tiêu bất biến so kỳ được (13 / 1 / 0 trên ba cửa sổ). Nhưng đó là **định nghĩa khác** — mọi request, không chỉ người có tạo hội thoại — nên phải đổi nhãn chứ không thay ngầm.
- [x] 6.3 Kiểm chéo: chỉ tiêu xuất hiện ở nhiều tab phải trùng **cả giá trị lẫn badge** (checklist nghiệm thu v2).
  > Usage vs Chat Analytics trên cùng range 30d: `requests 189 = 189`, `tokens 360.907 = 360.907`, `cost $0,0672 = $0,0672`. Badge thì trùng **từng ký tự**: `▼ −95%KT: 21/05/2026 19:40 – 20/06/2026 19:40 (3,907)` ở cả hai tab — kể cả mốc tới từng phút. Đây là D7 (ghim `now` một lần mỗi chu kỳ) trả công: trước refactor mỗi chỗ tự gọi `Date.now()` nên hai tab load cách nhau vài giây là hai cửa sổ khác nhau.
  > Mở tab Overview chỉ phát sinh **1** request `/summary` — không thể là cặp so sánh (cặp thì phải là 2), nên đó là nhịp poll. Cache dùng chung giữa Usage và Overview hoạt động.
  > **Một bẫy đã bịt trước khi nó nổ:** cache khoá theo `path|start|end`, **không** gồm hàm `pick`. Overview và Usage cùng đọc `/summary` bằng hai `pick` khác nhau, nên nếu cache lưu *kết quả đã pick* thì module thứ hai sẽ lặng lẽ nhận bản trích của module thứ nhất. Đã đổi sang cache **JSON thô**, `pick` áp sau khi lấy khỏi cache.

## 7. Cập nhật tài liệu

- [x] 7.1 `docs/dashboard_metrics_implementation_plan.md` Phase 2: thay luật CK cũ (`1h→24h · 1d→7d · 7d→28d`), xoá luật ẩn *"chồng lấn KT > 80%"*, ghi rõ backend không đổi dòng nào; tick các mục đã lên production.
- [x] 7.2 `docs/dashboard_prototype_prompt_addendum_v2.md` quyết định #9: ghi chú luật kỳ đã bị thay và lý do (thuật ngữ "cùng kỳ" = năm trước), giữ nguyên phần hình dạng badge đã được duyệt.
- [x] 7.3 `docs/dashboard_frontend_harvest.md`: cập nhật §2E nếu CSS lúc triển khai lệch snippet, và bổ sung `buildRangeParams()` vào §3a như hàm dùng chung mới (theo ghi chú tự-kiểm §7 của chính file đó).
- [x] 7.5 ✅ **Bug có sẵn phát hiện khi nghiệm thu nhóm 1 — ĐÃ SỬA 2026-07-20, commit riêng ngoài change này.** Truy ra gốc không phải merge `2cb7510` mà là **hai đợt rebase 13/07 + 15/07**; frontend chưa từng bị rà vì script audit chỉ glob `**/*.py`. Đã xoá **165 dòng** trùng lặp ở `index.html` / `users.js` / `settings.js` (diff thuần `-`). Chi tiết đầy đủ ở `docs/bad-merge-2cb7510-corruption.md` §11. Liên quan tới change này: form API Budgets trước đó render 11 ô thay vì 5 — **Phase 6 đọc đúng form đó**, nên nếu không sửa sẽ vướng ở phase sau.
- [x] 7.4 Ghi lại 2 khoản nợ đã phát hiện nhưng cố ý không sửa: 5 resolver range phân kỳ ở backend (có 1 chỗ nuốt lỗi trong `analytics._time_boundaries`), và thẻ Cost MTD neo mùng 1 theo `Date.UTC` trong khi cảnh báo ngân sách neo `date_trunc('month')` ở Postgres chạy `TZ: Asia/Ho_Chi_Minh` (lệch 7 tiếng, Phase 6 sẽ đụng).
