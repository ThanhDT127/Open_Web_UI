## ADDED Requirements

### Requirement: YAML Benchmark Ingestion
The system SHALL support loading benchmark test cases from a YAML file following the defined schema (id, title, files, question, expected).

#### Scenario: Valid YAML loading
- **WHEN** the benchmark suite is initialized with a valid YAML file
- **THEN** it SHALL parse all cases and prepare them for sequential execution

### Requirement: Multi-Document Case Support
The system SHALL support cases that require multiple files to be uploaded to a single Knowledge Base.

#### Scenario: Case with 2+ files
- **WHEN** a case defines multiple files in the `files` array
- **THEN** the system SHALL upload all of them to the test Knowledge Base before querying

### Requirement: Automated Result Aggregation
The system SHALL collect accuracy and performance data for every executed benchmark case and provide a consolidated summary.

#### Scenario: End of benchmark run
- **WHEN** all cases in the YAML file have been executed
- **THEN** the system SHALL output a summary table containing ID, Title, Status, and Latency for each case
