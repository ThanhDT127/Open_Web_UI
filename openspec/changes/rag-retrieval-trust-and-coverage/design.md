## Context

Tất cả số liệu trong tài liệu này đo trực tiếp trên `openwebui-postgres` ngày 31/07/2026, không phải ước lượng.

```
mw_request_log — 102.045 dòng, 04/05 → 31/07
  inbound / outbound     100.514      ← log HTTP thô
  chat.request               359      ← tử + mẫu của coverage
  chat.response              231      ← nguồn "có trích dẫn"
  chat.stream.sample         116      ← sample = "<data_url len=4022>", KHÔNG phải nội dung
```

Toàn bộ hoạt động RAG nằm gọn trong tháng 6 (embedding 3.736 lượt, lỗi 44,4%); tháng 7 còn **1 lượt**. Nên change này **nghiệm thu bằng bất biến**, không bằng đối chiếu số — giống Phase 8.

## Goals / Non-Goals

**Goals**
- Không con số nào trên tab được phép trình bày "không đọc được" thành một kết luận.
- Thêm đúng một chỉ tiêu mới, và nó không được vượt 100% trong bất kỳ cửa sổ nào.

**Non-Goals**
- Không đi vá dữ liệu lịch sử. 42 câu trả lời tháng 6 đã mất, không dựng lại được.
- Không đọc `chat.stream.sample` để cứu hit-rate — nội dung ở đó là `<data_url len=4022>`.
- Không đổi tên cột bảng sang tiếng Việt (quy tắc Phase 11: đổi thì đổi cho cả 12 tab).

## Decisions

### 1. `hit_rate` trả `None`, không phải `0.0`

`0.0` là một phát biểu: *"model đã trả lời và không trích nguồn nào"*. Khi không có câu trả lời nào đọc được thì phát biểu đó không có căn cứ. `None` buộc tầng hiển thị phải xử riêng, và nó hiện `—`.

Hệ quả: mẫu số của hit-rate là `evaluated` (số câu trả lời **đọc được**), không phải `attached`. Ba con số `attached` / `evaluated` / `unpaired` đều có trong payload để người đọc tự kiểm `attached = evaluated + unpaired`.

### 2. Mẫu số của coverage KHÔNG dùng lại `kb_attached`

Cách làm sai mà bản plan cũ hướng dẫn: lấy `total_chats` từ `analytics.py`.

```
   TỬ SỐ                          MẪU SỐ (nếu theo plan cũ)
   mw_request_log                 openwebui.chat
   đếm LƯỢT HỎI                   đếm CUỘC TRÒ CHUYỆN
   bảng middleware                bảng Open WebUI
   bất biến                       NGƯỜI DÙNG XOÁ ĐƯỢC

        43              ÷              24          =  179%
```

179%. Đây đúng là con lỗi Phase 8 vừa gỡ (`Tỷ lệ được đánh giá`), chỉ đổi tên.

Quy tắc rút ra: **tử số và mẫu số của một tỷ lệ phải cùng bảng, cùng đơn vị, cùng cửa sổ, cùng bộ lọc.** Khác một trong bốn thì tỷ lệ đó không có nghĩa, kể cả khi nó tình cờ nhỏ hơn 100%.

Nên `WHERE` tách làm hai tầng: `base` (ts + event + model + user) và `req` (`base` + điều kiện `<source>`). Numerator ⊆ denominator theo cấu trúc.

### 3. Coverage đếm `resource-type="collection"`, không đếm file lẻ

Thẻ `<source>` thật mang `resource-type`:

```
<source id="1" name="CocCocMoCuaChoAnhDe" resource-type="collection" ...>   ← kho chung
<source id="1" name="Vi_TCVN7670-2007.docx" resource-type="file" ...>       ← user tự kéo file vào chat
```

Đo được: **36 collection / 7 file**. Người dùng kéo PDF của riêng họ vào chat **không phải** đang dùng kho tài liệu công ty — gộp vào là thổi con số lên 16% bằng thứ không liên quan tới khoản đầu tư đang cần đánh giá.

Số file lẻ vẫn trả trong payload và in ở dòng chú thích, nhưng **không dựng thẻ riêng**: 7 điểm dữ liệu thì thẻ là thừa. Về sau nó đáng theo dõi vì **là dấu hiệu kho chung thiếu nội dung người ta cần**.

### 4. Đơn vị là LƯỢT HỎI, không phải cuộc trò chuyện

Catalog §3.7 ghi *"% cuộc trò chuyện"*. Payload `chat.request` có đúng 11 khoá và **không có `chat_id`** — middleware không biết request thuộc cuộc trò chuyện nào. Nên đếm theo cuộc trò chuyện là bất khả thi, không phải chưa làm. Sửa **nhãn cho khớp giá trị**, đúng hướng đã chọn ở `unify-audit-aggregation`.

