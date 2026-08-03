## Why

Khảo sát toàn bộ cơ chế so kỳ KT/CK ngày **03/08/2026**, đo trực tiếp trên `llm-mw/dashboard/`, `llm-mw/api/` và DB Postgres đang chạy.

**Ba tầng dưới đã chuẩn, tầng thứ tư thì chưa.** Cơ chế so kỳ có bốn tầng, và chỉ một tầng bị phân mảnh:

| Tầng | Ở đâu | Trạng thái |
|:---|:---|:---|
| ① Chốt kỳ hiện tại | `index.html` + `filters.js` | ✅ một nguồn duy nhất |
| ② Tính KT/CK từ kỳ đó | `period_compare.js` | ✅ một nguồn duy nhất |
| ③ **Xét kỳ quá khứ có đủ bằng chứng không** | **`pick()` rải trong 7 file tab** | ❌ **mỗi tab một kiểu** |
| ④ Định dạng · màu · mũi tên | `metrics_registry.js` | ✅ một nguồn duy nhất |

Tầng ③ có hai mức. Sáu tab chỉ hỏi *"mẫu số > 0?"*. Riêng `raghealth.js` hỏi thêm *"mẫu số ≥ `minSample`?"* — và nó hỏi vì **đã gặp lỗi thật**, ghi lại nguyên văn ở `raghealth.js:195`:

> *"on the June window this badge read `+13.5 điểm %` against a May window holding 5 questions."*

Bài học đó nằm lại trong một đoạn chú thích, không thành quy tắc. Nên `overview.js` vẫn ở mức một.

**Mẫu mỏng là trạng thái VẬN HÀNH BÌNH THƯỜNG, không phải giai đoạn đầu.** Đây là lý do gate phải có, và nó không phụ thuộc vào việc hôm nay DB có bao nhiêu dòng.

Ba yếu tố cấu trúc, cái nào cũng còn nguyên khi hệ thống chạy đủ lâu:

| Yếu tố | Vì sao vĩnh viễn |
|:---|:---|
| **Đánh giá là tự nguyện** | Chỉ một phần nhỏ lượt chat được bấm 👍/👎. Đây là bản chất của cơ chế feedback, không phải thứ sẽ tự khỏi khi có nhiều người dùng — càng đông người thì **cả tử số lẫn mẫu số** cùng lớn lên, tỷ lệ bấm không đổi |
| **Cửa sổ mặc định là `Last 1h`** | `filters.js:8` — `{ minutes: 60 }`, và nút `Last 1h` mang `class="time-btn active"`. Đây là thứ admin nhìn thấy **mỗi lần mở dashboard**. Một giờ nội bộ hiếm khi gom nổi 20 lượt khen/chê |
| **Ngưỡng 20 là ngưỡng thống kê, không phải ngưỡng vận hành** | Nó đến từ khoảng Wilson 95%: dưới 20 mẫu, một tỷ lệ quan sát 80% vẫn có thể thật sự nằm bất kỳ đâu trong 38–96%. Traffic tăng không làm con số này giảm |

Kết hợp lại: trên khung mặc định và các khung ngắn, mẫu dưới 20 là **tình trạng thường xuyên trong production**. Gate không phải bản vá cho môi trường dev — nó là quy tắc cho trạng thái mà dashboard sẽ ở phần lớn thời gian.

Và đó cũng là lý do **không** nên chặn hẳn (`compare:false`): trên khung 30 ngày hoặc 90 ngày — đúng lúc một xu hướng CSAT mới có nghĩa — mẫu sẽ vượt 20 và badge xuất hiện. Gate làm badge **hiện đúng lúc nó đáng tin**.

**Hình dạng lỗi khi thiếu gate.** Bất cứ khi nào cửa sổ rơi vào vùng mẫu mỏng, thẻ tự mâu thuẫn:

