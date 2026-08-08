## Why

Open WebUI v0.11.x provides a major architectural overhaul, including enhanced performance, new workspace capabilities, updated task management, and bug fixes over the current v0.9.6 image. We need a safe, verified upgrade path that updates the base image, handles PostgreSQL database migrations cleanly, and verifies that the middleware API and direct SQL queries remain fully functional without downtime or data corruption.

## What Changes

- **Base Image Update**: Update `Dockerfile.openwebui` from `ghcr.io/open-webui/open-webui:v0.9.6` to `ghcr.io/open-webui/open-webui:v0.11.0`.
- **Database Backup & Migration**: Establish automated database backup procedures prior to running v0.11.0 schema migrations.
- **Middleware SQL Schema Compatibility**: Audit and verify all direct SQL queries in `llm-mw/api/` (`analytics.py`, `group_analytics.py`, `knowledge_analytics.py`, `user_admin.py`) against any updated PostgreSQL tables/columns in v0.11.0.
- **Persistent Configuration Flag**: Configure `ENABLE_PERSISTENT_CONFIG=False` or adjust `.env` variables if needed to ensure environment variable settings are respected.
- **Verification & Testing**: Perform full system build, container health checks, and dashboard integration tests.

## Capabilities

### New Capabilities
- `openwebui-v011-upgrade`: Provides standard upgrade, database migration verification, and SQL schema compatibility checks for Open WebUI v0.11.0.

### Modified Capabilities
<!-- None -->

## Impact

- `Dockerfile.openwebui`: Updates `FROM` line to `v0.11.0`.
- `openwebui-postgres`: Database schema will be updated automatically by Open WebUI v0.11 migration script.
- `llm-mw/api/`: SQL queries in analytics and admin modules verified and adjusted if required.
- `docker-compose`: All containers rebuilt and restarted simultaneously.
