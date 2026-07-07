## Context

`docs/saas_platform_exploration.md` Section 2.3 lists twelve dashboard improvements; item #7 "Knowledge Analytics" (data source: OpenWebUI `knowledge` + `file`) was blocked on the "OpenWebUI DB access strategy" decision (Section 2.1). That decision has since been settled *organically*: `core/identity.py` and the shipped RAG Health Monitor (`core/rag_health.py`, item #8) both open unpooled read-only `psycopg2` connections to the OpenWebUI DB. This change follows that precedent — no new pool, no fork.

This design is grounded by a read-only spike against the live databases (3 KBs, 122 files, 157 chunks, 130 RAG-attached requests). The spike's findings drove several non-obvious decisions below and are treated as settled unless re-verified during implementation on a larger dataset.

Distinction from RAG Health Monitor (already shipped): Health answers "is RAG *broken*?" (anomalies, ops). Knowledge Analytics answers "is the knowledge being *created and used* well?" (adoption, value, governance). Different audience (admins/KB governance), different questions, so a separate tab.

## Goals / Non-Goals

**Goals:**
- Turn the OpenWebUI knowledge corpus into an adoption-and-value signal: inventory/growth, a per-KB value classification, and governance signals.
- Reuse the established full-stack pattern (`core/*.py` queries + TTL cache → admin-guarded `api/*.py` → `dashboard/js` tab module → `tabs.js`/`main.js`/`index.html` wiring).
- Ship read-only and additive — no schema migration, no hot-path change, trivial revert.

**Non-Goals:**
- Any remediation actions (delete duplicates, archive dead KBs, re-embed) — read-only monitoring only; actions are a possible later change.
- Retrieval *relevance* quality — "quality" here means citation-happened hit-rate (reused from rag-health), not whether the right chunk was cited.
- Sharing-posture (private/public) analytics — this OpenWebUI schema has no `access_control` column.
- A pooled OW-DB connection (Section 2.1 "Option A") — explicitly deferred, consistent with rag-health's decision.
- Fixing the stale `knowledge_file` join table or rag-health's use of it — out of scope; this change simply routes around it.

## Decisions

**1. KB↔usage linkage is by embedded filename markers, not the `<source name=>` attribute.**
The spike showed OpenWebUI (this build) embeds document identity as literal `Filename: <name>` and `Source: <name>` text inside `<source>` content in `mw_request_log.payload->body`; there is **no** `name="..."` attribute. Detection: regex the `Source:`/`Filename:` markers, match against `file.filename`, roll up via `file.meta.data.knowledge_id`.
- Alternative considered: reuse rag-health's `by_source` (which parses the `name=` attribute). Rejected — that attribute is absent here, so `by_source` currently yields only synthetic `source #N` labels and cannot name a document.

**2. Attachment detection requires a document marker, not a bare `<source id=`.**
The spike found only **55 of 130** `chat.request` bodies containing `<source id=` actually carry a document; the other 75 match only because the citation-instruction *template* contains the literal `<source id="1">`. Counting `<source id=` alone overcounts attachments ~2.4×. Filter on the `Source:`/`Filename:` marker instead.
- Alternative considered: keep rag-health's `LIKE '%<source id=%'` filter for consistency. Rejected — it is measurably wrong for a usage metric (though tolerable for rag-health's coarser hit-rate).

