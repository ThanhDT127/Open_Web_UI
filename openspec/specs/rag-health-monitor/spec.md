## ADDED Requirements

### Requirement: Ingestion Health Metrics
The system SHALL compute embedding-ingestion health metrics (call count, failure rate, average latency, and a list of recent failures) by querying `mw_audit_log` for calls to the embeddings endpoint, filterable by a date range.

#### Scenario: Embedding failures are visible
- **WHEN** an admin opens the RAG Health tab's Ingestion section for a given date range
- **THEN** the system displays the embedding call count, failure rate, average latency, and a table of recent failures (timestamp, user, error type, error message) sourced from `mw_audit_log`

#### Scenario: No embedding failures in range
- **WHEN** the selected date range contains no failed embedding calls
- **THEN** the failure rate displays as 0% and the recent-failures table is empty, without erroring

### Requirement: Retrieval Citation Hit-Rate
The system SHALL compute a citation hit-rate metric — the percentage of chat messages with a knowledge base attached (detected via `<source id="N">` tags in the logged request messages) that produced at least one `[N]`-style citation marker in the logged response text — derived from `mw_request_log.payload` JSONB data, independent of any runtime feature flag.

#### Scenario: Citation hit-rate is computed from existing logs
- **WHEN** an admin opens the RAG Health tab's Retrieval section for a given date range
- **THEN** the system displays the count of KB-attached messages, the count that received a citation, and the resulting hit-rate percentage, computed by scanning `mw_request_log.payload` for `chat.request`/`chat.response` event pairs

#### Scenario: Hit-rate breakdown by model
- **WHEN** an admin views the Retrieval section
- **THEN** the system displays citation hit-rate broken down by model

#### Scenario: Zero-citation messages are listed
- **WHEN** a KB-attached message produced no citation marker in its logged response
- **THEN** the system lists it in a "zero-citation messages" table with timestamp, user, and a preview of the question

#### Scenario: Historical data is queryable retroactively
- **WHEN** an admin selects a date range that predates this feature's deployment
- **THEN** the hit-rate metric is still computed correctly, since it relies only on data already persisted in `mw_request_log`

### Requirement: Storage Health Anomaly Detection
The system SHALL detect and surface storage-level RAG anomalies — zero-chunk knowledge bases, orphaned chunks, and chunk-count outliers — via read-only queries directly against the OpenWebUI database, using an unpooled connection consistent with the existing pattern in `llm-mw/core/identity.py`.

#### Scenario: Zero-chunk knowledge base detected
- **WHEN** a knowledge base has files attached but no corresponding rows exist in `document_chunk` for its collection
- **THEN** the system lists it in the Storage section's "zero-chunk knowledge bases" table with name, creation date, owner, and file count

#### Scenario: Orphaned chunks detected
- **WHEN** rows in `document_chunk` exist for a `collection_name` with no matching `file`/`knowledge_file` record
- **THEN** the system lists the affected collection and chunk count in the "orphaned chunks" table

#### Scenario: Chunk-count outlier detected
- **WHEN** a file's embedded chunk count is anomalously low relative to its size (heuristic threshold)
- **THEN** the system lists the file in the "chunk-count outliers" table with its chunk count and an expected-count estimate

#### Scenario: Storage queries do not require a new connection pool
- **WHEN** the Storage section's data is fetched
- **THEN** the system uses a read-only, unpooled `psycopg2` connection to the OpenWebUI database rather than introducing a new pooled connection

### Requirement: RAG Health Dashboard Tab
The system SHALL present ingestion, retrieval, and storage health data in a dedicated "RAG Health" tab in the middleware dashboard, with date-range, model, and user filters, independent of the existing Usage tab.

#### Scenario: Dashboard tab is accessible
- **WHEN** an admin navigates to the dashboard
- **THEN** a "RAG Health" tab is available alongside Usage, Access, Users, and Logs

#### Scenario: Filters apply across all three sections
- **WHEN** an admin changes the date-range filter on the RAG Health tab
- **THEN** the Ingestion, Retrieval, and Storage sections all update to reflect the selected range
