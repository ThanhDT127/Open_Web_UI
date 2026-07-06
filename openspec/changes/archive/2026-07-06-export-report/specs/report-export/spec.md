## ADDED Requirements

### Requirement: Export report endpoint
The system SHALL provide a `GET /v1/_mw/export/report` endpoint that generates a downloadable report file containing aggregated data from all dashboard data sources.

#### Scenario: Admin exports Excel report
- **WHEN** an authenticated admin sends `GET /v1/_mw/export/report?format=xlsx&start=2026-07-01T00:00:00&end=2026-07-31T23:59:59`
- **THEN** the system returns a `.xlsx` file with Content-Type `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` and Content-Disposition header with filename `LLM_Report_20260701_to_20260731.xlsx` (parsed `start`/`end` dates formatted as `YYYYMMDD`, colon-free and filesystem-safe on Windows)

#### Scenario: Admin exports CSV report
- **WHEN** an authenticated admin sends `GET /v1/_mw/export/report?format=csv&start=2026-07-01T00:00:00&end=2026-07-31T23:59:59`
- **THEN** the system returns a streaming CSV file with Content-Type `text/csv` and Content-Disposition filename `LLM_AuditLog_20260701_to_20260731.csv`, containing the full audit log for the time range

#### Scenario: Unauthenticated request
- **WHEN** a request without valid admin auth sends `GET /v1/_mw/export/report`
- **THEN** the system returns HTTP 401/403

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
- **WHEN** the Excel report is generated but OW DB group query fails
- **THEN** Sheet 4 "Phòng ban" SHALL contain a single row with message "Dữ liệu nhóm không khả dụng"

#### Scenario: Chat Analytics sheet
- **WHEN** the Excel report is generated and OW DB chat data is available
- **THEN** Sheet 5 "Chat Analytics" SHALL contain: total chats, total messages, active users count, and a user leaderboard with columns: User, Display Name, Chat Count, Request Count, Cost (USD), Top Model

#### Scenario: Satisfaction sheet
- **WHEN** the Excel report is generated and OW DB feedback data is available
- **THEN** Sheet 6 "Satisfaction" SHALL contain: total feedback count, positive count, negative count, CSAT percentage, and a model leaderboard with columns: Model, Positive, Negative, Total, CSAT %

#### Scenario: Audit Log sheet
- **WHEN** the Excel report is generated
- **THEN** Sheet 7 "Audit Log" SHALL contain raw audit log records (max 50,000 rows) sorted by timestamp descending, with all available columns: Timestamp, Request ID, User ID, Endpoint, Model, Status, Latency (ms), Tokens In, Tokens Out, Cost (USD), Error Type

### Requirement: Excel formatting
The system SHALL apply basic professional formatting to the Excel file for readability.

#### Scenario: Header row styling
- **WHEN** the Excel file is generated
- **THEN** each sheet SHALL have a bold header row with a colored background

#### Scenario: Column auto-width
- **WHEN** the Excel file is generated
- **THEN** column widths SHALL be auto-adjusted based on content length

#### Scenario: Freeze panes
- **WHEN** the Excel file is generated
- **THEN** each sheet SHALL freeze the header row so it remains visible when scrolling

#### Scenario: AutoFilter on tabular sheets
- **WHEN** the Excel file is generated
- **THEN** each tabular sheet (Top Users, Top Models, Groups, Chat Analytics, Satisfaction, Audit Log) SHALL have AutoFilter enabled on the header row, so the admin can filter/sort by any column (e.g. user, group, model) directly in Excel without additional setup

### Requirement: CSV streaming export
The system SHALL support CSV export of the full audit log using streaming response to handle large datasets efficiently.

#### Scenario: CSV contains all audit columns
- **WHEN** the CSV export is generated
- **THEN** the CSV SHALL include columns: Timestamp, Request ID, User ID, Endpoint, Model, Purpose, Status, Status Code, Latency (ms), Tokens In, Tokens Out, Tokens Total, Cost (USD), Image Count, TTS Chars, STT Seconds, Video Count, Error Type, Error Message

#### Scenario: CSV uses BOM for Excel compatibility
- **WHEN** the CSV file is downloaded and opened in Excel
- **THEN** the CSV SHALL include UTF-8 BOM prefix for correct character display

### Requirement: Dashboard export UI
The system SHALL provide an export button on the dashboard header that opens a modal for the admin to configure and download reports.

#### Scenario: Export button visible
- **WHEN** an admin is authenticated and viewing the dashboard
- **THEN** a "📥 Export Report" button SHALL be visible in the dashboard header area

#### Scenario: Export modal options
- **WHEN** the admin clicks the export button
- **THEN** a modal SHALL appear with: format selection (Excel/CSV), and the time range SHALL be pre-filled from the current dashboard time filter

#### Scenario: Download triggers
- **WHEN** the admin clicks "Download" in the modal
- **THEN** the browser SHALL initiate a file download from the export endpoint with the selected format and time range parameters
