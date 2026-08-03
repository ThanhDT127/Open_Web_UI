## Context

Tab Satisfaction đọc bảng `feedback` của Open WebUI. Toàn hệ thống dev có **5 dòng** — 4 khen, 1 chê, trải trên 2 tuần. Đây là ràng buộc chi phối toàn bộ thiết kế: Phase 7 nghiệm thu được bằng cách đối chiếu 4 101 request trên 10 cửa sổ; Phase 8 **không có** đặc quyền đó.

Ba sự thật về dữ liệu, đo ngày 2026-07-28, quyết định gần hết các lựa chọn dưới đây:

| Sự thật | Số đo | Vì sao quan trọng |
|-----------------------------------------------|-------------------------|--------------------------------------------------------------|
| Bảng `message` của Open WebUI **rỗng**        | 0 dòng / 24 chat        | Mẫu số mà plan §Phase 8 chỉ định không tồn tại                |
| Feedback **sống lâu hơn** chat                 | 2/5 trỏ vào chat đã xoá | `feedback` không có FK tới `chat` — Open WebUI cố ý tách rời  |
| Phần lớn request **không đánh giá được**       | 364/4 101 là chat       | Phần còn lại là gọi embedding của RAG, không có nút 👍👎       |

Ràng buộc thứ hai: `_time_boundaries` được **hai** endpoint trong `analytics.py` dùng chung (`get_chat_analytics` dòng 67, `get_satisfaction_analytics` dòng 191). Không thể sửa cho riêng Satisfaction mà không để lại hai bộ giải mã thời gian trong cùng một file.

## Goals / Non-Goals

**Goals:**

- Mọi con số hiển thị trên tab Satisfaction phải **đứng vững được trước câu hỏi "dựa vào đâu"**.
- Có chỉ tiêu trả lời được câu "người dùng có dùng nút đánh giá không".
- Xoá ba khoản nợ kỹ thuật đã biết đang nằm trên đường đi: resolver nuốt lỗi, ngưỡng chép hai nơi, Excel fail-open.

**Non-Goals** — bốn mục dưới đây **cố ý không làm**, và đều bị chặn bởi **cùng một lý do là dữ liệu quá ít, không phải vì khó**. Ghi kèm điều kiện mở khoá để người sau không phải điều tra lại:

| Không làm                    | Trạng thái dữ liệu hôm nay              | Kỹ thuật | Mở khoá khi                                  |
|------------------------------|-----------------------------------------|----------|----------------------------------------------|
| Xu hướng CSAT theo thời gian | 2 tuần có dữ liệu: 4 điểm và 1 điểm     | dễ       | ≥ 8 tuần liên tục, mỗi tuần ≥ ngưỡng mẫu     |
| Thống kê lý do bị chê        | **đúng 1 lượt chê** toàn hệ thống       | dễ       | ≥ 20 lượt chê — lúc đó mới đáng hỏi leader   |
| CSAT ghép chi phí theo model | 5 lượt trải trên 2 model                | **đã sẵn sàng** — tên model khớp giữa `feedback.meta.model_id` và `mw_audit_log.model`, không cần bảng ánh xạ | ≥ 2 model đạt ngưỡng mẫu |
| CSAT theo phòng ban          | ~1 lượt mỗi phòng                       | **đã sẵn sàng** — `_resolve_ow_ids_to_emails()` + bản đồ nhóm chính Phase 7 | phòng nhỏ nhất đạt ngưỡng mẫu |

Ngoài ra **không** Việt hoá 4 nhãn thẻ của tab (`CSAT Score`, `Positive`, `Negative`, `Total Votes`). Toàn dashboard đang có 45 nhãn tiếng Anh và 23 tiếng Việt; việc thống nhất là phạm vi Phase 11, đang chờ leader xác nhận cuối.

## Decisions

### D1 — Mẫu số coverage là request `chat/completions`, không phải mọi request

Chỉ loại request này mới có nút đánh giá. Đo trên dev:

```
/v1/embeddings          2 699  ← RAG đánh chỉ mục, không đánh giá được
embeddings              1 038  ← cùng loại, ghi khác chính tả
/v1/chat/completions      364  ← loại duy nhất tính vào mẫu số
```

Không lọc thì coverage toàn-thời-gian ra `5/4101 = 0,12%` thay vì `5/364 = 1,37%` — **sai 11 lần**.

> ⚠️ **Tỷ lệ 8,9% của dev là dữ liệu test RAG, KHÔNG phải kỳ vọng production.** Đợt embedding dồn hết vào tháng 6 (3 736 lượt) khi đang thử RAG; tháng 7 chỉ còn 1. Trên các cửa sổ gần đây tỷ lệ gần 1:1 (181/182). Đừng dùng 8,9% làm mốc kiểm tra — thứ cần kiểm là **bộ lọc có chạy không**, không phải tỷ lệ ra bao nhiêu.

