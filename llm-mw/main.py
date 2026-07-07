"""
LLM Middleware - Modular FastAPI Application
Provides authentication, quota management, and proxying for LLM requests.
"""

import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx

from config import logger
from utils.logging import detail_log, audit_log, audit_from_request
from core.audit_state import set_error_state, should_skip_audit, has_audit_state

# Import route handlers
from api.health import health_check
from api.models import list_models
from api.chat import chat_completions
from api.images import generate_images
from api.audio import transcribe_audio
from api.embeddings import create_embeddings
from api.rerank import rerank
from api.media import serve_media
from api.docling import docling_proxy
from api.admin import get_usage, reset_quota, reconcile_usage, stream_live_metrics, list_pending, force_remove_pending
from api.analytics import get_chat_analytics, get_satisfaction_analytics
from api.summary import get_summary
from api.summary_v2 import get_summary_v2
from api.stream import stream_audit
from api.access_logs import get_access_summary, stream_access
from api.audit_query import parse_audit_filters
from api.rag_health import get_rag_ingestion, get_rag_retrieval, get_rag_storage
from api.group_analytics import get_group_analytics, get_group_users
from api.user_admin import (
    list_users, create_user, update_user, 
    rotate_user_key, disable_user, enable_user, get_admin_audit,
    delete_user_endpoint, reconciliation_report, map_openwebui_user, get_users_sync_status, sync_user_now
)
from api.price_admin import list_prices, update_price, delete_price
from api.export_report import export_report
from api.dashboard_login import dashboard_login, dashboard_logout
from api.auth_check import get_auth_check
from api.auth_test import auth_test
from api.quota_status import get_quota_status, get_alert_config, update_alert_config, test_alert_email
from api.notifications import list_notifications, unread_count, mark_notification_read, mark_all_read
from api.oauth import router as oauth_router
from api.integrations import router as integrations_router
from api.approvals import router as approvals_router
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    # Startup
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=100)
    timeout = httpx.Timeout(300.0, connect=10.0)
    app.state.http_client = httpx.AsyncClient(limits=limits, timeout=timeout)
    app.state.start_time = time.time()
    logger.info("startup: http_client created")

    # Start daily digest scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from core.notification import send_daily_digest

        scheduler = AsyncIOScheduler(timezone="Asia/Ho_Chi_Minh")
        scheduler.add_job(send_daily_digest, 'cron', hour=8, minute=0, id='daily_digest')
        scheduler.start()
        app.state.scheduler = scheduler
        logger.info("startup: daily_digest scheduler started (8:00 AM VN)")
    except ImportError:
        logger.warning("startup: apscheduler not installed — daily digest DISABLED")
        app.state.scheduler = None
    except Exception as e:
        logger.error("startup: scheduler failed: %s", str(e))
        app.state.scheduler = None
    
    yield
    
    # Shutdown
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        logger.info("shutdown: scheduler stopped")
    client = getattr(app.state, "http_client", None)
    if client is not None:
        try:
            await client.aclose()
        except Exception:
            pass
    logger.info("shutdown: http_client closed")


# Create FastAPI app with lifespan
app = FastAPI(
    title="LLM Middleware (Quota+Auth+Stream+Reconcile)", 
    version="4.0-modular",
    lifespan=lifespan
)

# CORS middleware - Allow calls from production domain + internal Docker network
import os as _os
_MW_PUBLIC_URL = _os.getenv("MW_PUBLIC_URL", "https://openwebui.example.com:51122")
# Build allowed origins list:
# 1. Public URL (browser requests from Open WebUI Settings page)
# 2. HTTP variant (in case of internal proxy without SSL)
# 3. Server-to-server requests (no Origin header) bypass CORS automatically
_cors_origins = [_MW_PUBLIC_URL]
# Add http variant if public URL is https
if _MW_PUBLIC_URL.startswith("https://"):
    _cors_origins.append(_MW_PUBLIC_URL.replace("https://", "http://"))
