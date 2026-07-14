## Why

Several critical issues and bugs were introduced or left unresolved in the merged dashboard branch:
1. LiteLLM logs are written to an ephemeral, hardcoded Windows path inside the Docker container, making them inaccessible to the middleware dashboard.
2. Deleting an already soft-deleted user throws an unhandled HTTP 500 error instead of failing gracefully or returning an idempotent success.
3. RAG retrieval hit-rate calculation uses a case-sensitive and spacing-sensitive SQL `LIKE` query, causing it to miss valid RAG requests.
4. RAG base64 image migration script hardcodes `localhost:3000` for migrated images, which breaks image loading for remote clients.

## What Changes

- Update LiteLLM configuration to write logs to a proper `/app/logs/litellm.log` path mapped to the host.
- Modify the user deletion endpoint to be idempotent: returning a `200 OK` directly if a user is already soft-deleted and a purge is not requested.
- Update the RAG retrieval SQL queries to use case-insensitive and whitespace-flexible regex matching instead of case-sensitive `LIKE`.
- Modify the database migration script to use relative paths (`/v1/_mw/media/`) or resolve the domain dynamically via `MW_PUBLIC_URL` instead of hardcoding `localhost:3000`.

## Capabilities

### New Capabilities

- None

### Modified Capabilities

- `rag-health-monitor`: Improve the robustness of the citation hit-rate detection logic to support case-insensitive and whitespace-flexible source tag formats in the database request logs.

## Impact

- `litellm/litellm_config.yaml`: Logging file path updated.
- `llm-mw/api/user_admin.py`: User soft-deletion endpoint updated.
- `llm-mw/core/rag_health.py`: Database query for retrieval logs updated.
- `llm-mw/migrate_rag_base64_to_local_media.py`: Public URL generation for migrated WebP images updated to use relative paths.
