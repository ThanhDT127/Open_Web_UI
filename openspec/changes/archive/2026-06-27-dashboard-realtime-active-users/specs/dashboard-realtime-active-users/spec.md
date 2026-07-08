## ADDED Requirements

### Requirement: Real-time Active Users API Stream
The system SHALL provide an authenticated GET endpoint `/v1/_mw/admin/active-users/stream` that streams the active users count via Server-Sent Events (SSE).
The active user count SHALL be calculated as the sum of unique user IDs in the `mw_pending` table plus unique user IDs who have successfully completed requests in the last 5 minutes (based on `mw_audit_log` with status 'ok' or 'reconciled').

#### Scenario: Subscribing to SSE stream successfully
- **WHEN** an authenticated administrator sends a GET request to `/v1/_mw/admin/active-users/stream`
- **THEN** the system SHALL return a 200 response with `Content-Type: text/event-stream` and yield active users count events periodically.

### Requirement: Real-time UI updating of Active Users Card
The Admin Dashboard SHALL display an interactive metric card with ID `cardActiveUsers` showing the real-time count of active users.
The dashboard client-side Javascript SHALL subscribe to the SSE endpoint and dynamically update the card's text content with the latest count without requiring a manual page refresh.

#### Scenario: Card dynamically updates on event
- **WHEN** the EventSource receives an event with data `{"active_users": 5}`
- **THEN** the text content of `#metricActiveUsers` SHALL update to `5`.