Bộ lọc phải **liệt kê cái được tính** (`endpoint LIKE '%chat/completions%'`), không phải loại trừ cái không tính. Audit log có sẵn cột `image_count`, `tts_chars`, `stt_seconds` nên hệ thống có đường xử lý ảnh/giọng nói — dev chưa dùng tới. Lọc kiểu loại trừ sẽ âm thầm đếm chúng vào mẫu số khi production bật lên.

*Đã cân nhắc:* đếm tin nhắn assistant trong `chat.chat->'history'->'messages'`. **Bị loại** — xem D2.

### D2 — Không xoá feedback mồ côi; đổi mẫu số thay vì sửa dữ liệu

2/5 feedback trên dev trỏ vào cuộc chat người dùng đã xoá. Ba lý do không xoá chúng:

1. `feedback` là bảng của Open WebUI. Ba bảng khác (`chat_file`, `chat_message`, `shared_chat`) **có** FK tới `chat`; riêng `feedback` thì không — Open WebUI cố ý tách rời vòng đời. Trang Evaluations của OW đọc thẳng bảng này.
2. Lượt đánh giá khẳng định một điều **về model**, không phải về cuộc chat. Xoá 2 dòng làm CSAT nhảy từ 80% xuống 67% — phá 40% dữ liệu chất lượng của cả hệ thống để một phép chia trông gọn hơn.
3. Trái nguyên tắc đã chốt ở Phase 4: *đừng lọc bảng xếp hạng theo danh sách hiện tại; thực thể đã xoá vẫn phải hiện dữ liệu lịch sử*.

Và vấn đề **tự biến mất** khi chọn đúng mẫu số:

```
User xoá chat  →  chat            biến mất
                  chat.messages   biến mất
                  feedback        Ở LẠI   ← tử số
                  mw_audit_log    Ở LẠI   ← mẫu số
```

Hai vế cùng miễn nhiễm với thao tác xoá nên không bao giờ lệch nhau. Nếu lấy `chat` làm mẫu số, coverage sẽ **tự trôi lên theo thời gian** — trông y hệt một xu hướng tốt, mà thật ra chỉ là mẫu số bị bào mòn.

### D3 — Hàm đếm riêng, nhưng đặt cạnh hàm gom chung

Đo trên dev, lấy cùng một con số bằng hai cách:

| Cửa sổ    | `compute_usage_summary` | `COUNT(DISTINCT rid)` | Chậm hơn |
|-----------|------------------------:|----------------------:|---------:|
| 30 ngày   |                 2,67 ms |               0,41 ms |     6,6x |
| 90 ngày   |                29,43 ms |               1,11 ms |    26,6x |
| Toàn bộ   |                46,46 ms |               2,00 ms |    23,2x |

Hàm gom chung kéo mọi dòng về Python để dựng chuỗi thời gian, bảng theo người, bảng theo model — rồi ta chỉ lấy một con số. Ở quy mô production ước tính (~120 000 dòng/tháng) đó là khoảng **1,3 giây** mỗi lần mở tab, và tab Usage đã trả cái giá đó rồi.

Nhưng viết SQL rời trong `analytics.py` là **tái tạo hình dạng** của con bọ 264/189: hai nơi cùng định nghĩa "một request là gì". Comment ở `analytics.py:116-118` được để lại chính vì chuyện đó.

Chốt: `count_chat_completions(cutoff, end_time)` đặt **trong `summary_v2.py`**, cạnh `compute_usage_summary`, dùng chung `_resolve_range`. Ai sửa định nghĩa sẽ nhìn thấy cả hai nằm cạnh nhau. `analytics.py` gọi hàm đó, không tự viết SQL.

`idx_audit_ts` đã tồn tại nên câu đếm chạy bằng index scan (0,24 ms trên `EXPLAIN ANALYZE`), không cần thêm index.

### D4 — Bất biến là `<=`, **không** phải `==`

```
count_chat_completions(c, e)  <=  compute_usage_summary(c, e).totals.requests_total
```

Hai con số **cố ý khác nhau**: `requests_total` gồm cả embedding, hàm mới thì không. Trên cửa sổ 30 ngày gần đây chúng gần bằng nhau (181 vs 182) nên một phép thử đòi bằng nhau sẽ **đúng trên cửa sổ ngắn và sai trên cửa sổ dài** (364 vs 4 101) — loại bẫy tệ nhất. Phải viết `<=` và phải kiểm trên cửa sổ toàn-thời-gian.

