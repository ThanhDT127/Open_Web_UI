## Purpose
Define safe, targeted middleware user reads and mutations that preserve concurrent quota usage.

## Requirements

### Requirement: Get user by ID
The system SHALL provide a function `get_user_by_id(user_id: str)` that retrieves a single user from the database using an indexed query (`SELECT ... WHERE user_id = %s`). The function SHALL return the user dict (same format as `load_users()` entries) or `None` if not found. When the database is unavailable, the function SHALL fallback to loading from JSON file and filtering.

#### Scenario: User exists in database
- **WHEN** `get_user_by_id("alice")` is called and user "alice" exists in `mw_users`
- **THEN** the function returns a dict populated from the single DB row

#### Scenario: User does not exist
- **WHEN** `get_user_by_id("nonexistent")` is called and no such user exists
- **THEN** the function returns `None`

#### Scenario: Database unavailable - file fallback
- **WHEN** the DB pool is not initialized and `get_user_by_id("alice")` is called
- **THEN** the function loads users from JSON file, filters by `user_id`, and returns the matching user or `None`

### Requirement: Atomic quota increment
The system SHALL provide a function `update_user_quota(user_id: str, add_tokens: int = 0, add_cost_usd: float = 0.0, add_image_requests: int = 0, add_stt_requests: int = 0)` that atomically increments usage counters in the database using a targeted `UPDATE ... WHERE user_id = %s`. The function MUST NOT load or save the full user list. JSON backup snapshots SHALL be generated outside the request hot path from committed database state.

#### Scenario: Increment cost for existing user
- **WHEN** `update_user_quota("alice", add_cost_usd=0.05)` is called
- **THEN** the database atomically increments only Alice's quota and lifetime usage counters
- **THEN** the function does not rewrite the full JSON backup file

#### Scenario: Increment multiple fields
- **WHEN** `update_user_quota("alice", add_tokens=500, add_cost_usd=0.03)` is called
- **THEN** both token and cost counters are incremented in a single targeted database operation

#### Scenario: User not found
- **WHEN** `update_user_quota("nonexistent", add_cost_usd=0.05)` is called
- **THEN** the function returns `False` or raises an appropriate not-found error

### Requirement: Update user alerts_sent field
The system SHALL update alert eligibility for a single user through a targeted database operation or an atomic unique alert claim without loading or saving all users.

#### Scenario: Mark alert as sent
- **WHEN** the system claims the 80 percent threshold for Alice
- **THEN** only Alice's alert state for the current period is changed

### Requirement: Hot-path callers use single-user functions
All hot-path code executed for chat, embedding, image, quota status, or alert evaluation SHALL use targeted single-user database operations instead of `load_users()` plus `save_users()`.

#### Scenario: Alert evaluation
- **WHEN** `check_and_send_alerts("alice")` runs after a request
- **THEN** it reads Alice's committed quota state and atomically claims applicable alerts without saving other users

#### Scenario: Quota status
- **WHEN** quota status is requested for Alice
- **THEN** the system reads only Alice's committed user record

### Requirement: Backward compatibility
The existing `load_users()` function SHALL remain available for read-only administrative listing and reporting. Administrative mutations SHALL use targeted user operations and MUST NOT overwrite concurrent usage updates.

#### Scenario: Admin lists users
- **WHEN** an administrator requests the user list
- **THEN** the endpoint may load and return all users without modifying them

#### Scenario: Admin changes a quota limit during usage
- **WHEN** an administrator changes Alice's limit while Alice has concurrent usage updates
- **THEN** the limit change does not overwrite Alice's usage counters
