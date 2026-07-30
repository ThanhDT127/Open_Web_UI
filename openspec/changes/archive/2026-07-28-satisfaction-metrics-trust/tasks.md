## 1. Thống nhất bộ giải mã thời gian (chặn nhóm 5)

- [x] 1.1 Thay `analytics._time_boundaries` bằng `summary_v2._resolve_range` ở **cả hai** chỗ gọi: `get_chat_analytics` (dòng ~67) và `get_satisfaction_analytics` (dòng ~191). Xoá hẳn `_time_boundaries` sau khi không còn ai gọi — để lại hai bộ giải mã trong một file còn khó hiểu hơn vấn đề đang chữa
  - ⚠️ `_resolve_range` trả **3** giá trị. Chỉ lấy 2 giá trị đầu và **giữ nguyên** dòng `bucket_size = "hour" if minutes <= 1440 else "day"`. `filters.js:53-56` cảnh báo rõ: `get_chat_analytics` neo bucket theo `minutes`, để bộ giải mã tự suy ra bucket sẽ âm thầm đổi biểu đồ tab Chat Analytics từ theo giờ sang theo ngày
  - ⚠️ Mặc định khác nhau: `_time_boundaries` mặc định `minutes=43200`, `_resolve_range` mặc định `60`. Hai endpoint đều khai báo `Query(43200)` nên đường HTTP không đổi, nhưng **đừng** bỏ giá trị mặc định ở tầng `Query`
- [x] 1.2 Nghiệm thu **không đổi số** trên đường bình thường: gọi `/analytics/chat` và `/analytics/satisfaction` với `start`+`end` hợp lệ, so từng trường với bản trước khi sửa. `filters.js:51-52` cho thấy frontend luôn gửi cả hai nên đây là đường duy nhất người dùng đi
- [x] 1.3 Nghiệm thu **đổi hành vi** ở hai ca hỏng, cho **cả hai** endpoint: `start` sai định dạng → `400`; `start >= end` → `400`. Trước đây cả hai đều im lặng
  - ⚠️ Gọi tay bằng curl phải encode `+` thành `%2B`, nếu không `+07:00` bị hiểu thành dấu cách và ra `400` vì lý do khác
- [x] 1.4 Nghiệm thu bucket của tab Chat Analytics: cửa sổ ≤ 24 giờ vẫn gom **theo giờ**, không phải theo ngày

## 2. Ngưỡng mẫu tối thiểu

- [x] 2.1 Khai báo ngưỡng mẫu tối thiểu **20** và hai ngưỡng màu **80 / 50** trong `metrics_registry.js`, tại entry `csat_percent` — nơi đã giữ `label`, `fmt`, `delta`, `polarity` của chỉ tiêu này
- [x] 2.2 `satisfaction.js` và `overview.js` **nhập** ngưỡng từ registry. Xoá cả hai bản chép: `satisfaction.js:39` và `overview.js:109` — dòng `overview.js:108` có comment tự thú nhận *"Thresholds mirror satisfaction.js"*, xoá luôn comment đó khi bản sao không còn
- [x] 2.3 Sắp xếp bảng model **hai tầng**: nhóm đạt ngưỡng xếp theo CSAT giảm dần và có số hạng; nhóm chưa đạt nằm dưới một dòng ngăn, **không** số hạng, CSAT màu trung tính
  - ⚠️ Sort hiện tại `sorted(key=(csat_percent, total), reverse=True)` xếp CSAT trước, số mẫu chỉ là tiêu chí phụ khi CSAT bằng nhau **tuyệt đối** — nên 1 khen/0 chê (100%) đứng trên 50 khen/5 chê (90%)
  - Dòng ngăn phải `colspan="6"` (bảng có 6 cột: `#` · Model · 👍 · 👎 · Total · CSAT %)
- [x] 2.4 Thẻ "Mức hài lòng" ở tab Overview: dưới ngưỡng thì vẫn hiện phần trăm và số lượt, nhưng ở trạng thái **trung tính** thay vì ok/warn/danger
- [x] 2.5 Nghiệm thu trên dev: **không** model nào lên tầng xếp hạng (cả hệ thống mới có 5 lượt), nhưng **cả hai dòng model vẫn hiện** kèm số lượt — bảng không được trống. Thẻ Overview mất màu
- [x] 2.6 Nghiệm thu bằng dữ liệu bơm tay: thêm đủ lượt cho một model vượt 20 → model đó lên tầng trên, có số hạng, có màu; các model khác giữ nguyên ở tầng dưới. **Xoá sạch dữ liệu bơm sau khi kiểm**

## 3. Nhãn lý do đánh giá

- [x] 3.1 Bổ sung vào bảng dịch `satisfaction.js:105` hai lý do dev đang sinh ra: `positive_attitude`, `followed_instructions_perfectly`
- [x] 3.2 Thêm hàm dự phòng: lý do không có trong bảng thì đổi `_` thành dấu cách và viết hoa chữ đầu, kèm `console.warn` ghi lại giá trị lạ. Lý do rỗng hiện `Không nêu lý do`
  - Bảng dịch là danh sách **ưu tiên**, không phải danh sách đầy đủ — Open WebUI thêm lý do mới theo phiên bản, và không có hàm dự phòng thì lần sau sẽ không ai nhìn thấy cho tới khi có người hỏi
