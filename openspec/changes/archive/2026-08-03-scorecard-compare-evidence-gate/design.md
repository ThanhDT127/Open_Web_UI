## Context

Mọi con số dưới đây đo trực tiếp ngày **03/08/2026**, trên mã nguồn và trên DB Postgres đang chạy (`openwebui-postgres`, truy vấn chỉ đọc).

```
period_compare.js      101 dòng   ← định nghĩa KT/CK, 1 nguồn, 0 nơi trùng lặp
compare_data.js        126 dòng   ← fetch + cache, 1 nguồn
metrics_registry.js    495 dòng   ← format/màu/delta, 1 nguồn
pick() trong tab           7 bản  ← KHÔNG có nguồn chung
```

Bảy tab gọi `loadCompare`; cả bảy dùng chung đúng một định nghĩa cửa sổ. Cái phân mảnh là hàm `pick` — thứ quyết định **kỳ quá khứ có được phép lên màn hình hay không**.

### Vì sao `pick` tồn tại

Backend không phân biệt được *"bằng không"* với *"không có"*. `summary_v2.py:437`:

```python
error_rate = (error_count / requests_total * 100) if requests_total > 0 else 0.0
```

Vế `else 0.0` có mặt vì không chia được cho 0. Con `0.0` đó **không phải kết quả của phép chia nào** — nó là giá trị lấp chỗ. Ra khỏi API, nó giống hệt một `0.0` đo được thật.

`pick` kiểm tra **đúng cái điều kiện backend dùng để quyết định có bịa số hay không**. Backend nói *"khi điều kiện này sai, tôi đang bịa"*; frontend nói *"khi điều kiện này sai, tôi không dùng"*. Nó kiểm tra **mẫu số**, vì mẫu số quyết định tử số có nghĩa hay không.

Đối chiếu hai backend:

| | `summary_v2.py:437` | `rag_health.py:346` |
|:---|:---|:---|
| Khi mẫu số = 0 | `else 0.0` | `else None` |
| Ý nghĩa | bịa ra một số | thừa nhận không có số |

`rag_health.py:343` ghi lý do: *"None, not 0.0: with no answer to read there is no rate, and 0.0 is a verdict."*

### Vì sao mức một không đủ

`mẫu số > 0` chặn được `0/0`. Nó **không** chặn được `2/3`.

| Nếu KT là… | `csat_percent` |
|:---|---:|
| 2 khen / 1 chê | 66.7% |
| 3 khen / 0 chê | 100.0% |
| 1 khen / 2 chê | 33.3% |

Ba kết quả trải từ 33% tới 100% chỉ vì một người bấm khác đi. Con `66.7%` không sai số học — nó **không mang thông tin**. Đem làm gốc so sánh thì `+13.3 điểm %` cũng không mang thông tin, chỉ khác là nó đang đội mũ phần trăm nên trông như một kết luận.

### Mẫu mỏng là trạng thái vận hành, không phải giai đoạn đầu

Lập luận trên phải đứng vững **độc lập với lượng dữ liệu hiện có**, nếu không nó chỉ là cái cớ cho một môi trường dev còn trống.

Ba yếu tố dưới đây đều còn nguyên khi hệ thống chạy đủ lâu và đủ đông:

- **Đánh giá là tự nguyện.** Chỉ một phần nhỏ lượt chat được bấm 👍/👎. Đông người dùng hơn làm **cả tử số lẫn mẫu số** cùng lớn lên; tỷ lệ bấm không đổi. Đây không phải thứ tự khỏi theo thời gian.
- **Khung mặc định là `Last 1h`** (`filters.js:8`, nút mang `class="time-btn active"`). Đây là thứ admin thấy mỗi lần mở dashboard, và một giờ nội bộ hiếm khi gom nổi 20 lượt khen/chê.
- **Ngưỡng 20 là ngưỡng thống kê.** Nó đến từ khoảng Wilson 95%, không từ quy mô hệ thống: dưới 20 mẫu, tỷ lệ quan sát 80% vẫn có thể thật sự nằm trong 38–96%. Traffic tăng không kéo con số này xuống.