### 5. Thẻ có tên thắng thẻ trống cùng `id`

Thứ tự thẻ trong một body thật:

```
1. <source>                                              ← khuôn mẫu
2. <source id="1">                                       ← khuôn mẫu, KHÔNG name  ◀── code cũ lấy cái này
3-5. <source>
6-9. <source id="1" name="CocCocMoCuaChoAnhDe" resource-type="collection" ...>  ← thẻ THẬT, bị bỏ
```

Code cũ khử trùng theo `id` và giữ thẻ gặp trước → mọi tài liệu gộp thành một dòng `source #1`, bảng By Source vô dụng. `core/knowledge_analytics.py` đã ghi đúng cái bẫy này trong docstring và né bằng cách khớp marker `Filename:`/`Source:`; chỉ `rag_health` là vấp.

Sau sửa: `Rum 17 · RagFlood 16 · Vi_TCVN7670-2007.docx 7 · test 2 · CocCoc… 1` = 43, khớp `kb_attached`, và khớp phân loại `resource-type` đo bằng SQL độc lập (36 + 7).

### 6. Ngưỡng mẫu chặn cả cửa sổ đem ra so

Phát hiện khi nghiệm thu trình duyệt: badge Coverage của cửa sổ tháng 6 in `▲ +13,5 điểm %` trong khi cửa sổ KT (02/05→01/06) **chỉ có 5 lượt hỏi**.

Một kỳ quá mỏng để tô màu thì cũng quá mỏng để làm mốc so sánh. Nên `pick()` chặn **từng chỉ tiêu theo mẫu số riêng của nó** — `evaluated` cho hit-rate, `total_requests` cho coverage — vì hai cái mỏng đi độc lập nhau.

Dùng `clearDelta()` mới thay vì `renderDelta` rỗng: `KT: —` nghĩa là *"kỳ đó không có dữ liệu"*, còn ẩn badge nghĩa là *"kỳ này chưa đủ mẫu để so"*. Hai lý do khác nhau không được dùng chung một cách hiển thị.

### 7. Không khai `bands` cho coverage

Chưa ai nói bao nhiêu phần trăm là đạt, mà **màu là một phán quyết**. Cùng lý do `top10_pct_cost_share` để trung tính. Vẫn khai `minSample` vì nó dùng để chú thích cửa sổ mỏng và để chặn badge, không phải để tô màu.

### 8. Nhãn tiếng Việt: danh ngữ mở đầu bằng đơn vị của giá trị

`Số…` khi giá trị là đếm, `Tỷ lệ…` khi là phần trăm, `Thời gian…` khi là mili-giây. Đây là quy tắc nhãn-khớp-giá-trị đã áp ở Phase 0 (`Total Requests`) và Phase 8 (`Tổng lượt khen/chê`).

Cụ thể: thẻ `Failure Rate` đặt là **"Tỷ lệ nạp tài liệu thất bại"** chứ không phải *"Số lần thất bại khi nạp"* — giá trị hiện ra là `44,4%`, số đếm nằm ở dòng dưới (`1.660 lượt lỗi`).

## Risks / Trade-offs

| Rủi ro | Xử lý |
|:-------|:------|
| Người quen nhìn `0,0%` hôm sau thấy `—` sẽ tưởng hỏng | Dòng `⚠️ 42/42 lượt không đọc được câu trả lời` nói rõ lý do ngay dưới thẻ |
| Dữ liệu quá ít nên mọi thẻ đều ở trạng thái trung tính | Đó là trạng thái trung thực, không phải lỗi. Ghi vào doc để người sau khỏi điều tra lại |
| `api/` `core/` không bind-mount, sửa Python không ăn ngay | Phải `docker compose build middleware`. Đã ghi vào phần nghiệm thu |
| Chỉ 3 module JS được cache-bust | Phải `Ctrl+Shift+R`. Nợ kỹ thuật #5, đã vấp đúng lúc nghiệm thu |

## Nghiệm thu

Bằng **bất biến**, chạy trên dữ liệu thật:

1. `attached = evaluated + unpaired`
2. `cited ≤ evaluated`
3. số dòng Zero-Citation `= evaluated − cited` (**không phải** `attached − cited`)
4. `hit_rate is None ⟺ evaluated == 0`
5. `sum(by_model.attached) == kb_attached` và `sum(by_model.cited) == cited`
6. `kb_attached ≤ coverage.total_requests`
7. `kb_requests + adhoc_requests ≤ kb_attached`
8. `0 ≤ coverage_percent ≤ 100`, hoặc `None`
9. `coverage_percent is None ⟺ total_requests == 0`
10. Ba mục 1/2/4 áp cho **từng dòng** `by_model` · `by_source` · `by_user`
11. Gửi `start` rác → **cả 5 endpoint** (`/summary`, rag ingestion, rag retrieval, knowledge inventory, knowledge kb-value) cùng trả `400`
