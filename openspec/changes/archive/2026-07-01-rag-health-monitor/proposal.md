## Why

Admins have no visibility into whether the RAG pipeline is actually working: embedding calls can fail silently, knowledge-base retrieval can attach a source but produce zero citations, and vector storage can accumulate orphaned or under-populated chunks — none of this is currently surfaced anywhere. The data needed to detect all three failure modes already exists in `mw_audit_log`, `mw_request_log`, and the OpenWebUI `document_chunk`/`file`/`knowledge_file` tables; it's just never been queried or displayed.

## What Changes

- Add a new **RAG Health** tab to the middleware dashboard with three sections: Ingestion, Retrieval, Storage.
- **Ingestion health**: surface embedding-call failure rate, latency, and recent failures by mining existing `mw_audit_log` rows for `/v1/embeddings` calls (status/error columns already recorded).
- **Retrieval health**: compute a citation hit-rate metric — of chat messages where a knowledge base was attached (detected via `<source id="N">` tags in the logged request `messages`), what percentage produced a `[N]`-style citation marker in the logged response text. Break this down by model and by knowledge base, and surface a table of zero-citation messages for follow-up. Derived entirely from existing `mw_request_log.payload` JSONB (`chat.request` / `chat.response` events) — no new logging required.
- **Storage health**: surface zero-chunk knowledge bases (KB/files exist but no embedded chunks), orphaned chunks (vector rows whose `collection_name` has no matching `file`/`knowledge_file` record), and chunk-count outliers (files whose embedded chunk count looks anomalously low). Queried read-only, directly against the OpenWebUI database using the same ad-hoc `psycopg2.connect()` pattern already established in `llm-mw/core/identity.py` (no new pooled connection).
- New backend API endpoint(s) under the dashboard API to serve these three sections' data, plus corresponding dashboard SPA UI (new tab, charts, tables).

## Capabilities

### New Capabilities
- `rag-health-monitor`: Dashboard visibility into RAG pipeline health across ingestion (embedding failures), retrieval (citation hit-rate), and storage (orphaned/zero-chunk data) layers.

### Modified Capabilities
(none — this is purely additive; no existing capability's requirements change)

## Impact

- **Affected code**: `llm-mw/api/` (new route module, e.g. `rag_health.py`), `llm-mw/core/db.py` (read queries against `mw_audit_log`/`mw_request_log`), `llm-mw/core/identity.py`-style read-only OW DB access (new query functions, reusing the existing unpooled-connection pattern), `llm-mw/dashboard/` (new tab UI, charts, tables), `llm-mw/main.py` (route registration).
- **Dependencies**: None new — no new packages, no new infrastructure. Reuses existing JSONB payload data and the existing raw-connection pattern to the OpenWebUI DB.
- **Known caveats carried into design**: (1) whether OpenWebUI's `<source id=` tags carry a knowledge-base name/id distinct from the source document is unconfirmed — affects the per-KB breakdown table; (2) `document_chunk` has no FK to `file`/`knowledge_file`, so orphan/outlier detection relies on `collection_name` + `vmetadata` heuristics whose reliability is unverified; (3) the logged response text used for citation detection is truncated at 2000 characters, so very long answers with late citation markers could be missed; (4) a third ad-hoc raw connection to the OpenWebUI DB (beyond the two that already exist) adds incremental connection-exhaustion risk if the storage-health queries are run frequently — acceptable for now per explicit decision to defer pooling.