**3. KB membership uses `file.meta.data.knowledge_id`, not `knowledge_file`.**
The spike found `knowledge_file` has only **4 rows** while **121 files** carry a `knowledge_id` in `file.meta.data`. The join table is stale in this instance; the per-file meta is authoritative. Chunk linkage uses `file.meta.collection_name = document_chunk.collection_name`.
- Alternative considered: `knowledge_file` (what rag-health's storage layer uses). Rejected — it would undercount KB membership by ~30×.

**4. "Quality" reuses the citation hit-rate concept from rag-health, scoped per-KB.**
For a KB's attachments (requests whose matched filename belongs to that KB), quality = share whose paired `chat.response` carries a `[N]` citation marker. This layers cleanly on decision #1's request-log scan.
- Alternative considered: build a new relevance metric. Rejected — out of scope and not derivable from logs.

**5. Value classification is a 2×2 of demand × quality, guarded by a data-sufficiency floor.**
Star = high demand + high quality; Needs-tuning = high demand + low quality; Dead-knowledge = has chunks + ~0 demand; Unproven = demand below a minimum sample threshold (avoids labeling a barely-used KB "dead" or "star"). Thresholds are config constants, tuned as data grows; documented, not hard-coded magic.

**6. Governance pivots to duplicates / orphans / ownership (no access_control).**
The spike confirmed no `access_control` column, but `file.meta.file_hash` enables duplicate detection — and it already shows real waste (one `ITviec…pdf` hash present in 3 KBs). Governance = duplicate groups (reclaimable bytes), orphan/ad-hoc files (no `knowledge_id`), and owner concentration (names via the `"user"` table). Same-hash-across-KBs also underpins decision #7's ambiguity caveat.

**7. Ambiguous KB attribution is disclosed, not resolved.**
When a filename/hash lives in multiple KBs, a log line naming that filename can't be pinned to one KB (the log carries no file id or collection). The UI flags such usage as ambiguous rather than arbitrarily crediting one KB. Unique filenames are unambiguous.

**8. Separate "Knowledge" tab; shares the OW-DB TTL cache with rag-health where practical.**
Different audience/questions than RAG Health warrant a distinct tab (same rationale rag-health used vs. Usage). Heavy OW-DB reads (inventory, per-KB rollups) are cached server-side for a short TTL, mirroring `rag_health.query_storage_health`.

## Risks / Trade-offs

- **[Risk] Filename match is fuzzy** — logged `Source:` text may differ from `file.filename` by extension, truncation, or normalization (the spike saw `TCVN…904224.docx` in logs vs `TCVN…904224.pdf` in files). → Mitigation: normalize (strip extension/whitespace, case-fold) and treat unmatched markers as "unattributed usage" surfaced separately rather than dropped; verify match rate on a larger dataset during implementation.
- **[Risk] KB attribution ambiguity for shared files** — same hash in N KBs can't be pinned from logs. → Mitigation: disclose as ambiguous (decision #7); optionally split credit evenly with a caveat.
- **[Risk] Low current data volume** — 3 KBs / 130 requests make early value classifications noisy. → Mitigation: the Unproven category and a sample-size floor (decision #5); UI notes sparsity.
- **[Risk] Response-text truncation** — rag-health notes logged responses are capped at 2000 chars, so a late citation marker is invisible, undercounting quality. → Mitigation: inherit rag-health's documented caveat; revisit if false-negative rate matters.
- **[Risk] JSONB text scans on `mw_request_log`** have no supporting index and slow as the table grows. → Mitigation: bound queries by date range and cache; add a targeted index/generated column later if latency bites.
- **[Risk] Incremental OW-DB load from a third ad-hoc connection** — per rag-health Risk 4. → Mitigation: short-TTL server-side cache; share cache with rag-health where the same rows are read; monitor OW-DB connection count post-rollout.
- **[Trade-off] Routing around `knowledge_file`** means this feature and rag-health disagree on KB membership until rag-health is (separately) reconciled. Accepted; documented as a follow-up.

## Migration Plan

Purely additive: new `core/knowledge_analytics.py`, new `api/knowledge_analytics.py` route(s) registered in `main.py`, new `dashboard/js/knowledge.js` + tab markup in `index.html` and wiring in `tabs.js`/`main.js`. No schema migration, no backfill (usage is queryable over existing `mw_request_log` history). Rollback = revert the route registration and tab; no persisted state.

## Open Questions

- On a larger dataset, what is the actual `Source:`-marker → `file.filename` match rate after normalization? Determines how much usage lands in "unattributed."
- Are the demand/quality thresholds and the Unproven sample-size floor best fixed constants, or should they be admin-tunable in `mw_config`?
- Should duplicate-file storage waste ("reclaimable bytes") also account for shared chunk storage, or file bytes only? (Start with file bytes.)
- Worth reconciling rag-health's `knowledge_file` usage with `file.meta.data.knowledge_id` as a separate change?
