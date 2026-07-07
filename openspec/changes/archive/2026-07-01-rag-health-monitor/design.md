## Context

The middleware (`llm-mw/`) already logs everything needed for two of the three health layers, but nothing reads it back for this purpose:

- `mw_audit_log` (schema in `llm-mw/core/db.py:169-190`) records every proxied call including `/v1/embeddings`, with `status`, `status_code`, `error_type`, `error_message` columns.
- `mw_request_log` (`llm-mw/core/db.py:199-204`) stores a JSONB `payload` per `detail_log()` call. Two events matter here: `"chat.request"` (logs `body`, the full incoming request including `messages` — which contain OpenWebUI's `<source id="N">...</source>` tags when a knowledge base is attached) and `"chat.response"` (logs a 2000-char-truncated copy of the answer text, which retains any `[N]`-style citation markers the LLM produced, since logging happens before the middleware's own image-injection post-processing).
- `llm-mw/api/chat.py` already contains citation-detection logic (`_extract_rag_source_images` at line 732, regex `<source\s+id="(\d+)">` ; citation-marker regex `r'\[(\d+(?:\s*,\s*\d+)*)\]'` at lines 1313/1497) but only uses it transiently for image injection — it's never persisted as a structured field.

The third layer (storage health) requires reading OpenWebUI's own database (`document_chunk`, `file`, `knowledge_file` tables — schema documented in `docs/06-rag-architecture.md`). The middleware has no pooled connection to that database, by original design (`docs/saas_platform_exploration.md` Section 2.1). That doc is now stale: `llm-mw/core/identity.py:19` (`load_openwebui_users`, added 2026-06-16) already opens a second raw, unpooled `psycopg2.connect()` to the OpenWebUI DB for user-identity reconciliation, alongside the older one in `llm-mw/core/alerting.py:606`. No formal "Option A/B/C" architecture decision was ever made — direct read access grew organically. This design follows that established precedent rather than introducing a new pooled connection.

`document_chunk` has no foreign key to `file` or `knowledge_file` — the only link is `collection_name` plus whatever is stored in the `vmetadata` JSONB column. Orphan/outlier detection must use this as a heuristic join key.

## Goals / Non-Goals

**Goals:**
- Surface embedding ingestion failures using data already in `mw_audit_log`.
- Surface a citation hit-rate metric (KB attached → did the LLM cite anything) using data already in `mw_request_log`, independently re-derived from the raw JSONB rather than depending on the `MW_RAG_IMAGE_INJECT` feature flag or `request.state.rag_source_images`.
- Surface storage-level anomalies (zero-chunk KBs, orphaned chunks, chunk-count outliers) via read-only queries directly against the OpenWebUI DB.
- Ship all three sections in one change; none are blocked on a pending architecture decision.

