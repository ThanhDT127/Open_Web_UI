# Tasks: fix-rerank-audit-unknown-model

## 1. Audit contract fixes

- [x] 1.1 Add `/v1/rerank` to `LLM_ENDPOINT_ALLOWLIST` in `llm-mw/core/audit_state.py`
- [x] 1.2 Add a warning log in `init_audit_state` when the endpoint is not in the allowlist (name the endpoint in the message)
- [x] 1.3 In `llm-mw/api/rerank.py`: remove the manual `request.state.mw_request_id = rid` assignment and pass `rid` via `init_audit_state(..., rid=rid)` (same fix applied to `embeddings.py`, whose manual rid was being silently replaced by a generated one)
- [x] 1.4 In `llm-mw/api/rerank.py`: remove the manual `write_audit_line(...)` block and the now-unused `write_audit_line` import (also added missing `Response` import used in the upstream-error path)
- [x] 1.5 In `llm-mw/api/embeddings.py`: remove the manual `write_audit_line(...)` block and the now-unused `write_audit_line` import

## 2. Rerank pricing

- [x] 2.1 In `_calc_rerank_cost` (`llm-mw/api/rerank.py`): strip the `openrouter/` prefix from the model name before the `prices.json` lookup
- [x] 2.2 Add `cohere/rerank-v3.5` and `cohere/rerank-4-fast` entries ($2.00/1M input, $0 output) to `llm-mw/prices.json` (also inserted into the `mw_prices` DB table, which is the runtime price source — see design.md D3 note)

## 3. Historical data cleanup

- [x] 3.1 Write idempotent cleanup script `llm-mw/cleanup_audit_duplicates.py` (single transaction, prints affected counts): delete `endpoint='/v1/rerank' AND model IS NULL`, then rename `endpoint='rerank'` → `/v1/rerank`, then delete `endpoint='embeddings'`
- [x] 3.2 Run the cleanup script against the `middleware` Postgres DB and record the reported row counts — done: 263 rerank duplicates deleted, 144 renamed to `/v1/rerank`, 625 embedding duplicates deleted (1032 rows total)
- [x] 3.3 Re-run the script to confirm idempotency (zero affected rows) — confirmed: 0 rows on second run

## 4. Verification

- [x] 4.1 Restart the middleware container and trigger one RAG rerank query; confirm exactly one new `mw_audit_log` row with `endpoint='/v1/rerank'`, correct model, user, tokens, and cost — verified: single row `rrk-f792ce6fb4b1`, model `cohere/rerank-v3.5`, user `admin`, 200 tokens, $0.0004
- [x] 4.2 Verify `init_audit_state` warning fires for a non-allowlisted endpoint (unit-level check or temporary test call) — verified via in-container unit check
- [x] 4.3 Verify dashboard: TopModel shows no "unknown" model, TopUsers shows no "unknown" user, and total cost reflects the removed double-counting — verified via `/v1/_mw/summary` (30-day window): models list contains only real model names, users list only `admin`, `cost_total_usd` $0.886 (previously included ~$0.73 double-counted)
- [x] 4.4 Verify rerank cost calculation uses the `prices.json` entry for `cohere/rerank-v3.5` — verified: `load_prices()` contains both keys, `openrouter/` prefix stripped, fallback only for unlisted models
