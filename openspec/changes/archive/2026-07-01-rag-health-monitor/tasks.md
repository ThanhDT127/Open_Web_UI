## 1. Spikes (resolve open questions before building on top of them)

- [x] 1.1 Verify whether OpenWebUI's `<source id="N">` tags carry a knowledge-base-level identifier vs. only a source-document identifier; decide per-KB vs. per-source-document grouping for the retrieval breakdown accordingly
- [x] 1.2 Query a real dataset to assess `vmetadata` reliability as a join key between `document_chunk` and `file`/`knowledge_file`; decide whether outlier/orphan detection can be per-file or must fall back to per-collection aggregates

## 2. Ingestion Health (backend)

- [x] 2.1 Add a query function reading `mw_audit_log` for embeddings-endpoint calls within a date range (count, failure rate, avg latency)
- [x] 2.2 Add a query function for recent embedding failures (timestamp, user, error_type, error_message)
- [x] 2.3 Expose both via a new API route (e.g. `GET /dashboard/api/rag-health/ingestion`)

## 3. Retrieval Health (backend)

- [x] 3.1 Write a JSONB query joining `chat.request`/`chat.response` event pairs in `mw_request_log` by request correlation (confirm what key ties them together, e.g. request id)
- [x] 3.2 Implement `<source id="N">` detection against the joined request payload (reuse/port the regex from `llm-mw/api/chat.py:732`, independent of `MW_RAG_IMAGE_INJECT`)
- [x] 3.3 Implement `[N]` citation-marker detection against the logged response text (reuse/port the regex from `llm-mw/api/chat.py:1313`/`1497`)
- [x] 3.4 Compute hit-rate aggregate, breakdown by model, and breakdown by knowledge base (per outcome of task 1.1)
- [x] 3.5 Compute zero-citation messages list (timestamp, user, question preview)
- [x] 3.6 Expose via a new API route (e.g. `GET /dashboard/api/rag-health/retrieval`)

## 4. Storage Health (backend)

- [x] 4.1 Add a read-only OpenWebUI DB query module following the unpooled `psycopg2.connect()` pattern in `llm-mw/core/identity.py`
- [x] 4.2 Implement zero-chunk knowledge base detection query
- [x] 4.3 Implement orphaned chunk detection query (per outcome of task 1.2)
- [x] 4.4 Implement chunk-count outlier detection query (per outcome of task 1.2)
- [x] 4.5 Add short-TTL server-side caching for storage-health query results to limit connection frequency
- [x] 4.6 Expose via a new API route (e.g. `GET /dashboard/api/rag-health/storage`)

## 5. Dashboard UI

- [x] 5.1 Add "RAG Health" tab to the dashboard SPA navigation
- [x] 5.2 Build date-range/model/user filter controls shared across the tab
- [x] 5.3 Build Ingestion section: metric cards, failure-rate-over-time chart, recent-failures table
- [x] 5.4 Build Retrieval section: metric cards, hit-rate-over-time chart, per-model bar chart, per-KB table, zero-citation-messages table
- [x] 5.5 Build Storage section: metric cards, zero-chunk-KBs table, orphaned-chunks table, chunk-count-outliers table

## 6. Verification

- [x] 6.1 Manually verify ingestion metrics against known embedding failures in a test/staging `mw_audit_log`
- [x] 6.2 Manually verify retrieval hit-rate against a handful of known KB-attached chats (spot-check citations by hand)
- [x] 6.3 Manually verify storage anomalies against a deliberately-created zero-chunk KB and/or orphaned chunk in a test OpenWebUI DB
- [x] 6.4 Confirm no new pooled connection was introduced and OW DB connection count stays stable under normal dashboard usage
