## Context

Open WebUI is deployed as a customized Docker image (`Dockerfile.openwebui`) based on `ghcr.io/open-webui/open-webui:v0.9.6`. The system uses PostgreSQL (`openwebui-postgres`) as the underlying database, which stores user profiles, chats, knowledge collections, groups, and feedback.
The custom FastAPI middleware (`llm-mw`) executes direct SQL queries on PostgreSQL tables to aggregate analytics, manage quota, and serve the Admin Dashboard.
Upgrading Open WebUI from `v0.9.6` to `v0.11.x` executes automated database migrations on container boot. We must ensure that PostgreSQL migrations execute cleanly, all containers remain synchronized, and middleware SQL queries remain compatible.

## Goals / Non-Goals

**Goals:**
- Upgrade Open WebUI container image from `v0.9.6` to `v0.11.0`.
- Perform pre-upgrade PostgreSQL database snapshot/backup to allow instant rollback if migration fails.
- Audit and adjust any direct SQL queries in `llm-mw/api/*.py` if v0.11.0 alters table schemas.
- Ensure all 10 Docker Compose services start up cleanly and pass health checks.

**Non-Goals:**
- Forking or modifying Open WebUI's frontend Svelte source code.
- Altering external provider integration APIs (LiteLLM / SearXNG / Docling).

## Decisions

- **Decision 1: Full Database Backup before Upgrade**
  - *Rationale*: Open WebUI v0.11 executes non-reversible database schema migrations on startup. A `pg_dump` backup is essential for quick restoration if schema incompatibility occurs.
  - *Alternative Considered*: In-place upgrade without backup (rejected due to risk of unrecoverable DB state).

- **Decision 2: Simultaneous Service Restart**
  - *Rationale*: Open WebUI core team strictly enforces single-version database access. Running mixed v0.9 and v0.11 instances will cause crash loops.
  - *Alternative Considered*: Rolling update (rejected per Open WebUI upgrade guidelines).

- **Decision 3: Post-Migration SQL Audit**
  - *Rationale*: Verify all middleware endpoints (`/v1/_mw/admin/analytics/chat`, `/v1/_mw/admin/groups`, `/v1/_mw/admin/knowledge/inventory`) after startup to validate schema compatibility.

## Risks / Trade-offs

- **[Risk: DB Schema Mismatch]** → *Mitigation*: Run `pg_dump` prior to upgrade. Test middleware API routes post-migration. If errors occur, update Middleware SQL query strings or restore from SQL backup.
- **[Risk: Browser Asset Caching]** → *Mitigation*: Instruct admin to perform hard refresh (`Ctrl + F5`) to clear cached v0.9 frontend assets.
