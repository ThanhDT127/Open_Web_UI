## ADDED Requirements

### Requirement: Automated Knowledge Base Management
The system SHALL allow the test suite to programmatically create and delete Knowledge Bases (KB) for isolation during testing.

#### Scenario: Successful KB creation
- **WHEN** the test suite initiates a KB creation with a unique name
- **THEN** the system SHALL create the KB and it SHALL be visible in the KB list

### Requirement: Document Upload and Indexing Verification
The system SHALL support uploading multiple file formats (PDF, DOCX, XLSX) and provide status updates on the indexing process. The system SHALL now also detect indexing failures from the UI and report them immediately.

#### Scenario: File upload and indexing completion
- **WHEN** the test suite uploads a valid fixture file to a KB
- **THEN** the system SHALL successfully ingest the file and the indexing status SHALL eventually reach "completed" within the allowed timeout period

#### Scenario: Indexing failure detection
- **WHEN** the system UI displays an error notification during indexing
- **THEN** the system UI SHALL fail immediately with the descriptive error message

### Requirement: RAG Query Accuracy
The system SHALL retrieve relevant context from the uploaded documents to answer questions with verifiable facts and citations.

#### Scenario: Question answering with facts and citations
- **WHEN** the test suite queries the system about specific facts contained in the uploaded documents
- **THEN** the system SHALL provide an answer containing the expected facts AND SHALL include valid citations or source links to the original documents

### Requirement: Performance Latency Thresholds
The RAG pipeline SHALL respond within defined latency thresholds to ensure system usability. In benchmarking mode, latency SHALL be recorded without failing the test unless specified.

#### Scenario: Latency check
- **WHEN** a RAG query is performed
- **THEN** the system SHALL record the response time and store it for summary reporting
