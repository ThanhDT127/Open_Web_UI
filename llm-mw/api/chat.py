"""
Chat completions endpoint with streaming support.
"""

import uuid
import json
import asyncio
from datetime import datetime, timezone
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import httpx

from config import LITELLM_BASE, LITELLM_KEY, logger, MW_RAG_IMAGE_INJECT, MW_RAG_IMAGE_MAX
from core.auth import require_user, assert_model_allowed
from core.quota import maybe_reset_quota, enforce_and_bump_quota, get_quota_reset_info
from core.cost import calc_cost_usd, append_pending, remove_pending, load_prices, calc_image_cost_from_body
from core.audit_state import init_audit_state, set_usage_state, set_error_state, set_counters
from services.litellm import get_cost_from_headers, find_usage_in_log
from utils.helpers import truncate_text, extract_text_from_messages, safe_headers
from utils.logging import detail_log, write_audit_line


async def _safe_alert_check(user_id: str, cost_usd: float):
    """Wrapper that silently catches all alert errors."""
    try:
        from core.alerting import check_and_send_alerts
        await check_and_send_alerts(user_id, add_cost_usd=cost_usd)
    except Exception as e:
        logger.error("alert_check_error user=%s: %s", user_id, str(e))


def _get_quota_warning_text(user_id: str) -> str | None:
    """
    Check user's quota usage and return warning text if above threshold.
    Returns None if no warning needed (unlimited or below 80%).
    """
    try:
        from core.alerting import get_user_quota_status
        status = get_user_quota_status(user_id)
        if not status.get("found") or status.get("unlimited"):
            return None
        percent = status.get("percent_used", 0)
        remaining = status.get("remaining_usd", 0)
        used = status.get("used_cost_usd", 0)
        limit = status.get("limit_cost_usd", 0)
        if percent >= 100:
            return (
                f"\n\n---\n"
                f"🚫 **Quota đã hết**: Bạn đã sử dụng hết quota tháng này "
                f"(${used:.2f}/${limit:.2f}). "
                f"Các request tiếp theo sẽ bị chặn. "
                f"Vui lòng liên hệ admin để được nâng hạn mức."
            )
        elif percent >= 95:
            return (
                f"\n\n---\n"
                f"🔴 **Cảnh báo quota**: Bạn đã sử dụng "
                f"**{percent:.0f}%** quota tháng này "
                f"(còn ~${remaining:.2f}). "
                f"Vui lòng liên hệ admin nếu cần tăng quota."
            )
        elif percent >= 80:
            return (
                f"\n\n---\n"
                f"⚠️ Bạn đã sử dụng "
                f"**{percent:.0f}%** quota tháng này "
                f"(còn ~${remaining:.2f})."
            )
        return None
    except Exception as e:
        logger.debug("quota_warning_check_error user=%s: %s", user_id, e)
        return None


def _get_routing_warning_text(request: Request) -> str | None:
    """
    Return warning text if smart routing downgraded the model tier.
    """
    try:
        downgraded = getattr(request.state, "routing_downgraded", False)
        if not downgraded:
            return None
        quota_pct = getattr(request.state, "routing_quota_percent", 0)
        return (
            f"\n\n---\n"
            f"*✨ Hệ thống đang dùng model phù hợp để giữ trải nghiệm ổn định cho bạn "
            f"(quota hiện tại: {quota_pct:.0f}%).*"
        )
    except Exception:
        return None


def _is_image_generation_model(model: str) -> bool:
    """Check if model is an image generation model."""
    if not isinstance(model, str):
        return False
    model_lower = model.lower()
    # Check for renamed models that bypass OpenWebUI filter
    return any(pattern in model_lower for pattern in [
        "image", "dall-e", "dalle", "stable-diffusion", "midjourney", "imagen",
        "-draw", "draw-",  # detect renamed models like gpt-draw-1
        "img-"  # detect models like img-gemini-flash, img-gpt-dalle-3
    ])


def _normalize_provider_params(model: str, body: dict) -> None:
    """
    Normalize request parameters based on provider/model type.
    Modifies body in-place to ensure compatibility across providers.

    Handles:
    - GPT-5+: max_tokens → max_completion_tokens
    - xAI Grok: remove unsupported 'size' param
    - Anthropic Claude: clamp temperature to [0, 1]
    - General: ensure stream_options.include_usage for streaming
    """
    if not isinstance(model, str) or not isinstance(body, dict):
        return

    model_lower = model.lower()

    # GPT-5+ models: max_tokens → max_completion_tokens
    if model_lower.startswith(("gpt-5", "chat-gpt-5")):
        if "max_tokens" in body and "max_completion_tokens" not in body:
            body["max_completion_tokens"] = body.pop("max_tokens")
            logger.debug("normalize: %s max_tokens → max_completion_tokens", model)

    # xAI Grok: remove 'size' (uses aspect_ratio instead)
    if any(k in model_lower for k in ["grok", "xai"]):
        body.pop("size", None)

    # Anthropic Claude: clamp temperature to [0, 1]
    if "claude" in model_lower:
        temp = body.get("temperature")
        if isinstance(temp, (int, float)) and temp > 1.0:
            body["temperature"] = min(temp, 1.0)
            logger.debug("normalize: %s temperature clamped to 1.0", model)

    # Ensure stream_options.include_usage for streaming requests
    if body.get("stream"):
        stream_opts = body.get("stream_options") or {}
        stream_opts["include_usage"] = True
        body["stream_options"] = stream_opts

    # Provider-native web search: DISABLED
    # Using SearXNG (Open WebUI built-in) for web search instead.
    # To re-enable provider-native search in the future, inject web_search_options
    # selectively per provider (Gemini only, and only when no custom tools present).


# --- Task prompt detection (Fix #3) ---
_TASK_PATTERNS = [
    "### Task:\nGenerate a concise",       # title generation
    "### Task:\nGenerate 1-3 broad tags",  # tag generation
    "### Task:\nGenerate follow-up",       # follow-up suggestions
    "### Task:\nGenerate a query",         # search query generation
]


def _is_system_task_prompt(messages: list) -> str | None:
    """
    Detect Open WebUI internal task prompts (title/tags/follow-up generation).
    These should NOT be sent to image models.
    
    Returns:
        Task type string ('title', 'tags', 'follow_up', 'query') if detected, else None.
    """
    prompt = _extract_prompt_from_messages(messages)
    if not prompt:
        return None
    for pattern in _TASK_PATTERNS:
        if pattern in prompt:
            if "title" in pattern.lower():
                return "title"
            elif "tags" in pattern.lower():
                return "tags"
            elif "follow-up" in pattern.lower():
                return "follow_up"
            else:
                return "query"
    return None


def _extract_prompt_from_messages(messages: list) -> str:
    """Extract text prompt from last user message (for logging/display)."""
    if not isinstance(messages, list):
        return ""
    
    # Get last user message
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                # Extract text from content array
                texts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        texts.append(item.get("text", ""))
                return " ".join(texts)
    return ""


