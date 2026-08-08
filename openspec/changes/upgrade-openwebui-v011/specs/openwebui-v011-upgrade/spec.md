## ADDED Requirements

### Requirement: Open WebUI Base Image Version Upgrade
The system SHALL use `ghcr.io/open-webui/open-webui:v0.11.0` as the base image in `Dockerfile.openwebui`.

#### Scenario: Open WebUI image build and startup
- **WHEN** the container image is built and started via `docker compose up -d --build`
- **THEN** `openwebui-app` container runs version v0.11.0 and completes startup without migration failures

### Requirement: Pre-upgrade PostgreSQL Database Backup
The system SHALL execute a full PostgreSQL database dump of the `openwebui` database prior to running schema migrations.

#### Scenario: Database backup creation
- **WHEN** the database backup command is executed
- **THEN** a valid `.sql` dump file is generated in the backups directory

### Requirement: Middleware Database SQL Query Compatibility
The Middleware API SHALL execute all direct SQL queries against the updated PostgreSQL database schema without syntax or column missing errors.

#### Scenario: Analytics API query execution
- **WHEN** an admin user accesses `/v1/_mw/admin/analytics/chat` or `/v1/_mw/admin/groups`
- **THEN** the middleware queries the PostgreSQL database and returns structured JSON metrics with a 200 OK status
