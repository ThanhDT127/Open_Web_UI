"""
Audit state management for request tracking.

This module provides a contract-based approach to tracking request state
for audit logging. All endpoints should use these functions to set audit state,
and the middleware will automatically collect and log at request completion.
"""

import uuid
from typing import Optional
from fastapi import Request


# LLM Endpoint Allowlist - Only these endpoints will have usage audit
# This prevents background polling requests (chats, tasks, etc.) from being counted as LLM usage
LLM_ENDPOINT_ALLOWLIST = {
    "/v1/chat/completions",
    "/v1/embeddings",
    "/v1/images/generations",
    "/v1/audio/transcriptions",
    "/v1/audio/speech",
    "/v1/video/generations",
}


def init_audit_state(
    request: Request,
    user_id: str,
    endpoint: str,
    model: Optional[str] = None,
    rid: Optional[str] = None,
    purpose: Optional[str] = None
) -> str:
    """
    Initialize audit state on request object.
    
    This should be called early in endpoint handlers after user authentication.
    Sets default values for all audit fields.
    
    **IMPORTANT**: Only LLM endpoints in LLM_ENDPOINT_ALLOWLIST will have audit state initialized.
    This prevents background polling requests from inflating usage metrics.
    
    Args:
        request: FastAPI Request object
        user_id: Authenticated user ID
        endpoint: API endpoint path (e.g., "/v1/chat/completions")
        model: Model name if known (can be None)
        rid: Request ID (will generate if None)
        purpose: Request purpose/context (e.g., "user_chat", "background_task", "system_prompt")
    
    Returns:
        str: The request ID (rid) assigned, or empty string if endpoint not in allowlist
    
    Example:
        ```python
        async def chat_completions(request: Request):
            user = require_user(request)
            body = await request.json()
            model = body.get("model")
            
            # Extract purpose from header or query param
            purpose = request.headers.get("x-purpose") or request.query_params.get("purpose")
            
            # Initialize audit state (will only work for LLM endpoints)
            rid = init_audit_state(request, user["user_id"], "/v1/chat/completions", model, purpose=purpose)
            
            # ... rest of endpoint logic ...
        ```
    """
    # Check if endpoint is in LLM allowlist
    if endpoint not in LLM_ENDPOINT_ALLOWLIST:
        # Do not initialize audit state for non-LLM endpoints
        # This prevents background polling (chats, tasks, etc.) from being counted as LLM usage
        return ""
    # Generate or use provided request ID
    if rid is None:
        rid = f"mw_{uuid.uuid4().hex[:16]}"
    
    # Extract purpose from request if not provided
    if purpose is None:
        # Try to get from header first, then query param
        purpose = request.headers.get("x-purpose") or request.query_params.get("purpose")
    
    # Set all audit state fields with defaults
    request.state.mw_request_id = rid
    request.state.mw_user_id = user_id
    request.state.mw_endpoint = endpoint
    request.state.mw_model = model
    request.state.mw_purpose = purpose  # NEW: Track request purpose/context
    request.state.mw_auth_source = getattr(request.state, "mw_auth_source", "direct_subkey")
    request.state.mw_openwebui_user_id = getattr(request.state, "mw_openwebui_user_id", None)
    
    # Default status is "ok" (will be changed if error occurs)
    request.state.mw_status = "ok"
    
    # Usage counters (default to 0)
    request.state.mw_tokens_in = 0
    request.state.mw_tokens_out = 0
    request.state.mw_tokens_total = 0
    request.state.mw_cost_usd = 0.0
    
    # Latency (set by middleware)
    request.state.mw_latency_ms = None
    
    # Error tracking (None if no error)
    request.state.mw_error_type = None
    request.state.mw_error_message = None
    
    # Special counters for different request types
    request.state.mw_image_count = None
    request.state.mw_tts_chars = None
    request.state.mw_stt_seconds = None
    request.state.mw_video_count = None
    
    # Flag to prevent double-logging (used for streaming)
    request.state.mw_audit_already_logged = False
    
    return rid