```
┌──────────────────────────────────────────────┐
│ 😊 Mức hài lòng                              │
│ 100.0%                       ← XÁM, không tô │   overview.js:118 đã gate
│ 1 lượt khen/chê · chưa đủ 20 để đánh giá     │   việc TÔ MÀU bằng minSample
├──────────────────────────────────────────────┤
│ KT: ▲ +25.0 điểm %           ← XANH          │   nhưng BADGE thì chưa gate
└──────────────────────────────────────────────┘
```

Nửa dưới còn khẳng định **mạnh hơn** nửa trên: một con số đứng yên chỉ mô tả, còn mũi tên xanh là nhận định về **chiều hướng**. `_pickCsatTotals` chỉ hỏi `total > 0`, nên bất kỳ mẫu nào khác 0 đều lọt.

> **Kiểm chứng trên dev (03/08/2026), không phải căn cứ thiết kế:** bảng `feedback` có 5 dòng (29/06 → 07/07). Với `Last 30d`, kỳ hiện tại giữ 1 phiếu (100%) và KT giữ 4 phiếu (75%) → badge in đúng `▲ +25.0 điểm %` như hình trên. Dev data khớp với dự đoán của cấu trúc; nó không phải lý do để sửa.

**Rà toàn bộ 10 điểm đọc bảng Open WebUI — chỉ một chỗ hỏng.** Điều kiện để nguồn OW làm sai lệch một badge là hội đủ ba: đọc bảng OW **∩** có lọc thời gian **∩** có badge KT/CK.

| Nơi đọc | Bảng OW | Tab | Lọc t.gian | Badge | Kết luận |
|:---|:---|:---|:---:|:---:|:---|
| `analytics.py:113,127` | `chat` | Chat Analytics | ✅ | `compare:false` | ✅ đã xử lý đúng |
| `analytics.py:256,277,298` | `feedback` | Satisfaction · Overview | ✅ | **CÓ, không gate** | ❌ **chỗ duy nhất** |
| `group_analytics.py:50,57,68,80` | `"group"` · `group_member` · `"user"` | Groups | ❌ | gián tiếp | ⚠️ xem dưới |
| `knowledge_analytics.py:129-138` | `knowledge` · `file` · `document_chunk` | Knowledge | ❌ | ❌ | ✅ |
| `rag_health.py:411-431` | `document_chunk` · `knowledge` · `file` | RAG Health · Kho lưu trữ | ❌ | ❌ | ✅ |
| `tool_access.py:85,95,212,220,270` | `"group"` · `group_member` · `"user"` | Tool Access | ❌ | ❌ | ✅ |
| `user_admin.py:489,604` | `"user"` | Users | ❌ | ❌ | ✅ |
| `analytics.py:183` · `export_report.py:91` | `"user"` | tra tên | ❌ | ❌ | ✅ |
| `auth.py` · `identity.py` | `"user"` | định danh | ❌ | ❌ | ✅ |

Ba chỉ tiêu có badge của Chat Analytics (`requests_total` · `tokens_total` · `cost_total_usd`) lấy từ `mw_audit_log` qua `compute_usage_summary` (`analytics.py:154`), không đụng OW. Phân vùng đã chuẩn.

**Một chú thích sai trong code.** `compare_data.js:14` khẳng định:

> *"Comparison periods are **closed** periods: recomputing them every tick would re-fetch **a constant**"*

Đúng với `mw_request_log` — không có job dọn log, không có đường ghi nào từ phía người dùng. **Sai với `feedback`**: schema có `updated_at`, và **5/5 dòng có `updated_at > created_at`**, một dòng sửa sau **80.490 giây (22,4 giờ)**. Câu này không làm sai con số nào hôm nay, nhưng nó là tiền đề cho công việc sau — kéo dài cache, lưu sẵn giá trị KT — và những việc đó sẽ hỏng.

**Hai nợ nhỏ phát hiện kèm.**

