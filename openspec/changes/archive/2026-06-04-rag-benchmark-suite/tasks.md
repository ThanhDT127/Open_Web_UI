## 1. Setup and Library Integration

- [x] 1.1 Install `js-yaml` library in `tests/` directory
- [x] 1.2 Create `tests/fixtures/rag_benchmark.yaml` with the provided content

## 2. Implement YAML Data Loader

- [x] 2.1 Create a utility in `tests/utils/benchmark-loader.ts` to read and parse the YAML file
- [x] 2.2 Add TypeScript interfaces for the benchmark schema

## 3. Refactor Test Runner

- [x] 3.1 Update `tests/rag.spec.ts` to dynamically generate tests from the loaded YAML cases
- [x] 3.2 Implement logic to handle multiple files per Knowledge Base
- [x] 3.3 Ensure isolation (unique KB name) per test case

## 4. Reporting and Summary

- [x] 4.1 Implement a global results accumulator
- [x] 4.2 Create a summary reporter that prints a detailed table (ID, Title, Latency, Citation, Status)
- [x] 4.3 Log detailed LLM responses for failed cases

## 5. Validation

- [x] 5.1 Run the new YAML benchmark suite and verify the pass/fail reporting
- [x] 5.2 Confirm that citation and fact checks are working correctly per YAML definition