Hệ quả thiết kế: gate sẽ **thường xuyên chặn** trên các khung ngắn, ở production, lâu dài. Đó là ý định, không phải tác dụng phụ. Và nó cũng là lý do §2 không chọn `compare:false` — trên khung 30/90 ngày, đúng lúc xu hướng CSAT bắt đầu có nghĩa, mẫu vượt ngưỡng và badge trở lại.

> Số đo trên dev (03/08/2026: `feedback` có 5 dòng) **khớp** với dự đoán này nhưng không phải căn cứ của nó. Dev data dùng để kiểm chứng, không dùng để thiết kế.

## Goals / Non-Goals

**Goals**

- Không badge nào đưa ra nhận định mà con số nền không đỡ nổi.
- Quy tắc bằng chứng thành **cấu trúc**, không phải việc mỗi tab phải nhớ.
- Không con số nào trên màn hình đổi giá trị.

**Non-Goals**

- Đổi định nghĩa KT/CK.
- Đổi ngưỡng `minSample` của bất kỳ chỉ tiêu nào.
- Đặt `csat_percent` thành `compare:false` — xem §2.
- Cảnh báo trên UI về tính sửa được của nguồn feedback — xem §3.
- Thêm badge cho tab chưa có (Providers · Knowledge · Satisfaction).

## Decisions

### 1. Gate nằm ở `renderDelta`, không nằm ở `pick`

Đặt gate trong `pick` của từng tab là cách `raghealth.js` đang làm, và nó **đúng nhưng không nhân bản được**. Bằng chứng: nó đã đúng ở đó từ Phase 9, và `overview.js` vẫn sai cho tới hôm nay — vì không có gì bắt tab mới phải làm theo.

**Chỗ đặt gate phải là nơi biết `metricKey`.** Rà lại chữ ký thật của ba hàm:

| Hàm | Chữ ký | Có `metricKey`? | Có mẫu kỳ hiện tại? |
|:---|:---|:---:|:---:|
| `loadCompare` | `(path, pick, { extra })` | ❌ **không** | ❌ |
| `side` | `(sideObj, metricKey)` | ✅ | ❌ chỉ biết một kỳ quá khứ |
| `renderDelta` | `(id, metricKey, { current, kt, ck })` | ✅ | ✅ nhận cả `current` |

`loadCompare` **không hề nhận `metricKey`** — nó chỉ biết endpoint và hàm `pick`. Nó không thể tra `minSample`. `side` biết `metricKey` nhưng mỗi lần chỉ thấy **một** kỳ quá khứ, nên không gate được kỳ hiện tại.

Chỉ `renderDelta` thấy đủ ba kỳ cùng lúc và đã sẵn đọc registry. Nó cũng là **nút cổ chai chặt hơn**: mọi badge đều đi qua nó, kể cả badge được dựng bằng con đường không dùng `loadCompare`.

```
TRƯỚC                                    SAU
─────                                    ───
pick   → totals | null                   pick   → totals | null    (trách nhiệm cũ, giữ nguyên)
side   → { value, window, mismatch }     side   → { value, sample, window, mismatch }
renderDelta → vẽ                         renderDelta → GATE rồi mới vẽ

7 file, mỗi file tự nhớ                  1 file, tab không cần biết
```

Ba thay đổi tối thiểu:

1. `pick` phải để **mẫu số** lại trong `totals` (phần lớn đã sẵn — chỉ `_pickRetrieval` đang lọc bỏ mất).
2. `side(sideObj, metricKey, sampleField)` nhận thêm tên trường mẫu số và **chuyển tiếp** nó thành `sample`. Tên trường do tab cung cấp vì chỉ tab mới biết payload của mình gọi nó là gì — `total` · `evaluated` · `total_requests` là ba tên khác nhau cho cùng một vai trò.
3. `renderDelta(id, key, { current, currentSample, kt, ck })` so `currentSample`, `kt.sample`, `ck.sample` với `minSample(key)`.

`pick` giữ nguyên trách nhiệm cũ — *"cửa sổ này có dữ liệu không"*. Gate trả lời câu khác — *"dữ liệu có đủ dày cho chỉ tiêu NÀY không"*. Hai câu hỏi, hai chỗ, không chồng lấn.

