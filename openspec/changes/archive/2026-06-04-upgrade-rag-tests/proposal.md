## Why

The current RAG testing in `tests/rag.spec.ts` consists of basic smoke tests that only verify if the UI loads and navigation is possible. There is no automated verification of the actual RAG pipeline (upload, indexing, retrieval, and quality). As the system undergoes RAG tuning (Phase 1-4 of RAG_TASK.md), we need a robust, automated way to verify that improvements are working as expected and to catch regressions.

## What Changes

- **Enhanced RAG Test Suite**: Upgrade `tests/rag.spec.ts` to include full end-to-end RAG flows.
- **Automated Lifecycle Testing**: Implementation of a complete test cycle: Login -> Knowledge Base Creation -> Document Upload -> Indexing Verification -> Querying -> Fact/Citation Validation.
- **Performance Monitoring**: Integration of latency measurement for RAG queries with failure thresholds.
- **Benchmark Integration**: Use of standardized benchmark questions and fixture files for consistent testing.

## Capabilities

### New Capabilities
- `rag-functional-testing`: Automated verification of the RAG pipeline including document ingestion, indexing status, retrieval accuracy (facts/citations), and performance latency.

### Modified Capabilities
- None

## Impact

- **Affected Code**: `tests/rag.spec.ts` will be significantly refactored.
- **New Assets**: Addition of fixture files (PDF, DOCX, etc.) for testing in a `tests/fixtures/` directory (if not exists).
- **Environment**: Requires valid `TEST_ADMIN_EMAIL` and `TEST_ADMIN_PASSWORD` in `.env` (already present but needs verification).
- **Dependencies**: Relies on Playwright for UI/API interaction.
