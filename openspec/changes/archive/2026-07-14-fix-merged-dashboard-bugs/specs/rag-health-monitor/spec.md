## ADDED Requirements

### Requirement: Robust Citation Detection
The system SHALL use case-insensitive and whitespace-flexible regular expression matching when detecting source tags in the logged request messages to ensure high reliability of citation hit-rate computation.

#### Scenario: Robust citation tag parsing
- **WHEN** request body contains "<SOURCE id=" or multiple spaces like "<source  id="
- **THEN** the system still correctly detects and parses the source tag