def _prepare_image_messages(messages: list) -> list:
    """
    Prepare full conversation messages for Gemini image generation.
    Keeps conversation context so Gemini can understand references
    like "ảnh đấy" or "vẽ lại ảnh này" in follow-up messages.
    
    Cleans up messages by:
    - Keeping all user and assistant messages
    - Stripping assistant markdown image references (Gemini doesn't need them)
    - Preserving image_url content parts (for image editing)
    """
    if not isinstance(messages, list):
        return []
    
    cleaned = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "")
        content = msg.get("content", "")
        
        if role == "system":
            # Keep system messages as-is
            cleaned.append({"role": role, "content": content})
        elif role == "user":
            # Keep user messages fully (text + images)
            cleaned.append({"role": role, "content": content})
        elif role == "assistant":
            # For assistant messages, extract meaningful text
            # Remove markdown image links that Gemini can't use
            if isinstance(content, str):
                import re
                # Remove ![...](...) markdown images
                text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', content)
                text = text.replace("Here is the image you requested.", "").strip()
                if text:
                    cleaned.append({"role": role, "content": text})
                else:
                    # If only had image, add a short note
                    cleaned.append({"role": role, "content": "[I generated an image based on your request]"})
            else:
                cleaned.append({"role": role, "content": content})
    
    return cleaned if cleaned else []


def _build_contextual_prompt(messages: list, last_prompt: str) -> str:
    """
    Build a rich text prompt for GPT Image models from conversation history.
    
    GPT Image models only accept text prompts via /images/generations,
    so we combine conversation context into a single descriptive prompt.
    This helps the model understand references like "that image" or "modify it".
    
    Args:
        messages: Full conversation messages from Open WebUI
        last_prompt: The extracted last user message text
    
    Returns:
        A contextual prompt string with conversation summary
    """
    if not isinstance(messages, list) or len(messages) <= 1:
        return last_prompt
    
    context_parts = []
    has_image = False
    
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "")
        content = msg.get("content", "")
        
        if role == "user":
            # Check for image content
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "image_url":
                            has_image = True
                            context_parts.append("[User uploaded an image]")
                        elif item.get("type") == "text":
                            text = item.get("text", "").strip()
                            if text:
                                context_parts.append(f"User: {text}")
            elif isinstance(content, str) and content.strip():
                context_parts.append(f"User: {content.strip()}")
        
        elif role == "assistant":
            if isinstance(content, str):
                # Summarize assistant responses briefly
                import re
                text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '[generated image]', content)
                text = text.strip()
                if text and len(text) < 200:
                    context_parts.append(f"Assistant: {text}")
                elif text:
                    context_parts.append(f"Assistant: {text[:150]}...")
    
    # If only one message or no useful context, return original prompt
    if len(context_parts) <= 1:
        return last_prompt
    
    # Build contextual prompt
    context_summary = "\n".join(context_parts)
    
    if has_image:
        contextual = (
            f"Context of our conversation:\n{context_summary}\n\n"
            f"The user has uploaded an image in this conversation. "
            f"Based on the conversation context above, fulfill this request:\n{last_prompt}"
        )
    else:
        contextual = (
            f"Context of our conversation:\n{context_summary}\n\n"
            f"Based on the conversation context above, generate an image for:\n{last_prompt}"
        )
    
    return contextual


def _extract_images_from_messages(messages: list) -> list[str]:
    """
    Extract image URLs/base64 uploaded by the USER from conversation messages.
    
    Only scans USER messages (not assistant) to avoid including AI-generated images.
    Returns a list of image URLs (data:image/...;base64,... or http URLs).
    """
    image_urls = []
    if not isinstance(messages, list):
        return image_urls
    
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        # Only extract from user messages — skip assistant-generated images
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "image_url":
                    img_url_obj = item.get("image_url", {})
                    if isinstance(img_url_obj, dict):
                        url = img_url_obj.get("url", "")
                        if url and (url.startswith("data:image") or url.startswith("http")):
                            image_urls.append(url)
                    elif isinstance(img_url_obj, str):
                        if img_url_obj.startswith("data:image") or img_url_obj.startswith("http"):
                            image_urls.append(img_url_obj)
    
    return image_urls


