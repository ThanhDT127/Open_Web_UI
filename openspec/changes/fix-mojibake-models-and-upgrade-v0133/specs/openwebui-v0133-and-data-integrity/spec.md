## ADDED Requirements

### Requirement: Lossless CP437 Mojibake Repair
The maintenance script MUST detect strings where UTF-8 bytes were misinterpreted as CP437 (`Hß╗ù`, `≡ƒ`, `├í`, `─É`, etc.) and losslessly restore original UTF-8 text and JSON structures while leaving already-valid Vietnamese UTF-8 strings unchanged.

#### Scenario: Repairing corrupted Vietnamese and emoji strings idempotently
- **WHEN** `repair_cp437_mojibake()` runs on corrupted strings (`"Hß╗ù trß╗ú Gß╗¡i Email ≡ƒôº"`, `"Trß╗ú l├╜ ß║úo Hß╗úp ─Éß╗ông"`) and then runs a second time on the repaired strings
- **THEN** the first pass restores `"Hỗ trợ Gửi Email 📧"` and `"Trợ lý ảo Hợp Đồng"`, and the second pass leaves them unchanged

### Requirement: Complete Model Capabilities and Live Gemini 2.5 Flash Routing
All active chat and smart-routing (`*-auto`) models in Open WebUI `public.model` MUST have non-null `capabilities` (`vision`, `file_upload`, `web_search`, `image_generation`, `code_interpreter`, `citations`, `status_updates`, `builtin_tools`) and `toolIds` configured, and `chat-gemini-2.5-flash` in `litellm/litellm_config.yaml` MUST route via `gemini/gemini-2.5-flash` using `GEMINI_API_KEY`.

#### Scenario: Inspecting model configuration and calling chat-gemini-2.5-flash
- **WHEN** `litellm/litellm_config.yaml` and `public.model` are inspected and `chat-gemini-2.5-flash` is called through Middleware
- **THEN** `chat-gemini-2.5-flash` uses `gemini/gemini-2.5-flash` with `os.environ/GEMINI_API_KEY` (`HTTP 200`) and all 14 seeded models have full `capabilities` and `toolIds`

### Requirement: Open WebUI v0.13.3 Image Upgrade and Multi-Worker Redis Tether Configuration
`Dockerfile.openwebui` MUST build from `ghcr.io/open-webui/open-webui:v0.13.3` while preserving DejaVu fonts, export dependencies (`fpdf2`, `openpyxl`, `python-docx`), optional NLTK data, and directory ownership (`1000:0`), and `docker-compose.yml` MUST set `REDIS_URL=redis://redis:6379/1` on `open-webui` when `UVICORN_WORKERS > 1` so Open WebUI v0.13.3 Tether hub does not reject `/api/chat/completions` with `HTTP 503`.

#### Scenario: Verifying Dockerfile.openwebui base image, REDIS_URL, and runtime version
- **WHEN** `Dockerfile.openwebui` and `docker-compose.yml` are built and deployed to `openwebui-app`
- **THEN** `Dockerfile.openwebui` specifies `FROM ghcr.io/open-webui/open-webui:v0.13.3`, `docker-compose.yml` sets `REDIS_URL=redis://redis:6379/1`, `/api/version` reports `0.13.3`, and `/api/chat/completions` succeeds (`HTTP 200`) across multiple workers
