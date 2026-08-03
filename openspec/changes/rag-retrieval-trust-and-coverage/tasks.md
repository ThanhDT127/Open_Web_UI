## 1. Retrieval — tách "không đọc được" khỏi "không trích dẫn"

- [x] 1.1 `core/rag_health.py` — thêm `evaluated` / `unpaired`; `readable = content is not None`
- [x] 1.2 `hit_rate` trả `None` khi `evaluated == 0`, trả số thô (làm tròn một lần ở tầng hiển thị)
- [x] 1.3 `_rate()` chia trên `evaluated`, không chia trên `attached`
- [x] 1.4 `by_model` / `by_source` mang đủ `attached` · `evaluated` · `unpaired` · `cited` · `hit_rate`
- [x] 1.5 `zero_citation_messages` chỉ nhận ca `readable and not cited`
- [x] 1.6 Thêm `by_user` — bộ lọc user vốn lấy danh sách từ bảng Zero-Citation, sẽ rỗng sau khi 1.5 có hiệu lực

## 2. Retrieval — đặt tên tài liệu cho đúng

- [x] 2.1 `_SOURCE_RE` bắt thêm `resource-type`
- [x] 2.2 `_sources_from_body`: thẻ **có tên thắng** thẻ trống cùng `id` (khuôn mẫu trích dẫn đến trước thẻ thật)
- [x] 2.3 Kiểm: `By Source` từ 1 dòng `source #1 (43)` ra 5 tài liệu thật, cộng lại vẫn 43

## 3. Coverage — chỉ tiêu mới

- [x] 3.1 Tách `WHERE` làm hai tầng `base` / `req` để mẫu số chịu cùng bộ lọc với tử số
- [x] 3.2 `COUNT(*)` `chat.request` làm mẫu số, chạy trong cùng `db_conn()`
- [x] 3.3 Tử số đếm `resource-type="collection"`; `adhoc_requests` đếm riêng, không gộp
- [x] 3.4 `coverage_percent` trả `None` khi `total_requests == 0`
- [x] 3.5 Entry `kb_coverage_percent` trong `metrics_registry.js` — **không** khai `bands`, có khai `minSample`
- [x] 3.6 Thẻ mới + dòng chú thích in cả tử lẫn mẫu (`35/260 lượt hỏi · 7 lượt kéo file riêng`)

## 4. Ngưỡng mẫu tối thiểu

- [x] 4.1 Entry `citation_hit_rate` — `bands.good = 60` khớp hằng số `GOOD_HIT_RATE` sẵn có, `minSample = 20`
- [x] 4.2 Dưới ngưỡng: vẫn hiện số, bỏ màu, chú thích `Mẫu N/20 — chưa đủ để kết luận`
- [x] 4.3 Thêm `clearDelta()` — ẩn badge khác với `renderDelta` rỗng (`KT: —`)
- [x] 4.4 Ngưỡng chặn **cả cửa sổ đem ra so**, từng chỉ tiêu theo mẫu số riêng của nó
- [x] 4.5 Model chưa đọc được câu trả lời nào bị loại khỏi biểu đồ, kèm dòng đếm số model bị loại

## 5. Tab Knowledge — cùng lỗi, sửa cùng lúc

- [x] 5.1 `_query_stem_usage` thêm `evaluated`
- [x] 5.2 `_classify` nhận thêm `evaluated`; `attach > 0` mà `evaluated == 0` → `unproven`, **không** `needs_tuning`
- [x] 5.3 `query_kb_value` trả `evaluated` / `unpaired`, `hit_rate` thô hoặc `None`
- [x] 5.4 `hitRateCell()` — `—` có tooltip nêu lý do; có `unpaired` thì đánh dấu `*`
- [x] 5.5 Cập nhật `test_knowledge_analytics.py` (chữ ký `_classify` đổi) + thêm test cho ca buộc tội oan

## 6. Hết nuốt lỗi

- [x] 6.1 Gỡ `_parse_range` ở `api/rag_health.py` → `summary_v2._resolve_range`, giữ mặc định 7 ngày
- [x] 6.2 Gỡ `_parse_range` ở `api/knowledge_analytics.py` → nt., giữ mặc định 30 ngày
- [x] 6.3 Banner lỗi cho Ingestion · Retrieval (RAG) và Inventory · KB Value · Governance (Knowledge)
- [x] 6.4 Khi lỗi: xoá luôn giá trị, bảng, dòng chú thích và badge — không để số của kỳ trước nằm lại

## 7. So kỳ (Phase 2 wiring)

- [x] 7.1 Entry `embedding_calls`
- [x] 7.2 `renderIngestionCompare` / `renderRetrievalCompare`, dọn badge cũ ở **mọi** đường thoát
- [x] 7.3 Bộ lọc model/user đi kèm cửa sổ so sánh qua `extra`
- [x] 7.4 **Sửa `compare_data.js`**: khoá cache thiếu `extra` — tab này là caller đầu tiên truyền nó

## 8. Việt hoá nhãn tab

- [x] 8.1 3 tên mục + 2 tên biểu đồ + 6 tên bảng
- [x] 8.2 10 nhãn thẻ theo quy ước **danh ngữ mở đầu bằng đơn vị của giá trị**
- [x] 8.3 Banner mô tả tab, 2 ô lọc, 2 nút
- [x] 8.4 8 chuỗi trạng thái rỗng — `None 🎉` từng dùng chung cho 3 bảng nghĩa khác nhau
- [x] 8.5 Giữ nguyên tên cột bảng bằng tiếng Anh (quy tắc Phase 11)

## 9. Nghiệm thu

- [x] 9.1 11 bất biến × 5 cửa sổ × bộ lọc, chạy trên dữ liệu thật
- [x] 9.2 `test_knowledge_analytics.py` — 15 passed, 0 failed
- [x] 9.3 `docker compose build middleware` + kiểm 11 bất biến **qua HTTP thật** (16 tổ hợp)
- [x] 9.4 `start` rác → cả 5 endpoint cùng trả `400`; bỏ trống → về đúng mặc định cũ 7d/30d
- [x] 9.5 Nghiệm thu trình duyệt 3 cửa sổ (tháng 6 · 30 ngày · rỗng), console sạch
- [x] 9.6 Kiểm tĩnh: 4 module JS syntax, 50 DOM id, 8 `colspan`, CRLF nguyên vẹn
