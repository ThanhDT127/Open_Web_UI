## Context

Smart Routing v1 đã hoạt động: keyword heuristic scoring → 4 tiers (SIMPLE/MEDIUM/COMPLEX/REASONING) → chọn model concrete per provider. Tuy nhiên:
1. **Thiếu thinking control**: Tất cả request dùng default thinking level bất kể tier
2. **Heuristic accuracy ~75%**: Câu ngắn nhưng phức tạp ("prove P≠NP") bị route sai sang SIMPLE

### Hiện trạng code
- `core/smart_routing.py`: `PROVIDER_TIERS`, `score_complexity()`, `resolve_auto_model()`
- `api/chat.py`: Gọi `resolve_auto_model()` → set `body["model"]`
- `_normalize_provider_params()`: Đã có logic per-provider (GPT-5 max_tokens, Claude temp clamp)

## Goals / Non-Goals

**Goals:**
- Inject thinking/reasoning parameters tự động theo tier
- Nâng accuracy routing từ ~75% lên ~90% cho ambiguous cases
- Giữ backward compatibility — requests không dùng auto-model không bị ảnh hưởng

**Non-Goals:**
- Cascade routing (try cheap → escalate) — để Change 4
- User-facing routing preferences — để sau
- Thay đổi tier mapping (model list) — giữ nguyên từ v1

## Decisions

### 1. Thinking parameter injection — Per-provider mapping table

**Decision**: Thêm `PROVIDER_THINKING` dict trong `smart_routing.py`, map tier → provider-specific params.

**Rationale**: Mỗi provider dùng key khác nhau (Gemini: `thinking_config.thinking_level`, OpenAI: `reasoning.effort`, Claude: `thinking.type` + `thinking.effort`). Centralize mapping để dễ maintain.

**Implementation**:
```python
PROVIDER_THINKING = {
    "openai-auto": {
        "SIMPLE": {"reasoning": {"effort": "low"}},
        "MEDIUM": {"reasoning": {"effort": "medium"}},
        "COMPLEX": {"reasoning": {"effort": "high"}},
        "REASONING": {"reasoning": {"effort": "high"}},
    },
    "gemini-auto": {
        "SIMPLE": {"thinking_config": {"thinking_level": "MINIMAL"}},
        "MEDIUM": {"thinking_config": {"thinking_level": "MEDIUM"}},
        "COMPLEX": {"thinking_config": {"thinking_level": "HIGH"}},
        "REASONING": {"thinking_config": {"thinking_level": "HIGH"}},
    },
    "claude-auto": {
        "SIMPLE": {"thinking": {"type": "adaptive", "effort": "low"}},
        "MEDIUM": {"thinking": {"type": "adaptive", "effort": "medium"}},
        "COMPLEX": {"thinking": {"type": "adaptive", "effort": "high"}},
        "REASONING": {"thinking": {"type": "adaptive", "effort": "high"}},
    },
    # Grok: reasoning controlled by model variant, not params
    # DeepSeek: built-in reasoning, no separate params
}
```

**Alternative rejected**: Single `reasoning_effort` key for all providers → LiteLLM doesn't auto-translate for all cases.

### 2. LLM Classifier — Gemini 2.5 Flash as classifier

**Decision**: Dùng `chat-gemini-2.5-flash` (model rẻ nhất) với prompt cố định ~100 tokens. Chỉ gọi khi heuristic score = 3-7.

**Rationale**:
- Cost: ~$0.00005/call
- Latency: ~100-200ms
- 60-70% requests có score rõ ràng (≤2 hoặc ≥8) → skip classifier = free + 0 latency
- Classifier chỉ cần trả 1 từ: SIMPLE/MEDIUM/COMPLEX/REASONING

**Classifier prompt**:
```
Classify this user request complexity. Reply with exactly one word: SIMPLE, MEDIUM, COMPLEX, or REASONING.

SIMPLE: casual chat, greeting, short factual question
MEDIUM: explanation, comparison, moderate analysis
COMPLEX: deep analysis, design, coding, multi-step problem
REASONING: mathematical proof, formal logic, step-by-step derivation

User request: {prompt_preview}
```

**Fallback**: Nếu classifier call fail (timeout/error) → dùng heuristic result.

### 3. Injection point — After routing, inside `_normalize_provider_params`

**Decision**: Inject thinking params trong `_normalize_provider_params()` sau khi model đã được resolve.

**Rationale**: Function này đã handle per-provider normalization. Thêm thinking injection ở đây giữ logic tập trung.

## Risks / Trade-offs

- **[Classifier latency]** +100-200ms cho 30-40% requests → Mitigation: chỉ gọi khi ambiguous, timeout 2s
- **[Thinking cost]** Tier HIGH tăng ~20-50% output tokens → Mitigation: chỉ áp dụng cho COMPLEX/REASONING, SIMPLE dùng MINIMAL
- **[LiteLLM pass-through]** Một số param có thể bị drop → Mitigation: test từng provider, dùng `drop_params: true` trong LiteLLM config
- **[Classifier accuracy]** LLM classifier vẫn có thể sai → Mitigation: log mọi decision để audit, có thể tune prompt
