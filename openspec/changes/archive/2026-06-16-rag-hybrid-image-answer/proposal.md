## Why

Khi user query RAG và hệ thống trả lời dựa trên tài liệu có chứa hình ảnh (biểu đồ, bảng, sơ đồ...), LLM chỉ trả về text — ảnh minh họa liên quan từ tài liệu gốc bị bỏ qua. User phải tự mở citation, tìm file, lật tới đúng trang để xem hình. Điều này giảm chất lượng trải nghiệm và tốn thời gian.

Cần một cơ chế tự động inject hình ảnh liên quan từ RAG context vào response, giúp câu trả lời trực quan và đầy đủ hơn — đặc biệt với tài liệu kỹ thuật, báo cáo tài chính có nhiều biểu đồ.

## What Changes

- **Sửa RAG template** trên Open WebUI Admin: thêm instruction dạy LLM tự include ảnh liên quan (Markdown image syntax) khi trả lời từ RAG context (Chiến lược S3 — LLM-Assisted Selection).
- **Thêm post-response image injection** trong Middleware (`chat.py`): parse `<source>` tags từ input messages để extract image URLs, sau khi LLM trả lời — nếu LLM không tự include ảnh — Middleware dùng proximity matching để chọn và inject ảnh liên quan nhất vào cuối response (Chiến lược S1 — Context-Proximity Fallback).
- **Hỗ trợ cả streaming và non-streaming**: inject ảnh tại cuối stream (cùng pattern với quota warning injection hiện có).
- **Config điều khiển**: env var enable/disable, max images per response, logging.

## Capabilities

### New Capabilities
- `rag-image-injection`: Tự động phát hiện và inject hình ảnh từ RAG context vào LLM response. Bao gồm: parse source tags, extract image URLs, proximity-based image selection khi chunk có nhiều ảnh, và inject Markdown image vào response cho cả streaming/non-streaming modes.

### Modified Capabilities
_(Không có spec-level requirement change cho capabilities hiện tại)_

## Impact

- **Middleware `llm-mw/api/chat.py`**: Thêm logic parse source images từ messages, post-process LLM response để inject ảnh. Sửa cả `_handle_non_streaming()` và `_iter_with_quota_warning()`.
- **Open WebUI Admin Settings**: Cập nhật RAG Template (Documents settings) — thêm instruction cho LLM về image inclusion.
- **Không ảnh hưởng**: Ingest pipeline, vector DB schema, Docling proxy, embedding flow — tất cả giữ nguyên.
- **Dependencies**: Không thêm dependency mới. Dùng `re` (stdlib) cho parsing.
- **Tiền đề**: Ảnh trong RAG chunks phải tồn tại dưới dạng Markdown image URLs (đã được materialize bởi Docling proxy hiện tại).
