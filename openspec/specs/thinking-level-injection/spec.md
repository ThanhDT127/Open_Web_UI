# thinking-level-injection

## Requirements

1. Middleware MUST inject provider-specific thinking/reasoning parameters vào request body khi model là auto-routing model.
2. Thinking level MUST map theo tier đã resolve:
   - SIMPLE → lowest thinking (MINIMAL/low)
   - MEDIUM → balanced (MEDIUM/medium)
   - COMPLEX/REASONING → deepest (HIGH/high)
3. Provider parameter format:
   - Gemini: `thinking_config.thinking_level` (MINIMAL/LOW/MEDIUM/HIGH)
   - OpenAI: `reasoning.effort` (low/medium/high)
   - Claude: `thinking.type: adaptive` + `thinking.effort` (low/medium/high)
   - Grok: Controlled by model variant (reasoning vs non-reasoning), no parameter needed
   - DeepSeek: Built-in reasoning, no parameter needed
4. Thinking params MUST NOT be injected for non-auto-model requests (direct model selection).
5. LiteLLM MUST pass-through these params to providers without modification.
6. If LiteLLM drops a param (unsupported), the request MUST still succeed (graceful degradation).