# Add any extra origins from environment (comma-separated)
_extra_origins = _os.getenv("MW_CORS_ORIGINS", "")
if _extra_origins:
    _cors_origins.extend([o.strip() for o in _extra_origins.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with timing and audit trail"""
    t0 = time.perf_counter()
    status_code: int = 500
    detail_log("inbound", request=request)
    
    try:
        response = await call_next(request)
        status_code = getattr(response, "status_code", 200)
        return response
    except Exception as e:
        # Set error state if audit state was initialized
        if has_audit_state(request):
            set_error_state(request, "system", str(e))
        raise
    finally:
        dt_ms = (time.perf_counter() - t0) * 1000.0
        rid = getattr(request.state, "mw_request_id", None) or request.headers.get("X-Request-ID") or "-"
        
        logger.info(
            "req rid=%s method=%s path=%s status=%s ms=%.1f",
            rid,
            request.method,
            request.url.path,
            status_code,
            dt_ms,
        )
        detail_log("outbound", request=request, status=status_code, ms=round(dt_ms, 1))
        
        # New audit logic: write structured audit from request.state
        if has_audit_state(request) and not should_skip_audit(request):
            audit_from_request(request, rid, status_code, dt_ms)


# Register routes
# Health & Models
app.add_api_route("/health", health_check, methods=["GET"])
app.add_api_route("/v1/models", list_models, methods=["GET"])

# Chat, Images, Audio
app.add_api_route("/v1/chat/completions", chat_completions, methods=["POST"])
app.add_api_route("/v1/embeddings", create_embeddings, methods=["POST"])
app.add_api_route("/v1/rerank", rerank, methods=["POST"])
app.add_api_route("/v1/images/generations", generate_images, methods=["POST"])
app.add_api_route("/v1/audio/transcriptions", transcribe_audio, methods=["POST"])

# Media serving
app.add_api_route("/v1/_mw/media/{name}", serve_media, methods=["GET"])

# Docling Proxy (catch-all)
app.add_api_route("/docling-proxy/{path:path}", docling_proxy, methods=["GET", "POST", "PUT", "DELETE"])
app.add_api_route("/docling-proxy", docling_proxy, methods=["GET", "POST", "PUT", "DELETE"])

# Admin endpoints
app.add_api_route("/v1/_mw/admin/prices", list_prices, methods=["GET"])
app.add_api_route("/v1/_mw/admin/prices", update_price, methods=["POST"])
app.add_api_route("/v1/_mw/admin/prices/{model_name}", delete_price, methods=["DELETE"])
app.add_api_route("/v1/_mw/admin/active-users/stream", stream_live_metrics, methods=["GET"])
app.add_api_route("/admin/usage", get_usage, methods=["GET"])
app.add_api_route("/admin/reset", reset_quota, methods=["POST"])
app.add_api_route("/admin/reconcile", reconcile_usage, methods=["POST"])
app.add_api_route("/v1/_mw/admin/analytics/chat", get_chat_analytics, methods=["GET"])
app.add_api_route("/v1/_mw/admin/analytics/satisfaction", get_satisfaction_analytics, methods=["GET"])

# Summary & Stream endpoints
app.add_api_route("/v1/_mw/summary", get_summary_v2, methods=["GET"])  # Enhanced version with time range
app.add_api_route("/v1/_mw/stream", stream_audit, methods=["GET"])

# Access log endpoints (separate from usage)
app.add_api_route("/v1/_mw/access_summary", get_access_summary, methods=["GET"])
app.add_api_route("/v1/_mw/access_stream", stream_access, methods=["GET"])

# Group Analytics endpoint
app.add_api_route("/v1/_mw/admin/analytics/groups", get_group_analytics, methods=["GET"])
app.add_api_route("/v1/_mw/admin/analytics/groups/{group_id}/users", get_group_users, methods=["GET"])

# Audit log query endpoint (Logs tab)
app.add_api_route("/v1/_mw/audit/query", parse_audit_filters, methods=["GET"])

# Export report endpoint (Excel multi-sheet / CSV streaming)
app.add_api_route("/v1/_mw/export/report", export_report, methods=["GET"])

# RAG Health endpoints (RAG Health tab)
app.add_api_route("/v1/_mw/rag-health/ingestion", get_rag_ingestion, methods=["GET"])
app.add_api_route("/v1/_mw/rag-health/retrieval", get_rag_retrieval, methods=["GET"])
app.add_api_route("/v1/_mw/rag-health/storage", get_rag_storage, methods=["GET"])

# User management endpoints (admin only)
app.add_api_route("/v1/_mw/admin/pending", list_pending, methods=["GET"])
app.add_api_route("/v1/_mw/admin/pending/{request_id}", force_remove_pending, methods=["DELETE"])
app.add_api_route("/v1/_mw/admin/users/sync-status", get_users_sync_status, methods=["GET"])
app.add_api_route("/v1/_mw/admin/users/sync-now", sync_user_now, methods=["POST"])
app.add_api_route("/v1/_mw/admin/users", list_users, methods=["GET"])
app.add_api_route("/v1/_mw/admin/users", create_user, methods=["POST"])
app.add_api_route("/v1/_mw/admin/users/{user_id}", update_user, methods=["PATCH"])
app.add_api_route("/v1/_mw/admin/users/{user_id}", delete_user_endpoint, methods=["DELETE"])
app.add_api_route("/v1/_mw/admin/users/{user_id}/rotate_key", rotate_user_key, methods=["POST"])
app.add_api_route("/v1/_mw/admin/users/{user_id}/disable", disable_user, methods=["POST"])
app.add_api_route("/v1/_mw/admin/users/{user_id}/enable", enable_user, methods=["POST"])
app.add_api_route("/v1/_mw/admin/audit", get_admin_audit, methods=["GET"])
app.add_api_route("/v1/_mw/admin/users/reconciliation", reconciliation_report, methods=["GET"])
app.add_api_route("/v1/_mw/admin/users/{user_id}/openwebui-mapping", map_openwebui_user, methods=["PUT"])

# Quota status & Alert endpoints
app.add_api_route("/v1/_mw/quota-status", get_quota_status, methods=["GET"])
app.add_api_route("/v1/_mw/admin/alerts/config", get_alert_config, methods=["GET"])
app.add_api_route("/v1/_mw/admin/alerts/config", update_alert_config, methods=["PUT", "POST"])
app.add_api_route("/v1/_mw/admin/alerts/test-email", test_alert_email, methods=["POST"])

# Notification endpoints
app.add_api_route("/v1/_mw/admin/notifications", list_notifications, methods=["GET"])
app.add_api_route("/v1/_mw/admin/notifications/unread", unread_count, methods=["GET"])
app.add_api_route("/v1/_mw/admin/notifications/{notif_id}/read", mark_notification_read, methods=["POST"])
app.add_api_route("/v1/_mw/admin/notifications/read-all", mark_all_read, methods=["POST"])

# Dashboard auth endpoints
app.add_api_route("/v1/_mw/dashboard/login", dashboard_login, methods=["POST"])
app.add_api_route("/v1/_mw/dashboard/logout", dashboard_logout, methods=["POST"])
app.add_api_route("/v1/_mw/auth_check", get_auth_check, methods=["GET"])

# Auth diagnostic endpoint (any user with valid Bearer token)
app.add_api_route("/v1/_mw/auth-test", auth_test, methods=["GET"])

# Include OAuth, integrations and approvals routers (added for Phase 2)
app.include_router(oauth_router, prefix="/v1")
app.include_router(integrations_router, prefix="/v1")
app.include_router(approvals_router, prefix="/v1")

# Mount static files for dashboard (css, js, vendor)
import os
dashboard_dir = os.path.join(os.path.dirname(__file__), "dashboard")
app.mount("/dashboard/css", StaticFiles(directory=os.path.join(dashboard_dir, "css")), name="dashboard-css")
app.mount("/dashboard/js", StaticFiles(directory=os.path.join(dashboard_dir, "js")), name="dashboard-js")
app.mount("/dashboard/vendor", StaticFiles(directory=os.path.join(dashboard_dir, "vendor")), name="dashboard-vendor")

# Serve dashboard HTML (must be after static mounts)
@app.get("/dashboard")
@app.get("/dashboard/")
async def serve_dashboard():
    """Serve dashboard HTML"""
    dashboard_path = os.path.join(dashboard_dir, "index.html")
    return FileResponse(dashboard_path)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=False)
