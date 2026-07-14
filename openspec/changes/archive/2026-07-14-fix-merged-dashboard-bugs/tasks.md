## 1. LiteLLM Configuration

- [x] 1.1 Remove the duplicate Groq models block in `litellm/litellm_config.yaml` (since Groq is no longer used) to fix the YAML schema conflict.
- [x] 1.2 Update the `logging.file` path in `litellm/litellm_config.yaml` from the hardcoded Windows path to the standard path `/app/logs/litellm.log`.

## 2. Idempotent User Soft-Deletion

- [x] 2.1 Update `delete_user_endpoint` inside `llm-mw/api/user_admin.py` to check if the user is already soft-deleted when `purge` is `False`, returning a `200 OK` idempotent success directly.

## 3. Case-Insensitive RAG Citation Query

- [x] 3.1 Update the RAG retrieval query inside `llm-mw/core/rag_health.py` to use PostgreSQL regex operator `~* '<source\\s+id\\s*='` instead of the case-sensitive `LIKE '%%<source id=%%'`.

## 4. Relative URL path in Base64 Migration

- [x] 4.1 Update `process_base64_string` inside `llm-mw/migrate_rag_base64_to_local_media.py` to use relative path `/v1/_mw/media/` for image URLs instead of the hardcoded `https://localhost:3000`.