**Vì sao mẫu số không khai được trong registry:** tên trường phụ thuộc endpoint, mà registry cố ý không biết gì về endpoint. Khai `sampleField: 'total'` cho `csat_percent` sẽ đúng ở `/satisfaction` và sai ở bất kỳ endpoint nào khác cùng phục vụ chỉ tiêu đó.

**Hệ quả với `raghealth.js`:** gate hiện có ở `_pickRetrieval` trở thành thừa. Gỡ nó ra để không còn hai chỗ cùng quyết định một việc — đó chính là loại trùng lặp mà registry sinh ra để chặn.

### 1b. Vì sao hai mẫu số của RAG Health **không được gộp**

Đây là rủi ro cài đặt lớn nhất của change, nên lý do phải là **cấu trúc**, không phải quan sát trên một bộ dữ liệu.

`evaluated` và `total_requests` không phải hai phép đếm ngang hàng — chúng là hai điểm trên **cùng một cái phễu**, cách nhau hai lần lọc:

```
total_requests   mọi câu hỏi trong kỳ                    ← mẫu số của Coverage
   └── lọc 1: body chứa <source id=>
       attached
          └── lọc 2: ghép được chat.response cùng rid
              evaluated                                   ← mẫu số của Hit-rate

evaluated  =  total_requests × tỷ_lệ_đính_kèm × tỷ_lệ_ghép_được
                               └──── đều < 1 trong mọi môi trường ────┘
```

**Tỷ lệ đính kèm < 1 theo thiết kế.** Chatbot phục vụ cả hỏi đáp thường lẫn tra cứu tài liệu. Tỷ lệ này bằng 1 nghĩa là không ai hỏi chuyện thường — không xảy ra.

**Tỷ lệ ghép được < 1 vì ba nguyên nhân vĩnh viễn:**

| Nguyên nhân | Vì sao không bao giờ hết |
|:---|:---|
| **Hiệu ứng biên cửa sổ** | `resp` CTE cũng lọc `ts >= start AND ts <= end` (`rag_health.py:268`). Câu hỏi cuối kỳ, trả lời sang kỳ sau → không ghép được, **mãi mãi**, đúng theo thiết kế. Kỳ nào cũng có biên; kỳ càng ngắn tỷ lệ bị cắt càng cao |
| **Request lỗi giữa chừng** | Timeout · provider 5xx · người dùng bấm dừng → có `chat.request`, không bao giờ có `chat.response` |
| **Deploy / restart** | Câu hỏi bay đúng lúc middleware khởi động lại |

**Dải bất đồng, tính bằng số học.** Đặt `r = tỷ_lệ_đính_kèm × tỷ_lệ_ghép_được`:

```
   total_requests ≥ 20      →  Coverage  hiện badge
   total_requests × r < 20  →  Hit-rate  bị chặn

   ⟹  bất đồng khi   20 ≤ total_requests < 20/r
```

| `r` | Dải bất đồng |
|---:|:---|
| 0,50 | 20 → 40 câu hỏi |
| 0,20 | 20 → 100 câu hỏi |
| 0,10 | 20 → 200 câu hỏi |

`r` càng thực tế (càng nhỏ) thì dải càng rộng. Với khung mặc định `Last 1h`, một hệ thống 500 câu hỏi/ngày cho khoảng 40 câu hỏi mỗi giờ — **rơi thẳng vào giữa dải**. Hai chỉ tiêu bất đồng là trạng thái **bình thường**, không phải ngoại lệ.

**Thêm một nguồn phân kỳ chỉ tab này có:** filter model/user cục bộ (`raghealth.js:271-274`) chia `total_requests` theo thị phần model trong *tổng* câu hỏi, còn `evaluated` theo thị phần trong câu hỏi *có tài liệu*. Hai thị phần không bằng nhau — model mạnh thường được chọn cho tra cứu, model nhanh cho hỏi đáp thường.

**Và hai tỷ lệ di chuyển vì hai lý do độc lập:** tỷ lệ đính kèm đổi theo *nghiệp vụ* (publish kho mới, đào tạo người dùng); tỷ lệ ghép được đổi theo *hạ tầng* (deploy, timeout, provider chập chờn). Chúng không có lý do gì để đi cùng nhau — đó chính là nghĩa của *"the two thin out independently"* trong `raghealth.js:198`.