async def _handle_image_as_chat(request: Request, user: dict, model: str, body: dict):
    """
    Handle image generation models in chat format.
    Converts chat request to image generation, then formats response as chat.
    """
    rid = init_audit_state(request, user["user_id"], "/v1/chat/completions", model)
    
    # Extract messages and prompt
    messages = body.get("messages", [])
    prompt = _extract_prompt_from_messages(messages)
    
    if not prompt:
        raise HTTPException(400, "No prompt found in messages for image generation")
    
    # Fix #3: Detect and skip Open WebUI task prompts (title/tags generation)
    task_type = _is_system_task_prompt(messages)
    if task_type:
        detail_log(
            "chat.task_skipped",
            request=request,
            user_id=user.get("user_id"),
            model=model,
            task_type=task_type,
            reason="Task prompt sent to image model, returning dummy response",
        )
        # Return appropriate dummy response based on task type
        if task_type == "title":
            dummy_content = '{"title": "🎨 Image Generation"}'
        elif task_type == "tags":
            dummy_content = '{"tags": ["Art", "Image Generation"]}'
        elif task_type == "follow_up":
            dummy_content = '{"follow_ups": ["Generate another image", "Modify the image"]}'
        else:
            dummy_content = '{"query": "image generation"}'
        
        chat_response = {
            "id": f"chatcmpl-{rid}",
            "object": "chat.completion",
            "created": int(datetime.now(timezone.utc).timestamp()),
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": dummy_content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }
        # Handle streaming for task prompts too
        if body.get("stream", False):
            async def _stream_task():
                chunk = {"id": f"chatcmpl-{rid}", "object": "chat.completion.chunk", "created": int(datetime.now(timezone.utc).timestamp()), "model": model, "choices": [{"index": 0, "delta": {"role": "assistant", "content": dummy_content}, "finish_reason": None}]}
                yield f"data: {json.dumps(chunk)}\n\n"
                finish = {"id": f"chatcmpl-{rid}", "object": "chat.completion.chunk", "created": int(datetime.now(timezone.utc).timestamp()), "model": model, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
                yield f"data: {json.dumps(finish)}\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(_stream_task(), media_type="text/event-stream")
        return JSONResponse(status_code=200, content=chat_response)
    
    detail_log(
        "chat.image_model",
        request=request,
        user_id=user.get("user_id"),
        model=model,
        prompt=truncate_text(prompt, limit=2000),
    )
    
    assert_model_allowed(user, model)
    maybe_reset_quota(user)
    
    # Fix #1: Prepare full conversation messages for context
    image_messages = _prepare_image_messages(messages)
    
    # Prepare image generation request (for non-Gemini fallback)
    image_body = {
        "model": model,
        "prompt": prompt,
        "n": 1,
    }
    
    # xAI Grok Imagine does NOT support 'size' param (uses aspect_ratio instead)
    # Only add 'size' for providers that support it (OpenAI, DALL-E)
    is_xai_model = any(k in model.lower() for k in ["grok", "xai"])
    if not is_xai_model:
        image_body["size"] = body.get("size", "1024x1024")
    
    # Call image generation API
    client: httpx.AsyncClient = request.app.state.http_client
    headers = {
        "Authorization": f"Bearer {LITELLM_KEY}",
        "Content-Type": "application/json",
        "X-Request-ID": rid,
    }
    
    try:
        # Gemini models use chat/completions with full conversation context
        if "gemini" in model.lower():
            from api.images import _generate_image_via_chat
            image_data = await _generate_image_via_chat(client, headers, image_messages, model)
        else:
            # GPT Image / DALL-E / xAI Grok Imagine models
            # Check if user uploaded images → use /images/edits for editing
            uploaded_images = _extract_images_from_messages(messages)
            contextual_prompt = _build_contextual_prompt(messages, prompt)
            
            from api.images import _IMAGE_MODEL_MAP
            litellm_model = _IMAGE_MODEL_MAP.get(model, model)
            
            if uploaded_images and "dalle" not in model.lower() and not is_xai_model:
                # User uploaded image(s) → use /images/edits endpoint
                # Note: xAI Grok Imagine does not support /images/edits
                detail_log(
                    "chat.image_edit",
                    request=request,
                    user_id=user.get("user_id"),
                    model=model,
                    num_images=len(uploaded_images),
                    prompt=truncate_text(prompt, limit=200),
                )
                from api.images import _generate_via_gpt_image_edit
                image_data = await _generate_via_gpt_image_edit(
                    client, headers, uploaded_images, contextual_prompt,
                    model, size=body.get("size", "1024x1024"),
                )
                # If edit failed to extract images, fall back to generations
                if image_data is None:
                    detail_log("chat.image_edit_fallback", request=request,
                               reason="No valid images extracted, falling back to generations")
                    image_body["prompt"] = contextual_prompt
                    image_body["model"] = litellm_model
                    resp = await client.post(
                        f"{LITELLM_BASE}/images/generations",
                        headers=headers, json=image_body, timeout=120
                    )
                    if resp.status_code >= 400:
                        set_error_state(request, "provider", f"Image generation returned {resp.status_code}")
                        try: raise HTTPException(resp.status_code, resp.json())
                        except: raise HTTPException(resp.status_code, resp.text)
                    image_data = resp.json()
            else:
                # No uploaded images (or xAI model) → use /images/generations
                image_body["prompt"] = contextual_prompt
                image_body["model"] = litellm_model
                
                detail_log(
                    "chat.image_generations",
                    request=request,
                    user_id=user.get("user_id"),
                    model=model,
                    litellm_model=litellm_model,
                    is_xai=is_xai_model,
                    body_keys=list(image_body.keys()),
                )
                
                resp = await client.post(
                    f"{LITELLM_BASE}/images/generations",
                    headers=headers,
                    json=image_body,
                    timeout=120
                )
                if resp.status_code >= 400:
                    set_error_state(request, "provider", f"Image generation returned {resp.status_code}")
                    try:
                        error_data = resp.json()
                        raise HTTPException(resp.status_code, error_data)
                    except Exception:
                        raise HTTPException(resp.status_code, resp.text)
                image_data = resp.json()
    
    except httpx.RequestError as e:
        set_error_state(request, "provider", f"Image generation failed: {e.__class__.__name__}")
        raise HTTPException(503, f"Image generation unavailable: {e.__class__.__name__}")
    
    # Parse image response and materialize base64 to HTTP URL
    # CRITICAL: data:image/png;base64,... URLs are hundreds of KB and cause
    # "Chunk too big" errors in Open WebUI streaming. Must convert to HTTP URLs.
    image_url = None
    if isinstance(image_data.get("data"), list) and len(image_data["data"]) > 0:
        from utils.media import maybe_materialize_image_items
        maybe_materialize_image_items(request, image_data["data"], fallback_mime="image/png")
        image_url = image_data["data"][0].get("url")
    
    # Calculate cost and bump quota
    prices = load_prices()
    cost_usd = calc_image_cost_from_body(model, image_body, prices)
    if cost_usd > 0:
        enforce_and_bump_quota(user["user_id"], add_cost_usd=cost_usd, add_image_requests=1)
    
    set_usage_state(request, 0, 0, 0, cost_usd)
    set_counters(request, image_count=1)
    
    # Format as chat completion response
    content_text = f"![Generated Image]({image_url})\n\nHere is the image you requested." if image_url else "Sorry, I could not generate the image. Please try again."
    chat_response = {
        "id": f"chatcmpl-{rid}",
        "object": "chat.completion",
        "created": int(datetime.now(timezone.utc).timestamp()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": content_text
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        },
        "_mw_user": user["user_id"],
        "_mw_request_id": rid,
        "_mw_added_cost_usd": round(cost_usd, 6) if cost_usd > 0 else None
    }
    
    # Handle streaming vs non-streaming
    stream = body.get("stream", False)
    if stream:
        # Convert to SSE stream format
        async def _stream_image_response():
            # Send data chunk
            chunk = {
                "id": f"chatcmpl-{rid}",
                "object": "chat.completion.chunk",
                "created": int(datetime.now(timezone.utc).timestamp()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "content": content_text
                    },
                    "finish_reason": None
                }]
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            
            # Send finish chunk
            finish_chunk = {
                "id": f"chatcmpl-{rid}",
                "object": "chat.completion.chunk",
                "created": int(datetime.now(timezone.utc).timestamp()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }]
            }
            yield f"data: {json.dumps(finish_chunk)}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(_stream_image_response(), media_type="text/event-stream")
    else:
        return JSONResponse(status_code=200, content=chat_response)


