"""
Provider attribution (Phase 6 — change dashboard-provider-budget).

Maps each LLM model alias to the BILLING ACCOUNT actually invoiced (the account a
top-up is paid into), and sums prepaid spend per account. Used by BOTH the Providers
dashboard endpoint (api/providers.py) and the per-provider budget alert
(core/alerting.py CHECK 2) so the two never report different numbers.

Source of the map is LiteLLM's admin /model/info endpoint, reachable with the master
key the middleware already holds (LITELLM_KEY). We do NOT read litellm_config.yaml —
that file is mounted only into the litellm container, not this one (see design D1).

The map is a TOTAL partition: any model not in the map (a retired alias still in the
audit history, a name drift) falls into OTHER_ACCOUNT, so the sum of spend across all
accounts always equals total cost for the same window (design D2). This is a
production-logic guarantee, not a dev-data assumption.
"""

import time
import datetime as dt
from typing import Dict, Optional

import httpx

from config import LITELLM_BASE, LITELLM_KEY, logger

# Catch-all bucket for any model that does not resolve to a known billing account.
OTHER_ACCOUNT = "other"

# The map rarely changes (only when models are deployed/removed); cache it so we do not
# hit LiteLLM on every request or alert check.
_MAP_TTL_SECONDS = 300
_map_cache: Dict[str, object] = {"ts": 0.0, "map": {}}


def build_model_provider_map(force: bool = False) -> Dict[str, str]:
    """Return ``{alias -> billing_account}`` from LiteLLM ``/model/info``.

    The billing account is the first path segment of ``litellm_params.model``
    (e.g. ``openrouter/deepseek/deepseek-v4-flash`` -> ``openrouter``). Cached with a
    short TTL. On any failure returns the last good map (or ``{}``) instead of raising —
    callers then bucket everything into ``other`` without crashing (design D1).
    """
    now = time.time()
    cached_map: Dict[str, str] = _map_cache["map"]  # type: ignore[assignment]
    if not force and cached_map and (now - float(_map_cache["ts"])) < _MAP_TTL_SECONDS:
        return cached_map

    try:
        base = LITELLM_BASE.rstrip("/")
        resp = httpx.get(
            f"{base}/model/info",
            headers={"Authorization": f"Bearer {LITELLM_KEY}"},
            timeout=5.0,
        )
        resp.raise_for_status()
        payload = resp.json() or {}
        rows = payload.get("data") or payload.get("model_list") or []
        mapping: Dict[str, str] = {}
        for m in rows:
            if not isinstance(m, dict):
                continue
            name = m.get("model_name")
            params = m.get("litellm_params") or {}
            real = params.get("model") or ""
            if name and "/" in real:
                mapping[name] = real.split("/", 1)[0]
        if mapping:
            _map_cache["ts"] = now
            _map_cache["map"] = mapping
            return mapping
        # Empty/unexpected payload: keep last good map rather than wiping attribution.
        return cached_map
    except Exception as e:
        logger.warning("provider_attribution: /model/info failed: %s", e)
        return cached_map


def resolve_account(model: Optional[str], mapping: Optional[Dict[str, str]] = None) -> str:
    """Resolve a single audit ``model`` alias to its billing account (or ``other``)."""
    if mapping is None:
        mapping = build_model_provider_map()
    if not model:
        return OTHER_ACCOUNT
    return mapping.get(model, OTHER_ACCOUNT)


def _parse_funded_at(value) -> Optional[dt.datetime]:
    """Parse an ISO ``funded_at`` string into an aware UTC datetime; None if unusable."""
    if not value:
        return None
    if isinstance(value, dt.datetime):
        d = value
    else:
        try:
            d = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d


def spend_since_funding(funded_at_by_account: Dict[str, dt.datetime]) -> Dict[str, float]:
    """Prepaid spend per billing account, each measured since its own ``funded_at``.

    ``funded_at_by_account`` maps configured accounts to an aware datetime. Rows whose
    account has a funding time are counted only when ``ts >= funded_at``; rows resolving
    to an account without a funding time (``other`` / unconfigured) are all counted.
    Returns ``{account: usd}`` including ``other`` when present. Empty ``{}`` if the DB
    is unavailable (never raises).
    """
    try:
        from core.db import db_conn, _pool
        if _pool is None:
            return {}

        # Only scan from the earliest funding point among configured accounts; older
        # rows belong to previous funding periods and are never counted.
        funded_times = [v for v in funded_at_by_account.values() if v is not None]
        lower_bound = min(funded_times) if funded_times else None

        mapping = build_model_provider_map()
        result: Dict[str, float] = {}

        with db_conn() as conn:
            cur = conn.cursor()
            if lower_bound is not None:
                cur.execute(
                    "SELECT model, ts, cost_usd FROM mw_audit_log WHERE ts >= %s",
                    (lower_bound,),
                )
            else:
                cur.execute("SELECT model, ts, cost_usd FROM mw_audit_log")
            for model, ts, cost in cur.fetchall():
                account = resolve_account(model, mapping)
                fa = funded_at_by_account.get(account)
                if fa is not None and ts is not None and ts < fa:
                    continue  # before this account's current funding — skip
                result[account] = result.get(account, 0.0) + float(cost or 0.0)
            cur.close()
        return result
    except Exception:
        logger.error("provider_attribution: spend_since_funding failed", exc_info=True)
        return {}


def spend_by_account_uniform(start: dt.datetime, end: dt.datetime) -> Dict[str, float]:
    """Attribution over a single uniform window ``[start, end]`` — every row to its
    account (including ``other``). Used to verify the map is a total partition:
    ``sum(result.values())`` equals total cost over the same window. Empty ``{}`` if DB
    unavailable.
    """
    try:
        from core.db import db_conn, _pool
        if _pool is None:
            return {}
        mapping = build_model_provider_map()
        result: Dict[str, float] = {}
        with db_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT model, cost_usd FROM mw_audit_log WHERE ts >= %s AND ts <= %s",
                (start, end),
            )
            for model, cost in cur.fetchall():
                account = resolve_account(model, mapping)
                result[account] = result.get(account, 0.0) + float(cost or 0.0)
            cur.close()
        return result
    except Exception:
        logger.error("provider_attribution: spend_by_account_uniform failed", exc_info=True)
        return {}
