"""
PostgreSQL database layer for LLM Middleware.

Manages connection pool, schema creation, and data migration from JSON files.
All middleware data (users, prices, config, logs) lives in the 'middleware' database
on the same PostgreSQL instance used by Open WebUI.
"""

import os
import json
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

import psycopg2
import psycopg2.pool
import psycopg2.extras
from psycopg2 import sql

logger = logging.getLogger("llm_mw")

# ─── Connection pool ─────────────────────────────────────────

_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
_ow_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None


def _parse_dsn(database_url: str) -> dict:
    """Parse DATABASE_URL into keyword args for psycopg2."""
    # postgresql://user:pass@host:port/dbname
    from urllib.parse import urlparse
    parsed = urlparse(database_url)
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": parsed.username or "openwebui_user",
        "password": parsed.password or "",
        "dbname": parsed.path.lstrip("/") or "middleware",
    }


def _ensure_database(database_url: str):
    """
    Ensure the 'middleware' database exists on the PostgreSQL instance.
    Connects to 'postgres' default DB to create it if needed.
    """
    params = _parse_dsn(database_url)
    target_db = params["dbname"]

    # Connect to default 'postgres' database
    conn = psycopg2.connect(
        host=params["host"],
        port=params["port"],
        user=params["user"],
        password=params["password"],
        dbname="postgres",
    )
    conn.autocommit = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
        if not cur.fetchone():
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db)))
            logger.info("Created database '%s'", target_db)
        cur.close()
    finally:
        conn.close()


def init_pool(database_url: str, minconn: int = 2, maxconn: int = 10):
    """
    Initialize the connection pool. Called once at startup.
    Creates the target database if it doesn't exist, then creates tables.
    """
    global _pool, _ow_pool
    if _pool is not None:
        return

    _ensure_database(database_url)

    params = _parse_dsn(database_url)
    _pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=minconn,
        maxconn=maxconn,
        host=params["host"],
        port=params["port"],
        user=params["user"],
        password=params["password"],
        dbname=params["dbname"],
    )
    logger.info("DB pool initialized: %s@%s:%s/%s (min=%d, max=%d)",
                params["user"], params["host"], params["port"],
                params["dbname"], minconn, maxconn)

    # Initialize openwebui read-only connection pool
    try:
        ow_db_url = os.getenv("OPENWEBUI_DATABASE_URL", "").strip()
        if ow_db_url:
            ow_params = _parse_dsn(ow_db_url)
        else:
            ow_params = params.copy()
            ow_params["dbname"] = "openwebui"

        _ow_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=minconn,
            maxconn=maxconn,
            host=ow_params["host"],
            port=ow_params["port"],
            user=ow_params["user"],
            password=ow_params["password"],
            dbname=ow_params["dbname"],
        )
        logger.info("Open WebUI DB pool initialized: %s@%s:%s/%s (min=%d, max=%d)",
                    ow_params["user"], ow_params["host"], ow_params["port"], ow_params["dbname"], minconn, maxconn)
    except Exception as e:
        logger.error("Failed to initialize Open WebUI DB pool: %s", str(e))

    # Create tables
    _create_tables()

    # Auto-migrate from JSON if tables are empty
    _auto_migrate_if_empty()

    # Verify Open WebUI schema
    check_ow_schema()


def get_conn():
    """Get a connection from the pool."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool() first.")
    return _pool.getconn()


def put_conn(conn):
    """Return a connection to the pool."""
    if _pool is not None:
        _pool.putconn(conn)


@contextmanager
def db_conn():
    """Context manager for database connections with auto-commit/rollback."""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)


def get_ow_conn():
    """Get a connection from the Open WebUI pool."""
    if _ow_pool is None:
        raise RuntimeError("Open WebUI database pool not initialized. Call init_pool() first.")
    return _ow_pool.getconn()


def put_ow_conn(conn):
    """Return a connection to the Open WebUI pool."""
    if _ow_pool is not None:
        _ow_pool.putconn(conn)


@contextmanager
def db_ow_conn():
    """Context manager for Open WebUI database connections (read-only)."""
    conn = get_ow_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_ow_conn(conn)


def check_ow_schema() -> bool:
    """
    Verify that the Open WebUI 'user' table has the necessary columns.
    Logged at startup to prevent runtime errors.
    """
    try:
        with db_ow_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'user' AND column_name IN ('email', 'role', 'name')
            """)
            cols = [r[0] for r in cur.fetchall()]
            cur.close()
            if len(cols) < 3:
                logger.error("OW schema check failed: 'user' table is missing required columns (found: %s)", cols)
                return False
            logger.info("OW schema check passed: 'user' table has required columns (email, role, name)")
            return True
    except Exception as e:
        logger.error("OW schema check error: %s", str(e))
        return False


