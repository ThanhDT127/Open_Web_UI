# Tasks — smart-routing-v2-thinking

## Thinking Level Injection
- [x] 1. Thêm `PROVIDER_THINKING` mapping table vào `core/smart_routing.py` ✅
- [x] 2. Sửa `resolve_auto_model()` trả thêm thinking config dict ✅
- [x] 3. Sửa `chat.py` — inject thinking params từ routing result + await ✅
- [x] 4. Test Gemini: `thinking_config.thinking_level: MINIMAL` ✅
- [x] 5. Test OpenAI: `reasoning.effort: medium` ✅
- [x] 6. Test Claude: `thinking: adaptive, effort: high` ✅

## LLM Classifier
- [x] 7. Thêm `classify_with_llm()` function vào `core/smart_routing.py` ✅
- [x] 8. Integrate classifier vào `resolve_auto_model()` — gọi khi score 3-7 ✅
- [x] 9. Test classifier: verified heuristic gating works (score 3 triggers classifier) ✅
- [x] 10. Test fallback: classifier timeout → dùng heuristic result ✅

## Deploy & Verify
- [x] 11. Docker build + restart ✅
- [x] 12. End-to-end: simple → SIMPLE + MINIMAL thinking ✅
- [x] 13. End-to-end: complex → MEDIUM + medium reasoning ✅ (REASONING → HIGH ✅)
- [x] 14. Audit log: tier + thinking params logged in smart_route ✅
