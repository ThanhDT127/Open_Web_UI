## 1. TDD Red Phase

- [x] 1.1 Write unit tests in `tests/test_middleware_proxy_hardening.py` covering DB pool defaults, non-blocking Docling/logging execution, daily digest single-leader lock, multi-process log rotation, Nginx NAT/keepalive directives, and LiteLLM YAML key uniqueness

## 2. Middleware Concurrency & Resource Hardening (`llm-mw/`)

- [x] 2.1 Add `MultiProcessRotatingFileHandler` in `llm-mw/utils/file_lock_handler.py` and wire it into `llm-mw/config.py` and `llm-mw/api/user_admin.py`
- [x] 2.2 Configure `DB_POOL_MIN=2` and `DB_POOL_MAX=10` defaults in `llm-mw/config.py` and clean up `llm-mw/core/db.py`
- [x] 2.3 Offload Docling ZIP extraction + WebP conversion + base64 materialization to `asyncio.to_thread` in `llm-mw/api/docling.py`
- [x] 2.4 Offload blocking file + `psycopg2` dual-writes in `llm-mw/utils/logging.py` to a bounded `ThreadPoolExecutor` when called on an active `asyncio` loop
- [x] 2.5 Guard `send_daily_digest()` in `llm-mw/core/notification.py` with PostgreSQL advisory lock + daily date state in `mw_config` and run blocking SMTP/DB work on a worker thread

## 3. Reverse Proxy & Gateway Config Fixes

- [x] 3.1 Update `nginx/nginx.conf` with POST-only login rate-limit (`60r/m`, `burst=30`, `limit_req_status 429`), NAT-safe API/chat rates, and `keepalive 32` upstreams
- [x] 3.2 Deduplicate `general_settings` and `logging` blocks in `litellm/litellm_config.yaml`

## 4. Verification & VM Deployment

- [x] 4.1 Run pytest suite (`tests/test_middleware_proxy_hardening.py` and `tests/test_sanitization_audit.py`) with 0 failures
- [ ] 4.2 Commit & push to Git, pull & reload `middleware`, `litellm`, `nginx` on `VM_RAL_DBM_Open_WebUI`, blindly sync live AI keys from local project folders without exposing secrets, and verify live endpoints