# ─── Schema creation ─────────────────────────────────────────

_SCHEMA_SQL = """
-- Users table (replaces users.json)
CREATE TABLE IF NOT EXISTS mw_users (
    user_id        TEXT PRIMARY KEY,
    role           TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    openwebui_user_id TEXT UNIQUE,
    subkey_hash    TEXT,
    active         BOOLEAN DEFAULT true,
    allowed_models JSONB DEFAULT '["openai-auto", "gemini-auto", "grok-auto", "claude-auto", "deepseek-auto"]'::jsonb,
    used_tokens    BIGINT DEFAULT 0,
    used_cost_usd  DOUBLE PRECISION DEFAULT 0.0,
    quota          JSONB DEFAULT '{}'::jsonb,
    alerts_sent    JSONB DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ DEFAULT now(),
    updated_at     TIMESTAMPTZ DEFAULT now()
);

-- Prices table (replaces prices.json)
CREATE TABLE IF NOT EXISTS mw_prices (
    model_name TEXT PRIMARY KEY,
    pricing    JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Config table (replaces alert_config.json + system_alerts.json)
CREATE TABLE IF NOT EXISTS mw_config (
    config_key   TEXT PRIMARY KEY,
    config_value JSONB NOT NULL,
    updated_at   TIMESTAMPTZ DEFAULT now()
);

-- Pending requests (replaces pending.csv)
CREATE TABLE IF NOT EXISTS mw_pending (
    request_id TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    ts         BIGINT NOT NULL
);

-- Audit log (replaces audit.jsonl)
CREATE TABLE IF NOT EXISTS mw_audit_log (
    id            BIGSERIAL PRIMARY KEY,
    ts            TIMESTAMPTZ DEFAULT now(),
    rid           TEXT,
    user_id       TEXT,
    endpoint      TEXT,
    model         TEXT,
    purpose       TEXT,
    status        TEXT,
    status_code   INTEGER,
    latency_ms    DOUBLE PRECISION,
    tokens_in     INTEGER DEFAULT 0,
    tokens_out    INTEGER DEFAULT 0,
    tokens_total  INTEGER DEFAULT 0,
    cost_usd      DOUBLE PRECISION DEFAULT 0.0,
    image_count   INTEGER,
    tts_chars     INTEGER,
    stt_seconds   DOUBLE PRECISION,
    video_count   INTEGER,
    error_type    TEXT,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON mw_audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_audit_user ON mw_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_rid ON mw_audit_log(rid);

ALTER TABLE mw_audit_log ADD COLUMN IF NOT EXISTS auth_source TEXT;
ALTER TABLE mw_audit_log ADD COLUMN IF NOT EXISTS openwebui_user_id TEXT;

-- Request detail log (replaces middleware.requests.log)
CREATE TABLE IF NOT EXISTS mw_request_log (
    id      BIGSERIAL PRIMARY KEY,
    ts      TIMESTAMPTZ DEFAULT now(),
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reqlog_ts ON mw_request_log(ts);

-- Notifications table (alert history for dashboard + digest)
CREATE TABLE IF NOT EXISTS mw_notifications (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ DEFAULT now(),
    user_id     TEXT,
    type        TEXT NOT NULL,
    level       TEXT DEFAULT 'info',
    title       TEXT NOT NULL,
    message     TEXT NOT NULL,
    read        BOOLEAN DEFAULT false,
    emailed     BOOLEAN DEFAULT false,
    metadata    JSONB DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_notif_user ON mw_notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notif_read ON mw_notifications(read);
CREATE INDEX IF NOT EXISTS idx_notif_ts   ON mw_notifications(ts);

-- Atomic claims prevent duplicate quota alerts from concurrent requests.
CREATE TABLE IF NOT EXISTS mw_quota_alert_claims (
    user_id      TEXT NOT NULL,
    period_start BIGINT NOT NULL,
    threshold    INTEGER NOT NULL,
    alert_type   TEXT NOT NULL,
    snapshot     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, period_start, threshold, alert_type)
);

CREATE TABLE IF NOT EXISTS mw_migrations (
    migration_key TEXT PRIMARY KEY,
    details       JSONB NOT NULL DEFAULT '{}'::jsonb,
    applied_at    TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE mw_users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';
ALTER TABLE mw_users ADD COLUMN IF NOT EXISTS openwebui_user_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_mw_users_openwebui_user_id
    ON mw_users(openwebui_user_id) WHERE openwebui_user_id IS NOT NULL;
UPDATE mw_users SET role = 'user' WHERE role = 'manager' OR role IS NULL;
ALTER TABLE mw_users DROP CONSTRAINT IF EXISTS mw_users_role_check;
ALTER TABLE mw_users ADD CONSTRAINT mw_users_role_check CHECK (role IN ('admin', 'user'));
INSERT INTO mw_migrations (migration_key, details)
VALUES ('2026-06-10-manager-role-to-user', '{"manager_role_migrated_to":"user"}'::jsonb)
ON CONFLICT (migration_key) DO NOTHING;

-- User OAuth Integrations table (added for Phase 2)
CREATE TABLE IF NOT EXISTS mw_user_integrations (
    id SERIAL PRIMARY KEY,
    user_id_hash VARCHAR(64) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    expires_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT unique_user_provider UNIQUE (user_id_hash, provider)
);

-- Tool approvals table (added for Phase 2 Change 4)
CREATE TABLE IF NOT EXISTS mw_tool_approvals (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    tool_name   TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    payload     JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);
"""