### D5 — Ngưỡng mẫu tối thiểu là **20**

Không tìm thấy ngưỡng mẫu nào có sẵn trong codebase để bám theo, nên suy từ chính ngưỡng màu `80/50` mà code đang dùng. Khoảng tin cậy Wilson 95% khi CSAT quan sát được là 80%:

| n      | Sự thật có thể nằm trong | Rộng    | Phân biệt được "≥80" với "<50"? |
|-------:|--------------------------|--------:|---------------------------------|
| 3      | 20,8 – 93,9%             |   73 pp | không                           |
| 5      | 37,6 – 96,4%             |   59 pp | không                           |
| 10     | 49,0 – 94,3%             |   45 pp | không                           |
| **20** | **58,4 – 91,9%**         | **34 pp** | **có**                        |
| 30     | 62,7 – 90,5%             |   28 pp | có                              |

`n = 20` là điểm đầu tiên khoảng tin cậy không còn trùm qua vạch 50 — tức là lúc màu xanh/đỏ bắt đầu nói được điều gì. Với 5 mẫu, "80%" thật ra có thể là bất cứ đâu **từ 38% đến 96%**.

*Hệ quả nhìn thấy được:* hôm nay không model nào lên tầng xếp hạng, và thẻ "Mức hài lòng" ở Overview mất màu. Đó là **trạng thái trung thực**, không phải lỗi — và các dòng vẫn hiện đủ số lượt nên bảng không trống.

### D6 — Dưới ngưỡng thì hiện số nhưng bỏ hạng và bỏ màu — **không** dùng dấu `—`

Đây là chỗ **cố ý khác** luật Phase 7b:

```
chia cho 0        →  KHÔNG TÍNH ĐƯỢC   →  dấu — kèm lý do   (luật Phase 7b)
1 mẫu ra 100%     →  tính được, nhiễu   →  hiện số, bỏ hạng, bỏ màu
```

Hiện `—` sẽ **xoá mất** thông tin "model này bị chê 1 lần" — với 5 feedback thì đó là 20% dữ liệu chất lượng của cả hệ thống.

Cái sort hiện tại làm vấn đề nặng thêm: `sorted(key=(csat_percent, total), reverse=True)` xếp CSAT trước, số mẫu chỉ là tiêu chí phụ khi CSAT **bằng nhau tuyệt đối** — nên model 1 khen/0 chê (100%) đứng trên model 50 khen/5 chê (90%). Chuyển sang sắp xếp hai tầng: nhóm đạt ngưỡng xếp theo CSAT, nhóm chưa đạt xuống dưới một dòng ngăn, không đánh số hạng.

Ngưỡng phải áp cho **cả hai** màn hình — `satisfaction.js:39` (bảng model) và `overview.js:109` (thẻ CSAT). Sửa một nơi là chữa nửa bệnh.

### D7 — Bảng dịch lý do là danh sách **ưu tiên**, không phải danh sách đầy đủ

`satisfaction.js:105` có 8 lý do; dev đang sinh ra 2 lý do **không nằm trong bảng** (`positive_attitude`, `followed_instructions_perfectly`), và chúng đổ nguyên `snake_case` ra màn hình.

Đây không phải lỗi viết thiếu — **Open WebUI thêm lý do mới theo phiên bản**. Nên cần hàm dự phòng làm chuỗi lạ đọc được (`positive_attitude` → `Positive attitude`) kèm `console.warn`. Xấu hơn tiếng Việt nhưng **không bao giờ trông như lỗi**. Lý do rỗng hiện `Không nêu lý do`.

*Đã cân nhắc:* chỉ thêm 2 lý do đang thiếu. **Bị loại** — lần sau OW nâng cấp sẽ thiếu tiếp, và sẽ không ai nhìn thấy cho tới khi có người hỏi.

### D8 — CSAT trả số thô, làm tròn một lần ở tầng hiển thị

`int()` ở `analytics.py:218` và `:240` **cắt đuôi**, không làm tròn: `2/3 = 66,67%` hiện thành `66%`. Sai lệch có hệ thống, luôn thấp hơn sự thật.

Backend cắt rồi thì frontend vĩnh viễn không lấy lại được. Payload trả số thô; hiển thị dùng **`pct1` đã có sẵn** trong registry (`metrics_registry.js:38`), không viết `toFixed` rời — đúng cách `usd4` được dùng ở Phase 7b.

Giữ **1 chữ số thập phân** cho nhất quán với `error_rate_percent`, `adoption_rate_percent`, `top10_pct_cost_share` — cả nhóm đang dùng `fmt: 'pct1'`. Đổi riêng CSAT thành 0 chữ số sẽ tạo một ngoại lệ phải nhớ.

