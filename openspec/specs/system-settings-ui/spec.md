# system-settings-ui Specification

## Purpose
Provide a canonical specification for the admin dashboard Settings tab, including SMTP configuration, quota alert thresholds, provider API budgets, and notification channel controls used by middleware operators.

## Requirements
### Requirement: Centralized System Settings Interface
The system SHALL provide a dedicated "Settings" tab in the admin dashboard for managing system-wide configurations.

#### Scenario: Admin accesses settings tab
- **WHEN** an authenticated administrator clicks on the "Settings" tab in the dashboard
- **THEN** the system SHALL display sections for SMTP Configuration, Quota Thresholds, API Budgets, and Notification Channels.

### Requirement: SMTP Configuration Management
The system SHALL allow administrators to configure SMTP settings for outgoing email alerts.

#### Scenario: Admin saves SMTP settings
- **WHEN** an administrator enters SMTP details (host, port, username, from_email, password_env) and clicks "Save SMTP"
- **THEN** the system SHALL persist these settings to the system configuration and respond with a success notification.

#### Scenario: Admin tests SMTP connection
- **WHEN** an administrator clicks "Test Connection" after entering SMTP details
- **THEN** the system SHALL attempt to send a test email to the configured admin email addresses and report the outcome (success or error).

### Requirement: Quota Threshold Configuration
The system SHALL allow administrators to define percentage-based usage thresholds for triggering quota alerts.

#### Scenario: Admin updates quota thresholds
- **WHEN** an administrator modifies Info, Warning, or Critical percentage thresholds and clicks "Save Thresholds"
- **THEN** the system SHALL update the alerting configuration and apply these new thresholds to future usage checks.

### Requirement: API Budget Management
The system SHALL allow administrators to set monthly USD budgets for different LLM providers.

#### Scenario: Admin updates provider budgets
- **WHEN** an administrator enters budget amounts for providers (e.g., OpenAI, Gemini) and clicks "Save Budgets"
- **THEN** the system SHALL persist these budget limits and use them to monitor provider-wide usage.

### Requirement: Notification Channel Toggles
The system SHALL allow administrators to enable or disable specific notification channels and types.

#### Scenario: Admin toggles notification settings
- **WHEN** an administrator toggles settings for User Email Alerts, Admin Realtime Email, Dashboard Alerts, or Daily Digest and clicks "Save Toggles"
- **THEN** the system SHALL update the notification policy accordingly.