def _create_tables():
    """Create all middleware tables if they don't exist."""
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute(_SCHEMA_SQL)
        
        # Setup mcp_readonly_user dynamically
        mcp_password = os.getenv("MCP_DATABASE_PASSWORD") or os.getenv("POSTGRES_PASSWORD")
        if mcp_password:
            try:
                cur.execute(
                    sql.SQL("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'mcp_readonly_user') THEN
                                CREATE ROLE mcp_readonly_user WITH LOGIN PASSWORD {};
                            ELSE
                                ALTER ROLE mcp_readonly_user WITH PASSWORD {};
                            END IF;
                        END
                        $$;
                    """).format(sql.Literal(mcp_password), sql.Literal(mcp_password))
                )
                cur.execute("""
                    GRANT CONNECT ON DATABASE middleware TO mcp_readonly_user;
                    GRANT USAGE ON SCHEMA public TO mcp_readonly_user;
                    GRANT SELECT ON ALL TABLES IN SCHEMA public TO mcp_readonly_user;
                    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO mcp_readonly_user;
                """)
                logger.info("Successfully created/updated 'mcp_readonly_user' role with read-only privileges")
            except Exception as e:
                logger.error("Failed to setup mcp_readonly_user role: %s", str(e))
        else:
            logger.warning("MCP_DATABASE_PASSWORD is not set - skipping mcp_readonly_user setup")

        cur.close()
    logger.info("Database schema verified/created")


# ─── JSON → DB migration ─────────────────────────────────────

def _auto_migrate_if_empty():
    """Import data from JSON files. Always syncs missing users on startup."""
    # Compute paths locally to avoid circular import with config.py
    _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.path.join(_base, "data")
    BACKUP_DATA_DIR = os.path.join(DATA_DIR, "backup")

    with db_conn() as conn:
        cur = conn.cursor()

        # Check if mw_users is empty
        cur.execute("SELECT count(*) FROM mw_users")
        user_count = cur.fetchone()[0]

        if user_count == 0:
            logger.info("mw_users is empty — full import from JSON files...")
            _import_users(conn, cur, BACKUP_DATA_DIR, DATA_DIR)
            _import_prices(conn, cur, BACKUP_DATA_DIR, DATA_DIR)
            _import_config(conn, cur, BACKUP_DATA_DIR, DATA_DIR)
            _import_pending(conn, cur, BACKUP_DATA_DIR, DATA_DIR)
            logger.info("JSON → DB migration complete")
        else:
            # Always sync missing users and prices from JSON (ON CONFLICT DO NOTHING)
            logger.info("DB has %d users — syncing missing users and prices from JSON...", user_count)
            _import_users(conn, cur, BACKUP_DATA_DIR, DATA_DIR)
            _import_prices(conn, cur, BACKUP_DATA_DIR, DATA_DIR)

        # Backfill subkey_hash for users with plaintext subkey but no hash
        _backfill_subkey_hashes(conn, cur)

        cur.close()


def _backfill_subkey_hashes(conn, cur):
    """Generate subkey_hash for users who have plaintext subkey but NULL hash, then drop subkey column."""
    # Check if 'subkey' column exists
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name='mw_users' AND column_name='subkey'
        )
    """)
    subkey_exists = cur.fetchone()[0]
    if not subkey_exists:
        return

    # Use centralized hash_subkey() to avoid duplicating MW_SECRET logic
    from core.auth import hash_subkey

    cur.execute("SELECT user_id, subkey FROM mw_users WHERE subkey IS NOT NULL AND subkey != '' AND subkey_hash IS NULL")
    rows = cur.fetchall()

    if rows:
        for user_id, subkey in rows:
            subkey_hash = hash_subkey(subkey)
            cur.execute("UPDATE mw_users SET subkey_hash = %s WHERE user_id = %s", (subkey_hash, user_id))
            logger.info("Backfilled subkey_hash for user: %s", user_id)
        conn.commit()
        logger.info("Backfilled subkey_hash for %d users", len(rows))

    # Safely drop the subkey column now
    cur.execute("ALTER TABLE mw_users DROP COLUMN IF EXISTS subkey")
    conn.commit()
    logger.info("Dropped plaintext 'subkey' column from mw_users table")




def _import_users(conn, cur, data_dir: str, fallback_dir: str = None):
    """Import users from users.json into mw_users table."""
    users_file = os.path.join(data_dir, "users.json")
    if not os.path.exists(users_file) and fallback_dir:
        users_file = os.path.join(fallback_dir, "users.json")
    if not os.path.exists(users_file):
        logger.warning("users.json not found — skipping")
        return

    from config import DEFAULT_ALLOWED_MODELS
    from core.auth import hash_subkey

    with open(users_file, "r", encoding="utf-8-sig") as f:
        users = json.load(f)

    for u in users:
        subkey = u.get("subkey")
        subkey_hash = u.get("subkey_hash")
        if not subkey_hash and subkey:
            subkey_hash = hash_subkey(subkey)

        allowed_models = u.get("allowed_models")
        if not allowed_models:
            allowed_models = DEFAULT_ALLOWED_MODELS

        cur.execute("""
            INSERT INTO mw_users (user_id, role, openwebui_user_id, subkey_hash,
                                  active, allowed_models, used_tokens, used_cost_usd, quota, alerts_sent)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        """, (
            u.get("user_id"),
            "user" if u.get("role") == "manager" else u.get("role", "user"),
            u.get("openwebui_user_id"),
            subkey_hash,
            u.get("active", True),
            json.dumps(allowed_models),
            u.get("used_tokens", 0),
            u.get("used_cost_usd", 0.0),
            json.dumps(u.get("quota", {})),
            json.dumps(u.get("alerts_sent", {})),
        ))

    logger.info("Imported %d users from users.json", len(users))


def _import_prices(conn, cur, data_dir: str, fallback_dir: str = None):
    """Import prices from prices.json into mw_prices table."""
    prices_file = os.path.join(data_dir, "prices.json")
    if not os.path.exists(prices_file) and fallback_dir:
        prices_file = os.path.join(fallback_dir, "prices.json")
    if not os.path.exists(prices_file):
        logger.warning("prices.json not found — skipping")
        return

    with open(prices_file, "r", encoding="utf-8") as f:
        prices = json.load(f)

    # Store _schema as a special row
    schema_info = prices.pop("_schema", None)
    if schema_info:
        cur.execute("""
            INSERT INTO mw_prices (model_name, pricing)
            VALUES ('_schema', %s)
            ON CONFLICT (model_name) DO NOTHING
        """, (json.dumps(schema_info),))

    for model_name, pricing in prices.items():
        cur.execute("""
            INSERT INTO mw_prices (model_name, pricing)
            VALUES (%s, %s)
            ON CONFLICT (model_name) DO NOTHING
        """, (model_name, json.dumps(pricing)))

    logger.info("Imported %d price entries from prices.json", len(prices))


def _import_config(conn, cur, data_dir: str, fallback_dir: str = None):
    """Import alert_config.json and system_alerts.json into mw_config."""
    # Alert config
    alert_file = os.path.join(data_dir, "alert_config.json")
    if not os.path.exists(alert_file) and fallback_dir:
        alert_file = os.path.join(fallback_dir, "alert_config.json")
    if os.path.exists(alert_file):
        with open(alert_file, "r", encoding="utf-8") as f:
            config = json.load(f)
        cur.execute("""
            INSERT INTO mw_config (config_key, config_value)
            VALUES ('alert_config', %s)
            ON CONFLICT (config_key) DO NOTHING
        """, (json.dumps(config),))
        logger.info("Imported alert_config.json")

    alerts_file = os.path.join(data_dir, "system_alerts.json")
    if not os.path.exists(alerts_file) and fallback_dir:
        alerts_file = os.path.join(fallback_dir, "system_alerts.json")
    if os.path.exists(alerts_file):
        with open(alerts_file, "r", encoding="utf-8") as f:
            try:
                alerts = json.load(f)
            except json.JSONDecodeError:
                alerts = {}
        cur.execute("""
            INSERT INTO mw_config (config_key, config_value)
            VALUES ('system_alerts', %s)
            ON CONFLICT (config_key) DO NOTHING
        """, (json.dumps(alerts),))
        logger.info("Imported system_alerts.json")


def _import_pending(conn, cur, data_dir: str, fallback_dir: str = None):
    """Import pending.csv into mw_pending table."""
    import csv
    pending_file = os.path.join(data_dir, "pending.csv")
    if not os.path.exists(pending_file) and fallback_dir:
        pending_file = os.path.join(fallback_dir, "pending.csv")
    if not os.path.exists(pending_file):
        return

    with open(pending_file, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if len(rows) <= 1:
        return  # Empty or header-only

    count = 0
    for row in rows[1:]:
        if len(row) >= 3:
            cur.execute("""
                INSERT INTO mw_pending (request_id, user_id, ts)
                VALUES (%s, %s, %s)
                ON CONFLICT (request_id) DO NOTHING
            """, (row[0], row[1], int(row[2])))
            count += 1

    if count:
        logger.info("Imported %d pending requests from pending.csv", count)


# ─── Helper: write to audit/request log tables ───────────────

def insert_audit_log(data: dict):
    """Insert a row into mw_audit_log. Non-blocking best-effort."""
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO mw_audit_log
                    (ts, rid, user_id, endpoint, model, purpose, status,
                     status_code, latency_ms, tokens_in, tokens_out, tokens_total,
                     cost_usd, image_count, tts_chars, stt_seconds, video_count,
                     error_type, error_message, auth_source, openwebui_user_id)
                VALUES (
                    COALESCE(%s::timestamptz, now()), %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                data.get("ts"),
                data.get("rid"),
                data.get("user_id"),
                data.get("endpoint"),
                data.get("model"),
                data.get("purpose"),
                data.get("status"),
                data.get("status_code"),
                data.get("latency_ms"),
                data.get("tokens_in", 0),
                data.get("tokens_out", 0),
                data.get("tokens_total", 0),
                data.get("cost_usd", 0.0),
                data.get("image_count"),
                data.get("tts_chars"),
                data.get("stt_seconds"),
                data.get("video_count"),
                data.get("error_type"),
                data.get("error_message"),
                data.get("auth_source"),
                data.get("openwebui_user_id"),
            ))
            cur.close()
    except Exception as e:
        logger.error("insert_audit_log failed: %s", str(e))


def insert_request_log(payload: dict):
    """Insert a row into mw_request_log. Non-blocking best-effort."""
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO mw_request_log (payload) VALUES (%s)",
                (json.dumps(payload, ensure_ascii=False),)
            )
            cur.close()
    except Exception as e:
        logger.error("insert_request_log failed: %s", str(e))


