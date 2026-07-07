## ADDED Requirements

### Requirement: Admin can view detailed list of pending requests
The system SHALL allow authenticated administrators to view a list of all active pending requests, including the request ID, user ID, start time, model name, and endpoint.

#### Scenario: Successfully fetching pending requests list via API
- **WHEN** an authenticated administrator sends a GET request to `/v1/_mw/admin/pending`
- **THEN** the system SHALL query the `mw_pending` and `mw_audit_log` tables and return a JSON list of active pending requests with their metadata with status 200.

#### Scenario: Click pending card to open details modal
- **WHEN** the administrator clicks on the Pending card (`#metricPending`) on the dashboard
- **THEN** the system SHALL display the `#pendingModal` overlay containing the active pending requests table.
