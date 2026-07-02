# knowledge-analytics Specification

## Purpose
TBD - created by archiving change add-knowledge-analytics-dashboard. Update Purpose after archive.
## Requirements
### Requirement: Knowledge Corpus Inventory
The system SHALL compute inventory and growth metrics for the OpenWebUI knowledge corpus — total knowledge bases, total files, total chunks, total storage bytes, a KB/file creation timeseries, and file-type and file-size distributions — via read-only queries against the OpenWebUI `knowledge`, `file`, and `document_chunk` tables. File type and size SHALL be derived from `file.meta` (`content_type`, `size`), not from a schema column.

#### Scenario: Corpus totals are displayed
- **WHEN** an admin opens the Knowledge tab
- **THEN** the system displays total knowledge bases, total files, total chunks, and total storage bytes, sourced from the OpenWebUI database

#### Scenario: Growth over time
- **WHEN** an admin views the Inventory panel for a date range
- **THEN** the system displays a timeseries of knowledge bases and files created over time, derived from the `created_at` epoch fields

#### Scenario: File-type and size distribution
- **WHEN** an admin views the Inventory panel
- **THEN** the system displays a breakdown of files by `content_type` and a size distribution, both read from `file.meta`

#### Scenario: Empty corpus does not error
- **WHEN** there are no knowledge bases or files
- **THEN** all totals display as 0 and distributions are empty, without erroring

### Requirement: KB Membership Resolution
The system SHALL determine which files belong to a knowledge base using `file.meta.data.knowledge_id` as the authoritative link, and SHALL NOT rely on the `knowledge_file` join table (observed to be stale). Chunk counts per knowledge base SHALL be resolved by matching `file.meta.collection_name` against `document_chunk.collection_name`.

#### Scenario: Files are attributed to their knowledge base
- **WHEN** the system builds per-KB metrics
- **THEN** each file is associated with the knowledge base identified by its `file.meta.data.knowledge_id`, and files lacking that field are treated as not belonging to any knowledge base

#### Scenario: Per-KB chunk counts
- **WHEN** the system computes a knowledge base's chunk count
- **THEN** it sums `document_chunk` rows whose `collection_name` matches the `collection_name` of that knowledge base's files

### Requirement: KB Usage Linkage from Request Logs
The system SHALL derive knowledge-base usage (attach frequency) by extracting document filenames from `Filename:` / `Source:` markers embedded in the logged `<source>` content of `mw_request_log` `chat.request` payloads, matching them to `file.filename`, and rolling up to the owning knowledge base. The system SHALL NOT treat the presence of a bare `<source id=` string as evidence of an attachment, because that string also appears in the citation-instruction template; only requests carrying a `Filename:`/`Source:` document marker SHALL count as attachments.

#### Scenario: Attachment detected via document marker
- **WHEN** a `chat.request` payload contains a `Source:`/`Filename:` marker naming a file that matches a `file.filename`
- **THEN** the system counts one attachment for that file's knowledge base at the request timestamp

#### Scenario: Template-only source tags are not counted
- **WHEN** a `chat.request` payload contains `<source id=` only within the citation-instruction template and no `Filename:`/`Source:` document marker
- **THEN** the system does NOT count it as a knowledge-base attachment

#### Scenario: Ambiguous KB attribution is disclosed
- **WHEN** a matched filename exists in more than one knowledge base
- **THEN** the system surfaces the attribution as ambiguous (e.g. a caveat/flag) rather than silently assigning the usage to a single knowledge base

