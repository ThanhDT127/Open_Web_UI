# usage-audit-integrity

## ADDED Requirements

### Requirement: Single audit row per proxied LLM request
The middleware SHALL write exactly one audit record per proxied LLM request (chat, embeddings, rerank, images, audio, video), produced by the HTTP middleware via the audit-state contract (`init_audit_state` → `set_usage_state`/`set_error_state` → `audit_from_request`). Endpoint handlers SHALL NOT write audit lines directly for requests covered by the contract.

#### Scenario: Rerank request audited once
- **WHEN** a client sends `POST /v1/rerank` with model `cohere/rerank-v3.5` and the upstream call succeeds
- **THEN** exactly one row is written to `mw_audit_log` for that request ID, with `endpoint='/v1/rerank'`, `model='cohere/rerank-v3.5'`, the authenticated `user_id`, non-zero `tokens_total`, and the calculated `cost_usd`

#### Scenario: Embeddings request audited once
- **WHEN** a client sends `POST /v1/embeddings` with model `gemini-embedding-001` and the upstream call succeeds
- **THEN** exactly one row is written to `mw_audit_log` for that request ID, with `endpoint='/v1/embeddings'`, the correct model, the authenticated `user_id`, non-zero `tokens_total`, and the calculated `cost_usd`

### Requirement: Audit rows carry complete identity fields
Audit records for allowlisted LLM endpoints SHALL contain non-NULL `user_id`, `model`, and `endpoint` fields, so that dashboard aggregations never render synthetic "unknown" entries for traffic that carried this information.

#### Scenario: No unknown model in TopModel from rerank traffic
- **WHEN** the dashboard aggregates `mw_audit_log` after rerank requests have been processed
- **THEN** the model breakdown contains the actual rerank model names and no `"unknown"` model row attributable to rerank traffic

#### Scenario: No unknown user in TopUsers from embedding traffic
- **WHEN** the dashboard aggregates `mw_audit_log` after embedding requests have been processed
- **THEN** the user breakdown attributes all embedding cost to the authenticated user and contains no `"unknown"` user row attributable to embedding traffic

#### Scenario: Client omits model field
- **WHEN** a client sends a rerank or embeddings request without a `model` field in the body
- **THEN** the single audit row records model `"unknown"` (accurately reflecting the request) and all other fields are populated

### Requirement: Non-allowlisted audit initialization is observable
`init_audit_state` SHALL emit a warning log when called with an endpoint that is not in `LLM_ENDPOINT_ALLOWLIST`, identifying the endpoint, so that contract violations surface in logs instead of silently producing incomplete audit rows.

#### Scenario: Endpoint missing from allowlist
- **WHEN** an endpoint handler calls `init_audit_state` with an endpoint path absent from `LLM_ENDPOINT_ALLOWLIST`
- **THEN** a warning naming that endpoint path is written to the middleware log and no audit state is initialized

### Requirement: Rerank cost priced by actual model name
Rerank cost calculation SHALL look up `prices.json` by the request's model name after stripping any `openrouter/` prefix, and SHALL apply the hard-coded fallback rate only when the normalized model name has no price entry.

#### Scenario: Known rerank model priced from prices.json
- **WHEN** a rerank request for `cohere/rerank-v3.5` (or `openrouter/cohere/rerank-v3.5`) completes with N billed tokens and no upstream cost header
- **THEN** `cost_usd` equals N/1,000,000 × the `input_per_1m` rate of the `cohere/rerank-v3.5` entry in `prices.json`

#### Scenario: Unlisted rerank model uses fallback
- **WHEN** a rerank request for a model with no `prices.json` entry completes with N billed tokens and no upstream cost header
- **THEN** `cost_usd` equals N/1,000,000 × the documented fallback rate ($2.00/1M)

### Requirement: Historical duplicate audit rows are removed
A one-off, idempotent, transactional cleanup SHALL remove the historical duplicate audit rows and normalize legacy endpoint labels in `mw_audit_log`: duplicate rerank rows (`endpoint='/v1/rerank' AND model IS NULL`), duplicate embedding rows (`endpoint='embeddings'`), and legacy `endpoint='rerank'` rows renamed to `/v1/rerank` — deleting duplicates before renaming.

#### Scenario: Cleanup removes duplicates and preserves correct rows
- **WHEN** the cleanup script runs against a database containing the duplicate rows
- **THEN** rows with `endpoint='/v1/rerank' AND model IS NULL` and rows with `endpoint='embeddings'` are deleted, rows with `endpoint='rerank'` become `endpoint='/v1/rerank'`, all other rows are untouched, and the script reports affected row counts

#### Scenario: Cleanup is idempotent
- **WHEN** the cleanup script runs a second time
- **THEN** it reports zero affected rows and makes no changes
