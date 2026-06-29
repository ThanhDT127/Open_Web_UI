## ADDED Requirements

### Requirement: Source image extraction from RAG messages
Middleware SHALL parse `<source id="N">` tags từ input messages và extract tất cả Markdown image URLs (`![alt](URL)`) có trong mỗi source block. Kết quả SHALL được lưu vào `request.state.rag_source_images` dưới dạng dictionary `{source_id: [{url, alt_text, preceding_text}]}`.

#### Scenario: Messages chứa sources có ảnh
- **WHEN** user message chứa `<source id="1">` block với 1 Markdown image `![Biểu đồ](http://server/media/abc.png)` bên trong
- **THEN** `request.state.rag_source_images` SHALL chứa `{"1": [{"url": "http://server/media/abc.png", "alt_text": "Biểu đồ", "preceding_text": "...200 chars trước ảnh..."}]}`

#### Scenario: Messages chứa source với nhiều ảnh
- **WHEN** user message chứa `<source id="2">` block với 3 Markdown images
- **THEN** `request.state.rag_source_images["2"]` SHALL chứa list 3 items, mỗi item có url, alt_text, và preceding_text (200 chars trước ảnh)

#### Scenario: Messages không có source tags
- **WHEN** user message không chứa bất kỳ `<source>` tag nào (non-RAG query)
- **THEN** `request.state.rag_source_images` SHALL là empty dict `{}`

#### Scenario: Source không có ảnh
- **WHEN** `<source id="3">` chỉ chứa text, không có Markdown image
- **THEN** source "3" SHALL KHÔNG xuất hiện trong `rag_source_images`

---

### Requirement: LLM-assisted image selection via RAG template (S3)
Open WebUI RAG template SHALL được cập nhật để instruct LLM include hình ảnh liên quan từ context vào response khi trả lời. LLM SHALL giữ nguyên Markdown image syntax từ source content.

#### Scenario: LLM include đúng ảnh liên quan
- **WHEN** RAG context chứa `![Biểu đồ chi phí](url)` và user hỏi về chi phí
- **THEN** LLM response SHOULD chứa `![Biểu đồ chi phí](url)` inline (không bắt buộc — LLM non-deterministic)

#### Scenario: LLM bỏ qua ảnh
- **WHEN** LLM trả lời text-only mặc dù context có ảnh liên quan
- **THEN** Middleware fallback (S1) SHALL xử lý — đây là expected behavior

---

### Requirement: S3 validation — LLM-included image checking
Middleware SHALL validate ảnh mà LLM tự include trong response: URL MUST thuộc trusted domain pattern (`/v1/_mw/media/` hoặc `/rag-images/`). Nếu URL không hợp lệ, ảnh đó SHALL bị strip khỏi response.

#### Scenario: LLM include ảnh từ trusted domain
- **WHEN** LLM response chứa `![alt](https://server/v1/_mw/media/abc123.png)`
- **THEN** Middleware SHALL giữ nguyên ảnh — KHÔNG inject thêm ảnh cho cùng source

#### Scenario: LLM hallucinate URL
- **WHEN** LLM response chứa `![alt](https://external-site.com/fake.png)` không thuộc trusted domain
- **THEN** Middleware SHALL strip ảnh đó khỏi response

---

### Requirement: Post-response image injection fallback (S1)
Khi LLM response KHÔNG chứa ảnh nhưng có citations `[N]` tham chiếu source có ảnh, Middleware SHALL inject ảnh vào cuối response content.

#### Scenario: Citation tới source có 1 ảnh
- **WHEN** LLM response chứa `[1]` citation, source "1" có 1 ảnh, và response chưa có ảnh inline
- **THEN** Middleware SHALL append image section: `\n\n---\n📊 **Hình minh họa từ nguồn trích dẫn:**\n\n![Nguồn [1]](URL)\n`

#### Scenario: Citation tới source có nhiều ảnh — proximity matching
- **WHEN** LLM response chứa `[2]` citation, source "2" có 3 ảnh, response chưa có ảnh inline
- **THEN** Middleware SHALL chọn ảnh có proximity score cao nhất (dựa trên text overlap giữa response content và preceding_text + alt_text), và inject CHỈ ảnh đó

#### Scenario: Nhiều citations tới nhiều sources có ảnh
- **WHEN** LLM response cite `[1]`, `[2]`, `[3]` — mỗi source có ảnh
- **THEN** Middleware SHALL inject tối đa `MW_RAG_IMAGE_MAX` ảnh (default 3), ưu tiên sources được cite trước

#### Scenario: Citation nhưng source không có ảnh
- **WHEN** LLM response cite `[1]` nhưng source "1" không có ảnh
- **THEN** Middleware SHALL KHÔNG inject ảnh — response giữ nguyên

#### Scenario: Không có citations trong response
- **WHEN** LLM response không chứa bất kỳ pattern `[N]` nào
- **THEN** Middleware SHALL KHÔNG inject ảnh

---

### Requirement: Streaming mode image injection
Image injection SHALL hoạt động trong streaming mode bằng cách accumulate response text, sau đó inject image SSE chunks SAU stream kết thúc, TRƯỚC quota warning injection.

#### Scenario: Streaming response có citations và source ảnh
- **WHEN** streaming response kết thúc, accumulated text chứa `[1]`, source "1" có ảnh
- **THEN** Middleware SHALL yield thêm SSE data chunk chứa image section Markdown, trước `data: [DONE]`

#### Scenario: Streaming buffer vượt giới hạn
- **WHEN** accumulated response text vượt 200KB
- **THEN** Middleware SHALL disable image injection cho request đó (log warning)

---

### Requirement: Non-streaming mode image injection
Image injection SHALL hoạt động trong non-streaming mode bằng cách modify response content trước khi return JSONResponse.

#### Scenario: Non-streaming response có citations và source ảnh
- **WHEN** LLM JSON response nhận được, `choices[0].message.content` chứa `[1]`, source "1" có ảnh
- **THEN** Middleware SHALL append image section vào `content`, TRƯỚC quota/routing warning

---

### Requirement: Feature toggle và configuration
Image injection feature SHALL được điều khiển qua environment variables.

#### Scenario: Feature disabled
- **WHEN** env var `MW_RAG_IMAGE_INJECT` = `false`
- **THEN** Middleware SHALL skip toàn bộ image extraction và injection logic

#### Scenario: Default enabled
- **WHEN** env var `MW_RAG_IMAGE_INJECT` không được set
- **THEN** Feature SHALL enabled by default

#### Scenario: Max images configurable
- **WHEN** env var `MW_RAG_IMAGE_MAX` = `2`
- **THEN** Middleware SHALL inject tối đa 2 ảnh per response (thay vì default 3)
