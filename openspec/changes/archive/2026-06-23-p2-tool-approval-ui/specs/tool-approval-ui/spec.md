## ADDED Requirements

### Requirement: Detection of Approval Markers
The system SHALL scan assistant messages for the presence of approval markers in the format `[PENDING_APPROVAL:action_id]`.

#### Scenario: Approval marker detected
- **WHEN** an assistant message contains `[PENDING_APPROVAL:abc-123]`
- **THEN** the Action UI module detects the token and prepares UI rendering

### Requirement: Approval Button UI Rendering
The Action module SHALL render two interactive buttons: "Duyệt (Approve)" in green and "Từ chối (Reject)" in red directly under the message containing the pending approval marker.

#### Scenario: Buttons rendered below message
- **WHEN** an assistant message contains `[PENDING_APPROVAL:abc-123]`
- **THEN** two HTML buttons for "Duyệt (Approve)" and "Từ chối (Reject)" are injected and displayed under the message

### Requirement: Approve Action Command Submission
When a user clicks "Duyệt (Approve)", the system SHALL submit a command `/approve action_id` to the chat.

#### Scenario: User clicks Approve
- **WHEN** user clicks "Duyệt (Approve)" for action `abc-123`
- **THEN** the browser sends `/approve abc-123` as a message to the chat

### Requirement: Reject Action Command Submission
When a user clicks "Từ chối (Reject)", the system SHALL submit a command `/reject action_id` to the chat.

#### Scenario: User clicks Reject
- **WHEN** user clicks "Từ chối (Reject)" for action `abc-123`
- **THEN** the browser sends `/reject abc-123` as a message to the chat

### Requirement: Intercepting Approval Commands
The Custom Filter SHALL intercept any user message starting with `/approve` or `/reject` in the `inlet` phase to prevent them from directly reaching the LLM, and update the status in the state storage.

#### Scenario: Approve command intercepted
- **WHEN** user message `/approve abc-123` is sent
- **THEN** the filter intercepts it, updates the status of `abc-123` to `approved` in the database, executes the associated tool, and replaces the user message content with the execution results before forwarding to the LLM

#### Scenario: Reject command intercepted
- **WHEN** user message `/reject abc-123` is sent
- **THEN** the filter intercepts it, updates the status of `abc-123` to `rejected` in the database, and replaces the user message content with a rejection notification before forwarding to the LLM

### Requirement: State Storage
The system SHALL persist the state of all approval requests in the PostgreSQL database.

#### Scenario: Save pending approval
- **WHEN** a tool requests approval for a sensitive action
- **THEN** the system saves a record with status `pending`, along with the tool payload, user ID, and action ID to the PostgreSQL database
