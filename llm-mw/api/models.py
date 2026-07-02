"""
Models endpoint for listing available LLM models.
"""

from fastapi import Request
import httpx

from config import LITELLM_BASE, LITELLM_KEY, RESTRICTED_MODELS
from core.auth import require_user
from core.smart_routing import PROVIDER_TIERS
from utils.helpers import env_truthy
from utils.logging import detail_log

# Display names for auto-routing models
_AUTO_MODEL_NAMES = {
    "openai-auto": "ChatGPT (Auto)",
    "gemini-auto": "Gemini (Auto)",
    "grok-auto": "Grok (Auto)",
    "claude-auto": "Claude (Auto)",
    "deepseek-auto": "DeepSeek (Auto)",
}


async def list_models(request: Request):
    """
    List available models from LiteLLM.
    Filters out restricted models unless MW_EXPOSE_RESTRICTED_MODELS is enabled.
    Injects virtual auto-routing models for eligible users.
    """
    user = require_user(request)
    
    try:
        client: httpx.AsyncClient = request.app.state.http_client
        detail_log(
            "models.request",
            request=request,
            user_id=user.get("user_id"),
        )
        resp = await client.get(
            f"{LITELLM_BASE}/models",
            headers={"Authorization": f"Bearer {LITELLM_KEY}"},
            timeout=10,
        )
        if resp.status_code == 200:
            payload = resp.json() or {}
            data = payload.get("data")
            if isinstance(data, list):
                # Get user's allowed models
                from config import DEFAULT_ALLOWED_MODELS
                allowed_models = user.get("allowed_models") or DEFAULT_ALLOWED_MODELS
                allow_all = allowed_models == ["*"]
                
                filtered = []
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    mid = item.get("id") or item.get("model") or item.get("name")
                    
                    # Filter restricted models
                    if not env_truthy("MW_EXPOSE_RESTRICTED_MODELS", default=False):
                        if isinstance(mid, str) and mid in RESTRICTED_MODELS:
                            continue
                    
                    # Filter by user's allowed_models
                    if not allow_all and isinstance(mid, str):
                        if mid not in allowed_models:
                            continue
                    
                    filtered.append(item)

                # Inject auto-routing virtual models
                # Collect IDs of raw models in LiteLLM for tier eligibility check
                raw_ids = {
                    item.get("id") or item.get("model") or item.get("name")
                    for item in data if isinstance(item, dict)
                }
                for auto_name, tiers in PROVIDER_TIERS.items():
                    # User can use auto model if they have access to any tier model or if the auto model itself is explicitly allowed
                    tier_models = set(tiers.values())
                    if allow_all or auto_name in allowed_models or any(m in allowed_models for m in tier_models):
                        # Only add if at least one tier model exists in LiteLLM
                        if tier_models & raw_ids:
                            filtered.insert(0, {
                                "id": auto_name,
                                "object": "model",
                                "created": 1677610602,
                                "owned_by": "smart-routing",
                                "name": _AUTO_MODEL_NAMES.get(auto_name, auto_name),
                            })

                payload["data"] = filtered
            return payload
        return {"data": []}
    except Exception:
        # Fallback to empty list if LiteLLM is down
        return {"data": []}