Gộp một mẫu số chung là khẳng định hai điểm trên phễu bằng nhau, điều mà chính công thức trong `rag_health.py` phủ định. Hỏng theo cả hai chiều:

| Gộp về | Hậu quả thường trực |
|:---|:---|
| `total_requests` | Hit-rate hiện badge từ vài câu trả lời, **mỗi khi** admin ở khung ngắn — tức gần như mọi lúc |
| `evaluated` | Coverage mất badge **kể cả trên khung 30 ngày với hàng nghìn câu hỏi** |

> Kiểm chứng trên dev (03/08/2026): `total_requests = 362`, `evaluated = 1` trên toàn bộ lịch sử — chiều lệch đúng bằng chiều mà cấu trúc bắt buộc, độ lớn thì cực đoan vì lý do riêng của môi trường dev (42/42 câu hỏi có tài liệu trước 01/07 không ghép được câu trả lời). Dùng để kiểm chứng, không dùng làm căn cứ.

### 2. `csat_percent` được gate, **không** bị chặn

Đã cân nhắc `compare:false` theo tiền lệ `chats`, và bác. Hai chỉ tiêu đo hai loại sự vật:

| | `chats` | `csat_percent` |
|:---|:---|:---|
| Đo | **việc đã xảy ra** | **ý kiến** |
| Người dùng xoá nghĩa là | dọn lịch sử — việc **vẫn đã xảy ra** | rút lại đánh giá — **thật sự không còn ý kiến** |
| Đọc giá trị hiện tại | **sai** — mất bằng chứng của việc có thật | **đúng** — ý kiến vốn thuộc về hiện tại |
| Xu hướng khi bào mòn | lệch một chiều: quá khứ luôn thấp hơn | không lệch chiều nào |

Người dùng đổi 👍 thành 👎 thì CSAT kỳ đó tụt — và đó là phản ánh đúng, vì họ thật sự không hài lòng nữa. Giữ giá trị cũ mới sai: nó tiếp tục đếm một lời khen đã bị rút. KT, CK và kỳ hiện tại đều đọc tại cùng một thời điểm nên **nhất quán với nhau**.

Vấn đề của `csat_percent` chỉ là **mẫu mỏng**, và gate `minSample` giải quyết đúng và đủ.

### 3. Tính sửa được: sửa chú thích trong code, không cảnh báo trên UI

Đã xác minh trên DB:

```
 tong_dong | da_bi_sua | id_duy_nhat |        som_nhat        |        moi_nhat
-----------+-----------+-------------+------------------------+------------------------
         5 |         5 |           5 | 2026-06-29 11:01:13+07 | 2026-07-07 16:18:12+07
```

5/5 dòng có `updated_at > created_at`; số dòng bằng số `id` duy nhất → **ghi đè tại chỗ, không ghi dòng mới**. Chênh lệch: bốn dòng 13–47 giây (bấm 👍 → hộp thoại ghi `reason`/`tags` đè lên), một dòng **80.490 giây ≈ 22,4 giờ** — người dùng quay lại hôm sau. `version = 0` ở cả 5 dòng và không có bảng lịch sử → giá trị cũ **không khôi phục được**.

Điều này **không** làm sai con số nào (xem §2), nên không có gì để nói với người xem dashboard. Nhưng nó phủ định một câu đang nằm trong code (`compare_data.js:14`):

> *"Comparison periods are closed periods… would re-fetch **a constant**"*

Câu đó đúng với `mw_request_log` — đã rà: không có `DELETE FROM mw_request_log`, không có job retention, không có đường ghi nào từ phía người dùng. Nó **sai** với `feedback`. Người sửa code sau sẽ đọc nó và xây tiếp lên đó. Sửa chú thích, không đụng UI.

### 4. `clearDelta` chạy trước mọi đường thoát

Badge là phần tử duy nhất trên thẻ **sống sót qua một lần re-render** — mọi thứ khác bị ghi đè bằng `textContent`. Nên mỗi đường thoát sớm đều là một chỗ rò:

```
gate chặn vì mẫu mỏng     ─┐
pick trả null cả hai kỳ   ─┼─▶ renderDelta CÓ chạy  ─▶ tự dọn ở đầu hàm        ✅
                           │
loadCompare reject         ─┴─▶ renderDelta KHÔNG chạy ─▶ cần clearDelta ngoài  ⚠️
```

