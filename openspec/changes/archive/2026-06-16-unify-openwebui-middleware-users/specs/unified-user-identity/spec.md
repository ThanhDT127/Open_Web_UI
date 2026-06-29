## ADDED Requirements

### Requirement: Canonical Open WebUI identity mapping
The system SHALL support a unique mapping from an Open WebUI user UUID to a middleware user record.

#### Scenario: Mapped Open WebUI user sends a chat request
- **WHEN** an authenticated Open WebUI service request identifies a mapped Open WebUI user
- **THEN** middleware usage, quota, and audit records are attributed to that mapped user

#### Scenario: Open WebUI user name changes
- **WHEN** a mapped Open WebUI user changes name or email
- **THEN** the mapping remains valid because it uses the Open WebUI user UUID

### Requirement: Preserve direct API credentials
Direct API subkeys SHALL remain valid credentials associated with one middleware user and its canonical identity when present.

#### Scenario: Direct client uses a mapped user's subkey
- **WHEN** a direct API client authenticates with the user's subkey
- **THEN** usage is attributed to the same middleware quota record used by Open WebUI

### Requirement: Trusted forwarded identity
The middleware MUST trust a forwarded Open WebUI user identity only when the request is authenticated as the configured Open WebUI service.

#### Scenario: External client forges user header
- **WHEN** an external client sends a forwarded user identity header without the valid Open WebUI service credential
- **THEN** the middleware ignores or rejects the forwarded identity

### Requirement: Reconciliation report
The system SHALL provide an admin-only reconciliation process that reports matches, unmatched records, duplicates, and conflicts without silently deleting or merging users.

#### Scenario: Same email appears in multiple records
- **WHEN** reconciliation finds an ambiguous identity match
- **THEN** it reports the conflict and does not automatically map the records

### Requirement: Authorized quota lookup
A user SHALL only be able to retrieve their own quota status, while an authenticated administrator may retrieve any user's quota status.

#### Scenario: User requests another user's quota
- **WHEN** a non-admin user supplies another user's identifier to the quota status endpoint
- **THEN** the request is rejected
