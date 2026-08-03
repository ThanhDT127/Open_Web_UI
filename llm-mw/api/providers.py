"""
Providers endpoint (Phase 6 — change dashboard-provider-budget).

Prepaid credit view per BILLING ACCOUNT: how much was funded, how much has been spent
since the last top-up, how much is left, and roughly how many days until it runs out.
Not scoped by the dashboard time-range filter — it always reports current credit state
(design D7). Attribution + spend come from core.provider_attribution, shared with the
per-provider budget alert (CHECK 2) so the two never diverge.
"""

import datetime as dt
from typing import Dict, Any, Optional, List

from fastapi import Request
from fastapi.responses import JSONResponse

from config import logger
from core.provider_attribution import (
    build_model_provider_map,
    spend_since_funding,
    _parse_funded_at,
    OTHER_ACCOUNT,
)

# Below this many days since the last top-up, a runway estimate is too noisy to trust.
MIN_DAYS_FOR_RUNWAY = 2.0


def _status_for(used_percent: Optional[float], runway_days: Optional[float],
                remaining: Optional[float], thresholds: List[int]) -> str:
    """ok / warn / critical from utilization and runway. `unknown` if no credit set."""
    if remaining is None or used_percent is None:
        return "unknown"
    warn_at = min(thresholds) if thresholds else 80
    crit_at = max(thresholds) if thresholds else 100
    if remaining <= 0 or used_percent >= crit_at or (runway_days is not None and runway_days <= 3):
        return "critical"
    if used_percent >= warn_at or (runway_days is not None and runway_days <= 7):
        return "warn"
    return "ok"


def _runway_days(remaining: float, spent: float, days_since: float) -> Optional[float]:
    """Days until credit is exhausted at the current burn rate. None when it cannot be
    estimated reliably: too little time since funding, or zero burn (would divide by
    zero / project to infinity). 0 when already exhausted (design D4)."""
    if remaining <= 0:
        return 0.0
    if days_since < MIN_DAYS_FOR_RUNWAY:
        return None
    burn = spent / days_since
    if burn <= 0:
        return None
    return remaining / burn


def compute_providers(now: dt.datetime) -> Dict[str, Any]:
    """Assemble the providers payload. Pure — no Request, no auth, no HTTP framework."""
    from core.alerting import load_alert_config

    cfg = load_alert_config()
    api_budgets = (cfg.get("admin_alerts", {}) or {}).get("api_budgets", {}) or {}

    # Configured accounts -> funding time (aware datetime).
    funded_at_by_account: Dict[str, dt.datetime] = {}
    for name, pcfg in api_budgets.items():
        fa = _parse_funded_at((pcfg or {}).get("funded_at"))
        if fa is not None:
            funded_at_by_account[name] = fa

    spend = spend_since_funding(funded_at_by_account)  # {account: usd}, incl 'other'

    providers: List[Dict[str, Any]] = []
    total_remaining = 0.0
    total_spent = 0.0

    for name, pcfg in api_budgets.items():
        pcfg = pcfg or {}
        deposited = float(pcfg.get("deposited", 0) or 0)
        thresholds = pcfg.get("thresholds", [80, 100]) or [80, 100]
        fa = funded_at_by_account.get(name)
        spent = float(spend.get(name, 0.0))
        remaining = deposited - spent
        used_percent = round(spent / deposited * 100, 1) if deposited > 0 else None
        days_since = max(0.0, (now - fa).total_seconds() / 86400.0) if fa else 0.0
        runway = _runway_days(remaining, spent, days_since) if deposited > 0 else None
        if runway is not None:
            runway = round(runway, 1)

        providers.append({
            "name": name,
            "enabled": bool(pcfg.get("enabled", True)),
            "deposited": round(deposited, 4),
            "funded_at": fa.isoformat() if fa else None,
            "spent": round(spent, 4),
            "remaining": round(remaining, 4),
            "used_percent": used_percent,
            "runway_days": runway,
            "status": _status_for(used_percent, runway, remaining, thresholds),
        })
        total_remaining += remaining
        total_spent += spent

    # Catch-all: cost attributed to accounts with no configured credit (design D2/spec).
    # Reported as spend only — no deposit, remaining, runway or status.
    other_spent = float(spend.get(OTHER_ACCOUNT, 0.0))
    if other_spent > 0:
        providers.append({
            "name": OTHER_ACCOUNT,
            "enabled": True,
            "deposited": None,
            "funded_at": None,
            "spent": round(other_spent, 4),
            "remaining": None,
            "used_percent": None,
            "runway_days": None,
            "status": "unknown",
        })
        total_spent += other_spent

    # Total models: reuse the attribution map (LiteLLM /model/info). LiteLLM has no
    # *-auto aliases (middleware injects those), so nothing is normally subtracted; the
    # _AUTO_MODEL_NAMES filter is only defensive.
    total_models: Optional[int] = None
    try:
        from api.models import _AUTO_MODEL_NAMES
        mapping = build_model_provider_map()
        if mapping:
            total_models = sum(1 for alias in mapping if alias not in _AUTO_MODEL_NAMES)
    except Exception:
        logger.warning("providers: total_models count failed", exc_info=True)

    return {
        "as_of": now.isoformat(),
        "providers": providers,
        "totals": {
            "provider_count": sum(1 for p in providers if p["name"] != OTHER_ACCOUNT),
            "total_remaining": round(total_remaining, 4),
            "total_spent": round(total_spent, 4),
        },
        "total_models": total_models,
    }


