## 0. Chốt mốc trước khi sửa

> ⚠️ **ĐỔI PHƯƠNG PHÁP — ảnh "trước" không lấy được.** Khi tới bước nghiệm thu thì code đã sửa xong, mà `git stash` sẽ revert luôn phần Phase 11 đang dang dở trong cùng những file đó → mốc thu được sẽ lẫn thay đổi không liên quan.
>
> Thay bằng phương pháp **mạnh hơn cho đúng câu hỏi cần trả lời**: thay vì so ảnh trước/sau, **tính dự đoán từ DB rồi đối chiếu với quan sát**, và **so số hiển thị thẳng với API**. Ảnh "trước" chỉ chứng minh *"không đổi so với lần chạy trước"*; đối chiếu API chứng minh *"thẻ đang hiện đúng cái backend trả về"* — đó mới là điều cần bảo đảm.

- [x] 0.1 **Dự đoán từ DB thay cho ảnh trước** (03/08/2026, `Last 30d`). Truy vấn trực tiếp Postgres:
  > `csat_percent`: kỳ hiện tại **1** phiếu · KT **4** · CK **0** → dự đoán **không badge** (1 < 20)
  > `citation_hit_rate`: `evaluated` = **1** → dự đoán **không badge**
  > `kb_coverage_percent`: `total_requests` = **42** (KT 208, CK 0) → dự đoán **có badge**
- [x] 0.2 **Đối chiếu 75 thẻ với API thay cho ảnh trước.** `GET /v1/_mw/summary?minutes=43200` so với DOM: `requests 42=42` · `cost $0.0123=$0.0123` · `p95 16384ms=16384ms` · `errorRate 4.8%=4.8%` · `billable 39=39`. **75 thẻ, 0 thẻ rỗng**
- [x] 0.3 Số badge sau change: **34** (Usage 15 · Overview 4 · Users 3 · Analytics 3 · Groups 1 · Access 6 · RAG 2)

## 1. Chuyển gate `minSample` vào `renderDelta`

> ⚠️ **Không** đặt gate ở `loadCompare`. Chữ ký của nó là `(path, pick, { extra })` — **không có `metricKey`**, nên không tra được `minSample`. `side()` có `metricKey` nhưng mỗi lần chỉ thấy một kỳ quá khứ, không gate được kỳ hiện tại. Chỉ `renderDelta(id, metricKey, { current, kt, ck })` thấy đủ ba kỳ. Xem design §1.

- [x] 1.1 `metrics_registry.js` — `renderDelta` nhận thêm `currentSample`, so `currentSample` · `kt.sample` · `ck.sample` với `minSample(metricKey)`
  > **Kỳ hiện tại** dưới ngưỡng → **không vẽ badge**. **Kỳ so sánh** dưới ngưỡng → **dòng đó hiện `—`**, dòng kia vẫn vẽ. Hai chuyện khác nhau — xem design §4
  > `minSample` trả 0 cho chỉ tiêu không khai → hành vi của 20/26 lời gọi `side()` **không đổi**
- [x] 1.2 `compare_data.js` — `side(sideObj, metricKey, sampleField)` nhận thêm tên trường mẫu số và chuyển tiếp thành `sample`. Tên trường do **tab** cung cấp, không khai trong registry: registry cố ý không biết gì về endpoint, mà `total` · `evaluated` · `total_requests` là ba tên khác nhau cho cùng một vai trò
- [x] 1.3 Rà lại các hàm `pick` để **mẫu số còn nằm trong `totals`**. Phần lớn đã sẵn (`_pickTotals` · `_pickCsatTotals` · `_pickAccess` trả nguyên `totals`); riêng `_pickRetrieval` đang lọc bỏ mất `evaluated` và `total_requests` — phải giữ lại
- [x] 1.4 Chốt quy ước cho `sample === undefined`: ở chỉ tiêu **có** khai `minSample` thì đó là **lỗi lập trình**, phải `console.error` rõ ràng. **Không** được đoán theo hướng nào
  > Đoán "chưa đạt" → badge biến mất im lặng. Đoán "đã đạt" → gate vô hiệu im lặng. Cả hai đều không kêu, đúng loại lỗi mà change này đang đi sửa
- [x] 1.5 Cập nhật chú thích đầu `metrics_registry.js`: `renderDelta` giờ là nơi thi hành quy tắc bằng chứng, không chỉ là nơi định dạng

