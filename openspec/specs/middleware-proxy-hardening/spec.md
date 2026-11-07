# middleware-proxy-hardening Specification

## Purpose
Ensure multi-worker Middleware (`llm-mw`), Nginx reverse proxy, and LiteLLM gateway operate safely under concurrent enterprise load behind shared office NAT without event-loop stalls, duplicate cron digests, log rotation races, or connection pool exhaustion.

## Requirements

### Requirement: Bounded Multi-Worker Database Pool
Middleware MUST initialize PostgreSQL connection pools (`middleware` and `openwebui`) with configurable `DB_POOL_MIN` (default `2`) and `DB_POOL_MAX` (default `10`) per worker so two workers consume at most 40 connections out of PostgreSQL `max_connections=150`.

#### Scenario: Default pool limits under 2 workers
- **WHEN** `DB_POOL_MIN` and `DB_POOL_MAX` are not set in the environment
- **THEN** `config.py` passes `minconn=2` and `maxconn=10` to `init_pool()`

### Requirement: Non-Blocking Event Loop for Docling ZIP & Audit Logging
Middleware MUST offload CPU-bound/blocking ZIP image extraction, WebP conversion, and `psycopg2`/file log writes to worker threads when invoked inside an active `asyncio` event loop.

#### Scenario: Concurrent coroutine responsiveness during Docling ZIP conversion and logging
- **WHEN** `docling_proxy` processes a ZIP archive containing images or `detail_log`/`write_audit_line` dual-writes to DB inside an async request
- **THEN** blocking compression and DB writes execute on a background thread without blocking concurrent tasks on the event loop

### Requirement: Single-Execution Daily Digest Across Workers
Daily digest cron (`send_daily_digest`) MUST acquire a PostgreSQL leader advisory lock and verify the `Asia/Ho_Chi_Minh` calendar date in `mw_config` before sending SMTP email so multiple Uvicorn workers send at most one digest email per day.

#### Scenario: Two workers trigger daily digest on the same morning
- **WHEN** Worker 1 and Worker 2 both invoke `send_daily_digest()` for the same Vietnam date
- **THEN** exactly one SMTP digest email is sent and the second worker skips cleanly

### Requirement: Multi-Process Safe Log Rotation
All rotating file loggers in Middleware MUST synchronize emission and rollover via an inter-process file lock and reopen stale file streams if another worker rotated the file.

#### Scenario: Concurrent writes across rollover threshold
- **WHEN** multiple handlers targeting the same log file write past `maxBytes`
- **THEN** rollover succeeds without `PermissionError`/`FileNotFoundError` and subsequent writes land in the active log file rather than a rotated backup

### Requirement: Corporate NAT-Safe Nginx & Deduplicated LiteLLM Config
Nginx MUST apply login rate-limiting only to `POST` requests (`60r/m`, `burst=30`, status `429`), enable `keepalive` on upstream blocks, and `litellm_config.yaml` MUST contain no duplicate top-level keys.

#### Scenario: Office users behind one NAT IP load Open WebUI and LiteLLM parses config
- **WHEN** `GET /api/v1/auths/` session checks arrive from a shared NAT IP and `litellm_config.yaml` is parsed with strict duplicate-key detection
- **THEN** `GET` requests bypass the `login` rate-limit key, upstreams reuse keepalive connections, and `litellm_config.yaml` parses with zero duplicate top-level keys