> ⚠️ **Đính chính khi cài đặt.** Bản đầu kết luận `clearDelta` ở `raghealth.js` thành thừa hoàn toàn và cho gỡ. Sai: `renderDelta` chỉ dọn được những đường **đi qua nó**. Khi `loadCompare` reject, control nhảy thẳng vào `catch` và `renderDelta` không bao giờ chạy — badge của range trước nằm lại đúng lúc dữ liệu tải hỏng. Ba lời gọi đó được **giữ**, chỉ thu hẹp lý do trong chú thích.

Và gate phải phân biệt **kỳ hiện tại mỏng** với **kỳ so sánh mỏng** — hai chuyện khác nhau:

| Kỳ nào mỏng | Hiển thị | Nghĩa |
|:---|:---|:---|
| **Hiện tại** | **không có badge** | "thẻ này chưa đủ căn cứ để so bất cứ gì" |
| **So sánh** (KT hoặc CK) | dòng đó hiện `—` | "gốc so sánh này không dùng được" |

Vẽ một badge toàn gạch ngang khi kỳ hiện tại mỏng sẽ đổ lý do sang quá khứ, trong khi lý do nằm ở hiện tại — và dòng `metric-detail` của thẻ đã nói rồi (*"chưa đủ 20 để đánh giá"*).

Ở **mức từng dòng** thì "rỗng" và "quá mỏng" cố ý trùng nhau: cả hai đều là gốc so sánh không dùng được, nên cùng hiện `—`.

> ⚠️ Đây là điểm sửa sau khi bắt đầu cài đặt. Bản spec đầu tiên viết *"thiếu ở kỳ nào cũng mất cả badge"*, và như thế sẽ **đổi hành vi RAG Health** — trái task 2.3. Hiện `_pickRetrieval` bỏ chỉ tiêu khỏi `out` của kỳ mỏng, `side()` trả `undefined`, dòng đó hiện `—` còn dòng kia vẫn vẽ. Quy tắc mới giữ đúng hành vi đó, chỉ chuyển chỗ thi hành.

### 5. Neo badge là `.metric-value`, không phải một `.delta-badge` dựng sẵn

`renderDelta` tìm thẻ bằng `anchor.closest('.metric-card')` rồi dọn badge cũ bằng `card.querySelector('.delta-badge')`. Khi phần tử neo **chính nó** mang class `delta-badge` (`index.html:566`), câu `querySelector` tìm ra chính cái neo và xoá nó:

```
render #1   anchor bị xoá → badge mới (không id) được gắn        ✓ đúng
render #2   getElementById('grpAvgCostDelta') === null → return
            badge của #1 nằm lại nguyên vẹn                      ✗ SỐ CŨ
```

Sáu tab kia truyền id của `.metric-value` nên không dính. Sửa bằng cách bỏ phần tử neo dựng sẵn và truyền `grpAvgCostPerDept`.

**Ràng buộc kèm theo:** `renderDelta` phải từ chối một `valueElementId` trỏ vào phần tử mang class `delta-badge`, thay vì im lặng làm hỏng. Lỗi này tồn tại được vì nó không kêu.

### 6. `dept_avg_cost` — công bố mẫu số hằng, không đổi công thức

`group_analytics.py:50` (`SELECT id, name FROM "group"`, không `WHERE`) khiến `department_count` giống nhau ở cả ba cửa sổ. Delta kiểu `rel` do đó triệt tiêu mẫu số:

```
 (cost_KT / n) − (cost_now / n)      cost_KT − cost_now
 ─────────────────────────────  =  ────────────────────
        (cost_now / n)                    cost_now
```

Ba hướng đã cân nhắc:

| Hướng | Đánh giá |
|:---|:---|
| Lấy `department_count` theo lịch sử | Bảng `"group"` không lưu lịch sử. Không làm được mà không đổi schema OW. |
| Đặt `compare:false` | Mất một tín hiệu chi phí có thật, chỉ vì mẫu số không đổi. Quá tay. |
| **Giữ badge, ghi rõ mẫu số là cơ cấu hiện tại** | **Chọn.** Số đúng, chỉ cần người đọc biết nó chuẩn hoá theo cơ cấu **hôm nay**. |