### Requirement: KB Value Classification
The system SHALL classify each knowledge base into one of four value categories — **Star**, **Needs-tuning**, **Dead-knowledge**, or **Unproven** — computed from four signals: demand (attach count from request logs), quality (citation hit-rate over that KB's attachments, reusing the retrieval hit-rate computation), supply (file count, chunk count, storage size), and freshness (created/updated/last-attached timestamps). A knowledge base that has chunks but effectively zero attachments SHALL be classified as Dead-knowledge; one with high demand but low citation hit-rate SHALL be classified as Needs-tuning.

#### Scenario: Value matrix is displayed per KB
- **WHEN** an admin views the KB Value panel
- **THEN** the system lists each knowledge base with its demand, quality, supply, and freshness signals and its resulting value category

#### Scenario: Dead knowledge is flagged
- **WHEN** a knowledge base has embedded chunks but no attachments observed in the selected range
- **THEN** the system classifies it as Dead-knowledge

#### Scenario: High-use low-quality KB is flagged
- **WHEN** a knowledge base is attached frequently but its citation hit-rate is low
- **THEN** the system classifies it as Needs-tuning

#### Scenario: Sparse data yields Unproven
- **WHEN** a knowledge base has too few attachments to judge quality
- **THEN** the system classifies it as Unproven rather than Dead-knowledge or Star

### Requirement: Knowledge Governance Signals
The system SHALL surface governance signals derived from the OpenWebUI `file` table: duplicate files (multiple files sharing the same `file.meta.file_hash`, especially across different knowledge bases), orphaned/ad-hoc files (files with no `knowledge_id`), and owner concentration (per-owner counts of knowledge bases, files, and storage bytes, with owner names resolved from the `"user"` table). Sharing-posture (private/public) SHALL NOT be attempted, as no `access_control` column exists in this schema.

#### Scenario: Duplicate files across KBs are listed
- **WHEN** the same `file_hash` appears in more than one file record
- **THEN** the system lists the duplicate group with its filename, copy count, per-copy size, and the knowledge bases it appears in, as reclaimable storage

#### Scenario: Orphaned files are surfaced
- **WHEN** files exist that are not members of any knowledge base
- **THEN** the system reports their count and storage footprint separately from KB-member files

#### Scenario: Owner concentration is shown
- **WHEN** an admin views the Governance panel
- **THEN** the system displays top owners by knowledge-base count, file count, and storage bytes, with owner names resolved from the OpenWebUI `"user"` table

### Requirement: Read-Only Admin-Only Access
The system SHALL expose knowledge-analytics data only through admin-guarded middleware endpoints under `/v1/_mw/knowledge-analytics/`, performing read-only queries. OpenWebUI database access SHALL use an unpooled `psycopg2` connection consistent with `core/identity.py` and `core/rag_health.py`, and heavier queries SHALL be cached server-side for a short TTL to limit connection frequency.

#### Scenario: Non-admin is rejected
- **WHEN** a request without admin/session authorization hits a knowledge-analytics endpoint
- **THEN** the system rejects it, consistent with the other dashboard admin endpoints

#### Scenario: No writes to OpenWebUI data
- **WHEN** any knowledge-analytics query runs
- **THEN** it only reads from the OpenWebUI and middleware databases and never modifies knowledge, file, or chunk data

#### Scenario: Repeated loads reuse cached results
- **WHEN** the Knowledge tab is refreshed within the cache TTL
- **THEN** the system serves cached results rather than re-querying the OpenWebUI database each time

### Requirement: Knowledge Analytics Dashboard Tab
The system SHALL present inventory, KB value, and governance data in a dedicated "Knowledge" tab in the middleware dashboard, with a date-range filter, separate from the Usage and RAG Health tabs.

#### Scenario: Dashboard tab is accessible
- **WHEN** an admin navigates to the dashboard
- **THEN** a "Knowledge" tab is available alongside Usage, Access, Users, Logs, and RAG Health

#### Scenario: Date-range filter applies across panels
- **WHEN** an admin changes the date-range filter on the Knowledge tab
- **THEN** the Inventory growth, KB value demand/freshness, and usage-derived signals update to reflect the selected range

#### Scenario: Limitations are disclosed in the UI
- **WHEN** an admin views usage-derived metrics
- **THEN** the UI discloses that usage reflects only logged chats and that KB attribution can be ambiguous for filenames shared across knowledge bases