async def _finalize_streaming(request: Request, user: dict, model: str, request_id: str, usage_data: dict) -> str | None:
    """
    Finalize streaming request: Calculate cost, bump quota, write reconciled audit.
    
    Args:
        request: FastAPI Request
        user: User dict
        model: Model name
        request_id: Request ID
        usage_data: Usage dict from stream (if stream_options.include_usage), or None
    
    Returns:
        Quota warning text to inject into stream, or None.
    """
    try:
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        cost_usd = 0.0
        usage_missing = False
        
        # Method 1: Extract from stream (if stream_options.include_usage was set)
        if usage_data:
            prompt_tokens = int(usage_data.get("prompt_tokens", 0))
            completion_tokens = int(usage_data.get("completion_tokens", 0))
            total_tokens = int(usage_data.get("total_tokens", prompt_tokens + completion_tokens))
            logger.info("stream_finalize rid=%s tokens=%d (from stream)", request_id, total_tokens)
        
        # Method 2: Fallback to LiteLLM log parsing
        else:
            await asyncio.sleep(1)  # Wait for LiteLLM to write log
            usage = find_usage_in_log(request_id)
            if usage:
                prompt_tokens = int(usage.get("prompt_tokens", 0))
                completion_tokens = int(usage.get("completion_tokens", 0))
                total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))
                logged_cost = usage.get("response_cost")
                if logged_cost:
                    try:
                        cost_usd = float(logged_cost)
                    except Exception:
                        pass
                logger.info("stream_finalize rid=%s tokens=%d (from litellm log)", request_id, total_tokens)
        
        # CRITICAL: If no usage found, mark as missing and don't write reconciled audit
        if total_tokens == 0 and cost_usd == 0.0:
            usage_missing = True
            logger.warning("stream_finalize rid=%s: USAGE MISSING - no tokens or cost from stream or log", request_id)
            # Don't write reconciled audit with zeros - this would pollute billable metrics
            # The pending audit remains, showing the request was made but usage wasn't captured
            return None
        
        # Calculate cost if not from LiteLLM
        if cost_usd == 0.0 and total_tokens > 0:
            prices = load_prices()
            cost_usd = calc_cost_usd(model, prompt_tokens, completion_tokens, prices)
        
        # Bump quota (CRITICAL for billing) — O(1) atomic update
        if total_tokens > 0 or cost_usd > 0:
            from core.auth import update_user_quota
            update_user_quota(
                user["user_id"],
                add_tokens=total_tokens,
                add_cost_usd=cost_usd,
            )
            
            # Alert check (after quota bump, streaming already sent)
            asyncio.create_task(
                _safe_alert_check(user["user_id"], cost_usd)
            )
        
        # Extract cached tokens info (Anthropic prompt caching / Gemini implicit caching)
        _usage_src = usage_data or {}
        cached_tokens_created = int(_usage_src.get("cache_creation_input_tokens", 0))
        cached_tokens_read = int(_usage_src.get("cache_read_input_tokens", 0))
        # Gemini uses cached_content_token_count for implicit caching
        cached_tokens_read = cached_tokens_read or int(_usage_src.get("cached_content_token_count", 0))
        
        if cached_tokens_read > 0 or cached_tokens_created > 0:
            logger.info("stream_cache_info rid=%s created=%d read=%d", request_id, cached_tokens_created, cached_tokens_read)
        
        # Write reconciled audit line (only if we have actual usage)
        write_audit_line({
            "ts": datetime.now(timezone.utc).isoformat(),
            "rid": request_id,
            "user_id": user["user_id"],
            "auth_source": getattr(request.state, "mw_auth_source", None),
            "openwebui_user_id": getattr(request.state, "mw_openwebui_user_id", None),
            "endpoint": "/v1/chat/completions",
            "model": model,
            "status": "reconciled",
            "status_code": 200,
            "latency_ms": None,
            "tokens_in": prompt_tokens,
            "tokens_out": completion_tokens,
            "tokens_total": total_tokens,
            "cost_usd": cost_usd,
            "cached_tokens_created": cached_tokens_created,
            "cached_tokens_read": cached_tokens_read,
            "image_count": None,
            "tts_chars": None,
            "stt_seconds": None,
            "video_count": None,
            "error_type": None,
            "error_message": None
        })
        
        logger.info("stream_finalize_complete rid=%s tokens=%d cost=$%.6f", request_id, total_tokens, cost_usd)
        
        # Check quota warning AFTER bumping (so it reflects the latest usage)
        warning_text = _get_quota_warning_text(user["user_id"])
        return warning_text
    
    except Exception as e:
        logger.error("stream_finalize_error rid=%s: %s", request_id, str(e))
        return None


def _extract_rag_source_images(messages: list) -> dict:
    """
    Parse <source id="N"> tags in messages,
    extracting image URLs, alt text, and preceding context text.
    """
    import re
    source_images = {}
    
    if not isinstance(messages, list):
        return source_images
        
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if not isinstance(content, str):
            continue
            
        # Parse <source id="N">...</source>
        matches = re.finditer(r'<source\s+id="(\d+)">(.*?)</source>', content, re.DOTALL)
        for match in matches:
            source_id = match.group(1)
            source_content = match.group(2)
            
            # Find Markdown images in this source block: ![alt](url)
            img_matches = re.finditer(r'!\[([^\]]*)\]\((https?://[^\s)]+)\)', source_content)
            
            for img_match in img_matches:
                alt_text = img_match.group(1) or ""
                url = img_match.group(2)
                
                # Get up to 200 characters of text preceding this image in the source block
                start_pos = img_match.start()
                preceding = source_content[:start_pos]
                # Strip other markdown images from preceding text to avoid pollution
                preceding_clean = re.sub(r'!\[.*?\]\([^)]+\)', '', preceding)
                preceding_text = preceding_clean[-200:].strip()
                
                if source_id not in source_images:
                    source_images[source_id] = []
                    
                source_images[source_id].append({
                    "url": url,
                    "alt_text": alt_text,
                    "preceding_text": preceding_text
                })
                
    return source_images


def _validate_llm_images(response_content: str) -> str:
    """
    Scan response for Markdown images, validate if URL is trusted.
    If URL is not from trusted domains (/v1/_mw/media/ or /rag-images/),
    remove the image from the response.
    """
    import re
    if not isinstance(response_content, str):
        return response_content
        
    def replace_img(match):
        alt = match.group(1)
        url = match.group(2)
        if "/v1/_mw/media/" in url or "/rag-images/" in url:
            return match.group(0)
        logger.info("rag_image_strip: stripped untrusted image URL: %s", url)
        return ""
        
    pattern = r'!\[([^\]]*)\]\((https?://[^\s)]+)\)'
    return re.sub(pattern, replace_img, response_content)


def _response_has_valid_images(response_content: str, source_images: dict) -> bool:
    """
    Check if the LLM response already contains any valid images from our sources.
    """
    import re
    if not isinstance(response_content, str) or not source_images:
        return False
        
    all_source_urls = set()
    for img_list in source_images.values():
        for img in img_list:
            all_source_urls.add(img["url"])
            
    pattern = r'!\[[^\]]*\]\((https?://[^\s)]+)\)'
    response_urls = re.findall(pattern, response_content)
    
    for url in response_urls:
        if url in all_source_urls:
            return True
            
    return False