- [x] 3.3 Nghiệm thu: 5 feedback trên dev không còn dòng nào hiện chuỗi `snake_case`. Bơm thêm một feedback với lý do bịa (`some_brand_new_reason`) → hiện `Some brand new reason`, không phải chuỗi gốc

## 4. Làm tròn và nhãn số lượt

- [x] 4.1 Bỏ `int()` ở `analytics.py:218` (CSAT tổng) và `:240` (CSAT từng model); trả tỷ lệ **chưa làm tròn**
- [x] 4.2 Ba nơi hiển thị dùng formatter `pct1` **đã có sẵn** (`metrics_registry.js:38`), không viết `toFixed` rời — đúng cách `usd4` được dùng ở Phase 7b:
  - `satisfaction.js:31` — thẻ CSAT Score
  - `overview.js:106` — thẻ Mức hài lòng
  - `export_report.py:359` — làm tròn **tại ô** Excel, như sheet Groups đã làm
  - Huy hiệu so kỳ ở Overview **không cần sửa** — đã đi qua registry
- [x] 4.3 Payload thêm `feedback_rows` = đếm **mọi** dòng feedback trong cửa sổ (không lọc rating). `totals.total` giữ nguyên nghĩa `khen + chê` vì đó là mẫu số của CSAT
- [x] 4.4 Chỉ khi `feedback_rows > total` mới hiện chú thích số lượt bị loại. Hôm nay hai số bằng nhau nên **màn hình không được đổi gì** — đây là chốt an toàn, không phải chỉ tiêu mới
- [x] 4.5 Sửa nhãn ở hai chỗ: `export_report.py` ô `"Tổng feedback"` → `"Tổng lượt khen/chê"`; `overview.js:107` `"N lượt đánh giá"` → `"N lượt khen/chê"`
  - ⚠️ **KHÔNG** đụng 4 nhãn tiếng Anh của thẻ tab (`CSAT Score`, `Positive`, `Negative`, `Total Votes`). `Total Votes` đã đúng nghĩa, và toàn dashboard đang 45 nhãn Anh / 23 Việt — thống nhất là phạm vi Phase 11
- [x] 4.6 Nghiệm thu: bơm feedback sao cho CSAT ra tỷ lệ lặp (ví dụ 2/3) → **cả ba** nơi hiện `66.7%`, không nơi nào hiện `66%` hay `66.66666666666667%`. Kiểm cả file Excel tải về, không chỉ màn hình

## 5. Tỷ lệ câu trả lời được đánh giá

- [x] 5.1 Thêm `count_chat_completions(cutoff, end_time)` vào **`summary_v2.py`**, cạnh `compute_usage_summary`, dùng chung `_resolve_range`. Lọc `endpoint LIKE '%chat/completions%'`
  - ⚠️ Lọc kiểu **liệt kê cái được tính**, không phải loại trừ. Audit log có sẵn cột `image_count`, `tts_chars`, `stt_seconds` nên hệ thống có đường xử lý ảnh/giọng nói — dev chưa dùng tới. Lọc kiểu loại trừ sẽ âm thầm đếm chúng vào mẫu số khi production bật lên
  - `idx_audit_ts` đã tồn tại, `EXPLAIN ANALYZE` cho index scan 0,24 ms. **Không** thêm index
  - ⚠️ **Không** viết SQL này trong `analytics.py`. `analytics.py:116-118` có comment do người sửa con bọ 264/189 để lại: *"This endpoint must NOT re-aggregate that table"*
- [x] 5.2 `get_satisfaction_analytics` gọi `count_chat_completions` và trả thêm tỷ lệ được đánh giá vào payload
- [x] 5.3 Hiển thị chỉ tiêu với nhãn **"% câu trả lời được đánh giá"** — không phải "% tin nhắn", vì ta không đếm tin nhắn. Nhãn phải nói rõ hai trục thời gian khác nhau: lượt đánh giá tính theo **lúc bấm**, câu trả lời tính theo **lúc sinh ra**
- [x] 5.4 Nghiệm thu bộ lọc bằng con số đã đo: cửa sổ **toàn bộ lịch sử** phải cho `364` chứ không phải `4101`. Không lọc thì coverage ra `0,12%` thay vì `1,37%` — sai 11 lần
  - ⚠️ Tỷ lệ `8,9%` của dev là **dữ liệu test RAG**, không phải kỳ vọng production: 3 736 lượt embedding dồn vào tháng 6, tháng 7 chỉ còn 1. Điều kiện nghiệm thu là *bộ lọc có chạy không* (`364 ≠ 4101`), **không** phải tỷ lệ ra bao nhiêu
