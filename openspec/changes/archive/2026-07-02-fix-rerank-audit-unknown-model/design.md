# Design: Fix Rerank/Embeddings Audit Double-Logging

## Context

The middleware audits LLM traffic via a contract: endpoint handlers call `init_audit_state()` early, set usage with `set_usage_state()`, and the HTTP middleware (`log_requests` in `main.py`) writes a single audit row at request completion via `audit_from_request()` — dual-written to `audit.jsonl` and the `mw_audit_log` Postgres table. The dashboard (`/v1/_mw/summary` → `summary_v2.py`) aggregates that table; NULL `model`/`user_id` render as `"unknown"` (`summary_v2.py:42-43`).

Two handlers violate the contract, each producing a duplicate audit row per request:

**Rerank (`api/rerank.py`)** — "unknown" *model*:
1. Line 62 sets `request.state.mw_request_id = rid` manually, before `init_audit_state`.
2. `init_audit_state(..., endpoint="/v1/rerank")` early-returns because `/v1/rerank` is missing from `LLM_ENDPOINT_ALLOWLIST` (`core/audit_state.py:16-23`) — `mw_model`, `mw_user_id`, `mw_endpoint` never set.
3. `set_usage_state()` still stores tokens/cost on `request.state`.
4. `has_audit_state()` only checks `mw_request_id` — true because of step 1 — so the middleware writes a row with `model=NULL`, full cost.
5. The handler *also* writes its own line (line 172) with correct model but non-standard `endpoint="rerank"`.

**Embeddings (`api/embeddings.py`)** — "unknown" *user*:
- `/v1/embeddings` IS in the allowlist, so the middleware row is fully correct.
- But lines 143-155 *also* write a manual line with wrong keys: `"user"` instead of `"user_id"` (what `insert_audit_log` reads, `db.py:545`), `"prompt_tokens"/"completion_tokens"` instead of `"tokens_in"/"tokens_out"/"tokens_total"`, and non-standard `endpoint="embeddings"`. Result: rows with `user_id=NULL`, `tokens=0`, duplicated cost.

Production data confirms both (exact cost mirroring between duplicate and correct rows):

| user_id | endpoint | model | rows | cost |
|---|---|---|---|---|
| unknown | `/v1/rerank` | NULL | 263 | $0.5290 |
| admin | `rerank` | cohere/rerank-* | 144 | $0.5290 |
| NULL | `embeddings` | gemini-embedding-* | 625 | $0.1985 |
| admin | `/v1/embeddings` | gemini-embedding-* | 662 | $0.1985 |

New embedding traffic stopped when the system switched to a local embedding model (bypasses middleware), but the historical NULL-user rows persist — hence "unknown" still shows in the dashboard.

Secondary defect: rerank pricing looks up `prices.json` by the client-sent model name (`cohere/rerank-v3.5`, sometimes with `openrouter/` prefix), but the only rerank key present is `rerank-cohere-fast`, so every request silently falls through to the hard-coded `RERANK_COST_PER_1M = 2.0` fallback.

## Goals / Non-Goals

**Goals:**
- Exactly one audit row per rerank/embeddings request, with correct `model`, `user_id`, canonical endpoint path, tokens, and cost.
- No new "unknown" model/user rows from these endpoints going forward.
- Rerank cost priced from `prices.json` by actual model name; fallback rate only when the model is genuinely unlisted.
- One-off cleanup of historical duplicate rows so the dashboard is correct immediately.

**Non-Goals:**
- Adding a "rerank" call-type counter to dashboard totals (`chat_calls`, `embedding_calls`, …) — separate UI/API change if wanted later.
- Rewriting `has_audit_state()` semantics — a warning log in `init_audit_state` gives the diagnostic value without touching every endpoint's assumptions.
- Cleaning historical entries inside rotated `audit.jsonl` files (DB is primary; file fallback only matters when the DB pool is down).
- Quota reconciliation — `update_user_quota` was always called exactly once per request; only the audit trail double-counted.

## Decisions