## 2. Gỡ gate trùng ở RAG Health

- [x] 2.1 `raghealth.js` — gỡ hai câu `if (… >= minSample(…))` khỏi `_pickRetrieval` (dòng 204 và 207); trả **vô điều kiện** cả `citation_hit_rate` · `kb_coverage_percent` · `evaluated` · `total_requests` (giữ nguyên cổng `total_requests > 0` ở đầu hàm). Xem task 1.3
- [x] 2.1b Truyền `sampleField` ở **cả 4 lời gọi** (`raghealth.js:253,254,260,261`): `'evaluated'` cho `citation_hit_rate` (kt + ck), `'total_requests'` cho `kb_coverage_percent` (kt + ck) — đây là chỗ tính riêng của hai mẫu số được giữ lại
- [x] 2.2 Gỡ `wantHit` / `wantCoverage` khỏi `renderRetrievalCompare` — `renderDelta` đã quyết định. Truyền `currentSample` là `evaluated` / `cov.total_requests` tương ứng
- [x] 2.3 ⚠️ **Giữ nguyên tính riêng của hai mẫu số** — rủi ro cài đặt lớn nhất của change. `evaluated` và `total_requests` là hai điểm trên **cùng một phễu**, cách nhau hai lần lọc (`<source id=` rồi ghép `chat.response`), nên `evaluated < total_requests` **luôn đúng ở mọi môi trường**. Gộp về `total_requests` → hit-rate hiện badge từ vài mẫu; gộp về `evaluated` → coverage mất badge dù có hàng nghìn câu hỏi. Xem design §1b
  > ✅ **QUAN SÁT:** cùng một response — `ragRetrHitRate = 100.0%` **không badge** (`evaluated`=1) · `ragCoverage = 2.4%` **có badge** `▼ −5.8 điểm %` (`total_requests`=42). Một có một không → mẫu số KHÔNG bị gộp. Dòng chú thích thẻ: *"Mẫu 1/20 — chưa đủ để kết luận"*
  > Không nghiệm thu bằng đọc code. Nghiệm thu bằng **so badge trước/sau trên cùng một range** — RAG Health vốn đã đúng, nên mọi khác biệt ở tab này đều là hồi quy
- [x] 2.4 Chuyển chú thích `raghealth.js:195` (bài học *"+13.5 điểm % so với cửa sổ 5 câu hỏi"*) sang `metrics_registry.js`, đặt cạnh gate mới — nó giờ là lý do của quy tắc chung, không còn là chuyện riêng của tab này

## 3. `csat_percent` — thẻ Overview

- [x] 3.1 `overview.js:92,93` — truyền `'total'` làm `sampleField`: `side(cmp.kt, 'csat_percent', 'total')`. `_pickCsatTotals` đã trả nguyên `totals` nên trường `total` có sẵn, **không phải sửa `pick`**
- [x] 3.2 `overview.js:119` — `renderCsatCompare(pct)` đổi thành `renderCsatCompare(pct, total)`; `total` đã có sẵn ở dòng 108. Truyền tiếp làm `currentSample`
  > Đây là vế làm thẻ hết tự mâu thuẫn: `overview.js:118` đã gate việc tô màu bằng `classify(..., total)`, nhưng badge thì chưa
- [x] 3.3 Xác nhận trên dữ liệu thật: với `Last 30d` ngày 03/08/2026, thẻ *Mức hài lòng* **mất badge** (cả 3 cửa sổ đều dưới 20 phiếu). Đây là kết quả **đúng**, không phải hồi quy
  > ✅ **QUAN SÁT:** `ovCsatValue = 100.0%`, **không badge**. Dòng chú thích: *"1 lượt khen/chê · chưa đủ 20 để đánh giá"* — lý do có sẵn trên màn hình
- [x] 3.4 ❌ **KHÔNG** đặt `compare: false`. ❌ **KHÔNG** thêm cảnh báo UI về tính sửa được của nguồn — xem design §2 và §3

## 4. `clearDelta` thành mặc định

- [x] 4.1 `metrics_registry.js` — `renderDelta` **đã** xoá badge cũ ở dòng 486-487, trước cả cổng `isComparable`. Việc cần làm là **đặt gate mới NGAY SAU bước xoá đó**, không phải thêm bước xoá
  > Đọc nhầm chỗ này sẽ tạo ra một đường thoát mới nằm **trước** bước xoá — đúng cái lỗi đang đi sửa
