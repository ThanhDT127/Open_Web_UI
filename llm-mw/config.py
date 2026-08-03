"""
Configuration module for LLM Middleware.
Contains all constants, environment variables, and logging setup.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

# ============================================================================
# BASE PATHS
# ============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load environment variables from .env file
_env_candidates = [
    os.path.join(BASE_DIR, ".env"),
    os.path.abspath(os.path.join(BASE_DIR, "..", ".env")),
]
for _env_path in _env_candidates:
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
        break
else:
    load_dotenv()

# ============================================================================
# DATA FILES (in data/ subdirectory)
# ============================================================================

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Backup directory for JSON/CSV files (DB is primary, files are backup)
BACKUP_DATA_DIR = os.path.join(DATA_DIR, "backup")
os.makedirs(BACKUP_DATA_DIR, exist_ok=True)

USERS_FILE = os.path.join(BACKUP_DATA_DIR, "users.json")
PRICES_FILE = os.path.join(BACKUP_DATA_DIR, "prices.json")
PENDING_CSV = os.path.join(BACKUP_DATA_DIR, "pending.csv")

# ============================================================================
# LOG FILES (in ../logs/ directory)
# ============================================================================

LOG_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "logs"))
os.makedirs(LOG_DIR, exist_ok=True)

# Backup directory for log files (DB is primary, files are backup)
BACKUP_LOG_DIR = os.path.join(LOG_DIR, "backup")
os.makedirs(BACKUP_LOG_DIR, exist_ok=True)

MW_LOG_FILE = os.path.join(LOG_DIR, "middleware.log")
MW_DETAIL_LOG_FILE = os.path.join(BACKUP_LOG_DIR, "middleware.requests.log")
AUDIT_LOG_FILE = os.path.join(BACKUP_LOG_DIR, "audit.jsonl")
LITELLM_LOG_FILE = os.path.abspath(os.path.join(BASE_DIR, "..", "litellm", "litellm.log"))

# Media storage (in logs/mw_media/)
MW_MEDIA_DIR = os.path.join(LOG_DIR, "mw_media")
os.makedirs(MW_MEDIA_DIR, exist_ok=True)

# ============================================================================
# ENVIRONMENT VARIABLES
# ============================================================================

LITELLM_BASE = os.getenv("LITELLM_BASE", "http://127.0.0.1:4000/v1").strip()
LITELLM_KEY = os.getenv("LITELLM_KEY", "").strip()
ADMIN_KEY = os.getenv("ADMIN_KEY", "").strip()
JWT_SECRET = os.getenv("JWT_SECRET", "default-jwt-secret-CHANGE-IN-PRODUCTION").strip()
MW_SECRET = os.getenv("MW_SECRET", "default-secret-CHANGE-IN-PRODUCTION").strip()
OPENWEBUI_SERVICE_KEY = os.getenv("OPENWEBUI_SERVICE_KEY", "").strip()
# Secret Open WebUI dùng ký cookie phiên `token` (JWT HS256). Middleware xác minh cookie
# này để biết user thật của trình duyệt trong luồng OAuth connect (chống CSRF token-binding).
WEBUI_SECRET_KEY = os.getenv("WEBUI_SECRET_KEY", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

DEFAULT_ALLOWED_MODELS_ENV = os.getenv("DEFAULT_ALLOWED_MODELS", "openai-auto,gemini-auto,grok-auto,claude-auto,deepseek-auto").strip()
if DEFAULT_ALLOWED_MODELS_ENV.startswith("["):
    try:
        import json as _json
        DEFAULT_ALLOWED_MODELS = _json.loads(DEFAULT_ALLOWED_MODELS_ENV)
    except Exception:
        DEFAULT_ALLOWED_MODELS = ["openai-auto", "gemini-auto", "grok-auto", "claude-auto", "deepseek-auto"]
else:
    DEFAULT_ALLOWED_MODELS = [m.strip() for m in DEFAULT_ALLOWED_MODELS_ENV.split(",") if m.strip()]



# ============================================================================
# LOGGING SETUP
# ============================================================================

# Main logger (middleware.log + stdout)
logger = logging.getLogger("llm_mw")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    
    # 1. File Handler
    _fh = RotatingFileHandler(MW_LOG_FILE, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(_fh)
    
    # 2. Console Handler (for Docker logs)
    import sys
    _ch = logging.StreamHandler(sys.stdout)
    _ch.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(_ch)

# Detail logger (middleware.requests.log - JSON format)
detail_logger = logging.getLogger("llm_mw_detail")
if not detail_logger.handlers:
    detail_logger.setLevel(logging.INFO)
    _dh = RotatingFileHandler(MW_DETAIL_LOG_FILE, maxBytes=20_000_000, backupCount=5, encoding="utf-8")
    _dh.setFormatter(logging.Formatter("%(message)s"))
    detail_logger.addHandler(_dh)

# Audit logger (audit.jsonl)
audit_logger = logging.getLogger("llm_mw_audit")
if not audit_logger.handlers:
    audit_logger.setLevel(logging.INFO)
    _ah = RotatingFileHandler(AUDIT_LOG_FILE, maxBytes=50_000_000, backupCount=5, encoding="utf-8")
    _ah.setFormatter(logging.Formatter("%(message)s"))
    audit_logger.addHandler(_ah)

# Security warnings for default values (AFTER logger initialization)
if JWT_SECRET == "default-jwt-secret-CHANGE-IN-PRODUCTION":
    logger.warning("⚠️  JWT_SECRET is using default value - CHANGE IN PRODUCTION!")
if MW_SECRET == "default-secret-CHANGE-IN-PRODUCTION":
    logger.warning("⚠️  MW_SECRET is using default value - CHANGE IN PRODUCTION!")
if not ADMIN_KEY:
    logger.warning("⚠️  ADMIN_KEY is empty - Admin endpoints will be inaccessible!")

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

try:
    from core.db import init_pool
    init_pool(DATABASE_URL, minconn=5, maxconn=30)
except Exception as _db_err:
    logger.error("Failed to initialize database pool: %s", str(_db_err))
    logger.warning("Middleware will run in FILE-ONLY mode (no PostgreSQL)")

# ============================================================================
# CONSTANTS
# ============================================================================

# Restricted models (special handling)
RESTRICTED_MODELS = {"gpt-image-1", "sora-2", "sora-2-pro"}

# Sensitive keys for redaction in logs
SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "access_token",
    "token",
    "secret",
    "password",
    "openai_api_key",
    "gemini_api_key",
    "litellm_key",
    "subkey",
    "subkey_hash",
}

# RAG Image Injection Configuration
from utils.helpers import env_truthy
MW_RAG_IMAGE_INJECT = env_truthy("MW_RAG_IMAGE_INJECT", default=True)
try:
    MW_RAG_IMAGE_MAX = int(os.getenv("MW_RAG_IMAGE_MAX", "3"))
except ValueError:
    MW_RAG_IMAGE_MAX = 3

