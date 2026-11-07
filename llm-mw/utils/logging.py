"""
Logging utilities for detailed and audit logging.
Offloads blocking file and PostgreSQL dual-writes to a bounded worker pool
when invoked from an active asyncio event loop.
"""

import asyncio
import atexit
import concurrent.futures
import datetime as dt
import json
import threading
from typing import Any, Callable, Dict, Optional
from zoneinfo import ZoneInfo
from fastapi import Request

from config import detail_logger, audit_logger
from utils.helpers import env_truthy, redact
from utils.client_ip import client_address


_LOG_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="mw-log-io",
)
_PENDING_FUTURES_LOCK = threading.Lock()
_PENDING_FUTURES: set[concurrent.futures.Future] = set()


def _cleanup_future(fut: concurrent.futures.Future) -> None:
    with _PENDING_FUTURES_LOCK:
        _PENDING_FUTURES.discard(fut)


def _dispatch_log_io(fn: Callable[..., None], *args: Any) -> None:
    """Run blocking log/DB write on _LOG_EXECUTOR if an asyncio loop is running, else inline."""
    try:
        asyncio.get_running_loop()
        loop_running = True
    except RuntimeError:
        loop_running = False

    if loop_running:
        try:
            fut = _LOG_EXECUTOR.submit(fn, *args)
            with _PENDING_FUTURES_LOCK:
                _PENDING_FUTURES.add(fut)
            fut.add_done_callback(_cleanup_future)
            return
        except RuntimeError:
            # Executor shutting down at process exit — fall through to inline write
            pass
    fn(*args)


def flush_log_executor(timeout: float = 5.0) -> None:
    """Wait for all currently queued background log/DB writes to complete."""
    with _PENDING_FUTURES_LOCK:
        snapshot = list(_PENDING_FUTURES)
    if snapshot:
        concurrent.futures.wait(snapshot, timeout=timeout)


atexit.register(_LOG_EXECUTOR.shutdown, wait=True)


def _write_detail_io(payload: Dict[str, Any]) -> None:
    try:
        detail_logger.info(json.dumps(payload, ensure_ascii=False))
        try:
            import core.db as _db
            if _db._pool is not None:
                _db.insert_request_log(payload)
        except Exception:
            pass
    except Exception:
        pass


def _write_audit_io(data: dict) -> None:
    try:
        audit_logger.info(json.dumps(data, ensure_ascii=False))
        try:
            import core.db as _db
            if _db._pool is not None:
                _db.insert_audit_log(data)
        except Exception:
            pass
    except Exception:
        pass


def detail_log(
    event: str, 
    *, 
    request: Optional[Request] = None, 
    rid: Optional[str] = None, 
    user_id: Optional[str] = None, 
    **fields: Any
):
    """
    Log detailed event information to detail logger.
    
    Args:
        event: Event name/type
        request: Optional FastAPI request object
        rid: Optional request ID
        user_id: Optional user ID
        **fields: Additional fields to log (will be redacted)
    """
    if not env_truthy("MW_DETAILED_LOG", default=True):
        return
    
    try:
        payload: Dict[str, Any] = {
            "ts": dt.datetime.now(tz=ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
            "event": event,
        }
        
        if request is not None:
            payload.update(
                {
                    "method": request.method,
                    "path": request.url.path,
                    "client": client_address(request),
                }
            )
        
        rid_val = rid or (getattr(request.state, "mw_request_id", None) if request is not None else None)
        if rid_val:
            payload["rid"] = rid_val
        
        uid_val = user_id or (getattr(request.state, "mw_user_id", None) if request is not None else None)
        if uid_val:
            payload["user"] = uid_val

        for k, v in fields.items():
            payload[k] = redact(v)

        _dispatch_log_io(_write_detail_io, payload)
    except Exception:
        # Never break API behavior due to logging failures.
        return


def audit_log(
    user_id: str,
    request_id: str,
    endpoint: str,
    model: Optional[str] = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
    image_requests: int = 0,
    stt_requests: int = 0,
    tts_chars: int = 0,
    duration_ms: int = 0,
    status: str = "success",
):
    """
    Write structured audit log entry to audit.jsonl.
    One line per request for aggregation and analysis.
    """
    try:
        entry = {
            "timestamp": dt.datetime.now(tz=ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
            "request_id": request_id,
            "user_id": user_id,
            "endpoint": endpoint,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": round(cost_usd, 6),
            "image_requests": image_requests,
            "stt_requests": stt_requests,
            "tts_chars": tts_chars,
            "duration_ms": duration_ms,
            "status": status,
        }
        _dispatch_log_io(lambda e: audit_logger.info(json.dumps(e, ensure_ascii=False)), entry)
    except Exception:
        return


def write_audit_line(data: dict):
    """
    Write a raw audit line to audit.jsonl and dual-write to PostgreSQL off the event loop.
    """
    try:
        snapshot = dict(data)
        _dispatch_log_io(_write_audit_io, snapshot)
    except Exception:
        # Never break application due to logging failure
        pass


def audit_from_request(
    request: Request,
    rid: str,
    status_code: int,
    duration_ms: float
):
    """
    Extract audit data from request.state and write audit line.
    """
    try:
        # Build audit line from request state synchronously before request lifecycle ends
        data = {
            "ts": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
            "rid": rid,
            "user_id": getattr(request.state, "mw_user_id", "unknown"),
            "endpoint": getattr(request.state, "mw_endpoint", request.url.path),
            "model": getattr(request.state, "mw_model", None),
            "purpose": getattr(request.state, "mw_purpose", None),
            "status": getattr(request.state, "mw_status", "ok"),
            "status_code": status_code,
            "latency_ms": round(duration_ms, 1) if duration_ms is not None else None,
            "tokens_in": getattr(request.state, "mw_tokens_in", 0),
            "tokens_out": getattr(request.state, "mw_tokens_out", 0),
            "tokens_total": getattr(request.state, "mw_tokens_total", 0),
            "cost_usd": round(getattr(request.state, "mw_cost_usd", 0.0), 6),
            "image_count": getattr(request.state, "mw_image_count", None),
            "tts_chars": getattr(request.state, "mw_tts_chars", None),
            "stt_seconds": getattr(request.state, "mw_stt_seconds", None),
            "video_count": getattr(request.state, "mw_video_count", None),
            "error_type": getattr(request.state, "mw_error_type", None),
            "error_message": getattr(request.state, "mw_error_message", None),
            "auth_source": getattr(request.state, "mw_auth_source", None),
            "openwebui_user_id": getattr(request.state, "mw_openwebui_user_id", None),
        }
        
        write_audit_line(data)
    except Exception:
        # Never break application due to logging failure
        pass
