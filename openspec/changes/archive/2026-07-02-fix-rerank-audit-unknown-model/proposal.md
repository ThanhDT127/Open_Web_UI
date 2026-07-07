# Fix Rerank/Embeddings Audit Double-Logging and "unknown" Entries in Dashboard

## Why

Rerank and embeddings requests are each written to the audit trail **twice** — once by the HTTP middleware and once manually by the endpoint handler — producing "unknown" entries in the dashboard and double-counted cost. Two distinct failure modes, same root pattern (handlers bypassing the audit-state contract):

- **Rerank**: `/v1/rerank` is missing from `LLM_ENDPOINT_ALLOWLIST`, so `init_audit_state` early-returns without setting model/user/endpoint; but the handler pre-sets `mw_request_id` (the only thing `has_audit_state()` checks), so the middleware still writes a row with `model=NULL` → TopModel shows **"unknown" model** whose cost exactly equals total rerank spend (production: $0.5290 NULL rows vs $0.5290 correct rows).
- **Embeddings**: `/v1/embeddings` IS in the allowlist so the middleware row is correct, but the handler *also* writes a manual audit line with wrong field keys — `"user"` instead of `"user_id"`, `"prompt_tokens"` instead of `"tokens_in"/"tokens_total"` — producing rows with `user_id=NULL`, `tokens=0`, duplicated cost → TopUsers shows an **"unknown" user** carrying ~$0.1985 of Gemini embedding cost (production: 625 NULL-user rows mirroring 662 correct rows).

## What Changes

- Add `/v1/rerank` to `LLM_ENDPOINT_ALLOWLIST` in `core/audit_state.py` so rerank audit state is fully initialized.
- In `api/rerank.py`: remove the manual `request.state.mw_request_id = rid` assignment (pass `rid` via `init_audit_state(rid=...)`) and remove the manual `write_audit_line(...)` block — the middleware becomes the single audit writer.
- In `api/embeddings.py`: remove the manual `write_audit_line(...)` block (the middleware row is already correct and complete).
- Log a warning in `init_audit_state` when called with an endpoint not in the allowlist, so future endpoints can't silently produce NULL-field audit rows.
- Fix rerank price lookup: strip `openrouter/` prefix before lookup and add `prices.json` entries keyed by actual served model names (`cohere/rerank-v3.5`, `cohere/rerank-4-fast`); keep $2/1M fallback as documented last resort.
- One-off idempotent cleanup of `mw_audit_log`: delete duplicate rerank rows (`endpoint='/v1/rerank' AND model IS NULL`), delete duplicate embedding rows (`endpoint='embeddings'`), normalize legacy `endpoint='rerank'` → `/v1/rerank`.

## Capabilities

### New Capabilities

- `usage-audit-integrity`: Every LLM proxy request (chat, embeddings, rerank, images, audio, video) produces exactly one audit row with correct user, model, endpoint, tokens, and cost; audit rows are written only by the middleware via the audit-state contract; rerank cost is priced from `prices.json` by actual model name with a documented fallback.

### Modified Capabilities

<!-- No existing spec covers audit logging or usage tracking; no delta specs needed. -->

## Impact

- `llm-mw/core/audit_state.py` — allowlist gains `/v1/rerank`; warning on non-allowlisted init.
- `llm-mw/api/rerank.py` — remove manual rid assignment + manual audit line; unused `write_audit_line` import removed.
- `llm-mw/api/embeddings.py` — remove manual audit line; unused `write_audit_line` import removed.
- `llm-mw/prices.json` — add rerank model price entries.
- `mw_audit_log` table (Postgres `middleware` DB) — one-off cleanup script (`llm-mw/` root, alongside existing migration scripts).
- Dashboard (no code change): "unknown" model and "unknown" user disappear; `cost_total_usd` drops by the previously double-counted rerank (~$0.53) and embedding (~$0.20) spend.
