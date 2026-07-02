## MODIFIED Requirements

### Requirement: Document Upload and Indexing Verification
The system SHALL support uploading multiple file formats (PDF, DOCX, XLSX) and provide status updates on the indexing process. The system SHALL now also detect indexing failures from the UI and report them immediately.

#### Scenario: File upload and indexing completion
- **WHEN** the test suite uploads a valid fixture file to a KB
- **THEN** the system SHALL successfully ingest the file and the indexing status SHALL eventually reach "completed" within the allowed timeout period

#### Scenario: Indexing failure detection
- **WHEN** the system UI displays an error notification during indexing
- **THEN** the test suite SHALL fail immediately with the descriptive error message

### Requirement: Performance Latency Thresholds
The RAG pipeline SHALL respond within defined latency thresholds to ensure system usability. In benchmarking mode, latency SHALL be recorded without failing the test unless specified.

#### Scenario: Latency check
- **WHEN** a RAG query is performed
- **THEN** the system SHALL record the response time and store it for summary reporting