def _select_image_by_proximity(response_text: str, image_list: list) -> str:
    """
    Select the image that has the highest proximity/semantic match score
    with the response text, using n-gram word overlaps.
    """
    if not image_list:
        return ""
    if len(image_list) == 1:
        return image_list[0]["url"]
        
    scored = []
    response_lower = response_text.lower()
    
    for idx, img in enumerate(image_list):
        score = 0
        preceding = img.get("preceding_text", "").lower()
        alt = img.get("alt_text", "").lower()
        
        prec_words = preceding.split()
        if len(prec_words) >= 3:
            ngrams = [" ".join(prec_words[i:i+3]) for i in range(len(prec_words)-2)]
            match_count = sum(1 for ng in ngrams if ng in response_lower)
            score += match_count
            
        alt_words = alt.split()
        if alt_words:
            alt_match = sum(1 for w in alt_words if len(w) > 2 and w in response_lower)
            score += alt_match * 2
            
        logger.debug("proximity_score idx=%d url=%s score=%d", idx, img["url"], score)
        scored.append((score, idx, img["url"]))
        
    scored.sort(key=lambda x: (x[0], -x[1]), reverse=True)
    return scored[0][2]


def _build_image_injection_text(cited_images: list, max_images: int = 3) -> str:
    """
    Build Markdown section containing the selected cited images.
    """
    if not cited_images:
        return ""
        
    seen_urls = set()
    unique_images = []
    for item in cited_images:
        url = item["url"]
        if url not in seen_urls:
            seen_urls.add(url)
            unique_images.append(item)
            
    images_to_inject = unique_images[:max_images]
    if not images_to_inject:
        return ""
        
    img_section = "\n\n---\n📊 **Hình minh họa từ nguồn trích dẫn:**\n"
    for item in images_to_inject:
        cid = item["source_id"]
        url = item["url"]
        img_section += f"\n![Nguồn [{cid}]]({url})\n"
        
    return img_section