def get_providers(request: Request):
    """Admin endpoint: prepaid credit state per billing account. Mirrors get_summary_v2's
    auth. Always reports current state (not time-range scoped)."""
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    now = dt.datetime.now(tz=dt.timezone.utc)
    return compute_providers(now)


async def topup_provider(request: Request):
    """Record a prepaid top-up for one billing account (Phase 6).

    Carries the account's current unspent balance forward, adds the deposited amount to
    form the new baseline, and stamps ``funded_at = now`` so spent-since-funding restarts
    from zero (design D3). This is the "Nạp thêm" action; the "Sửa" correction goes
    through the existing deep-merge alert-config endpoint (which preserves ``funded_at``).
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)

    from core.alerting import load_alert_config, save_alert_config

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    account = (body.get("account") or "").strip()
    try:
        amount = float(body.get("amount"))
    except (TypeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "amount must be a number"})
    if not account:
        return JSONResponse(status_code=400, content={"error": "account required"})
    if amount <= 0:
        return JSONResponse(status_code=400, content={"error": "amount must be > 0"})

    cfg = load_alert_config()
    api_budgets = (cfg.get("admin_alerts", {}) or {}).get("api_budgets", {}) or {}
    pcfg = api_budgets.get(account)
    if pcfg is None:
        return JSONResponse(status_code=404, content={"error": f"unknown account: {account}"})

    # Current remaining = deposited - spent since the previous funding.
    fa = _parse_funded_at(pcfg.get("funded_at"))
    spent = 0.0
    if fa is not None:
        spent = float(spend_since_funding({account: fa}).get(account, 0.0))
    deposited = float(pcfg.get("deposited", 0) or 0)
    remaining = max(0.0, deposited - spent)

    now = dt.datetime.now(tz=dt.timezone.utc)
    pcfg["deposited"] = round(remaining + amount, 6)
    pcfg["funded_at"] = now.isoformat()
    api_budgets[account] = pcfg
    cfg.setdefault("admin_alerts", {})["api_budgets"] = api_budgets
    save_alert_config(cfg)

    logger.info("provider_topup account=%s amount=$%.2f new_deposited=$%.2f",
                account, amount, pcfg["deposited"])
    return {"ok": True, "account": account,
            "deposited": pcfg["deposited"], "funded_at": pcfg["funded_at"]}
