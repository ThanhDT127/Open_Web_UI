## Why

Thẻ **🎯 Hit-Rate** trên tab RAG Health đang hiển thị một con số sai, và sai theo hướng buộc tội chính hệ thống mình đang đo.

Hàm `query_retrieval_health` ghép `chat.request` với `chat.response` bằng `LEFT JOIN`. Khi không tìm thấy câu trả lời, `content` ra `NULL`, rồi `_has_citation(None)` trả `False` — tức **"không đọc được câu trả lời"** bị đếm y như **"model không trích nguồn"**. Hai chuyện khác hẳn nhau gộp làm một, đúng loại lỗi `identity_ok` mà Phase 8 vừa dọn.

Vì sao thiếu câu trả lời: nhánh **streaming** chỉ bắt đầu ghi `chat.response` từ **01/07/2026** (`api/chat.py:1318`, commit `8f1b41d` — chính change `rag-health-monitor`), mà người dùng luôn chat ở chế độ stream.

Đo trên dữ liệu thật ngày 31/07/2026:

| Tháng   | Có đính tài liệu | Ghép được câu trả lời | Có `[N]` | Hit-Rate hiện ra |
|:--------|-----------------:|----------------------:|---------:|-----------------:|
| 06/2026 |               42 |                 **0** |        0 |     **0,0%** sai |
| 07/2026 |                1 |                     1 |        1 |  100,0% trên 1 mẫu |

Chọn tháng 6 thì dashboard báo *"chatbot chưa bao giờ trích được nguồn nào"*. Chọn tháng 7 thì báo **100%** và tô xanh, từ đúng một lượt. Không con số nào trong hai con số đó dùng được.

Đồng thời còn thiếu chỉ tiêu duy nhất trả lời câu hỏi **"khoản đầu tư kho tài liệu có được dùng không"**: ba lăng kính hiện có (Ingestion · Retrieval · Storage) đều chỉ đo *chất lượng khi đã dùng*, không lăng kính nào đo *có ai dùng*. Đo được: **36/359 = 10,0%** toàn thời gian, riêng tháng 7 là **1/94 = 1,1%** — tức 99% câu hỏi trong tháng 7 chatbot trả lời mà không có tài liệu công ty nào.

## What Changes

**Sửa cho đúng — số đang hiển thị sẽ ĐỔI:**

- Tách `unpaired` (không ghép được câu trả lời) khỏi `cited = false`. `hit_rate` trả **`None`** chứ không phải `0.0` khi không có gì để đọc — `0.0` là một kết luận.
- Bảng *Zero-Citation* chỉ nhận ca **đã đọc được** câu trả lời. Trước đây 42 request không ghi được câu trả lời bị đẩy vào đây như thể model đã trả lời mà không trích nguồn.
- Ngưỡng mẫu tối thiểu 20 cho hit-rate, khai ở `metrics_registry.js` — áp cho **cả cửa sổ hiện tại lẫn cửa sổ đem ra so kỳ**.
- Sửa `_sources_from_body`: thẻ **có tên thắng** thẻ trống cùng `id`. Open WebUI phát khuôn mẫu hướng dẫn trích dẫn — một `<source id="1">` trống — **trước** các thẻ đính kèm thật, nên bảng *By Source* gộp mọi tài liệu thành một dòng `source #1`.
- Tab **Knowledge** chép lại đúng cái `LEFT JOIN` hỏng: `_classify` nay nhận thêm `evaluated`. Kho được đính kèm 35 lần mà không đọc được câu trả lời nào phải là `unproven`, **không phải** `needs_tuning` — cái sau là lời buộc tội chính kho đó.
- Gỡ 2 `_parse_range` nuốt lỗi (`api/rag_health.py`, `api/knowledge_analytics.py`) → dùng `summary_v2._resolve_range`. Giữ nguyên mặc định cũ (7 ngày / 30 ngày); thay đổi duy nhất là tham số hỏng trả `400` thay vì im lặng hiện một cửa sổ không ai yêu cầu.
- Mọi khúc hỏng đều có banner đỏ **và xoá luôn số cũ**: banner đặt trên dãy số của khoảng thời gian trước vẫn đọc như thể dãy số đó thuộc khoảng đang chọn.

**Thêm chỉ tiêu — số chỉ có THÊM:**

- **Tỷ lệ câu hỏi dùng kho chung** (`coverage_percent`). Cả tử lẫn mẫu lấy từ `chat.request` cùng cửa sổ, cùng bộ lọc, nên **không bao giờ vượt 100% theo cấu trúc**.
- Badge so kỳ cho 3 thẻ: số lượt nạp · tỷ lệ trích được nguồn · tỷ lệ câu hỏi dùng kho chung.
- Việt hoá nhãn tab theo quy ước **danh ngữ mở đầu bằng đơn vị của giá trị** (`Số…` / `Tỷ lệ…` / `Thời gian…`).

**BREAKING (đối với người đọc, không phải API):** Hit-Rate của mọi cửa sổ trước 01/07/2026 đổi từ `0,0%` sang `—`. Payload thêm khoá, không xoá khoá nào.

## Impact

- Specs: `rag-health-monitor` · `knowledge-analytics` · `dashboard-metric-registry` · `dashboard-period-compare`
- Code: `core/rag_health.py` · `core/knowledge_analytics.py` · `api/rag_health.py` · `api/knowledge_analytics.py` · `dashboard/index.html` · `dashboard/js/{raghealth,knowledge,metrics_registry,compare_data}.js` · `test_knowledge_analytics.py`
- Đóng nốt **nợ kỹ thuật #1** (resolver thời gian phân kỳ): Phase 8 xoá `analytics._time_boundaries`, phase này xoá hai bản cuối. Nay chỉ còn `summary_v2._resolve_range`.
- `compare_data.js` sửa một lỗi tiềm ẩn ngoài phạm vi RAG: khoá cache thiếu `extra`. Tab này là caller **đầu tiên** truyền `extra`, nên lỗi chưa từng lộ. Khoá khi không lọc giữ nguyên đúng định dạng cũ nên 8 caller sẵn có không đổi hành vi.
