## Context

Several critical bugs and configuration errors were identified in the merged dashboard branch:
1. LiteLLM logs are written to a hardcoded Windows path inside the Linux container, resulting in lost log files and inaccessible logs in the middleware.
2. Soft-deleted user deletion triggers an HTTP 500 error when deletion is run again, instead of behaving idempotently.
3. RAG retrieval citation hit-rate checks are case and space-sensitive, missing some valid requests.
4. RAG base64 image migration script hardcodes `localhost:3000` for public URLs, breaking image loads for remote users.

## Goals / Non-Goals

**Goals:**
- Fix the LiteLLM log file location inside `litellm_config.yaml`.
- Implement idempotent soft-deletion of users inside `user_admin.py`.
- Improve the SQL query filtering for RAG citation logs to be case and space-insensitive.
- Update base64 image migration to use relative paths for migrated WebP images instead of hardcoding localhost.

**Non-Goals:**
- Re-enabling Groq models or altering any other parts of model configuration in LiteLLM.
- Altering the database schema or connection pooling design.

## Decisions

### Decision 1: LiteLLM Log Path Adjustment
- **Choice**: Update `logging.file` inside `litellm/litellm_config.yaml` to `/app/logs/litellm.log`.
- **Rationale**: The LiteLLM docker service mounts a persistent volume `litellm_logs` to `/app/logs`. Writing logs to this path ensures they are preserved across container restarts and can be correctly consumed by other services.

### Decision 2: Idempotent Soft-Delete API
- **Choice**: In `delete_user_endpoint`, inspect if the user record already has `deleted_at` set. If `purge=False`, return a standard `200 OK` response directly.
- **Rationale**: Prevents attempting database updates that modify 0 rows and return `False`, which previously resulted in a 500 error. Making deletion idempotent is standard REST design and prevents confusing errors in the dashboard UI.

### Decision 3: Robust SQL Matching for RAG Citations
- **Choice**: Replace the case-sensitive `LIKE '%%<source id=%%'` operator with the case-insensitive regular expression operator `~* '<source\\s+id\\s*='`.
- **Rationale**: Open WebUI's source tag markup injection is prone to casing and spacing variations (e.g. `<SOURCE id="..."` or `<source  id="..."`). Regex matching ensures the retrieval health monitor captures all valid RAG-attached queries.

### Decision 4: Relative URLs for Migrated Images
- **Choice**: Use the relative path `/v1/_mw/media/{filename}` in the base64 migration script.
- **Rationale**: Relative paths are fully domain-independent and resolve correctly in the user's browser, whether they access the chatbot via `localhost` or a public domain.

## Risks / Trade-offs

- **[Risk 1]** Regex search (`~*`) in PostgreSQL performs slower than simple `LIKE` comparisons.
  - **Mitigation**: The query applies the timestamp index filter `ts >= %s AND ts <= %s` first, which significantly limits the search space before regex matching is run.
