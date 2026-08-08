## 1. Database Backup & Safety Prep

- [x] 1.1 Perform PostgreSQL database backup using `docker exec openwebui-postgres pg_dump` to `backups/openwebui_pre_v011.sql`
- [x] 1.2 Verify backup SQL file size and non-empty table statements

## 2. Docker Base Image Update

- [x] 2.1 Update `Dockerfile.openwebui` line 1 from `ghcr.io/open-webui/open-webui:v0.9.6` to `ghcr.io/open-webui/open-webui:v0.11.0`
- [x] 2.2 Rebuild and start container services via `docker compose up -d --build`

## 3. Post-Upgrade Verification & Audit

- [x] 3.1 Inspect Open WebUI container logs for successful Alembic database migration completion
- [x] 3.2 Test Middleware SQL query endpoints (`/v1/_mw/admin/analytics/chat`, `/v1/_mw/admin/groups`, `/v1/_mw/admin/knowledge/inventory`) for 200 OK status
- [x] 3.3 Verify user login and dashboard metrics rendering post-upgrade
