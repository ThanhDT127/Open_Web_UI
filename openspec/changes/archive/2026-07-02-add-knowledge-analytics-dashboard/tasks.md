## 1. Spike verification (larger dataset)

- [x] 1.1 Re-run the filename-linkage spike on a fuller dataset: measure the `Source:`/`Filename:` marker → `file.filename` match rate after normalization (strip extension/whitespace, case-fold); record unmatched ("unattributed") share
- [x] 1.2 Confirm `file.meta.data.knowledge_id` coverage vs `knowledge_file`, and `file.meta.collection_name` = `document_chunk.collection_name` on real rows; note any KBs where linkage breaks
- [x] 1.3 Lock threshold constants: high/low demand cutoffs, low-hit-rate cutoff, and the Unproven sample-size floor (document defaults; decide fixed-const vs `mw_config`)

## 2. Backend — inventory & membership (`core/knowledge_analytics.py`)

- [x] 2.1 Add `_openwebui_database_url()` + unpooled read-only connection helper (mirror `core/rag_health.py`), plus a short-TTL cache wrapper for heavy OW-DB reads
- [x] 2.2 Implement `query_inventory()` — totals (KBs, files, chunks, storage bytes), created-over-time series, and `content_type`/size distributions from `file.meta`
- [x] 2.3 Implement KB membership resolution keyed on `file.meta.data.knowledge_id`; per-KB chunk counts via `file.meta.collection_name` ↔ `document_chunk.collection_name`
- [x] 2.4 Resolve owner names from the OpenWebUI `"user"` table for use across all panels

## 3. Backend — usage linkage & value (`core/knowledge_analytics.py`)

- [x] 3.1 Implement `extract_attachment_filenames(body)` — regex `Filename:`/`Source:` markers from `mw_request_log` `chat.request` payloads; exclude template-only `<source id=` matches
- [x] 3.2 Implement `query_kb_usage(start, end)` — match extracted filenames to files, roll up attach counts per KB, capture last-attached timestamp and an unattributed bucket
- [x] 3.3 Compute per-KB citation hit-rate (quality) by pairing `chat.request`/`chat.response` for that KB's attachments (reuse rag-health's `[N]`-marker citation logic)
- [x] 3.4 Implement `classify_kb_value()` — Star / Needs-tuning / Dead-knowledge / Unproven from demand × quality with the sample-size floor
- [x] 3.5 Flag ambiguous KB attribution when a matched filename/hash belongs to more than one KB

## 4. Backend — governance (`core/knowledge_analytics.py`)

- [x] 4.1 Implement duplicate detection grouped by `file.meta.file_hash` (copy count, per-copy size, KBs involved, reclaimable bytes)
- [x] 4.2 Implement orphan/ad-hoc file reporting (files with no `knowledge_id`: count + storage footprint)
- [x] 4.3 Implement owner-concentration rollup (per-owner KB count, file count, storage bytes; names resolved in 2.4)

## 5. API endpoints (`api/knowledge_analytics.py`)

- [x] 5.1 Add admin-guarded routes under `/v1/_mw/knowledge-analytics/` (inventory, kb-value, governance) with `require_admin_or_session` and a shared `_parse_range` date filter (reuse rag-health pattern)
- [x] 5.2 Return graceful `{"error": ...}` / empty shapes on OW-DB failure and empty corpus; honor a `refresh` flag to bypass cache
- [x] 5.3 Register routes in `llm-mw/main.py`

## 6. Dashboard frontend

- [x] 6.1 Add "Knowledge" tab markup + panels (Inventory & Growth, KB Value Matrix, Governance) with date-range filter to `dashboard/index.html`
- [x] 6.2 Create `dashboard/js/knowledge.js` — fetch via `mwFetch`, render stat cards, growth/type charts (Chart.js lazy-init like `raghealth.js`), KB value table, and governance tables
- [x] 6.3 Wire the tab in `dashboard/js/tabs.js` (load-on-switch) and expose apply/reset via `window` in `dashboard/js/main.js`
- [x] 6.4 Add UI disclosures: usage = logged chats only; KB attribution ambiguous for shared filenames; sparse-data note

## 7. Tests & docs

- [x] 7.1 Unit-test the pure helpers: filename extraction (incl. template-only exclusion), normalization/matching, membership resolution, and value classification (Star/Needs-tuning/Dead/Unproven boundaries)
- [x] 7.2 Smoke-test each endpoint for admin-guard rejection, empty-corpus safety, and cache reuse
- [x] 7.3 Update `docs/08-dashboard.md` with the Knowledge tab; note the known limitations and the `knowledge_file`-vs-`file.meta` membership divergence as a follow-up