- `index.html:566` đặt phần tử neo `<div class="delta-badge" id="grpAvgCostDelta">`. `renderDelta` giả định phần tử neo là **ô giá trị**, nên `card.querySelector('.delta-badge')` tìm ra chính cái neo và xoá nó. Lần render đầu vẽ đúng; từ lần thứ hai `getElementById` trả `null` và hàm thoát sớm — **badge của range cũ nằm lại dưới số của range mới**. `fetchData()` chạy mỗi lần mở tab Groups (`tabs.js:50`), nên lỗi này gặp thường xuyên.
- `failed_dashboard_logins` khai báo đầy đủ trong registry (`metrics_registry.js:239`, không `compare:false`), giá trị được vẽ ở `access.js:111`, nhưng `_renderCompare` (`access.js:59`) chỉ nối 5 thẻ và bỏ sót thẻ này. Một khai báo có chủ đích không có consumer.

## What Changes

**Quy tắc chốt — tầng ③ trở thành cấu trúc, không còn là việc mỗi tab phải nhớ.**

Việc kiểm tra `minSample` chuyển từ `pick()` của từng tab vào **`renderDelta`** (`metrics_registry.js`). Rà chữ ký thật của ba hàm cho thấy chỉ một chỗ đủ thông tin:

| Hàm | Chữ ký | Biết `metricKey`? | Thấy cả 3 kỳ? |
|:---|:---|:---:|:---:|
| `loadCompare` | `(path, pick, { extra })` | ❌ | ❌ |
| `side` | `(sideObj, metricKey)` | ✅ | ❌ mỗi lần một kỳ |
| **`renderDelta`** | `(id, metricKey, { current, kt, ck })` | ✅ | ✅ |

`loadCompare` **không nhận `metricKey`** nên không tra được `minSample`; `side` chỉ thấy một kỳ quá khứ nên không gate được kỳ hiện tại. `renderDelta` thấy đủ, đã sẵn đọc registry, và là nút cổ chai mà **mọi** badge đều đi qua. Tab thứ tám sau này không thể quên, vì nó không còn là việc tab phải làm.

**Quy tắc bằng chứng, áp cho mọi badge:**

> Một badge chỉ được hiện khi **cả kỳ hiện tại và kỳ so sánh** đều đạt `minSample` của chính chỉ tiêu đó. Chỉ tiêu không khai `minSample` thì ngưỡng là 0 — hành vi hiện tại không đổi.

Lý do gate **cả hai phía**: một kỳ quá mỏng để tô màu thì cũng quá mỏng để làm gốc so sánh. Đây là nguyên văn lập luận `raghealth.js:195` đã chốt, nay nâng thành quy tắc.

Hiện có 4 chỉ tiêu khai `minSample`, trong đó 2 đã có gate:

| Chỉ tiêu | `minSample` | Trạng thái hiện tại |
|:---|---:|:---|
| `citation_hit_rate` | 20 | ✅ đã gate (`raghealth.js:204`) |
| `kb_coverage_percent` | 20 | ✅ đã gate (`raghealth.js:207`) |
| `csat_percent` | 20 | ❌ **chưa gate** — thẻ Overview |
| `cost_anomaly_series` | 7 | không phải thẻ có badge |

**`clearDelta` thành mặc định.** Gate nghĩa là đôi khi *không* có badge. Badge là phần tử duy nhất trên thẻ sống sót qua một lần re-render, nên mọi đường thoát sớm đều phải xoá badge cũ trước — nếu không, đúng lúc gate chặn lại là lúc delta của range trước nằm lại dưới số của range mới.

**Sửa neo badge ở Groups.** `renderDelta` nhận id của `.metric-value`, không nhận id của một `.delta-badge` dựng sẵn.

**Nối `failed_dashboard_logins`**, hoặc ghi `blockedReason` nếu quyết định không so kỳ. Không để một khai báo lửng lơ.

