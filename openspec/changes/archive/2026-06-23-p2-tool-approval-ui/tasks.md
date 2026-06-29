## 1. Database and API Setup

- [x] 1.1 Create mw_tool_approvals PostgreSQL table in llm-mw/core/db.py
- [x] 1.2 Implement middleware APIs for creating, reading, and updating tool approvals in llm-mw/main.py

## 2. Tool Integration and Custom Function Implementation

- [x] 2.1 Update tools/google_gmail_tool.py to register a pending approval and return [PENDING_APPROVAL:id] marker
- [x] 2.2 Create tools/action_approval_ui.py to scan messages for pending approvals and show Approve/Reject buttons via JS Injection modal
- [x] 2.3 Create tools/filter_approval_handler.py to intercept /approve and /reject commands, execute approved actions, and replace content for LLM

## 3. Verification

- [x] 3.1 Write automated tests for database operations and API endpoints
- [x] 3.2 Add Playwright test to verify approval/rejection button clicks and Gmail OAuth execution flow
