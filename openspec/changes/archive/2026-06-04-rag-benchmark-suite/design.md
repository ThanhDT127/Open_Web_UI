## Context

We are moving from a single static test to a comprehensive benchmarking suite. The system must be able to handle dozens of cases across multiple documents, verifying facts and citations for each, and then providing a high-level report.

## Goals / Non-Goals

**Goals:**
- Decouple test data (questions/facts) from test code.
- Support YAML as the primary configuration format for its readability and nested structure support.
- Provide a clear performance and accuracy summary at the end of the run.
- Support per-case file specification (automatic upload and management).

**Non-Goals:**
- Implementing a full LLM evaluation backend (this remains an E2E UI test).
- Supporting parallel execution of questions within the same chat.

## Decisions

### 1. Data Format: YAML
- **Rationale**: YAML is more expressive than Excel for nested data (e.g., list of files per case, list of expected keywords). It is easily version-controlled.
- **Tool**: `js-yaml` library for parsing.

### 2. Test Execution: Dynamic Generation
- **Decision**: The test suite will load the YAML file at runtime and use Playwright's `test()` function in a loop to generate discrete test results for each benchmark case.
- **Rationale**: Provides better reporting in the Playwright HTML reporter (one result per case).

### 3. Reporting: Post-Execution Summary
- **Decision**: Collect results in an array and print a summary table at the end of the test run using a custom reporter or console output.

### 4. YAML Schema
```yaml
version: 1
name: benchmark_name
defaults:
  timeout_ms: 60000
  require_citation: true
cases:
  - id: case_id
    title: Case Title
    files:
      - path: tests/fixtures/doc.pdf
        type: pdf
    question: "Prompt text"
    expected:
      answer_contains: ["keyword1", "keyword2"]
      source_contains: ["filename.pdf"]
```

## Risks / Trade-offs

- **[Risk]** Handling multiple files per Knowledge Base.
  - **Mitigation**: Create a unique Knowledge Base per test case to ensure isolation and prevent context pollution.
- **[Risk]** Very slow execution for large suites.
  - **Mitigation**: Implement tags in YAML to allow running a subset of the benchmark.