- [x] 5.5 Nghiệm thu bất biến trên ít nhất 4 cửa sổ, gồm **bắt buộc** một cửa sổ toàn-thời-gian:
  ```
  count_chat_completions(c,e)  <=  compute_usage_summary(c,e).totals.requests_total
  ```
  - ⚠️ Phải viết `<=`, **không** phải `==`. Hai số cố ý khác nhau. Cửa sổ 30 ngày cho `181` vs `182` nên phép thử đòi bằng nhau sẽ **đúng trên cửa sổ ngắn và sai trên cửa sổ dài** (`364` vs `4101`)
- [x] 5.6 Nghiệm thu cửa sổ rỗng: mẫu số bằng 0 → hiện `—` kèm lý do, **không** hiện `0%` và không chia cho 0

## 6. Hàm thuần và Excel hết fail-open

- [x] 6.1 Tách `compute_satisfaction(cutoff, end_time)` thuần khỏi `get_satisfaction_analytics`; handler chỉ còn lo auth và giải mã tham số. Theo đúng khuôn `compute_group_analytics` của Phase 7a
- [x] 6.2 `export_report._collect_satisfaction` gọi hàm thuần và **bỏ `except Exception: return {}`**
  - Lời giải thích đã nằm sẵn cách đó 20 dòng, trong docstring `_collect_groups`: *"the previous version swallowed every exception, so a failure here used to produce a report whose department sheet quietly said 'unavailable' while the file downloaded as if it were complete. Let it raise."*
  - ⚠️ `_collect_chat_analytics` ngay bên trên **cùng bệnh** nhưng thuộc tab khác — **để riêng**, đừng gộp vào change này
- [x] 6.3 Nghiệm thu: tạm làm hỏng query feedback → gọi export phải trả lỗi HTTP, **không** tải về file có sheet Satisfaction toàn số 0
- [x] 6.4 Nghiệm thu ngược: cửa sổ rỗng thật (không có feedback nào) mà mọi query đều chạy → file **vẫn** tải về bình thường với sheet rỗng. Phân biệt được "lỗi" với "chưa ai đánh giá" là mục đích của cả mục này

## 7. Nghiệm thu tổng thể

- [x] 7.1 Nghiệm thu trên trình duyệt, ghi rõ cửa sổ **có mũi giờ**: 4 thẻ · bảng model hai tầng · feed lý do · tỷ lệ được đánh giá · không lỗi console
- [x] 7.2 Nghiệm thu **tab Chat Analytics** — tab nằm ngoài tên gọi của change nhưng dùng chung bộ giải mã: số liệu không đổi, bucket biểu đồ không đổi
- [x] 7.3 Nghiệm thu **tab Overview** — thẻ "Mức hài lòng": phần trăm 1 chữ số thập phân, trạng thái trung tính khi dưới ngưỡng, nhãn `lượt khen/chê`, huy hiệu so kỳ vẫn chạy
- [x] 7.4 Tải file Excel và **mở ra xem**: nhãn ô, CSAT làm tròn, bảng model. Không kiểm bằng mã trạng thái `200`
- [x] 7.5 Xác nhận **không ghi vào database của Open WebUI**: chụp `feedback` trước và sau khi gọi mọi endpoint vài lượt, so từng dòng

## 8. Đồng bộ tài liệu

- [x] 8.1 Cập nhật `docs/dashboard_metrics_implementation_plan.md` §Phase 8 — đánh dấu xong, ghi số nghiệm thu kèm cửa sổ có mũi giờ
  - ⚠️ Dòng plan hiện ghi mẫu số là `COUNT(*) FROM message`. Bảng đó **rỗng** (0 dòng / 24 chat) và câu query đã bị xoá ở change `unify-audit-aggregation`. Phải sửa hẳn dòng đó, nếu không phase sau lại đi theo
- [x] 8.2 Ghi 4 mục tiêu-không-làm kèm **điều kiện mở khoá** vào plan: xu hướng CSAT · thống kê lý do bị chê · CSAT × chi phí theo model · CSAT theo phòng ban. Nêu rõ cả bốn bị chặn vì **dữ liệu quá ít, không phải vì khó** — và với hai mục cuối thì kỹ thuật **đã sẵn sàng** (tên model khớp giữa hai hệ thống; `_resolve_ow_ids_to_emails()` + bản đồ nhóm chính Phase 7 đã có)
- [x] 8.3 Ghi vào plan hai điều đã kiểm được, để phase sau khỏi điều tra lại: `feedback` **không** có FK tới `chat` (Open WebUI cố ý tách rời vòng đời, nên feedback sống lâu hơn chat); và `feedback` chỉ có index khoá chính — chấp nhận được vì dữ liệu do người bấm tay nên luôn nhỏ
- [x] 8.4 `openspec validate satisfaction-metrics-trust --strict` rồi `openspec archive`. ⚠️ Nếu archive báo lỗi giữa chừng, **kiểm `git status` trước khi chạy lại** — Phase 7 gặp trường hợp công cụ in "Aborted. No files were changed" nhưng thực tế đã ghi một file
