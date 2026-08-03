"""
Health check endpoint for middleware monitoring.
"""

import time
import shutil
from urllib.parse import urlsplit, urlunsplit

from fastapi import Request
from fastapi.responses import JSONResponse
import httpx

from config import LITELLM_BASE, LITELLM_KEY, LOG_DIR, logger
from core.auth import load_users


def _litellm_health_url() -> str:
    """Return LiteLLM proxy health URL even when LITELLM_BASE includes /v1."""
    parts = urlsplit(LITELLM_BASE)
    base = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    return f"{base}/health/liveliness"


async def _collect_health(request: Request) -> dict:
    """Gather the health report. Shared by the container probe and the dashboard route,
    so the two can never drift into reporting different things."""
    status = {"ok": True, "time": int(time.time())}
    
    # Uptime
    start_time = getattr(request.app.state, "start_time", None)
    if start_time:
        status["uptime_seconds"] = int(time.time() - start_time)
    
    # LiteLLM connectivity check
    try:
        client: httpx.AsyncClient = request.app.state.http_client
        resp = await client.get(
            _litellm_health_url(),
            headers={"Authorization": f"Bearer {LITELLM_KEY}"},
            timeout=15.0
        )
        if resp.status_code == 200:
            status["litellm"] = "ok"
        else:
            status["litellm"] = f"degraded: {resp.status_code}"
            status["ok"] = False
            logger.warning("health_check_failed component=litellm status=%d", resp.status_code)
    except Exception as e:
        err_msg = str(e)[:100] or repr(e)
        status["litellm"] = f"error: {err_msg}"
        status["ok"] = False
        logger.error("health_check_failed component=litellm error=%s", err_msg)
    
    # Disk space check (logs directory)
    try:
        disk = shutil.disk_usage(LOG_DIR)
        free_gb = disk.free / (1024 ** 3)
        status["disk_free_gb"] = round(free_gb, 2)
        if free_gb < 1.0:
            status["ok"] = False
            status["warning"] = "Low disk space"
    except Exception:
        pass
    
    # Active users count
    try:
        users = load_users()
        status["active_users"] = sum(1 for u in users if u.get("active", True))
    except Exception:
        pass
    
    return status


async def health_check(request: Request):
    """
    Health check endpoint with comprehensive system status.
    Returns 200 if healthy, 503 if degraded.

    This is the container liveness probe (``/health``); Docker HEALTHCHECK reads the
    status code, so the 503 must stay.
    """
    status = await _collect_health(request)
    return JSONResponse(
        status_code=200 if status["ok"] else 503,
        content=status
    )


async def health_report(request: Request):
    """Same report, for the dashboard (``/v1/_mw/health``).

    Two deliberate differences from ``health_check``:

    * **Admin-guarded.** ``/health`` is unauthenticated because the container probes it,
      but this path is reachable through the public proxy and the report carries
      ``disk_free_gb`` and ``active_users``.
    * **Always HTTP 200.** A degraded dependency is the report's *content*, not a failure
      to produce it. Returning 503 here would make ``res.ok`` false in the browser, and
      the health card would blank itself at exactly the moment it has something to say.
      Callers read ``ok`` in the body.
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)
    return JSONResponse(status_code=200, content=await _collect_health(request))