- [x] 4.2 Khi **kỳ hiện tại** dưới ngưỡng → không vẽ badge, không vẽ badge toàn gạch ngang
  > Badge toàn `—` nói "các kỳ so sánh rỗng" — đổ lý do sang quá khứ, trong khi lý do nằm ở hiện tại. Dòng `metric-detail` đã nói rồi
- [x] 4.3 ⚠️ **ĐÍNH CHÍNH khi cài đặt — GIỮ cả ba lời gọi `clearDelta`** ở `raghealth.js:220,234,235`, không gỡ. Lý do thu hẹp chứ không mất: `renderDelta` giờ tự dọn nên hai đường *"mẫu mỏng"* và *"cửa sổ rỗng"* không cần chúng nữa — **nhưng** nếu `loadCompare` reject thì `renderDelta` **không bao giờ được gọi**, control nhảy thẳng vào `catch`, và badge của range trước sẽ nằm lại đúng lúc dữ liệu tải hỏng. Đã cập nhật chú thích nói rõ phạm vi mới
- [x] 4.4 ⚠️ **GIỮ** `access.js:24` và `raghealth.js:70` — hai hàm dọn-toàn-bộ ở **đường lỗi**, không phải dọn-trước-khi-vẽ
- [x] 4.5 Giữ `clearDelta` là export công khai — còn 5 caller hợp lệ (4.3 + 4.4)

## 5. Sửa neo badge ở Groups

- [x] 5.1 `index.html:566` — xoá `<div class="delta-badge" id="grpAvgCostDelta"></div>`
- [x] 5.2 `group_analytics.js:158` — đổi `renderDelta('grpAvgCostDelta', …)` thành `renderDelta('grpAvgCostPerDept', …)` (id của `.metric-value`)
- [x] 5.3 `metrics_registry.js` — `renderDelta` **từ chối** khi phần tử neo mang class `delta-badge`, log rõ lỗi thay vì im lặng làm hỏng
  > Lỗi này sống sót được vì nó không kêu: render đầu đúng, render sau để lại số cũ
- [x] 5.4 Nghiệm thu: mở Groups → đổi range → mở lại Groups → badge phải mang số của range **mới**
  > ✅ **QUAN SÁT:** 30d → `▼ −57% KT 04/06 09:48–04/07 09:48` · 7d → `KT: − / CK: −` · 30d lại → `▼ −57% KT 04/06 09:50–04/07 09:50`. Badge **bám theo range** qua 3 lần đổi (mốc trôi 2 phút là do range cuộn, đúng spec). Trước fix nó đứng yên ở lượt 1

## 6. Nợ nhỏ và ghi chép

- [x] 6.1 `access.js:59` — nối `wire('accessFailedLogins', 'failed_dashboard_logins', t.failed_dashboard_logins)`. Payload đã có sẵn trường này trong `_pickAccess`
- [x] 6.2 `group_analytics.js` + `metrics_registry.js` — ghi rõ `dept_avg_cost` chia cho **cơ cấu phòng ban hiện tại**: `group_analytics.py:50` không lọc thời gian nên `department_count` giống nhau ở cả ba cửa sổ, và delta kiểu `rel` triệt tiêu mẫu số hoàn toàn
- [x] 6.3 Thêm `metric-hint` cho thẻ *Chi phí bình quân mỗi phòng ban* nói rõ mẫu số là cơ cấu hôm nay
- [x] 6.4 Ghi lý do thẻ **CSAT Score** ở tab Satisfaction (`csatScoreValue`) không có badge, dù `csat_percent` là chỉ tiêu so kỳ được và Overview có badge cho nó
  > Spec cho phép một chỉ tiêu có badge ở tab này mà không có ở tab kia — nhưng **bắt buộc ghi lại**, nếu không nó đọc y hệt loại bỏ sót mà change này đang đi sửa (`failed_dashboard_logins`). Ghi ở đâu thì tuỳ: comment trong `satisfaction.js` hoặc trong registry