⚠️ Đổi kiểu giá trị này chạm **ba** nơi hiển thị cùng lúc; sót một chỗ là ra `66.66666666666667%`:

```
satisfaction.js:31     `${data.totals.csat_percent}%`
overview.js:106        `${pct}%`
export_report.py:359   ghi thẳng vào ô Excel  →  làm tròn tại ô, như sheet Groups
```

Huy hiệu so kỳ ở Overview **không cần sửa** — nó đã đi qua registry và đã dùng `pct1`.

### D9 — Sửa nhãn ở Excel và Overview, **không** đụng thẻ tab

Cùng một giá trị (`khen + chê`) đang mang ba nhãn khác nhau:

| Nơi              | Nhãn hiện tại        | Đánh giá                                       | Xử lý           |
|------------------|----------------------|------------------------------------------------|-----------------|
| Thẻ tab          | `📊 Total Votes`     | **đúng** — "vote" là một lượt 👍/👎             | giữ nguyên      |
| Overview         | `N lượt đánh giá`    | mơ hồ — "đánh giá" nghe rộng hơn               | → `lượt khen/chê` |
| Excel sheet 6    | `Tổng feedback`      | **sai** — giá trị không phải mọi feedback       | → `Tổng lượt khen/chê` |

### D10 — `feedback_rows` là chốt an toàn, không phải tính năng

`totals.total` chỉ cộng rating `1` và `-1`. Nếu Open WebUI ghi `rating: 0` hoặc `null`, con số sẽ đếm thiếu **trong im lặng**.

Payload thêm `feedback_rows` đếm **mọi** dòng trong cửa sổ. **Chỉ khi** `feedback_rows > total` mới hiện chú thích. Hôm nay hai số bằng nhau nên **màn hình không đổi gì** — đây là cái chốt, không phải chỉ tiêu mới.

CSAT vẫn phải chia cho `khen + chê`; nhét đánh giá trung tính vào mẫu số sẽ kéo CSAT xuống vô lý. Hai con số **buộc phải khác nhau** — vấn đề chưa bao giờ là phép tính, mà là cái nhãn.

### D11 — Ngưỡng khai báo tại `metrics_registry.js`

`overview.js:108` có comment tự thú nhận là bản sao: *"Thresholds mirror satisfaction.js"*. Change này **thêm** một ngưỡng nữa (số mẫu tối thiểu) — chép tiếp là tự đẻ bản sao thứ hai.

Registry đã giữ nhãn, formatter và chiều tốt/xấu của `csat_percent`, nên đó là chỗ đúng để giữ cả ngưỡng phân loại. Hai module hiển thị nhập từ đó.

### D12 — Tách hàm thuần, Excel bỏ fail-open

```python
# export_report.py:178 — hiện tại
def _collect_satisfaction(request, cutoff, end_time):
    try:
        return get_satisfaction_analytics(request, ...)   # gọi HANDLER
    except Exception:
        return {}                                          # nuốt lỗi
```

Đúng hai lỗi Phase 7a đã dẹp cho Groups — và lời giải thích nằm **cách đó 20 dòng**, trong docstring của `_collect_groups`: *"Calls the pure function, not the endpoint handler … the previous version swallowed every exception, so a failure here used to produce a report whose department sheet quietly said 'unavailable' while the file downloaded as if it were complete. Let it raise."*

Hôm nay nếu query feedback lỗi, Excel vẫn tải về với sheet Satisfaction toàn số 0 — không phân biệt được "lỗi" với "chưa ai đánh giá".

`_collect_chat_analytics` ngay bên trên cùng bệnh nhưng thuộc tab khác — **để riêng**, đừng gộp vào change này.

Nhân đây sửa một **cảnh spec đã lỗi thời**: `report-export` vẫn ghi *"OW DB group query fails → Sheet 4 chứa một dòng 'Dữ liệu nhóm không khả dụng'"*. Phase 7a đã đổi `_collect_groups` sang gọi hàm thuần và để lỗi lan ra, nhưng **không cập nhật spec**. Đây là sửa tài liệu cho khớp code đang chạy — không đổi hành vi, không có task code kèm theo. Ghi ra để việc sửa spec này không trông như một thay đổi lén.

### D13 — Đổi hẳn resolver, chấp nhận chạm Chat Analytics

`_time_boundaries` được cả hai endpoint dùng. Sửa cho riêng Satisfaction sẽ để lại **hai** bộ giải mã thời gian trong một file — khó hiểu hơn cả vấn đề đang chữa.

