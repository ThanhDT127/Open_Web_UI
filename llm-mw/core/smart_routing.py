"""
Smart Routing v2 — Complexity-based model tier selection + thinking injection.

Maps "auto" model names (e.g. openai-auto) to concrete model names
based on request complexity scoring. Integrates with quota-based downgrade.
v2: Adds thinking/reasoning parameter injection per provider and
LLM-assisted classification for ambiguous requests.
"""

import re
import httpx
import json
from config import logger, LITELLM_BASE, LITELLM_KEY

# ── Provider tier mappings ──────────────────────────────────────
# Each provider maps: tier → concrete LiteLLM model alias
# Tiers: SIMPLE (cheapest), MEDIUM, COMPLEX, REASONING (most capable)

PROVIDER_TIERS = {
    "openai-auto": {
        "SIMPLE": "chat-gpt-5",
        "MEDIUM": "chat-gpt-5.2",
        "COMPLEX": "chat-gpt-5.4",
        "REASONING": "chat-gpt-5.4",
    },
    "gemini-auto": {
        "SIMPLE": "chat-gemini-2.5-flash",
        "MEDIUM": "chat-gemini-3.1-flash-lite",
        "COMPLEX": "chat-gemini-3.1-pro",
        "REASONING": "chat-gemini-3.1-pro",
    },
    "grok-auto": {
        "SIMPLE": "chat-grok-4.1-fast-lite",
        "MEDIUM": "chat-grok-4.1-fast",
        "COMPLEX": "chat-grok-4.20",
        "REASONING": "chat-grok-4.20",
    },
    "claude-auto": {
        "SIMPLE": "chat-claude-haiku-4.5",
        "MEDIUM": "chat-claude-sonnet-4.6",
        "COMPLEX": "chat-claude-opus-4.6",
        "REASONING": "chat-claude-opus-4.6",
    },
    "deepseek-auto": {
        "SIMPLE": "chat-deepseek-v4-flash",
        "MEDIUM": "chat-deepseek-v4-flash",
        "COMPLEX": "chat-deepseek-v4-pro",
        "REASONING": "chat-deepseek-v4-pro",
    },
}

# ── Provider thinking/reasoning parameters per tier ──────────────
# Keep auto-routing compatible by default. Direct provider params for OpenAI,
# Gemini, and Claude currently fail through the LiteLLM chat-completions path
# used by this middleware, while direct model aliases work without them.
# Reasoning depth is therefore controlled by tier -> model selection here.
PROVIDER_THINKING = {}

# ── Complexity keywords (Vietnamese + English) ──────────────────
_BOOST_KEYWORDS = re.compile(
    r"(?i)\b("
    r"phân tích|so sánh|đánh giá|giải thích chi tiết|chứng minh|tóm tắt dài|"
    r"viết báo cáo|thiết kế|kiến trúc|tối ưu|debug|refactor|"
    r"analyze|compare|evaluate|explain in detail|prove|summarize|"
    r"write a report|design|architect|optimize|step by step|"
    r"code review|implement|algorithm|complexity"
    r")\b"
)

_REASONING_KEYWORDS = re.compile(
    r"(?i)\b("
    r"chứng minh rằng|tại sao|why does|prove that|"
    r"step by step reasoning|chain of thought|think carefully|"
    r"mathematical proof|logical deduction"
    r")\b"
)

# Quota downgrade threshold
QUOTA_DOWNGRADE_PERCENT = 60


def is_auto_model(model: str) -> bool:
    """Check if model is an auto-routing model name."""
    return isinstance(model, str) and model in PROVIDER_TIERS


def _extract_last_user_text(messages: list) -> str:
    """Extract text from the last user message."""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                return " ".join(
                    item.get("text", "") for item in content
                    if isinstance(item, dict) and item.get("type") == "text"
                )
    return ""


def score_complexity(messages: list, has_vision: bool = False, has_files: bool = False) -> tuple[str, int]:
    """
    Score request complexity and return tier name + raw score.

    Returns: (tier_name, raw_score)
        - tier_name: "SIMPLE", "MEDIUM", "COMPLEX", or "REASONING"
        - raw_score: integer score for classifier gating (3-7 = ambiguous)
    """
    score = 0

    if not isinstance(messages, list):
        return "SIMPLE", 0

    # --- Conversation depth ---
    user_messages = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
    num_turns = len(user_messages)

    if num_turns >= 6:
        score += 3
    elif num_turns >= 3:
        score += 1

    # --- Last message length ---
    last_text = _extract_last_user_text(messages)

    char_count = len(last_text)
    if char_count > 2000:
        score += 3
    elif char_count > 500:
        score += 2
    elif char_count > 100:
        score += 1

    # --- Total conversation token estimate ---
    total_chars = sum(
        len(m.get("content", "")) if isinstance(m.get("content"), str) else 0
        for m in messages if isinstance(m, dict)
    )
    if total_chars > 10000:
        score += 2
    elif total_chars > 3000:
        score += 1

    # --- Keyword boost ---
    boost_hits = len(_BOOST_KEYWORDS.findall(last_text))
    score += min(boost_hits, 3)  # Cap at +3

    # --- Reasoning detection (force tier) ---
    if _REASONING_KEYWORDS.search(last_text):
        return "REASONING", score + 10  # High score to signal clear case

    # --- Vision/file boost ---
    if has_vision:
        score += 2
    if has_files:
        score += 1

    # --- Map score to tier ---
    if score >= 6:
        return "COMPLEX", score
    elif score >= 3:
        return "MEDIUM", score
    else:
        return "SIMPLE", score


