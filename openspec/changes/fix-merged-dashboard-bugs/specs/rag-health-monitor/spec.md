## MODIFIED Requirements

### Requirement: Retrieval Citation Hit-Rate
The system SHALL compute a citation hit-rate metric — the percentage of chat messages with a knowledge base attached (detected via case-insensitive and whitespace-flexible `<source id="N">` tags in the logged request messages) that produced at least one `[N]`-style citation marker in the logged response text — derived from `mw_request_log.payload` JSONB data, independent of any runtime feature flag.

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