**`dept_avg_cost` — công bố mẫu số không đổi theo kỳ.** `group_analytics.py:50` là `SELECT id, name FROM "group"`, không có `WHERE` thời gian, nên `department_count` giống hệt ở cả ba cửa sổ. Với delta kiểu `rel`, mẫu số hằng triệt tiêu hoàn toàn:

```
 (cost_KT / n) − (cost_now / n)      cost_KT − cost_now
 ─────────────────────────────  =  ────────────────────
        (cost_now / n)                    cost_now
```

Badge trên thẻ *"Chi phí bình quân mỗi phòng ban"* in ra **đúng bằng** phần trăm mà một badge trên tổng chi phí sẽ in. Không sai số học, nhưng nhãn hứa xu hướng *bình quân đầu phòng ban* và giao xu hướng *tổng chi phí*. Registry đã ghi `department_count` là `compare:false` vì *"không phụ thuộc khoảng thời gian đang xem"*; cùng con số đó đang làm mẫu số cho một thẻ **có** badge, và chỗ đó chưa ai ghi lại.

**Sửa chú thích sai** ở `compare_data.js:14` — nêu rõ giả định "kỳ đóng" đúng với `mw_request_log` và không đúng với `feedback`.

## Non-Goals

- **Không đặt `csat_percent` thành `compare:false`.** Đã cân nhắc và bác. `chats` bị chặn vì nó đo **việc đã xảy ra**, mà xoá một hội thoại không làm hội thoại đó chưa từng xảy ra — dữ liệu bị bào mòn một chiều. `csat_percent` đo **ý kiến**, mà ý kiến vốn là thứ của hiện tại: người dùng đổi 👍 thành 👎 thì CSAT kỳ đó tụt xuống là **phản ánh đúng**, còn đóng băng giá trị cũ mới sai vì nó tiếp tục đếm một lời khen đã bị rút. Ba cửa sổ đều đọc tại cùng một thời điểm nên nhất quán với nhau.
- **Không thêm cảnh báo trên UI về việc nguồn feedback sửa được.** Không con số nào trên dashboard là đóng băng; gắn cảnh báo riêng vào đây sẽ ngụ ý có gì đó hỏng trong khi không hỏng. Việc cần làm chỉ là sửa chú thích trong code cho người sửa code sau, không phải nói với người xem dashboard.
- **Không đổi định nghĩa cửa sổ KT/CK.** `period_compare.js` đúng và không đụng tới.
- **Không đổi `minSample` của chỉ tiêu nào.** Con số 20 (dựa trên khoảng Wilson 95%) giữ nguyên; change này chỉ làm nó được **thi hành** ở nơi đang thiếu.
- **Không thêm badge cho tab chưa có.** Providers · Knowledge · Satisfaction đứng ngoài phạm vi. Riêng thẻ *CSAT Score* ở Satisfaction thì **ghi lại lý do** không có badge (task 6.4) — vì `csat_percent` là chỉ tiêu so kỳ được và Overview có badge cho nó, nên sự vắng mặt ở đây phải đọc được là quyết định, không phải bỏ sót.
- **Không đụng backend.** Mọi thay đổi nằm ở `llm-mw/dashboard/`.

## Impact

- Specs: `dashboard-period-compare`
- Code: `compare_data.js` · `metrics_registry.js` · `overview.js` · `raghealth.js` · `group_analytics.js` · `access.js` · `index.html`
- Số trên màn hình: **không thẻ nào đổi giá trị**. Chỉ badge xuất hiện/biến mất.
- Thẻ *Mức hài lòng* (Overview) sẽ **không có badge trên các khung ngắn**, kể cả khi lên production — đây là hành vi đúng lâu dài, không phải trạng thái tạm của môi trường dev. Badge trở lại khi admin chọn khung đủ dài để gom trên 20 lượt khen/chê, tức đúng lúc một xu hướng CSAT bắt đầu có nghĩa.
- Thẻ *Đăng nhập dashboard thất bại* (Access) **thêm** badge — đây là thay đổi duy nhất theo chiều tăng.
