# admin-pending-force-clear Specification

## Purpose
TBD - created by archiving change dashboard-pending-detail-views. Update Purpose after archive.
## Requirements
### Requirement: Admin can force clear stuck pending requests
The system SHALL allow authenticated administrators to force-remove a stuck pending request from the active pending list (both DB and CSV backup file) without requiring log reconciliation.

#### Scenario: Successfully force clearing a pending request via API
- **WHEN** an authenticated administrator sends a DELETE request to `/v1/_mw/admin/pending/{request_id}`
- **THEN** the system SHALL delete the request ID from the `mw_pending` table and `pending.csv` backup file, returning a success JSON response with status 200.

#### Scenario: Click clear button on dashboard modal
- **WHEN** the administrator clicks the Clear action button next to a pending request in the modal
- **THEN** the system SHALL prompt for confirmation and then trigger the DELETE API request to clear it.

