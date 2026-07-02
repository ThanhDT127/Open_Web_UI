## Context

Hiện tại khi user query RAG, Open WebUI retrieve chunks từ PGVector và inject vào messages dưới dạng `<source id="N">` tags. Middleware forward messages này tới LLM, LLM trả lời text + citations `[N]`. Ảnh trong tài liệu gốc (biểu đồ, bảng, sơ đồ) đã được Docling extract và materialize thành HTTP URLs tại ingest time bởi Docling proxy (`llm-mw/api/docling.py`). Những URLs này nằm trong chunk text dưới dạng Markdown image syntax `![alt](URL)`, nhưng LLM thường bỏ qua chúng trong response.

**Kiến trúc hiện tại liên quan**:
- `llm-mw/api/chat.py:753-823` — RAG Context Cleaning: materialize base64 còn sót trong messages
- `llm-mw/api/chat.py:1294-1311` — Non-streaming: inject quota/routing warnings vào response content
- `llm-mw/api/chat.py:1173-1209` — Streaming: `_iter_with_quota_warning()` inject warnings sau stream
- `llm-mw/utils/media.py` — Materialize base64 → file → public URL

**Dữ liệu production**: md_content từ Docling ~318K chars, 2 ảnh materialized mỗi lần upload. 65 ảnh đã lưu trong `logs/mw_media/`. Chunk size 1500 chars → đa số chunks có 0-1 ảnh, ~5-10% chunks có 2+ ảnh.

## Goals / Non-Goals

**Goals:**
- LLM response bao gồm hình ảnh minh họa liên quan từ RAG context khi có
- Chọn đúng ảnh khi chunk chứa nhiều ảnh (2+ ảnh)
- Hoạt động cả streaming và non-streaming mode
- Không tăng token cost đáng kể
- Không thay đổi ingest pipeline hoặc vector DB schema

**Non-Goals:**
- Multimodal RAG (gửi ảnh cho vision model) — đó là cải tiến riêng, chi phí cao
- Image description indexing (Vision LLM mô tả ảnh tại ingest time) — phase sau
- Pre-process ảnh tại ingest time (di chuyển ảnh ra khỏi query path) — đã có kế hoạch riêng trong `RAG_image_answer.md`
- Sửa Open WebUI source code — chỉ sửa RAG template config

## Decisions

### Decision 1: Hybrid 2-layer approach (S3 primary + S1 fallback)

**Chọn**: Kết hợp LLM-Assisted Selection (S3) với Context-Proximity Fallback (S1).

**Tại sao không chỉ S3 (LLM tự chọn)?**
- LLM không deterministic — có thể bỏ sót hoặc hallucinate URL (~20-30% cases)
- Không kiểm soát được format và số lượng ảnh

**Tại sao không chỉ S1 (Proximity matching)?**
- Khi chunk có 1 ảnh → inject luôn, không cần chọn (85% cases)
- Khi chunk có 2+ ảnh → proximity matching đúng ~80-90%
- Nhưng LLM chọn chính xác hơn vì hiểu semantic (~70-80% tự include đúng)

**Hybrid flow**:
```
LLM response nhận được
    │
    ├─ Response ĐÃ CÓ ![](URL) hợp lệ?
    │   └─ YES → Validate URL thuộc source → XONG (S3 thành công)
    │
    └─ NO → Response có citations [N]?
        └─ YES → Source [N] có ảnh?
            ├─ 1 ảnh → Inject luôn
            └─ 2+ ảnh → Proximity matching (S1) → Inject top 1
```

**Alternatives considered**:
- **S2 (Alt-text only)**: Quá phụ thuộc vào Docling alt text, thường empty/generic → rejected.
- **S4 (Sub-source indexing)**: Cần sửa ingest pipeline → violates non-goal → rejected.

### Decision 2: Inject ảnh ở cuối response, không inline

**Chọn**: Append image section sau response content, trước quota warning.

**Tại sao?**
- Middleware nhận response đã hoàn chỉnh — không biết đoạn nào trong response tương ứng với ảnh nào
- Inject cuối an toàn hơn: không phá vỡ flow trả lời của LLM
- Dùng format rõ ràng: `📊 Hình minh họa từ nguồn trích dẫn:`

**Alternative**: Inject sau mỗi paragraph liên quan → quá phức tạp, dễ phá formatting.

### Decision 3: Parse `<source>` tags tại middleware, cache trong request.state

**Chọn**: Parse source images một lần khi nhận messages, lưu vào `request.state.rag_source_images`.

**Tại sao?**
- Messages đã có `<source id="N">` tags từ Open WebUI
- Parse sớm → dùng lại cho cả S3 validation và S1 fallback
- `request.state` đã là pattern chuẩn trong middleware (audit state, routing state)

### Decision 4: Tối đa 3 ảnh / response

**Chọn**: Hard limit 3 ảnh, configurable qua env var `MW_RAG_IMAGE_MAX`.

**Tại sao?**
- Tránh spam khi query match nhiều sources có ảnh
- 3 ảnh đủ cung cấp visual context mà không overwhelming
- Open WebUI chat bubble có giới hạn hiển thị hợp lý

### Decision 5: Streaming — accumulate text, inject sau [DONE]

**Chọn**: Buffer toàn bộ response text trong streaming, inject ảnh cùng thời điểm quota warning.

**Tại sao?**
- Cần full response text để detect citations [N] và check ảnh existing
- Pattern đã proven: `_iter_with_quota_warning()` đã intercept [DONE] và inject extra SSE chunks
- Không ảnh hưởng TTFT (Time To First Token)
- Buffer overhead minimal (~50-100KB max cho response text)

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Open WebUI không render `![](URL)` inline | Feature không hoạt động | Verify trước khi implement; fallback: hiển thị text link |
| Ảnh URL đã expired/deleted | Broken image trong chat | Validate URL exists (HEAD request) trước inject; skip nếu 404 |
| LLM hallucinate URL (S3) | Inject ảnh không tồn tại | S3 validation: check URL thuộc domain `_mw/media/` hoặc `rag-images/` |
| Streaming buffer quá lớn | Memory spike | Set max buffer 200KB; nếu vượt, disable image injection cho request đó |
| `<source>` tag format thay đổi sau Open WebUI upgrade | Parser break | Regex flexible; log warning nếu parse 0 sources từ message có "Nhiệm vụ" prefix |
| RAG template change bị admin reset | S3 layer mất | S1 fallback vẫn hoạt động; document rõ template change |

## Open Questions

1. **Verify**: Open WebUI v0.9.5 có render Markdown images `![](URL)` inline trong chat response không? — Cần test trước khi implement.
2. **Proximity scoring**: N-gram matching đủ chính xác hay cần TF-IDF/embedding-based matching? — Bắt đầu với n-gram, iterate sau.
3. **HEAD request validation**: Có nên HEAD check URL trước inject không? Thêm latency ~50-100ms nhưng tránh broken images.