**D1 — Fix by joining the audit contract, not by patching around it.**
Rerank: add `/v1/rerank` to `LLM_ENDPOINT_ALLOWLIST`, pass `rid` via `init_audit_state(rid=rid)`, delete the manual `mw_request_id` assignment and manual `write_audit_line()`. Embeddings: delete the manual `write_audit_line()` block (middleware row already correct). The middleware becomes the single writer for both, same as chat/images.
*Alternative:* keep manual lines and suppress middleware writes with `mark_audit_logged()`. Rejected — perpetuates non-standard endpoint labels (`rerank`, `embeddings`) and leaves handlers responsible for audit-field completeness, which is exactly how the embeddings key-mismatch bug happened.

**D2 — Harden `init_audit_state` failure mode (small, contained).**
When the endpoint is not in the allowlist, `init_audit_state` currently returns `""` silently. Log a warning in that branch so a future endpoint added without an allowlist entry shows up in logs instead of producing NULL-field audit rows.
*Alternative:* make `has_audit_state()` also require `mw_user_id`. Rejected for this change — wider blast radius, same diagnostic value.

**D3 — Price lookup: normalize then look up; keep fallback.**
In `_calc_rerank_cost`, strip the `openrouter/` prefix before the `prices.json` lookup (the upstream call already strips it for the request body), and add entries keyed by served model names: `cohere/rerank-v3.5`, `cohere/rerank-4-fast` (both $2.00/1M input, matching the existing `rerank-cohere-fast` estimate).
*Alternative:* alias table mapping model → price key. Rejected — keying `prices.json` by real model names matches how chat models are keyed.

*Implementation note:* `load_prices()` prefers the `mw_prices` DB table over `prices.json`, and the JSON is only imported when `mw_users` is empty (initial migration). Editing `prices.json` alone does not change runtime pricing — the new rerank entries were also inserted into `mw_prices` directly (`INSERT ... ON CONFLICT DO NOTHING`).

**D4 — Data cleanup as an idempotent SQL script, not a migration framework.**
Repo precedent: one-off scripts like `migrate_rag_base64_to_local_media.py`. Cleanup, in one transaction, printing affected counts:
1. `DELETE FROM mw_audit_log WHERE endpoint = '/v1/rerank' AND model IS NULL;` — duplicate middleware rows; cost fully carried by paired `endpoint='rerank'` rows. **Must run before step 2** (while `endpoint='rerank'` still distinguishes the keepers).
2. `UPDATE mw_audit_log SET endpoint = '/v1/rerank' WHERE endpoint = 'rerank';` — normalize legacy labels.
3. `DELETE FROM mw_audit_log WHERE endpoint = 'embeddings';` — duplicate manual rows (all NULL user, zero tokens); correct rows live under `/v1/embeddings`.
All statements are idempotent (re-run is a no-op).

## Risks / Trade-offs

- **[Risk] Deleting rows from `mw_audit_log` is destructive** → targets are provably duplicates (cost sums mirror paired rows exactly); script runs in a transaction and prints counts before commit. Optionally `pg_dump -t mw_audit_log` first.
- **[Risk] A client could call `/v1/rerank` or `/v1/embeddings` without a `model` field** → `body.get("model", "unknown")` default remains; such a request is audited as model `"unknown"` *once*, which is accurate. Current callers (Open WebUI RAG) always send a model.
- **[Risk] Something downstream might depend on the legacy `endpoint='rerank'` / `endpoint='embeddings'` labels** → checked: `summary.py`/`summary_v2.py` `LLM_ENDPOINTS` maps use `/v1/...` paths only; the legacy labels were never counted in type breakdowns. Normalizing only makes them consistent.
- **[Trade-off] Rerank stays out of `llm_calls_total` and type counters** — `LLM_ENDPOINTS` maps don't include `/v1/rerank`; its cost still appears in totals and model breakdown. Unchanged from today; explicit non-goal.

## Migration Plan

1. Deploy code changes (allowlist + rerank.py + embeddings.py + prices.json) — middleware container restart.
2. Run cleanup script against the `middleware` DB (idempotent, transactional).
3. Verify:
   - Dashboard TopModel has no "unknown" model; TopUsers has no "unknown" user.
   - `SELECT endpoint, model, user_id, count(*) FROM mw_audit_log WHERE endpoint LIKE '%rerank%' OR endpoint LIKE '%embedding%' GROUP BY 1,2,3;` shows only `/v1/...` endpoints with non-NULL model and user.
   - Trigger one RAG rerank query and confirm exactly one new audit row with correct model/user/cost.

Rollback: revert the code commit. Deleted duplicate rows are not restored, but they carried no unique information.
