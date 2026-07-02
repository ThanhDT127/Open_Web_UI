## Why

Smart Routing v1 chỉ đổi model theo tier nhưng **không điều chỉnh thinking depth**. Tất cả request đều dùng default thinking level → lãng phí token reasoning cho câu đơn giản, và thiếu suy luận sâu cho câu phức tạp. Ngoài ra, heuristic scoring (regex + point) chỉ đạt ~70-80% accuracy — cần bổ sung LLM classifier cho các trường hợp mập mờ.

## What Changes

- **Inject thinking parameters theo tier**: Middleware tự động thêm `thinking_config` (Gemini), `reasoning.effort` (OpenAI), `thinking` (Claude) vào request body tương ứng với tier đã chọn (SIMPLE→MINIMAL/low, COMPLEX→HIGH/high).
- **LLM classifier cho ambiguous cases**: Khi heuristic scoring ra điểm 3-7 (không rõ ràng), gọi `chat-gemini-2.5-flash` để classify intent trước khi route. Cases rõ ràng (≤2 hoặc ≥8) vẫn đi fast-path.
- **Thinking level config table**: Thêm mapping table `PROVIDER_THINKING` vào `smart_routing.py` để dễ maintain.

## Capabilities

### New Capabilities
- `thinking-level-injection`: Inject provider-specific thinking/reasoning parameters vào request body theo tier routing. Hỗ trợ Gemini (thinking_level), OpenAI (reasoning.effort), Claude (thinking.type adaptive + effort). Grok và DeepSeek dùng model variant thay vì parameter.
- `llm-classifier-routing`: Sử dụng LLM nhỏ (Gemini 2.5 Flash) để phân loại complexity cho ambiguous requests (heuristic score 3-7), nâng accuracy từ ~75% lên ~90%+.

### Modified Capabilities
<!-- No existing spec-level behavior changes. -->

## Impact

- **`llm-mw/core/smart_routing.py`**: Thêm `PROVIDER_THINKING` mapping table, thêm `classify_with_llm()` function, sửa `resolve_auto_model()` trả thêm thinking config.
- **`llm-mw/api/chat.py`**: Sửa `_normalize_provider_params()` để inject thinking params từ routing result.
- **LiteLLM**: Không cần thay đổi — pass-through `thinking_config`, `reasoning`, `thinking` tự động.
- **Cost**: LLM classifier ~$0.00005/call (chỉ 30-40% requests). Thinking tokens ở tier HIGH thêm ~20-50% cost nhưng chất lượng cao hơn rõ rệt.
