## ADDED Requirements

### Requirement: Multi-hop Search Loop
The system SHALL support running multiple search iterations (hops) using SearXNG, caving web pages, and detecting information gaps via LLM before producing the final report.

#### Scenario: Iterative search execution
- **WHEN** user requests a deep research query
- **THEN** the system executes the first search iteration, crawls top web pages, analyzes information gaps, executes a second iteration for missing details, and synthesizes findings

### Requirement: Real-time Thinking Progress
The system SHALL stream research progress updates (e.g., plans, queries, caved URLs) to the user interface in real-time using thinking message frames.

#### Scenario: Real-time status display
- **WHEN** the agent is executing multi-hop search and crawling steps
- **THEN** progress updates are formatted and streamed to the chat screen in real-time

### Requirement: Automatic Citations and References
The system SHALL map key claims in the report to their corresponding source URLs using citations (e.g., `[1]`, `[2]`) and append a References section at the end of the report.

#### Scenario: Source citations rendered
- **WHEN** the final report is generated
- **THEN** facts are annotated with numeric citations, and a References section list of all crawled sources is appended to the bottom of the document
