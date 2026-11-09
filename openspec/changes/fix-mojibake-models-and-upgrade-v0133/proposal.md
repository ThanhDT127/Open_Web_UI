## Why

1. **CP437 Mojibake in PostgreSQL (`openwebui` DB)**: Vietnamese text and emojis across `chat`, `model`, `knowledge`, `document`, `prompt`, `group`, `tool`, `memory`, and `tag` tables were corrupted (`Hß╗ù trß╗ú Gß╗¡i Email ≡ƒôº`, `Trß╗ú l├╜ ß║úo Hß╗úp ─Éß╗ông`) when `pg_dump` output was redirected through Windows PowerShell (`>` decoded UTF-8 bytes as CP437 and re-encoded as UTF-8).
2. **Missing Model Capabilities/Tools & Vertex 403 on `chat-gemini-2.5-flash`**: 14 models seeded into `public.model` (`chat-gpt-5.4`, `openai-auto`, `claude-auto`, `gemini-auto`, `grok-auto`, `deepseek-auto`, `chat-claude-opus-4.6`, `chat-claude-sonnet-4.6`, `chat-gemini-3.1-pro`, `chat-gemini-3.1-flash-lite`, `chat-gemini-2.5-flash-openrouter`, `chat-grok-4.1-fast`, `chat-grok-4.20`, `chat-deepseek-v4-pro`, `chat-deepseek-v4-flash`) had `capabilities: null` and no `toolIds`/`defaultFeatureIds`, stripping Web Search, Vision, File Upload, Code Interpreter, and MCP/Gmail tools in the UI. Additionally, `chat-gemini-2.5-flash` (default pinned model and base model for Workspace presets `demo` and `test-rag`) pointed to `vertex_ai/gemini-2.5-flash` (`403 SERVICE_DISABLED`) instead of `gemini/gemini-2.5-flash` (`GEMINI_API_KEY`).
3. **Open WebUI Version Outdated (`v0.11.0` vs `v0.13.3`)**: `Dockerfile.openwebui` was pinned to `v0.11.0` while upstream released `v0.13.3`.

## What Changes

- Create a deterministic, idempotent CP437-to-UTF-8 recovery utility (`scripts/db_maintenance/fix_cp437_mojibake_and_models.py`) that detects CP437 mojibake sequences without touching valid Vietnamese UTF-8 and repairs all affected text/JSON columns in PostgreSQL (`openwebui` and `middleware` DBs).
- Synchronize full `capabilities`, `toolIds`, `defaultFeatureIds`, `profile_image_url`, and wildcard `read` `access_grant` entries for all active chat and `*-auto` models in `public.model`, and align `rag.docling_server_url` in `public.config` with `http://middleware:5000/docling-proxy`.
- Switch `chat-gemini-2.5-flash` and `gemini-embedding-2` in `litellm/litellm_config.yaml` to `gemini/` with `os.environ/GEMINI_API_KEY` so default chat and Workspace presets (`demo`, `test-rag`) return `HTTP 200`.
- Upgrade `Dockerfile.openwebui` from `ghcr.io/open-webui/open-webui:v0.11.0` to `ghcr.io/open-webui/open-webui:v0.13.3` after taking a pre-upgrade `pg_dump` backup on the VM.

## Impact

- Modified files: `Dockerfile.openwebui`, `litellm/litellm_config.yaml`
- New files: `scripts/db_maintenance/fix_cp437_mojibake_and_models.py`, `tests/test_mojibake_models_and_v0133.py`
