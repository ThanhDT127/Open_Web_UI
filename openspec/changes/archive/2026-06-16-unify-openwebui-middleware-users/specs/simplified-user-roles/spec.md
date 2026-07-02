## ADDED Requirements

### Requirement: Two middleware roles
The middleware SHALL support only the roles `admin` and `user`.

#### Scenario: Dashboard creates a user
- **WHEN** an administrator opens the role selector
- **THEN** only `admin` and `user` are available

#### Scenario: API receives manager role
- **WHEN** a create or update request specifies `manager`
- **THEN** the API rejects the value after migration is complete

### Requirement: Persist role
The middleware SHALL persist each user's role in the database and return the persisted role through user administration APIs.

#### Scenario: Service restarts
- **WHEN** a user role is changed and the middleware restarts
- **THEN** the user retains the saved role

### Requirement: Migrate manager to user
Existing middleware users with role `manager` MUST be migrated to role `user` with an audit record.

#### Scenario: Existing manager record
- **WHEN** the role migration runs for an existing manager
- **THEN** the role becomes `user` and the migration is recorded

### Requirement: Keep Open WebUI pending separate
Open WebUI's `pending` account state SHALL NOT become a middleware role and SHALL NOT receive middleware access until approved or provisioned.

#### Scenario: Pending Open WebUI account
- **WHEN** an Open WebUI account is pending and has no approved middleware mapping
- **THEN** it cannot consume middleware quota
