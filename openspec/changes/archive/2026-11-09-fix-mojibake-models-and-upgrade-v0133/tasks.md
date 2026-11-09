## 1. TDD Red Phase

- [x] 1.1 Write unit tests in `tests/test_mojibake_models_and_v0133.py` covering lossless/idempotent CP437-to-UTF-8 repair (text + nested JSON), model `meta` capabilities/toolIds normalization, `litellm_config.yaml` `chat-gemini-2.5-flash` Gemini API routing, and `Dockerfile.openwebui` `v0.13.3` base image

## 2. Implementation (Mojibake Repair, Model Sync, LiteLLM Route, Dockerfile v0.13.3)

- [x] 2.1 Create `scripts/db_maintenance/fix_cp437_mojibake_and_models.py` with idempotent CP437 mojibake repair and Open WebUI `public.model` / `public.config` synchronization
- [x] 2.2 Update `litellm/litellm_config.yaml` so `chat-gemini-2.5-flash` and `gemini-embedding-2` route through `gemini/` with `os.environ/GEMINI_API_KEY`
- [x] 2.3 Update `Dockerfile.openwebui` base image from `v0.11.0` to `v0.13.3` and verify pytest suite passes
- [x] 2.4 Configure `REDIS_URL=redis://redis:6379/1` in `docker-compose.yml` for Open WebUI `v0.13.3` multi-worker Tether coordination (`UVICORN_WORKERS=6`) and add unit test in `tests/test_mojibake_models_and_v0133.py`

## 3. VM Database Backup, Repair, Upgrade & Live Verification

- [x] 3.1 Commit & push to Git, pull on `VM_RAL_DBM_Open_WebUI`, and take a clean UTF-8 `pg_dump` backup (`/home/rd/openwebui/backups/pre_v0133_and_mojibake_fix.dump`)
- [x] 3.2 Execute `scripts/db_maintenance/fix_cp437_mojibake_and_models.py` against `openwebui-postgres` on VM and verify 0 remaining mojibake strings and 100% model `capabilities`/`toolIds` populated
- [x] 3.3 Recreate `litellm` and rebuild `open-webui` (`v0.13.3`) on VM, then verify `/api/version` (`0.13.3`), Alembic migrations, repaired chat/model titles, and `HTTP 200` on `chat-gemini-2.5-flash`, `test-rag`, and `chat-gpt-5.4`