Ghi vào `blockedReason`-style comment trong registry và vào `metric-hint` của thẻ. Không đổi công thức.

### 7. `failed_dashboard_logins` — nối, không phải gỡ khai báo

Registry khai `fmt` · `delta: 'abs'` · `polarity: 'down-good'` và **không** `compare:false`. Nguồn là `access_summary`, đã có sẵn trong payload `_pickAccess` đang nhận. Nối một dòng. Nếu về sau quyết định không so kỳ thì phải ghi `blockedReason`, không để khai báo lửng lơ như hiện tại.

## Risks / Trade-offs

**Thẻ *Mức hài lòng* ở Overview sẽ vắng badge phần lớn thời gian — kể cả trên production.** Không phải trạng thái tạm của môi trường dev: trên khung mặc định `Last 1h` và các khung ngắn, mẫu dưới 20 là tình trạng thường xuyên (xem Context §"Mẫu mỏng là trạng thái vận hành"). Đây là kết quả **đúng**, nhưng nó sẽ trông như mất tính năng với người quen nhìn badge ở đó. Dòng `metric-detail` đã nói *"chưa đủ 20 để đánh giá"* nên lý do có sẵn trên màn hình; nếu vẫn gây thắc mắc thì việc cần làm là **làm rõ dòng đó**, không phải nới ngưỡng.

**Gỡ gate khỏi `_pickRetrieval` có thể làm đổi hành vi RAG Health nếu chuyển sai.** Gate hiện tại xét `evaluated` và `total_requests` **riêng cho từng chỉ tiêu**; lớp mới phải giữ đúng tính riêng đó, không được gộp thành một mẫu số chung. Nghiệm thu phải so trước/sau trên cùng một range.

**RAG Health sẽ phát sinh thêm request khi cả hai chỉ tiêu dưới ngưỡng.** Hiện `renderRetrievalCompare` thoát sớm ở `raghealth.js:243` (`if (!wantHit && !wantCoverage) return`) nên **không gọi mạng**. Sau change, quyết định chuyển xuống `renderDelta` nên `loadCompare` đã chạy xong trước đó — thêm một cặp request bị bỏ đi. Chấp nhận: chúng đi qua cache của `compare_data.js` nên chỉ tốn một lần cho mỗi range, đổi lại là gate không còn nằm rải ở hai tầng.

**Trạng thái thứ ba đang bị gộp — biết, và cố ý để ngoài phạm vi.** `fetchWindow` bắt lỗi mạng và trả `null` (`compare_data.js:84`, chú thích: *"the badge just renders as 'no data'"*), nên **fetch hỏng** và **cửa sổ rỗng** cùng hiện `—`. Đây đúng là loại lỗi §4 đang đi sửa — hai lời phát biểu khác nhau dùng chung một cách hiển thị — nhưng nó là hành vi có sẵn, có chủ ý, và mở rộng phạm vi sang đó sẽ kéo theo cả cách xử lý lỗi của 7 tab. Ghi lại ở đây để lần sau không phải phát hiện lại, không xử lý trong change này.

**Tab phải khai tên trường mẫu số.** `side()` nhận thêm tham số thứ ba, nên mỗi lời gọi `side(cmp.kt, key)` hiện có phải được rà: chỉ tiêu có `minSample` thì bắt buộc truyền, chỉ tiêu không có thì bỏ trống. Bỏ sót ở chỉ tiêu **có** `minSample` sẽ làm `sample` là `undefined` — và nếu gate xử `undefined` như "không đạt" thì badge biến mất im lặng, còn nếu xử như "đạt" thì gate vô hiệu im lặng. **Cả hai đều không kêu.** Quy ước phải chốt: `undefined` ở một chỉ tiêu có khai `minSample` là **lỗi lập trình**, phải log rõ, không được đoán.

Đo được **26 lời gọi `side(...)`** trong 7 file. Chỉ **6 lời gọi** chạm tới chỉ tiêu có `minSample`: `overview.js:92,93` (`csat_percent`) · `raghealth.js:253,254` (`citation_hit_rate`) · `raghealth.js:260,261` (`kb_coverage_percent`). **20 lời gọi còn lại không phải đụng tới** — đây là thước đo phạm vi thật của change.