Rủi ro thực tế thấp: `filters.js:51-52` cho thấy frontend **luôn** gửi `start` + `end`, và cả hai resolver đều ưu tiên nhánh đó, nên với thao tác bình thường kết quả **y hệt**. Chỉ đổi ở hai ca hỏng, và cả hai đều là cải thiện:

| Ca                        | Trước                     | Sau   |
|---------------------------|---------------------------|-------|
| Ngày giờ sai định dạng    | im lặng lấy 30 ngày       | `400` |
| `start >= end`            | cửa sổ âm, im lặng        | `400` |

⚠️ `_resolve_range` trả **3** giá trị và tự suy ra bucket. Chỉ lấy 2 giá trị đầu và **giữ nguyên** `bucket_size = "hour" if minutes <= 1440 else "day"`. Comment ở `filters.js:53-56` cảnh báo rõ: `get_chat_analytics` neo bucket theo `minutes`, để `_resolve_range` tự quyết sẽ âm thầm đổi biểu đồ tab đó từ theo giờ sang theo ngày.

### D14 — Hai đồng hồ phải được nói ra bằng nhãn

```
feedback.created_at   =  lúc BẤM đánh giá     (epoch giây)
mw_audit_log.ts       =  lúc SINH câu trả lời (timestamptz)
```

Người dùng có thể đánh giá một câu trả lời từ tuần trước, nên tử số và mẫu số lọc theo hai mốc khác nhau. Không sửa được bằng code — Open WebUI không lưu thời điểm của tin nhắn được đánh giá ở nơi ta đọc được. Xử lý bằng nhãn, đúng cách Phase 7b phân biệt *"Chi tiêu (khoảng đang xem)"* với *"Đã dùng hạn mức (kỳ này)"*.

Lưu ý đơn vị: một bên là **giây**, một bên là **timestamptz**. Nhầm ×1000 là lỗi kinh điển.

### D15 — Nghiệm thu bằng bất biến và hành vi, không bằng con số

```
Phase 7:  4 101 request  →  Σ nhóm == totals trên 10 cửa sổ  →  chứng minh chắc
Phase 8:      5 feedback  →  CSAT 80% từ 5 mẫu               →  chứng minh được gì?
```

Mọi tiêu chí nghiệm thu phải kiểm được bằng **bơm dữ liệu giả và gọi tay**, không chờ ai bấm đánh giá. Xem `tasks.md` cho danh sách đầy đủ.

## Risks / Trade-offs

**Bộ lọc `endpoint` mới chỉ kiểm trên 3 giá trị của dev** → Liệt kê cái được tính chứ không loại trừ, nên endpoint lạ bị bỏ ra ngoài mẫu số theo mặc định — hướng an toàn. Nghiệm thu trên production phải in ra danh sách `endpoint` phân biệt trước khi tin con số.

**Tỷ lệ 8,9% của dev là dữ liệu test RAG** → Đừng dùng làm mốc kiểm tra. Điều kiện nghiệm thu là *bộ lọc có chạy không* (`364 ≠ 4101` trên cửa sổ toàn-thời-gian), không phải tỷ lệ ra bao nhiêu.

**Ngưỡng 20 làm bảng xếp hạng trống trong thời gian dài** → Các dòng vẫn hiện kèm số lượt ở tầng dưới, nên không trông như hỏng. Dòng ngăn nói rõ ngưỡng. Đây là trạng thái trung thực; một bảng xếp hạng dựng trên 1–2 mẫu mới là thứ gây hại.

**Đổi resolver chạm Chat Analytics — tab ngoài tên gọi của change** → Đưa Chat Analytics vào danh sách nghiệm thu bắt buộc, kiểm cả con số lẫn bucket của biểu đồ.

**Đổi `csat_percent` từ `int` sang số thô chạm 3 nơi hiển thị** → Sót một chỗ là ra `66.66666666666667%` ngay trên màn hình lãnh đạo. Nghiệm thu phải kiểm **đủ cả ba**, kể cả file Excel tải về.

**Coverage 2,8% có thể bị đọc thành "hệ thống kém"** → Nhãn phải nói rõ đây là *tỷ lệ được đánh giá*, không phải *tỷ lệ hài lòng*. Con số thấp là thông tin về **thói quen bấm nút**, không phải về chất lượng model.

## Open Questions

Không còn. Sáu câu từng treo đã có đáp án bằng số đo, ghi ở D1 (mẫu số), D5 (ngưỡng), D9 (nhãn), D13 (phạm vi Chat Analytics), và mục Non-Goals (xu hướng CSAT · lý do bị chê · CSAT × chi phí · CSAT theo phòng ban).
