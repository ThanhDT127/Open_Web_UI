## 1. Verification & Tiền đề

- [x] 1.1 Test Open WebUI render Markdown images: gửi response chứa `![test](http://valid-url.png)` qua chat → verify Open WebUI hiển thị ảnh inline trong chat bubble
- [x] 1.2 Upload 1 PDF có biểu đồ → query RAG → inspect messages tại middleware (rag_debug log) → xác nhận `<source>` tags chứa Markdown image URLs

## 2. RAG Template Update (S3 — LLM-Assisted Selection)

- [x] 2.1 Cập nhật RAG Template trong Open WebUI Admin Settings → Documents: thêm instruction dạy LLM include ảnh liên quan từ context bằng Markdown image syntax
- [x] 2.2 Test S3: query RAG với document có ảnh → verify LLM tự include ảnh trong response

## 3. Source Image Extraction

- [x] 3.1 Tạo hàm `_extract_rag_source_images(messages)` trong `llm-mw/api/chat.py`: parse `<source id="N">` tags, extract Markdown image URLs (`![alt](URL)`), trả về dict `{source_id: [{url, alt_text, preceding_text}]}`
- [x] 3.2 Gọi `_extract_rag_source_images()` trong `chat_completions()` sau khi parse messages, lưu kết quả vào `request.state.rag_source_images`
- [x] 3.3 Thêm config: đọc env vars `MW_RAG_IMAGE_INJECT` (default true) và `MW_RAG_IMAGE_MAX` (default 3) trong `config.py`

## 4. S3 Validation — LLM-Included Image Checking

- [x] 4.1 Tạo hàm `_validate_llm_images(response_content, trusted_patterns)`: scan response cho `![](URL)`, validate URL thuộc trusted domain (`/v1/_mw/media/`, `/rag-images/`), strip ảnh không hợp lệ
- [x] 4.2 Tạo hàm `_response_has_valid_images(response_content, source_images)`: kiểm tra response đã có ảnh hợp lệ từ source hay chưa, trả về bool

## 5. Proximity Matching (S1 — Fallback)

- [x] 5.1 Tạo hàm `_select_image_by_proximity(response_text, image_list)`: dùng n-gram matching giữa response text với preceding_text + alt_text của mỗi ảnh, trả về URL ảnh có score cao nhất
- [x] 5.2 Tạo hàm `_build_image_injection_text(cited_images, max_images)`: build Markdown section `📊 Hình minh họa từ nguồn trích dẫn:` với danh sách ảnh đã chọn

## 6. Integration — Non-Streaming Path

- [x] 6.1 Trong `_handle_non_streaming()`: sau khi nhận LLM response, gọi `_validate_llm_images()` để strip hallucinated URLs
- [x] 6.2 Trong `_handle_non_streaming()`: nếu `_response_has_valid_images()` trả false → parse citations `[N]` từ response, match với `rag_source_images`, dùng proximity matching nếu cần, inject ảnh TRƯỚC quota warning injection (line ~1294)

## 7. Integration — Streaming Path

- [x] 7.1 Trong `_iter_bytes()`: accumulate full response text vào buffer (max 200KB)
- [x] 7.2 Trong `_iter_with_quota_warning()`: sau khi stream kết thúc, validate + inject ảnh bằng thêm SSE data chunk trước quota warning chunk và trước `data: [DONE]`

## 8. Logging & Observability

- [x] 8.1 Log event `rag_image_extract`: số sources, số ảnh tìm thấy
- [x] 8.2 Log event `rag_image_inject`: source IDs, URLs injected, method (s3_llm / s1_proximity / s1_single)
- [x] 8.3 Log event `rag_image_skip`: reason (no_sources / no_citations / no_images / disabled / buffer_overflow)

## 9. Testing & Validation

- [x] 9.1 Test non-streaming: query RAG document có ảnh → verify ảnh được inject vào response
- [x] 9.2 Test streaming: query RAG document có ảnh (stream=true) → verify ảnh xuất hiện sau stream text
- [x] 9.3 Test multi-image chunk: query document có trang nhiều biểu đồ → verify chỉ ảnh liên quan được chọn
- [x] 9.4 Test non-RAG query: query bình thường không có knowledge → verify KHÔNG inject ảnh
- [x] 9.5 Test feature toggle: set `MW_RAG_IMAGE_INJECT=false` → verify skip injection
