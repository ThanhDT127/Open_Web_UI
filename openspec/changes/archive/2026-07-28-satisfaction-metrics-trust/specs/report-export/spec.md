## MODIFIED Requirements

### Requirement: Excel report contains 7 sheets
The system SHALL generate an Excel file with the following sheets, each containing data aggregated for the requested time range.

#### Scenario: Summary sheet
- **WHEN** the Excel report is generated
- **THEN** Sheet 1 "Tổng quan" SHALL contain: total requests, total cost (USD), total tokens, error rate, P95 latency, breakdown by request type (chat/image/audio/video), and the report time range

#### Scenario: Top Users sheet
- **WHEN** the Excel report is generated
- **THEN** Sheet 2 "Top Users" SHALL contain all users with activity in the time range, sorted by cost descending, with columns: User ID, Display Name, Requests, Cost (USD), Tokens, Top Model

#### Scenario: Top Models sheet
- **WHEN** the Excel report is generated
- **THEN** Sheet 3 "Top Models" SHALL contain all models used in the time range, sorted by cost descending, with columns: Model, Requests, Cost (USD), Tokens

#### Scenario: Groups sheet
- **WHEN** the Excel report is generated and OW DB group data is available
- **THEN** Sheet 4 "Phòng ban" SHALL contain per-group aggregated data with columns: Group Name, Requests, Cost (USD), Tokens, Avg Latency (ms), Top Model

#### Scenario: Groups sheet when OW DB unavailable
- **WHEN** the Excel report is generated but the OW DB group query fails
- **THEN** the export SHALL fail with an error and no file SHALL be produced, so that an incomplete report is never delivered as though it were complete

#### Scenario: Chat Analytics sheet
- **WHEN** the Excel report is generated and OW DB chat data is available
- **THEN** Sheet 5 "Chat Analytics" SHALL contain: total chats, total messages, active users count, and a user leaderboard with columns: User, Display Name, Chat Count, Request Count, Cost (USD), Top Model

#### Scenario: Satisfaction sheet
- **WHEN** the Excel report is generated and OW DB feedback data is available
- **THEN** Sheet 6 "Satisfaction" SHALL contain: the count of positive-and-negative votes under a label naming them as such, positive count, negative count, CSAT percentage rounded at the cell, and a model leaderboard with columns: Model, Positive, Negative, Total, CSAT %

#### Scenario: Satisfaction sheet when the feedback query fails
- **WHEN** the Excel report is generated but the OW DB feedback query fails
- **THEN** the export SHALL fail with an error and no file SHALL be produced, rather than delivering a satisfaction sheet whose counts are all zero

#### Scenario: Audit Log sheet
- **WHEN** the Excel report is generated
- **THEN** Sheet 7 "Audit Log" SHALL contain raw audit log records (max 50,000 rows) sorted by timestamp descending, with all available columns: Timestamp, Request ID, User ID, Endpoint, Model, Status, Latency (ms), Tokens In, Tokens Out, Cost (USD), Error Type

## ADDED Requirements

### Requirement: A sheet that cannot be filled stops the export

Sheets sourced from data outside the middleware database SHALL propagate their failures. The export SHALL NOT substitute an empty or zero-filled sheet for data it failed to read.

An empty sheet and a genuinely empty time range are indistinguishable to the reader, and the file downloads with the same name and the same appearance either way. The reader has no way to tell that part of the report is missing, which makes a silent failure worse than a loud one.

Sheets SHALL obtain their data by calling the corresponding pure aggregation function rather than by invoking an HTTP endpoint handler, since handlers re-check authorisation and raise HTTP errors that an exporter is tempted to swallow.

#### Scenario: A failing data source aborts the whole export

- **WHEN** any sheet's underlying query raises
- **THEN** the export request fails with an error and no partial file is returned

#### Scenario: A genuinely empty range still produces a file

- **WHEN** the requested time range contains no data but every query succeeds
- **THEN** the file is produced normally with empty sheets, because nothing failed