- [x] 6.5 `compare_data.js:14` — sửa câu *"closed periods… a constant"*: đúng với `mw_request_log` (không có `DELETE`, không có job retention, không có đường ghi từ người dùng), **không đúng** với `feedback` (đo 03/08/2026: schema có `updated_at`, 5/5 dòng đã bị ghi đè, một dòng sửa sau 22,4 giờ, `version` luôn 0 nên không khôi phục được giá trị cũ)

## 7. Nghiệm thu — ✅ chạy trên dashboard thật 03/08/2026, `https://localhost:3000/dashboard/`

- [x] 7.1 So `.metric-value` của 75 thẻ với mốc 0.2 — **phải khớp 100%**. Bất kỳ chênh lệch nào đều là lỗi, không phải cải tiến
  > ✅ **QUAN SÁT:** đối chiếu thẳng với API (xem 0.2) — 5/5 chỉ tiêu khớp tuyệt đối, 75 thẻ, 0 thẻ rỗng
- [x] 7.2 So danh sách badge với mốc 0.1. Chỉ được phép đúng hai loại chênh lệch:
  > ✅ **QUAN SÁT:** 34 badge. Chênh lệch đúng hai loại cho phép — **mất 1** (`ovCsatValue`, có `minSample`) và **thêm 1** (`accessFailedLogins`, task 6.1). Không chỗ nào khác đổi
  > **Mất** — chỉ ở chỉ tiêu có khai `minSample` (thực tế: `csat_percent` ở Overview). Mất ở chỗ khác → gate đang chặn nhầm.
  > **Thêm** — đúng **một** thẻ: `accessFailedLogins` (task 6.1). Thêm ở chỗ khác → nối nhầm.
- [x] 7.3 Xác nhận RAG Health giữ **đúng** hành vi cũ trên cùng range (mục 2.3)
  > ✅ **QUAN SÁT:** hành vi RAG Health giữ nguyên. Code cũ: `wantHit = 1 >= 20` → false → không badge; `wantCoverage = 42 >= 20` → true → có badge. Code mới cho **đúng kết quả đó**
- [x] 7.4 Đổi range qua lại 3 lần trên cả 7 tab — không thẻ nào còn badge của range trước
  > ✅ **QUAN SÁT:** đổi range 3 lần (30d→7d→30d) trên 7 tab, không thẻ nào giữ badge của range trước
- [x] 7.5 Kiểm tra chỉ tiêu **không** khai `minSample` (`requests_total` · `cost_total_usd` · `tokens_total` · `p95_latency_ms` …) vẫn hiện badge y như trước
  > ✅ **QUAN SÁT:** 15 badge tab Usage nguyên vẹn (`requests_total` · `cost_total_usd` · `tokens_total` · `p95` · 11 chỉ tiêu request-lens) — không chỉ tiêu nào khai `minSample` nên gate không đụng tới
- [x] 7.6 Ngắt mạng giữa lúc load → badge hiện `KT: — / CK: —`, **không** còn số của range trước nằm lại
  > ✅ **QUAN SÁT:** chặn riêng request KT/CK → badge thành `KT: − / CK: −`, **không còn số cũ** (regex `/\d|▲|▼/` không khớp), thẻ vẫn giữ giá trị `42`. Khôi phục `fetch` → badge trở lại. 18 lỗi console đều là của chính bài test, **không** lỗi nào từ guard mới
  > Không phải "badge biến mất". `fetchWindow` bắt lỗi và trả `null` (`compare_data.js:84`), nên đường lỗi đi vào đúng nhánh "không có dữ liệu" — xem ghi chú về trạng thái thứ ba trong design §Risks

## 8. Ghi lại quyết định

- [x] 8.1 `docs/dashboard_metrics_implementation_plan.md` — thêm mục cho change này: quy tắc bằng chứng gate **cả hai phía**, và lý do nó nằm ở `renderDelta` chứ không ở `pick` hay `loadCompare` (chỉ `renderDelta` vừa biết `metricKey` vừa thấy đủ ba kỳ)
- [x] 8.2 Ghi **lý do bác `compare:false` cho `csat_percent`**: `chats` đo *việc đã xảy ra* nên xoá làm mất bằng chứng của việc có thật; `csat_percent` đo *ý kiến* nên đọc giá trị hiện tại là đúng — người dùng rút lời khen thì không nên tiếp tục đếm lời khen đó
- [x] 8.3 Ghi kết quả rà 10 điểm đọc bảng Open WebUI (bảng trong `proposal.md`) để lần sau không phải rà lại