# ─── Single-user query functions (O(1) indexed) ─────────────

_USER_COLUMNS = (
    "user_id", "role", "openwebui_user_id", "subkey_hash", "active",
    "allowed_models", "used_tokens", "used_cost_usd", "quota", "alerts_sent"
)

_USER_SELECT = """
    SELECT user_id, role, openwebui_user_id, subkey_hash, active,
           allowed_models, used_tokens, used_cost_usd, quota, alerts_sent
    FROM mw_users
"""


def _row_to_user_dict(row) -> Optional[Dict[str, Any]]:
    """Convert a DB row tuple to user dict. Returns None if row is None."""
    if not row:
        return None
    from config import DEFAULT_ALLOWED_MODELS
    return {
        "user_id": row[0],
        "role": row[1] or "user",
        "openwebui_user_id": row[2],
        "subkey": None,
        "subkey_hash": row[3],
        "active": row[4],
        "allowed_models": row[5] if row[5] else DEFAULT_ALLOWED_MODELS,
        "used_tokens": row[6] or 0,
        "used_cost_usd": row[7] or 0.0,
        "quota": row[8] if row[8] else {},
        "alerts_sent": row[9] if row[9] else {},
    }


def get_user_by_id_db(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a single user by user_id using indexed PRIMARY KEY lookup.
    Returns user dict or None. O(1) complexity.
    """
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(_USER_SELECT + " WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            cur.close()
        return _row_to_user_dict(row)
    except Exception as e:
        logger.error("get_user_by_id_db failed user=%s: %s", user_id, str(e))
        return None


def get_user_by_openwebui_id_db(openwebui_user_id: str) -> Optional[Dict[str, Any]]:
    """Get one middleware user by unique Open WebUI UUID mapping."""
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(_USER_SELECT + " WHERE openwebui_user_id = %s", (openwebui_user_id,))
            row = cur.fetchone()
            cur.close()
        return _row_to_user_dict(row)
    except Exception as e:
        logger.error("get_user_by_openwebui_id_db failed openwebui_user=%s: %s", openwebui_user_id, str(e))
        return None


def update_user_quota_db(
    user_id: str,
    *,
    add_tokens: int = 0,
    add_cost_usd: float = 0.0,
    add_image_requests: int = 0,
    add_stt_requests: int = 0,
) -> bool:
    """
    Atomically increment user quota counters in a single UPDATE.
    Uses SQL arithmetic (field = field + value) — no application-level lock needed.
    Returns True if user was found and updated.
    """
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            # Build the atomic update: increment both top-level and quota JSON fields
            cur.execute("""
                UPDATE mw_users SET
                    used_tokens = COALESCE(used_tokens, 0) + %s,
                    used_cost_usd = COALESCE(used_cost_usd, 0) + %s,
                    quota = jsonb_set(
                        jsonb_set(
                            jsonb_set(
                                jsonb_set(
                                    COALESCE(quota, '{}'::jsonb),
                                    '{used_tokens}',
                                    to_jsonb(COALESCE((quota->>'used_tokens')::bigint, 0) + %s)
                                ),
                                '{used_cost_usd}',
                                to_jsonb(COALESCE((quota->>'used_cost_usd')::double precision, 0) + %s)
                            ),
                            '{used_image_requests}',
                            to_jsonb(COALESCE((quota->>'used_image_requests')::int, 0) + %s)
                        ),
                        '{used_stt_requests}',
                        to_jsonb(COALESCE((quota->>'used_stt_requests')::int, 0) + %s)
                    ),
                    updated_at = now()
                WHERE user_id = %s
            """, (
                add_tokens, add_cost_usd,
                add_tokens, add_cost_usd,
                add_image_requests, add_stt_requests,
                user_id,
            ))
            updated = cur.rowcount > 0
            cur.close()
        return updated
    except Exception as e:
        logger.error("update_user_quota_db failed user=%s: %s", user_id, str(e))
        return False


def update_user_alerts_db(user_id: str, alerts_sent: dict) -> bool:
    """
    Update the alerts_sent JSON field for a single user.
    Returns True if user was found and updated.
    """
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE mw_users SET
                    alerts_sent = %s,
                    updated_at = now()
                WHERE user_id = %s
            """, (json.dumps(alerts_sent), user_id))
            updated = cur.rowcount > 0
            cur.close()
        return updated
    except Exception as e:
        logger.error("update_user_alerts_db failed user=%s: %s", user_id, str(e))
        return False


