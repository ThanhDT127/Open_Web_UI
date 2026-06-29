"""
Logging utilities for detailed and audit logging.
"""

import json
import datetime as dt
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo
from fastapi import Request

from config import detail_logger, audit_logger
from utils.helpers import env_truthy, redact


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
                    "client": getattr(request.client, "host", None),
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

        detail_logger.info(json.dumps(payload, ensure_ascii=False))

        # Dual-write to DB (best-effort, non-blocking)
        try:
            from core.db import insert_request_log, _pool
            if _pool is not None:
                insert_request_log(payload)
        except Exception:
            pass
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
    
    Args:
        user_id: User identifier
        request_id: Unique request ID
        endpoint: API endpoint path
        model: Model name (if applicable)
        tokens_in: Input tokens
        tokens_out: Output tokens
        cost_usd: Cost in USD
        image_requests: Number of image requests
        stt_requests: Speech-to-text requests
        tts_chars: Text-to-speech characters
        duration_ms: Request duration in milliseconds
        status: Request status (success/error)
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
        audit_logger.info(json.dumps(entry, ensure_ascii=False))
    except Exception:
        return


def write_audit_line(data: dict):
    """
    Write a raw audit line to audit.jsonl.
    
    This is the low-level function used by both middleware and endpoints
    to write structured audit data. Accepts a dict that will be serialized to JSON.
    
    Args:
        data: Dictionary containing audit fields (ts, rid, user_id, etc.)
    
    Example:
        ```python
        write_audit_line({
            "ts": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
            "rid": "mw_abc123",
            "user_id": "admin",
            "endpoint": "/v1/chat/completions",
            "model": "gpt-4o-mini",
            "status": "pending",
            "status_code": 200,
            "latency_ms": None,
            "tokens_in": 0,
            "tokens_out": 0,
            "tokens_total": 0,
            "cost_usd": 0.0,
            "image_count": None,
            "tts_chars": None,
            "stt_seconds": None,
            "video_count": None,
            "error_type": None,
            "error_message": None
        })
        ```
    """
    try:
        audit_logger.info(json.dumps(data, ensure_ascii=False))

        # Dual-write to DB (best-effort)
        try:
            from core.db import insert_audit_log, _pool
            if _pool is not None:
                insert_audit_log(data)
        except Exception:
            pass
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
    
    This function is called by the middleware at request completion
    to collect all audit state set by endpoints and write a single audit line.
    
    Args:
        request: FastAPI Request object with audit state
        rid: Request ID
        status_code: HTTP status code
        duration_ms: Request duration in milliseconds
    
    The function reads these request.state fields:
        - mw_user_id (required)
        - mw_endpoint
        - mw_model
        - mw_status ("ok" or "error")
        - mw_tokens_in, mw_tokens_out, mw_tokens_total
        - mw_cost_usd
        - mw_error_type, mw_error_message
        - mw_image_count, mw_tts_chars, mw_stt_seconds, mw_video_count
    """
    try:
        # Build audit line from request state
        data = {
            "ts": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
            "rid": rid,
            "user_id": getattr(request.state, "mw_user_id", "unknown"),
            "endpoint": getattr(request.state, "mw_endpoint", request.url.path),
            "model": getattr(request.state, "mw_model", None),
            "purpose": getattr(request.state, "mw_purpose", None),  # NEW: Log request purpose
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
