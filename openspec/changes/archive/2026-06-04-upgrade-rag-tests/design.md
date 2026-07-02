## Context

The current RAG test in `tests/rag.spec.ts` is insufficient for verifying the end-to-end RAG pipeline. We need a more comprehensive test suite that covers the full lifecycle of a RAG document, from ingestion to querying and citation verification. This will serve as a foundation for ongoing RAG tuning.

## Goals / Non-Goals

**Goals:**
- Replace basic smoke tests with a comprehensive RAG functional test.
- Automate document upload and indexing verification.
- Implement fact-checking and citation validation logic in the test suite.
- Measure and enforce latency thresholds for RAG queries.
- Provide a repeatable benchmark for RAG performance and quality.

**Non-Goals:**
- Tuning the RAG parameters themselves (this is done in separate phases).
- Implementing a full-blown LLM evaluation framework (e.g., Ragas).
- Testing non-RAG related UI components.

## Decisions

### 1. Test Framework: Playwright
- **Rationale**: The project already uses Playwright for E2E testing. It provides robust capabilities for UI automation and API interaction.
- **Alternatives**: Cypress (would introduce a new dependency), Jest (not suitable for E2E UI testing).

### 2. Test Data Management: Dedicated Test Knowledge Base
- **Decision**: Create a fresh Knowledge Base (KB) for each test run and delete it after completion.
- **Rationale**: Ensures test isolation and prevents data pollution. Simplifies cleanup.
- **Alternatives**: Using a static test KB (risks data pollution), using existing user KBs (insecure and unpredictable).

### 3. Verification Logic: Fact and Citation Matching
- **Decision**: Define "Expected Facts" and "Expected Citations" for each benchmark question. Use simple string matching or regex for verification.
- **Rationale**: Simple to implement and maintain while being effective for basic functional testing.
- **Alternatives**: LLM-based evaluation (more complex, introduces potential instability/cost).

### 4. Latency Monitoring: Performance.now()
- **Decision**: Use `performance.now()` in the Playwright test to measure the time between query submission and response completion.
- **Rationale**: Accurate and easy to integrate into existing test scripts.
- **Alternatives**: Backend-side logging (more accurate for pure pipeline latency but harder to integrate into E2E UI tests).

## Risks / Trade-offs

- **[Risk]** Indexing time can be unpredictable depending on system load.
  - **Mitigation**: Implement a robust polling mechanism with a generous timeout for indexing status.
- **[Risk]** UI changes might break Playwright selectors.
  - **Mitigation**: Use stable data-testid or accessible roles/placeholders where possible.
- **[Risk]** LLM responses can be non-deterministic.
  - **Mitigation**: Use clear, specific benchmark questions and flexible matching (regex) for facts.