def reset_user_quota_period_db(user_id: str, period_start: int) -> Optional[Dict[str, Any]]:
    """Reset one user's period counters and alert state if its anchor is stale."""
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE mw_users SET
                    quota = jsonb_set(
                        jsonb_set(
                            jsonb_set(
                                jsonb_set(
                                    jsonb_set(
                                        COALESCE(quota, '{}'::jsonb),
                                        '{period_start}', to_jsonb(%s::bigint)
                                    ),
                                    '{used_tokens}', '0'::jsonb
                                ),
                                '{used_cost_usd}', '0'::jsonb
                            ),
                            '{used_image_requests}', '0'::jsonb
                        ),
                        '{used_stt_requests}', '0'::jsonb
                    ),
                    alerts_sent = '{}'::jsonb,
                    updated_at = now()
                WHERE user_id = %s
                  AND COALESCE((quota->>'period_start')::bigint, 0) < %s
                RETURNING user_id, role, openwebui_user_id, subkey_hash,
                          active, allowed_models, used_tokens, used_cost_usd, quota, alerts_sent
            """, (period_start, user_id, period_start))
            row = cur.fetchone()
            if not row:
                cur.execute(_USER_SELECT + " WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
            cur.close()
        return _row_to_user_dict(row)
    except Exception as e:
        logger.error("reset_user_quota_period_db failed user=%s: %s", user_id, str(e))
        return None


def clear_user_quota_usage_db(user_id: str) -> Optional[Dict[str, Any]]:
    """Explicitly clear one user's period usage without changing period alert claims."""
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE mw_users SET
                    quota = jsonb_set(
                        jsonb_set(
                            jsonb_set(
                                jsonb_set(COALESCE(quota, '{}'::jsonb), '{used_tokens}', '0'::jsonb),
                                '{used_cost_usd}', '0'::jsonb
                            ),
                            '{used_image_requests}', '0'::jsonb
                        ),
                        '{used_stt_requests}', '0'::jsonb
                    ),
                    updated_at = now()
                WHERE user_id = %s
                RETURNING user_id, role, openwebui_user_id, subkey_hash,
                          active, allowed_models, used_tokens, used_cost_usd, quota, alerts_sent
            """, (user_id,))
            row = cur.fetchone()
            cur.close()
        return _row_to_user_dict(row)
    except Exception as e:
        logger.error("clear_user_quota_usage_db failed user=%s: %s", user_id, str(e))
        return None


def update_user_admin_fields_db(
    user_id: str,
    *,
    active=None,
    allowed_models=None,
    quota_limits: Optional[Dict[str, Any]] = None,
    subkey_hash=None,
    role=None,
    openwebui_user_id=None,
    update_openwebui_mapping: bool = False,
) -> Optional[Dict[str, Any]]:
    """Targeted admin update that never replaces quota usage counters."""
    sets = []
    params = []
    if active is not None:
        sets.append("active = %s")
        params.append(active)
    if role is not None:
        sets.append("role = %s")
        params.append(role)
    if update_openwebui_mapping:
        sets.append("openwebui_user_id = %s")
        params.append(openwebui_user_id)
    if allowed_models is not None:
        sets.append("allowed_models = %s")
        params.append(json.dumps(allowed_models))
    if subkey_hash is not None:
        sets.append("subkey_hash = %s")
        params.append(subkey_hash)
    quota_expr = "COALESCE(quota, '{}'::jsonb)"
    quota_params = []
    for key, value in (quota_limits or {}).items():
        quota_expr = f"jsonb_set({quota_expr}, %s, %s::jsonb, true)"
        quota_params.extend([[key], json.dumps(value)])
    if quota_limits:
        sets.append(f"quota = {quota_expr}")
        params.extend(quota_params)
    if not sets:
        return get_user_by_id_db(user_id)
    sets.append("updated_at = now()")
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE mw_users SET {', '.join(sets)} WHERE user_id = %s "
                "RETURNING user_id, role, openwebui_user_id, subkey_hash, "
                "active, allowed_models, used_tokens, used_cost_usd, quota, alerts_sent",
                (*params, user_id),
            )
            row = cur.fetchone()
            cur.close()
        return _row_to_user_dict(row)
    except Exception as e:
        logger.error("update_user_admin_fields_db failed user=%s: %s", user_id, str(e))
        return None


def create_user_db(user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Insert one user without reading or rewriting other user records."""
    try:
        from config import DEFAULT_ALLOWED_MODELS
        allowed_models = user.get("allowed_models")
        if not allowed_models:
            allowed_models = DEFAULT_ALLOWED_MODELS

        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO mw_users
                    (user_id, role, openwebui_user_id, subkey_hash, active, allowed_models,
                     used_tokens, used_cost_usd, quota, alerts_sent)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO NOTHING
                RETURNING user_id, role, openwebui_user_id, subkey_hash,
                          active, allowed_models, used_tokens, used_cost_usd, quota, alerts_sent
            """, (
                user.get("user_id"), user.get("role", "user"), user.get("openwebui_user_id"),
                user.get("subkey_hash"),
                user.get("active", True), json.dumps(allowed_models),
                user.get("used_tokens", 0), user.get("used_cost_usd", 0.0),
                json.dumps(user.get("quota", {})), json.dumps(user.get("alerts_sent", {})),
            ))
            row = cur.fetchone()
            cur.close()
        return _row_to_user_dict(row)
    except Exception as e:
        logger.error("create_user_db failed user=%s: %s", user.get("user_id"), str(e))
        return None


def claim_quota_alert_db(
    user_id: str,
    period_start: int,
    threshold: int,
    alert_type: str,
    snapshot: Dict[str, Any],
) -> bool:
    """Atomically claim a quota alert. True means this caller owns delivery."""
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO mw_quota_alert_claims
                    (user_id, period_start, threshold, alert_type, snapshot)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (user_id, period_start, threshold, alert_type, json.dumps(snapshot)))
            claimed = cur.rowcount == 1
            if claimed:
                key = f"alert_{threshold}"
                cur.execute("""
                    UPDATE mw_users SET
                        alerts_sent = jsonb_set(
                            COALESCE(alerts_sent, '{}'::jsonb),
                            %s, to_jsonb(now()::text), true
                        ),
                        updated_at = now()
                    WHERE user_id = %s
                """, ([key], user_id))
            cur.close()
        return claimed
    except Exception as e:
        logger.error("claim_quota_alert_db failed user=%s threshold=%s: %s", user_id, threshold, str(e))
        return False


def save_tool_approval_db(approval_id: str, user_id: str, tool_name: str, payload: dict) -> bool:
    """Save or update a tool approval request."""
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO mw_tool_approvals (id, user_id, tool_name, status, payload)
                VALUES (%s, %s, %s, 'pending', %s)
                ON CONFLICT (id) DO UPDATE SET
                    status = 'pending',
                    payload = %s,
                    updated_at = now()
            """, (approval_id, user_id, tool_name, json.dumps(payload), json.dumps(payload)))
            cur.close()
        return True
    except Exception as e:
        logger.error("save_tool_approval_db failed id=%s: %s", approval_id, str(e))
        return False


def get_tool_approval_db(approval_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve details of a tool approval request."""
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, user_id, tool_name, status, payload, created_at, updated_at
                FROM mw_tool_approvals
                WHERE id = %s
            """, (approval_id,))
            row = cur.fetchone()
            cur.close()
        if row:
            return {
                "id": row[0],
                "user_id": row[1],
                "tool_name": row[2],
                "status": row[3],
                "payload": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
                "updated_at": row[6].isoformat() if row[6] else None
            }
        return None
    except Exception as e:
        logger.error("get_tool_approval_db failed id=%s: %s", approval_id, str(e))
        return None


def update_tool_approval_status_db(approval_id: str, status: str) -> bool:
    """Update status of a tool approval request."""
    try:
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE mw_tool_approvals
                SET status = %s, updated_at = now()
                WHERE id = %s
            """, (status, approval_id))
            updated = cur.rowcount > 0
            cur.close()
        return updated
    except Exception as e:
        logger.error("update_tool_approval_status_db failed id=%s status=%s: %s", approval_id, status, str(e))
        return False