# ── LLM Classifier ──────────────────────────────────────────────
_CLASSIFIER_PROMPT = """Classify this user request complexity. Reply with exactly one word: SIMPLE, MEDIUM, COMPLEX, or REASONING.

SIMPLE: casual chat, greeting, short factual question, translation
MEDIUM: explanation, comparison, moderate analysis, summarization
COMPLEX: deep analysis, system design, coding, multi-step problem, debugging
REASONING: mathematical proof, formal logic, step-by-step derivation

User request: {prompt}"""

_VALID_TIERS = {"SIMPLE", "MEDIUM", "COMPLEX", "REASONING"}


async def classify_with_llm(prompt_preview: str) -> str | None:
    """
    Use a cheap LLM (Gemini 2.5 Flash) to classify request complexity.
    Returns tier string or None on failure.
    Timeout: 2 seconds.
    """
    if not prompt_preview or len(prompt_preview) < 5:
        return None

    # Truncate to ~500 chars to keep classifier fast
    truncated = prompt_preview[:500]
    classify_body = {
        "model": "chat-gemini-2.5-flash",
        "messages": [
            {"role": "user", "content": _CLASSIFIER_PROMPT.format(prompt=truncated)}
        ],
        "max_tokens": 10,
        "temperature": 0,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{LITELLM_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {LITELLM_KEY}", "Content-Type": "application/json"},
                json=classify_body,
            )
            if resp.status_code != 200:
                logger.warning("classifier_error status=%d", resp.status_code)
                return None

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip().upper()
            # Extract first valid tier word
            for word in content.split():
                if word in _VALID_TIERS:
                    logger.info("classifier_result tier=%s raw=%s", word, content[:30])
                    return word
            logger.warning("classifier_invalid response=%s", content[:50])
            return None
    except Exception as e:
        logger.warning("classifier_fail error=%s", str(e)[:100])
        return None


async def resolve_auto_model(
    model: str,
    messages: list,
    quota_percent: float,
    has_vision: bool = False,
    has_files: bool = False
) -> tuple[str, str, bool, dict]:
    """
    Resolve an auto-model name to a concrete model + thinking config.

    Args:
        model: Auto model name (e.g. "openai-auto")
        messages: Chat messages for complexity scoring
        quota_percent: User's quota usage percentage (0-100+)
        has_vision: Whether request contains vision/image content
        has_files: Whether request contains file attachments

    Returns:
        Tuple of (resolved_model, tier, was_downgraded, thinking_params)
        - resolved_model: concrete model name
        - tier: tier that was selected
        - was_downgraded: True if forced to SIMPLE due to quota
        - thinking_params: dict of provider-specific thinking/reasoning params
    """
    tiers = PROVIDER_TIERS.get(model)
    if not tiers:
        return model, "UNKNOWN", False, {}

    was_downgraded = False
    classifier_used = False

    # Quota-based downgrade: >=60% → force SIMPLE
    if quota_percent >= QUOTA_DOWNGRADE_PERCENT:
        tier = "SIMPLE"
        was_downgraded = True
    else:
        tier, raw_score = score_complexity(messages, has_vision, has_files)

        # LLM classifier for ambiguous cases (score 3-7)
        if 3 <= raw_score <= 7:
            prompt_text = _extract_last_user_text(messages)
            llm_tier = await classify_with_llm(prompt_text)
            if llm_tier:
                tier = llm_tier
                classifier_used = True
                logger.info("classifier_override heuristic=%s llm=%s score=%d", tier, llm_tier, raw_score)

    resolved = tiers.get(tier, tiers.get("SIMPLE", model))

    # Get thinking params for this provider + tier
    thinking_params = {}
    provider_thinking = PROVIDER_THINKING.get(model)
    if provider_thinking:
        thinking_params = provider_thinking.get(tier, {})

    logger.info(
        "smart_route model=%s tier=%s resolved=%s quota=%.0f%% downgraded=%s classifier=%s thinking=%s",
        model, tier, resolved, quota_percent, was_downgraded, classifier_used,
        json.dumps(thinking_params) if thinking_params else "none",
    )

    return resolved, tier, was_downgraded, thinking_params
