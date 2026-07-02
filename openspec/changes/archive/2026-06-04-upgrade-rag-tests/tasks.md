## 1. Setup and Preparation

- [x] 1.1 Verify `.env` contains `TEST_ADMIN_EMAIL` and `TEST_ADMIN_PASSWORD`
- [x] 1.2 Create `tests/fixtures` directory for test documents
- [x] 1.3 Add TCVN7722-2-3_2007_904224.docx from TaiLieuTemp/Tieu chuan den duong as test file to `tests/fixtures`
- [x] 1.4 Install any necessary Playwright dependencies if missing
- [x] 1.5 Make sure using chat-deepseek-v4-flash as LLM in test case(specific on local, can change)

## 2. Refactor Login and Utility Functions

- [x] 2.1 Enhance `loginAsAdmin` helper in `tests/rag.spec.ts` for better reliability
- [x] 2.2 Add helper function to create a new Knowledge Base (KB) via UI/API
- [x] 2.3 Add helper function to upload a document to a specific KB
- [x] 2.4 Add helper function to poll for indexing status completion
- [x] 2.5 Add helper function to delete a KB for cleanup

## 3. Implement Core Functional Tests

- [x] 3.1 Implement test case for creating a KB and uploading a document
- [x] 3.2 Implement test case for waiting for indexing to complete
- [x] 3.3 Implement test case for querying the document and verifying the answer contains expected facts
- [x] 3.4 Implement test case for verifying citations/sources are present and correct
- [x] 3.5 Implement latency measurement and assertion in the query test

## 4. Finalization and Cleanup

- [x] 4.1 Ensure all tests include proper cleanup (deleting test KBs)
- [x] 4.2 Run the full test suite and verify it passes
- [x] 4.3 Update `PROJECT.md` or `README.md` if necessary to document how to run the new RAG tests
