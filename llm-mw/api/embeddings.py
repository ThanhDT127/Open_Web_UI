"""
Embeddings endpoint - Proxy with auth, quota, and cost tracking.
Routes embedding requests through middleware to LiteLLM for monitoring via dashboard.
"""

import uuid
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
import httpx

from config import LITELLM_BASE, LITELLM_KEY, logger
from core.auth import require_user, update_user_quota
from core.quota import maybe_reset_quota
from core.cost import load_prices
from core.audit_state import init_audit_state, set_usage_state, set_error_state
from services.litellm import get_cost_from_headers


# Gemini embedding pricing: $0.15 / 1M tokens
EMBEDDING_COST_PER_1M = 0.15

# PGVector HNSW index supports max 2000 dimensions.
# Gemini embedding-001 outputs 3072 natively, so we reduce via API param.
EMBEDDING_TARGET_DIMS = 1536


def _calc_embedding_cost(model: str, total_tokens: int, prices: dict) -> float:
    """
    Calculate embedding cost.
    Uses prices.json if available, otherwise falls back to default rate.
    """
    price = prices.get(model, {})
    
    # Support input_per_1m format (same as chat models)
    if "input_per_1m" in price:
        rate = float(price.get("input_per_1m", 0.0) or 0.0)
        return (total_tokens / 1_000_000.0) * rate
    
    # Support per-1K format
    if "in" in price:
        rate = float(price.get("in", 0.0) or 0.0)
        return (total_tokens / 1000.0) * rate
    
    # Default: Gemini embedding rate
    return (total_tokens / 1_000_000.0) * EMBEDDING_COST_PER_1M


async def create_embeddings(request: Request):
    """
    POST /v1/embeddings
    Proxies embedding requests to LiteLLM with auth, quota enforcement, and cost tracking.
    """
    # ── Auth ──
    user = require_user(request)
    user_id = user["user_id"]
    
    # ── Quota reset check ──
    maybe_reset_quota(user)
    
    # ── Parse body ──
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    
    model = body.get("model", "unknown")
    rid = f"emb-{uuid.uuid4().hex[:12]}"

    # ── Init audit state ──
    init_audit_state(request, user_id=user_id, model=model, endpoint="/v1/embeddings", rid=rid)
    
    logger.info(
        "embedding_request rid=%s user=%s model=%s",
        rid, user_id, model
    )
    
    # ── Dimension reduction ──
    # Inject dimensions param so Gemini returns 1536-dim vectors
    # (fits PGVector HNSW max 2000 dims & matches existing DB schema)
    if "dimensions" not in body:
        body["dimensions"] = EMBEDDING_TARGET_DIMS
        logger.info("embedding_inject_dims rid=%s dims=%d", rid, EMBEDDING_TARGET_DIMS)
    
    # ── Forward to LiteLLM ──
    url = f"{LITELLM_BASE}/embeddings"
    headers = {
        "Authorization": f"Bearer {LITELLM_KEY}",
        "Content-Type": "application/json",
        "X-Request-ID": rid,
    }
    
    try:
        client: httpx.AsyncClient = request.app.state.http_client
        resp = await client.post(url, json=body, headers=headers, timeout=60.0)
    except httpx.TimeoutException:
        set_error_state(request, "timeout", "LiteLLM embedding timeout")
        raise HTTPException(504, "Embedding request timeout")
    except Exception as e:
        set_error_state(request, "connection", str(e))
        raise HTTPException(502, f"LiteLLM connection error: {e}")
    
    if resp.status_code != 200:
        error_text = resp.text[:500]
        logger.warning(
            "embedding_error rid=%s status=%s error=%s",
            rid, resp.status_code, error_text
        )
        set_error_state(request, "upstream", error_text)
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    
    # ── Parse response ──
    result = resp.json()
    usage = result.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0) or usage.get("total_tokens", 0)
    total_tokens = usage.get("total_tokens", prompt_tokens)
    
    # ── Cost calculation ──
    # Try LiteLLM header first
    cost_usd = get_cost_from_headers(resp.headers)
    if cost_usd <= 0:
        prices = load_prices()
        cost_usd = _calc_embedding_cost(model, total_tokens, prices)
    
    # ── Update user quota ── O(1) atomic update
    update_user_quota(
        user_id,
        add_tokens=total_tokens,
        add_cost_usd=cost_usd,
    )
    
    # ── Audit ──
    set_usage_state(
        request,
        tokens_in=total_tokens,
        tokens_out=0,
        tokens_total=total_tokens,
        cost_usd=cost_usd,
    )
    
    logger.info(
        "embedding_done rid=%s user=%s model=%s tokens=%d cost=%.6f",
        rid, user_id, model, total_tokens, cost_usd
    )
    
    return JSONResponse(content=result)