async def chat_completions(request: Request):
    """
    Proxy chat completions to LiteLLM with quota enforcement.
    Supports both streaming and non-streaming modes.
    Also handles image generation models by converting to chat format.
    """
    user = require_user(request)

    # Parse body once and reuse
    try:
        body = await request.json()
    except UnicodeDecodeError as e:
        raise HTTPException(400, f"Invalid UTF-8 encoding in request body: {str(e)}")
        
    # --- User Sync via Forward Headers (Standard) ---
    # Open WebUI sends X-OpenWebUI-User-Email when ENABLE_FORWARD_USER_INFO_HEADERS=true.
    # If the request is authenticated as 'admin' (Global Connection key), we look up the
    # actual user from this header and attribute usage to them via lazy provisioning.
    if user.get("user_id") == "admin":
        ow_email = request.headers.get("X-OpenWebUI-User-Email", "")
        if ow_email:
            from core.auth import get_user_by_id, lazy_provision_user
            actual_user = get_user_by_id(ow_email)
            if not actual_user:
                actual_user = lazy_provision_user(ow_email)
            if actual_user and actual_user.get("active", True):
                user = actual_user
                request.state.mw_user_id = user.get("user_id")
                logger.info("user_sync: impersonated admin -> %s via header", ow_email)
    
    model = body.get("model")
    if not model:
        raise HTTPException(400, "Missing model")
    
    # Detect image generation models and route to image generation
    is_image_model = _is_image_generation_model(model)
    if is_image_model:
        return await _handle_image_as_chat(request, user, model, body)
    
    # --- RAG Context Cleaning: Materialize Base64 images in messages ---
    messages = body.get("messages")
    logger.info("rag_debug: processing %d messages", len(messages) if isinstance(messages, list) else 0)
    
    # Bypass Base64 scanning to optimize Query Path latency.
    # Images are already materialized in WebP format on local storage at Ingest-time.
    # Direct user chat attachments are kept as-is to be processed natively by Vision Models.

    # Initialize audit state early
    rid = init_audit_state(request, user["user_id"], "/v1/chat/completions", model)

    # Extract RAG source images for hybrid injection
    request.state.rag_source_images = {}
    if MW_RAG_IMAGE_INJECT and isinstance(messages, list):
        try:
            request.state.rag_source_images = _extract_rag_source_images(messages)
            logger.info("rag_image_extract: extracted %d sources with images", len(request.state.rag_source_images))
        except Exception as e:
            logger.error("rag_image_extract_error: %s", e)

    # Process multimodal content (images, documents, and other file attachments in messages)
    messages = body.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    
                    # Handle image_url content type
                    if item.get("type") == "image_url":
                        image_url_obj = item.get("image_url")
                        if isinstance(image_url_obj, dict):
                            url = image_url_obj.get("url")
                            if isinstance(url, str) and url.startswith("data:"):
                                # Keep data URLs inline - don't materialize 
                                # LiteLLM has issues downloading from localhost
                                pass
                    
                    # Handle file attachments (documents, PDFs, etc.)
                    # Some models accept file content in various formats
                    elif item.get("type") in ("file", "document", "attachment"):
                        # Check for data URL in various fields
                        for url_field in ["url", "file_url", "data"]:
                            url = item.get(url_field)
                            if isinstance(url, str) and url.startswith("data:"):
                                # Keep data URLs inline
                                pass
                                break
                    
                    # Handle generic data URLs in any content item
                    elif "url" in item:
                        url = item.get("url")
                        if isinstance(url, str) and url.startswith("data:"):
                            # Keep data URLs inline
                            pass

    prompt_preview = extract_text_from_messages(body.get("messages"))
    detail_log(
        "chat.request",
        request=request,
        user_id=user.get("user_id"),
        model=model,
        stream=bool(body.get("stream")),
        prompt=truncate_text(prompt_preview, limit=2000),
        body=body,
    )

    assert_model_allowed(user, model)

    maybe_reset_quota(user)
    quota = user.get("quota", {})
    limit_tokens = int(quota.get("limit_tokens", 0))
    used_tokens = int(quota.get("used_tokens", 0))
    limit_cost = float(quota.get("limit_cost_usd", 0.0))
    used_cost = float(quota.get("used_cost_usd", 0.0))

    # ── PRE-CHECK: Block if quota already exceeded BEFORE calling LLM ──
    _quota_already_exceeded = False
    if limit_cost > 0 and used_cost >= limit_cost:
        _quota_already_exceeded = True
    if limit_tokens > 0 and used_tokens >= limit_tokens:
        _quota_already_exceeded = True

    if _quota_already_exceeded:
        reset_info = get_quota_reset_info(user)
        period_label = reset_info["period_label"]
        days_left = reset_info["days_until_reset"]
        quota_msg = (
            f"🔒 Bạn đã sử dụng hết quota {period_label} này. "
            f"Quota tiếp theo sẽ reset trong **{days_left} ngày**.\n\n"
            f"Vui lòng liên hệ admin nếu cần nâng hạn mức."
        )
        logger.info("quota_pre_block user=%s period=%s days_left=%d", user["user_id"], period_label, days_left)
        # Return fake response instead of 403 error
        from datetime import datetime, timezone
        fake_resp = {
            "id": f"chatcmpl-quota-{rid}",
            "object": "chat.completion",
            "created": int(datetime.now(timezone.utc).timestamp()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": quota_msg},
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "_mw_user": user["user_id"],
            "_mw_quota_blocked": True,
        }
        is_stream = bool(body.get("stream"))
        if is_stream:
            # Fake streaming response
            async def _fake_stream():
                chunk = {
                    "id": f"chatcmpl-quota-{rid}",
                    "object": "chat.completion.chunk",
                    "created": int(datetime.now(timezone.utc).timestamp()),
                    "model": model,
                    "choices": [{"index": 0, "delta": {"role": "assistant", "content": quota_msg}, "finish_reason": None}]
                }
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8")
                done_chunk = {
                    "id": f"chatcmpl-quota-{rid}",
                    "object": "chat.completion.chunk",
                    "created": int(datetime.now(timezone.utc).timestamp()),
                    "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                }
                yield f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\n".encode("utf-8")
                yield b"data: [DONE]\n\n"
            return StreamingResponse(_fake_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Request-ID": rid})
        else:
            return JSONResponse(status_code=200, content=fake_resp)

    # ── Smart Routing: resolve auto-model to concrete model ──
    _routing_downgraded = False
    _routing_tier = None
    from core.smart_routing import is_auto_model, resolve_auto_model
    if is_auto_model(model):
        # Calculate quota percentage
        quota_percent = (used_cost / limit_cost * 100) if limit_cost > 0 else 0.0

        # Detect vision/file content in messages
        _has_vision = False
        _has_files = False
        if isinstance(messages, list):
            for msg in messages:
                if isinstance(msg, dict):
                    content = msg.get("content")
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                if item.get("type") == "image_url":
                                    _has_vision = True
                                elif item.get("type") in ("file", "document", "attachment"):
                                    _has_files = True

        original_model = model
        model, _routing_tier, _routing_downgraded, _thinking_params = await resolve_auto_model(
            model, messages or [], quota_percent,
            has_vision=_has_vision, has_files=_has_files,
        )
        body["model"] = model

        # Inject thinking/reasoning params per provider + tier
        if _thinking_params:
            body.update(_thinking_params)
            logger.info("thinking_inject model=%s tier=%s params=%s",
                        model, _routing_tier, list(_thinking_params.keys()))

        detail_log(
            "chat.smart_route",
            request=request,
            user_id=user.get("user_id"),
            original_model=original_model,
            resolved_model=model,
            tier=_routing_tier,
            quota_percent=round(quota_percent, 1),
            downgraded=_routing_downgraded,
            thinking=list(_thinking_params.keys()) if _thinking_params else None,
        )

    # Normalize provider-specific parameters (replaces old GPT-5 only handling)
    _normalize_provider_params(model, body)

    # Use rid from audit_state (already generated)
    request_id = rid
    body["user"] = user["user_id"]
    metadata = body.get("metadata") or {}
    metadata["mw_request_id"] = request_id
    body["metadata"] = metadata

    headers = {
        "Authorization": f"Bearer {LITELLM_KEY}",
        "Content-Type": "application/json",
        "X-Request-ID": request_id,
    }

    # Store smart routing info for warning injection
    request.state.routing_downgraded = _routing_downgraded
    request.state.routing_tier = _routing_tier
    request.state.routing_quota_percent = (used_cost / limit_cost * 100) if limit_cost > 0 else 0.0

    is_stream = bool(body.get("stream"))

    if is_stream:
        return await _handle_streaming(request, user, model, body, headers, request_id)
    else:
        return await _handle_non_streaming(request, user, model, body, headers, request_id, limit_tokens, used_tokens, limit_cost, used_cost)


async def _handle_streaming(request: Request, user: dict, model: str, body: dict, headers: dict, request_id: str):
    """Handle streaming chat completions"""
    from utils.logging import write_audit_line
    from core.audit_state import mark_audit_logged
    from datetime import datetime, timezone
    
    # Write pending audit line immediately before streaming
    write_audit_line({
        "ts": datetime.now(timezone.utc).isoformat(),
        "rid": request_id,
        "user_id": user["user_id"],
        "auth_source": getattr(request.state, "mw_auth_source", None),
        "openwebui_user_id": getattr(request.state, "mw_openwebui_user_id", None),
        "endpoint": "/v1/chat/completions",
        "model": model,
        "status": "pending",
        "status_code": None,
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
    
    # Mark as logged to prevent middleware from logging again
    mark_audit_logged(request)
    
    append_pending(request_id, user["user_id"])

    # Important: like TTS, don't create the upstream stream inside an `async with` that
    # exits before StreamingResponse iterates. We open the stream first, validate status,
    # then stream bytes and always clean up.
    logger.info("stream_start rid=%s model=%s", request_id, model)

    # Use shared connection pool from app.state (not a new client per request)
    client = request.app.state.http_client
    detail_log(
        "upstream.request",
        request=request,
        rid=request_id,
        user_id=user.get("user_id"),
        upstream=f"{LITELLM_BASE}/chat/completions",
        method="POST",
        headers=safe_headers(headers),
        body=body,
    )
    req = client.build_request("POST", f"{LITELLM_BASE}/chat/completions", headers=headers, json=body)
    resp = await client.send(req, stream=True)

    if resp.status_code >= 400:
        try:
            error_bytes = await resp.aread()
        finally:
            error_text = error_bytes.decode("utf-8", errors="ignore")
            
            # Write error audit to close the pending request
            write_audit_line({
                "ts": datetime.now(timezone.utc).isoformat(),
                "rid": request_id,
                "user_id": user["user_id"],
                "auth_source": getattr(request.state, "mw_auth_source", None),
                "openwebui_user_id": getattr(request.state, "mw_openwebui_user_id", None),
                "endpoint": "/v1/chat/completions",
                "model": model,
                "status": "error",
                "status_code": resp.status_code,
                "upstream_status": resp.status_code,
                "latency_ms": 0,
                "tokens_in": 0,
                "tokens_out": 0,
                "tokens_total": 0,
                "cost_usd": 0.0,
                "image_count": None,
                "tts_chars": None,
                "stt_seconds": None,
                "video_count": None,
                "error_type": "upstream_error",
                "error_message": truncate_text(error_text, 500)
            })
            
            remove_pending(request_id)
            await resp.aclose()
            # NOTE: Do NOT close client here — it's the shared pool from app.state
        logger.warning("stream_error rid=%s status=%s body=%s", request_id, resp.status_code, error_text[:500])
        raise HTTPException(resp.status_code, error_text)

    response_text_holder = [""]
    buffer_overflow_holder = [False]

    async def _iter_bytes():
        sampled: bytearray = bytearray()
        usage_data = None  # Track usage from stream_options.include_usage
        done_sent = False  # Track if we intercepted [DONE]
        
        try:
            async for chunk in resp.aiter_bytes():
                if len(sampled) < 8192:
                    sampled.extend(chunk[: max(0, 8192 - len(sampled))])
                
                # Try to extract usage and text content from SSE data
                try:
                    chunk_str = chunk.decode("utf-8", errors="ignore")
                    for line in chunk_str.split("\n"):
                        line = line.strip()
                        if line.startswith("data: ") and not line.startswith("data: [DONE]"):
                            json_str = line[6:].strip()
                            if json_str:
                                chunk_data = json.loads(json_str)
                                # Extract usage from final chunk
                                if "usage" in chunk_data:
                                    usage_data = chunk_data["usage"]
                                
                                # Accumulate text content for image injection proximity match
                                choices = chunk_data.get("choices", [])
                                if choices and isinstance(choices, list):
                                    delta = choices[0].get("delta", {})
                                    delta_content = delta.get("content")
                                    if delta_content and isinstance(delta_content, str):
                                        if len(response_text_holder[0]) < 200000:
                                            response_text_holder[0] += delta_content
                                        else:
                                            if not buffer_overflow_holder[0]:
                                                buffer_overflow_holder[0] = True
                                                logger.warning("rag_image_stream_buffer_overflow rid=%s", request_id)
                except Exception:
                    pass  # Ignore parsing errors
                
                # Intercept [DONE] marker — we'll send it after quota warning
                chunk_str_raw = chunk.decode("utf-8", errors="ignore")
                if "data: [DONE]" in chunk_str_raw:
                    # Yield everything before [DONE]
                    before_done = chunk_str_raw.replace("data: [DONE]\n\n", "").replace("data: [DONE]\n", "").replace("data: [DONE]", "")
                    if before_done.strip():
                        yield before_done.encode("utf-8")
                    done_sent = True
                    # Don't yield [DONE] yet — we'll add quota warning first
                    continue
                
                yield chunk
        except (httpx.StreamClosed, httpx.RemoteProtocolError, asyncio.CancelledError):
            return
        finally:
            # Finalize streaming: reconcile usage and bump quota
            warning_text = await _finalize_streaming(request, user, model, request_id, usage_data)
            
            # Inject quota warning as extra SSE chunk before [DONE]
            # Note: We can only inject if we intercepted [DONE] (done_sent=True)
            # If stream ended abnormally, skip injection
            # (warning_text is set in _finalize_streaming after quota bump)
            
            remove_pending(request_id)
            await resp.aclose()
            # NOTE: Do NOT close client — shared pool from app.state
            logger.info("stream_end rid=%s", request_id)
            if sampled:
                detail_log(
                    "chat.stream.sample",
                    request=request,
                    rid=request_id,
                    user_id=user.get("user_id"),
                    sample_bytes=len(sampled),
                    sample=truncate_text(sampled.decode("utf-8", errors="ignore"), limit=4000),
                )
            # Persist the assembled answer text so retrieval-health (citation
            # hit-rate) can be derived for streamed chats too — mirrors the
            # non-streaming chat.response event. Logged before RAG image
            # injection, so it reflects the model's own [N] citation markers.
            if response_text_holder[0]:
                detail_log(
                    "chat.response",
                    request=request,
                    rid=request_id,
                    user_id=user.get("user_id"),
                    status=resp.status_code,
                    model=model,
                    content=truncate_text(response_text_holder[0], limit=2000),
                    usage=usage_data,
                    stream=True,
                )

    # Wrap _iter_bytes to inject quota warning after stream ends
    async def _iter_with_quota_warning():
        warning_text_holder = [None]
        
        async for chunk in _iter_bytes():
            yield chunk
        
        # RAG image injection fallback for streaming
        source_images = getattr(request.state, "rag_source_images", {})
        if MW_RAG_IMAGE_INJECT and source_images and not buffer_overflow_holder[0]:
            response_text = response_text_holder[0]
            try:
                if not _response_has_valid_images(response_text, source_images):
                    import re
                    citations = re.findall(r'\[(\d+(?:\s*,\s*\d+)*)\]', response_text)
                    cited_ids = set()
                    for cit in citations:
                        for part in cit.split(','):
                            cited_ids.add(part.strip())
                            
                    selected_images = []
                    for cid in sorted(list(cited_ids)):
                        if cid in source_images:
                            img_list = source_images[cid]
                            if img_list:
                                if len(img_list) == 1:
                                    selected_images.append({
                                        "source_id": cid,
                                        "url": img_list[0]["url"]
                                    })
                                    logger.info("rag_image_inject rid=%s source=%s method=s1_single url=%s (stream)", request_id, cid, img_list[0]["url"])
                                else:
                                    best_url = _select_image_by_proximity(response_text, img_list)
                                    selected_images.append({
                                        "source_id": cid,
                                        "url": best_url
                                    })
                                    logger.info("rag_image_inject rid=%s source=%s method=s1_proximity url=%s (stream)", request_id, cid, best_url)
                                    
                    if selected_images:
                        image_injection = _build_image_injection_text(selected_images, MW_RAG_IMAGE_MAX)
                        if image_injection:
                            image_chunk = {
                                "id": f"chatcmpl-{request_id}",
                                "object": "chat.completion.chunk",
                                "created": int(datetime.now(timezone.utc).timestamp()),
                                "model": model,
                                "choices": [{
                                    "index": 0,
                                    "delta": {"content": image_injection},
                                    "finish_reason": None
                                }]
                            }
                            yield f"data: {json.dumps(image_chunk)}\n\n".encode("utf-8")
                            logger.info("rag_image_inject rid=%s: injected %d images to stream", request_id, len(selected_images))
                    else:
                        logger.info("rag_image_skip rid=%s: no matching source images for citations (stream)", request_id)
                else:
                    logger.info("rag_image_skip rid=%s: response already contains valid source images (stream)", request_id)
            except Exception as e:
                logger.error("rag_image_stream_injection_error rid=%s: %s", request_id, e)
        else:
            if not MW_RAG_IMAGE_INJECT:
                logger.info("rag_image_skip rid=%s: feature disabled (stream)", request_id)
            elif buffer_overflow_holder[0]:
                logger.info("rag_image_skip rid=%s: buffer overflow (stream)", request_id)
            else:
                logger.info("rag_image_skip rid=%s: no source images extracted (stream)", request_id)

        # After stream completes, check quota warning
        # _finalize_streaming already ran in the finally block
        # We need to check quota status here since we can now yield
        combined_warnings = ""
        routing_warning = _get_routing_warning_text(request)
        if routing_warning:
            combined_warnings += routing_warning
        quota_warning = _get_quota_warning_text(user["user_id"])
        if quota_warning:
            combined_warnings += quota_warning
        if combined_warnings:
            # Yield warnings as an extra SSE content chunk
            warning_chunk = {
                "id": f"chatcmpl-{request_id}",
                "object": "chat.completion.chunk",
                "created": int(datetime.now(timezone.utc).timestamp()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": combined_warnings},
                    "finish_reason": None
                }]
            }
            yield f"data: {json.dumps(warning_chunk)}\n\n".encode("utf-8")
            logger.info("stream_warning_injected rid=%s user=%s", request_id, user["user_id"])
        
        # Send [DONE] marker last
        yield b"data: [DONE]\n\n"

    return StreamingResponse(
        _iter_with_quota_warning(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id,
        },
    )


async def _handle_non_streaming(request: Request, user: dict, model: str, body: dict, headers: dict, request_id: str, limit_tokens: int, used_tokens: int, limit_cost: float, used_cost: float):
    """Handle non-streaming chat completions"""
    client: httpx.AsyncClient = request.app.state.http_client
    detail_log(
        "upstream.request",
        request=request,
        rid=request_id,
        user_id=user.get("user_id"),
        upstream=f"{LITELLM_BASE}/chat/completions",
        method="POST",
        headers=safe_headers(headers),
        body=body,
    )
    resp = await client.post(f"{LITELLM_BASE}/chat/completions", headers=headers, json=body)
    if resp.status_code >= 400:
        try:
            raise HTTPException(resp.status_code, resp.json())
        except Exception:
            raise HTTPException(resp.status_code, resp.text)
    data = resp.json()
    try:
        content_preview = (((data.get("choices") or [{}])[0].get("message") or {}).get("content"))
    except Exception:
        content_preview = None
    detail_log(
        "chat.response",
        request=request,
        rid=request_id,
        user_id=user.get("user_id"),
        status=resp.status_code,
        model=model,
        content=truncate_text(content_preview, limit=2000),
        usage=data.get("usage"),
    )
    litellm_cost = get_cost_from_headers(resp.headers)

    usage = data.get("usage", {}) or {}
    prompt_tokens = int(usage.get("prompt_tokens", 0))
    completion_tokens = int(usage.get("completion_tokens", 0))
    total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))
    
    # Extract cached tokens info (Anthropic prompt caching / Gemini implicit caching)
    cached_tokens_created = int(usage.get("cache_creation_input_tokens", 0))
    cached_tokens_read = int(usage.get("cache_read_input_tokens", 0))
    # Gemini uses cached_content_token_count for implicit caching
    cached_tokens_read = cached_tokens_read or int(usage.get("cached_content_token_count", 0))
    
    if cached_tokens_read > 0 or cached_tokens_created > 0:
        logger.info("cache_info rid=%s model=%s created=%d read=%d", request_id, model, cached_tokens_created, cached_tokens_read)
    
    # Load prices for cost calculation
    from core.cost import load_prices
    prices = load_prices()
    cost_usd = litellm_cost if litellm_cost > 0 else calc_cost_usd(model, prompt_tokens, completion_tokens, prices)
    
    # Set usage state for audit (BEFORE quota check - will be logged even if quota fails)
    set_usage_state(request, prompt_tokens, completion_tokens, total_tokens, cost_usd)

    if limit_tokens > 0 and used_tokens + total_tokens > limit_tokens:
        # Log but do NOT raise 403 — response already sent to user.
        # Pre-check will block the NEXT request.
        logger.warning("quota_post_exceeded user=%s type=tokens used=%d limit=%d",
                        user["user_id"], used_tokens + total_tokens, limit_tokens)
    if limit_cost > 0 and used_cost + cost_usd > limit_cost + 1e-9:
        logger.warning("quota_post_exceeded user=%s type=cost used=%.4f limit=%.2f",
                        user["user_id"], used_cost + cost_usd, limit_cost)

    enforce_and_bump_quota(user["user_id"], add_tokens=total_tokens, add_cost_usd=cost_usd)

    # Alert check (async, non-blocking)
    asyncio.create_task(
        _safe_alert_check(user["user_id"], cost_usd)
    )

    # Extract RAG image injection state and process content
    source_images = getattr(request.state, "rag_source_images", {})
    try:
        choices = data.get("choices", [])
        if choices and isinstance(choices, list):
            msg = choices[0].get("message", {})
            content = msg.get("content")
            if isinstance(content, str):
                # Validate & strip untrusted images
                content = _validate_llm_images(content)
                
                # Check for RAG image injection fallback
                if MW_RAG_IMAGE_INJECT and source_images:
                    if not _response_has_valid_images(content, source_images):
                        import re
                        citations = re.findall(r'\[(\d+(?:\s*,\s*\d+)*)\]', content)
                        cited_ids = set()
                        for cit in citations:
                            for part in cit.split(','):
                                cited_ids.add(part.strip())
                        
                        selected_images = []
                        for cid in sorted(list(cited_ids)):
                            if cid in source_images:
                                img_list = source_images[cid]
                                if img_list:
                                    if len(img_list) == 1:
                                        selected_images.append({
                                            "source_id": cid,
                                            "url": img_list[0]["url"]
                                        })
                                        logger.info("rag_image_inject rid=%s source=%s method=s1_single url=%s", request_id, cid, img_list[0]["url"])
                                    else:
                                        best_url = _select_image_by_proximity(content, img_list)
                                        selected_images.append({
                                            "source_id": cid,
                                            "url": best_url
                                        })
                                        logger.info("rag_image_inject rid=%s source=%s method=s1_proximity url=%s", request_id, cid, best_url)
                                        
                        if selected_images:
                            injection_text = _build_image_injection_text(selected_images, MW_RAG_IMAGE_MAX)
                            if injection_text:
                                content += injection_text
                                logger.info("rag_image_inject rid=%s: injected %d images", request_id, len(selected_images))
                        else:
                            logger.info("rag_image_skip rid=%s: no matching source images for citations", request_id)
                    else:
                        logger.info("rag_image_skip rid=%s: response already contains valid source images (s3_llm)", request_id)
                else:
                    if not MW_RAG_IMAGE_INJECT:
                        logger.info("rag_image_skip rid=%s: feature disabled", request_id)
                    else:
                        logger.info("rag_image_skip rid=%s: no source images extracted", request_id)
                
                msg["content"] = content
    except Exception as e:
        logger.error("rag_image_non_streaming_injection_error rid=%s: %s", request_id, e)

    # Inject warnings into response content (routing downgrade + quota)
    combined_warnings = ""
    routing_warning = _get_routing_warning_text(request)
    if routing_warning:
        combined_warnings += routing_warning
    quota_warning = _get_quota_warning_text(user["user_id"])
    if quota_warning:
        combined_warnings += quota_warning
    if combined_warnings:
        try:
            choices = data.get("choices", [])
            if choices and isinstance(choices, list):
                msg = choices[0].get("message", {})
                if isinstance(msg.get("content"), str):
                    msg["content"] += combined_warnings
                    logger.info("non_stream_warning_injected rid=%s user=%s", request_id, user["user_id"])
        except Exception as e:
            logger.debug("warning_inject_failed rid=%s: %s", request_id, e)

    data["_mw_user"] = user["user_id"]
    data["_mw_request_id"] = request_id
    data["_mw_added_tokens"] = total_tokens
    data["_mw_added_cost_usd"] = round(cost_usd, 6)

    return JSONResponse(status_code=200, content=data)