def set_usage_state(
    request: Request,
    tokens_in: int,
    tokens_out: int,
    tokens_total: int,
    cost_usd: float
):
    """
    Set usage counters for token-based requests.
    
    Call this after receiving response from LLM provider and calculating cost.
    
    Args:
        request: FastAPI Request object
        tokens_in: Input/prompt tokens
        tokens_out: Output/completion tokens
        tokens_total: Total tokens (usually in + out)
        cost_usd: Calculated cost in USD
    
    Example:
        ```python
        # After getting response from LiteLLM
        usage = response.json().get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        tokens_total = usage.get("total_tokens", tokens_in + tokens_out)
        
        cost = calc_cost_usd(model, tokens_in, tokens_out)
        set_usage_state(request, tokens_in, tokens_out, tokens_total, cost)
        ```
    """
    request.state.mw_tokens_in = tokens_in
    request.state.mw_tokens_out = tokens_out
    request.state.mw_tokens_total = tokens_total
    request.state.mw_cost_usd = cost_usd


def set_error_state(
    request: Request,
    error_type: str,
    message: str
):
    """
    Mark request as failed and record error details.
    
    Call this in exception handlers to record error information.
    
    Args:
        request: FastAPI Request object
        error_type: Error category (e.g., "auth", "quota", "provider", "system")
        message: Error message (will be truncated if too long)
    
    Example:
        ```python
        try:
            response = await client.post(...)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            set_error_state(request, "provider", f"LiteLLM error: {e.response.status_code}")
            raise HTTPException(502, "Provider error")
        ```
    """
    request.state.mw_status = "error"
    request.state.mw_error_type = error_type
    
    # Truncate message to avoid huge audit lines
    if len(message) > 500:
        message = message[:497] + "..."
    request.state.mw_error_message = message


def set_counters(
    request: Request,
    image_count: Optional[int] = None,
    tts_chars: Optional[int] = None,
    stt_seconds: Optional[float] = None,
    video_count: Optional[int] = None
):
    """
    Set special counters for non-token requests (images, audio, video).
    
    Use this for requests that don't use tokens but have other measurable units.
    
    Args:
        request: FastAPI Request object
        image_count: Number of images generated
        tts_chars: Text-to-speech character count
        stt_seconds: Speech-to-text audio duration in seconds
        video_count: Number of videos generated
    
    Example:
        ```python
        # For image generation
        image_count = body.get("n", 1)
        cost = calc_image_cost_from_body(model, body)
        set_usage_state(request, 0, 0, 0, cost)
        set_counters(request, image_count=image_count)
        
        # For STT
        audio_duration = get_audio_duration(audio_file)
        cost = calc_stt_cost(model, audio_duration)
        set_usage_state(request, 0, 0, 0, cost)
        set_counters(request, stt_seconds=audio_duration)
        ```
    """
    if image_count is not None:
        request.state.mw_image_count = image_count
    if tts_chars is not None:
        request.state.mw_tts_chars = tts_chars
    if stt_seconds is not None:
        request.state.mw_stt_seconds = stt_seconds
    if video_count is not None:
        request.state.mw_video_count = video_count


def mark_audit_logged(request: Request):
    """
    Mark that audit has already been logged for this request.
    
    Used for streaming requests where endpoint writes audit line directly
    (with status="pending") and middleware should skip logging.
    
    Args:
        request: FastAPI Request object
    
    Example:
        ```python
        # In streaming endpoint, before returning StreamingResponse
        write_audit_line({
            # ... audit data with status="pending" ...
        })
        mark_audit_logged(request)
        
        return StreamingResponse(stream_generator(), ...)
        ```
    """
    request.state.mw_audit_already_logged = True


def should_skip_audit(request: Request) -> bool:
    """
    Check if middleware should skip writing audit for this request.
    
    Returns True if endpoint already wrote audit line (e.g., for streaming).
    
    Args:
        request: FastAPI Request object
    
    Returns:
        bool: True if audit already logged, False otherwise
    """
    return getattr(request.state, "mw_audit_already_logged", False)


def has_audit_state(request: Request) -> bool:
    """
    Check if request has audit state initialized.
    
    Used by middleware to determine if request should be audited.
    Only returns True if init_audit_state() was properly called.
    
    Args:
        request: FastAPI Request object
    
    Returns:
        bool: True if init_audit_state was called (has mw_request_id), False otherwise
    """
    return hasattr(request.state, "mw_request_id")