**Non-Goals:**
- Retrieval *relevance* quality (e.g. "were the cited chunks actually the right ones") — this only measures whether citation happened at all, not whether it was correct.
- Any remediation actions (re-embedding a file, deleting orphaned chunks) — this is a read-only monitoring dashboard. Actions are a possible future change.
- Introducing a pooled connection to the OpenWebUI DB (Section 2.1's "Option A") — explicitly deferred; this change reuses the existing ad-hoc unpooled pattern.
- Historical backfill tooling — the retrieval metric is queryable over existing `mw_request_log` history for free, but no separate backfill job is being built.

## Decisions

**1. Retrieval health is computed by direct regex/JSONB query, not by reusing `chat.py`'s runtime detection.**
`_extract_rag_source_images` and the citation regex run per-request and their results are discarded after image injection. Re-running equivalent regexes against the persisted `mw_request_log.payload` (`payload->'body'->'messages'` for `<source id=`, `payload->>'content'` for `[N]` markers) keeps the dashboard decoupled from that feature's on/off state and lets it query historical data retroactively.
- Alternative considered: persist a `has_rag`/`citations` field at log-write time going forward. Rejected for now — it would only apply to future data, whereas the JSONB-scan approach works on everything already logged, and there's no other pressure to modify the hot request path.

**2. Storage health uses the existing unpooled `psycopg2.connect()` pattern (following `identity.py`), not a new pool.**
Confirmed via git history that this pattern is already in production use (`identity.py`, added 2026-06-16, backing a shipped dashboard feature). Adding a third ad-hoc connection is consistent with current practice and avoids scope creep into an unrelated infrastructure decision.
- Alternative considered: add a proper `ThreadedConnectionPool` for OW DB (Section 2.1 Option A). Rejected for this change — explicitly deferred by product decision; would benefit other roadmap items too but is out of scope here. Revisit if storage-health query frequency causes connection pressure (see Risks).

**3. Orphan/outlier detection joins on `collection_name` + `vmetadata`, accepting heuristic imprecision.**
No FK exists between `document_chunk` and `file`/`knowledge_file`. The join key must be `collection_name` (present on `document_chunk`) matched against however OpenWebUI names/derives collections for a knowledge base, cross-referenced with `vmetadata` for any file-level identifiers.
- Open risk: reliability of this heuristic is unverified (see Open Questions). If `vmetadata` doesn't reliably carry a `file_id`, chunk-count-outlier detection may need to fall back to `collection_name`-level aggregates only (per-KB, not per-file).

**4. New tab in the dashboard SPA, not folded into the existing Usage tab.**
RAG health has a different audience (KB owners/RAG operators) and different filter dimensions (model, KB) than Usage's cost/quota focus. A dedicated tab keeps both simpler.

## Risks / Trade-offs

- **[Risk] Citation truncation blind spot** — logged response text is capped at 2000 chars; a citation marker appearing later in a long answer would be invisible to the hit-rate query, undercounting true positives. → Mitigation: document this as a known limitation in the UI (e.g. a tooltip); revisit if false-negative rate proves material.
- **[Risk] Per-KB naming unconfirmed** — unverified whether `<source id="N">` tags carry a distinct knowledge-base name/id vs. just a source document identifier. → Mitigation: verify during implementation (task-level spike) before building the per-KB breakdown table; fall back to source-document-level grouping if no KB-level identifier exists.
- **[Risk] `vmetadata` heuristic reliability** — orphan/outlier detection's join key is unverified for consistency across upload paths (e.g. different behavior for base64-migrated docs per `migrate_rag_base64_to_local_media.py`). → Mitigation: spike a query against a real dataset early in implementation; scope down to KB-level aggregates if per-file joins prove unreliable.
- **[Risk] Third raw unpooled OW DB connection adds incremental load** — storage-health queries (chunk counts, joins) are heavier than the existing single-row lookups in `identity.py`/`alerting.py`, and a dashboard tab may be refreshed/polled more often than an identity-reconciliation action. → Mitigation: cache storage-health query results server-side for a short TTL (e.g. 1-5 min) rather than querying on every dashboard load; monitor OW DB connection count after rollout; revisit pooling (Option A) if this becomes a bottleneck.
- **[Risk] JSONB text-search performance** — `payload::text LIKE '%<source id="%'`-style queries over `mw_request_log` have no supporting index and will scan/slow as the table grows. → Mitigation: add a targeted index (e.g. a partial index or generated column) if query latency becomes a problem post-launch; not blocking for initial ship given current table size.

## Migration Plan

Purely additive — no schema migrations, no data backfill required, no changes to existing request/response handling. Deploy as a new API route + new dashboard tab. Rollback is a simple revert (remove the route registration and tab); no persisted state to unwind.

## Open Questions

- Does OpenWebUI's `<source id="N">` tag carry a knowledge-base-level identifier, or only a source-document identifier? Determines whether the retrieval per-KB breakdown table is buildable as designed or needs to be scoped down.
- Is `vmetadata` on `document_chunk` reliable enough (across all ingestion paths) to serve as the join key for orphan/outlier detection, or does it need a fallback to `collection_name`-only aggregation?

## Open Questions — Resolutions (spikes, tasks 1.1 / 1.2)

**1.1 — `<source id="N">` grouping.** The `id` in `<source id="N">` is a per-request *sequential source index* (1, 2, 3, …), not a stable knowledge-base identifier. Recent OpenWebUI builds may additionally emit a `name="…"` attribute on the tag carrying the source *document* label. Decision: the retrieval breakdown is grouped **by source document** (the `name` attribute when present, otherwise `source #N`), not by knowledge base, and the UI labels it "By Source" with a tooltip that this reflects source documents, not KBs. Hit-rate aggregate and the **by-model** breakdown are unaffected (model is a first-class logged field and fully reliable).

**1.2 — `vmetadata` / join-key reliability.** `document_chunk` has no FK and `vmetadata` contents vary across ingestion paths, so per-chunk `vmetadata` is **not** used as the join key. Decision: storage-health joins on **`collection_name`** matched against the set `{knowledge.id} ∪ {file.id} ∪ {'file-' || file.id}` (covering both KB-level and per-file collection-naming conventions observed in OpenWebUI). Zero-chunk / orphan detection operate at this collection level. Chunk-count-outlier detection is a documented **heuristic** (chunk count vs. an estimate derived from `file.meta` size) surfaced with an explicit "heuristic" caveat rather than treated as authoritative.
