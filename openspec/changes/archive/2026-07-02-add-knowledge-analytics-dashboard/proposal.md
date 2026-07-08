## Why

Admins can see *that* RAG works (the shipped RAG Health Monitor surfaces ingestion/retrieval/storage anomalies) but not *whether the knowledge itself is worth the effort* — which knowledge bases are actually used, which sit dead, who owns them, and where storage is being wasted on duplicate uploads. With a growing corpus (already 122 files across 3 KBs, heading toward 200 users), there is no view that turns the OpenWebUI knowledge/file tables into an adoption-and-value signal admins can act on. This is Section 2.3 item #7 ("Knowledge Analytics") of `docs/saas_platform_exploration.md`; its blocking dependency (OpenWebUI DB access strategy) is already resolved in production by the RAG Health Monitor.

## What Changes

- Add a new **Knowledge** tab to the middleware dashboard SPA with three panels:
  - **Inventory & Growth** — corpus totals (KBs, files, chunks, storage), KB/file growth over time, file-type and size distribution.
  - **KB Value Matrix** — classify each KB as **Star** / **Needs-tuning** / **Dead-knowledge** / **Unproven** from four signals: demand (attach count), quality (citation hit-rate), supply (#files/#chunks/size), and freshness (created/updated/last-attached).
  - **Governance** — duplicate files (same `file_hash` across KBs = storage waste), orphaned/ad-hoc files (no KB membership), owner concentration, and per-owner footprint.
- Add read-only, admin-only API endpoints under `/v1/_mw/knowledge-analytics/*` that query the OpenWebUI DB (via the existing unpooled `psycopg2` + short-TTL cache pattern) and the middleware `mw_request_log`.
- Derive KB↔usage linkage by extracting `Filename:` / `Source:` markers embedded in logged `<source>` content and matching them to `file.filename`, rolled up to a KB via `file.meta.data.knowledge_id`.
- No schema migrations, no changes to the request/response hot path — purely additive.

## Capabilities

### New Capabilities
- `knowledge-analytics`: Admin-facing analytics over the OpenWebUI knowledge corpus — inventory/growth metrics, a per-KB value classification combining usage-demand with citation-quality, and governance signals (duplicates, orphans, ownership) — served read-only from OpenWebUI DB plus middleware request logs and rendered as a dedicated dashboard tab.

### Modified Capabilities
<!-- None. rag-health-monitor stays as-is; this change reuses its DB-access pattern and retrieval hit-rate logic without changing its requirements. -->

## Impact

- **New code**: `llm-mw/core/knowledge_analytics.py` (queries + TTL cache), `llm-mw/api/knowledge_analytics.py` (endpoints), `llm-mw/dashboard/js/knowledge.js` (tab module).
- **Modified code**: `llm-mw/main.py` (route registration), `llm-mw/dashboard/index.html` (new tab + panels), `llm-mw/dashboard/js/tabs.js` and `js/main.js` (tab wiring).
- **Data sources (read-only)**: OpenWebUI DB tables `knowledge`, `file` (esp. `meta` JSON: `content_type`, `size`, `file_hash`, `data.knowledge_id`, `collection_name`), `document_chunk`, `"user"`; middleware `mw_request_log` JSONB.
- **Dependencies**: none new. Reuses `rag_health` retrieval hit-rate computation and the OW-DB access precedent from `core/identity.py` / `core/rag_health.py`.
- **Known limitations (from data-driven spike)**: KB attribution is ambiguous when the same filename/hash exists in multiple KBs; usage is only observable for chats logged in `mw_request_log`; low current data volume (3 KBs) makes early numbers sparse.
