"""Resolve allowed multiplier values from Deriv API (contracts_for) and pick the best one for the symbol."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.infrastructure.deriv.deriv_ws_client import DerivWSClient
from src.infrastructure.logging.logging import get_logger

log = get_logger("multiplier_resolver")
JsonDict = Dict[str, Any]

CACHE_PATH = Path("data/deriv_multiplier_cache.json")


async def get_allowed_multipliers(
    client: DerivWSClient,
    symbol: str,
    currency: str = "USD",
) -> List[int]:
    """
    Call Deriv contracts_for for the symbol and return the list of allowed multiplier values.
    Returns empty list on error or if not found (caller should fallback to config).
    """
    try:
        req: JsonDict = {
            "contracts_for": symbol,
            "currency": currency,
            "landing_company": "svg",
            "product_type": "basic",
        }
        resp = await client.request(req)
        if resp.get("error"):
            log.warning("contracts_for_error", symbol=symbol, error=resp.get("error"))
            return []

        cf = resp.get("contracts_for")
        if not isinstance(cf, dict):
            return []

        # Top-level multipliers (some API versions)
        multipliers = cf.get("multipliers")
        if isinstance(multipliers, list) and multipliers:
            out = _parse_multiplier_list(multipliers)
            if out:
                return sorted(set(out))
        # Top-level multiplier_range
        mr = cf.get("multiplier_range")
        if isinstance(mr, dict):
            out = _range_to_list(mr)
            if out:
                return out

        # From available contracts (MULTUP / MULTDOWN)
        available = cf.get("available") or []
        for contract in available:
            if not isinstance(contract, dict):
                continue
            ct = contract.get("contract_type") or ""
            if ct not in ("MULTUP", "MULTDOWN"):
                continue
            # Try "multipliers" (list) or "multiplier" (some APIs)
            for key in ("multipliers", "multiplier"):
                multipliers = contract.get(key)
                if isinstance(multipliers, list) and multipliers:
                    out = _parse_multiplier_list(multipliers)
                    if out:
                        return sorted(set(out))
            # Some APIs return multiplier_range: { min, max }
            mr = contract.get("multiplier_range")
            if isinstance(mr, dict):
                out = _range_to_list(mr)
                if out:
                    return out

        # Debug: log structure when we get nothing so we can see what Deriv returns
        if available:
            multi_contract = next(
                (c for c in available if isinstance(c, dict) and c.get("contract_type") in ("MULTUP", "MULTDOWN")),
                None,
            )
            if multi_contract:
                raw_mul = multi_contract.get("multipliers") or multi_contract.get("multiplier")
                log.info(
                    "contracts_for_multiplier_keys",
                    symbol=symbol,
                    keys=list(multi_contract.keys()),
                    raw_multipliers_sample=str(raw_mul)[:400] if raw_mul is not None else None,
                )
        else:
            log.info("contracts_for_no_available", symbol=symbol, cf_keys=list(cf.keys()) if cf else [])

        # Fallback: Volatility indices (R_10, R_25, R_50, R_75, R_100) suelen tener 50, 100, 200, 300, 500 (no 10)
        if symbol and symbol.startswith("R_") and symbol not in ("R_CRASH_500", "R_BOOM_500", "R_CRASH_1000", "R_BOOM_1000"):
            fallback = [50, 100, 200, 300, 500]
            log.info("multiplier_using_fallback", symbol=symbol, allowed=fallback)
            return fallback

        return []
    except Exception as e:
        log.warning("get_allowed_multipliers_failed", symbol=symbol, error=str(e))
        return []


def _parse_multiplier_list(multipliers: list) -> List[int]:
    out = []
    for m in multipliers:
        if isinstance(m, (int, float)):
            out.append(int(m))
        elif isinstance(m, str) and m.isdigit():
            out.append(int(m))
        elif isinstance(m, dict):
            v = m.get("value") or m.get("display_value")
            if v is not None:
                try:
                    out.append(int(v))
                except (TypeError, ValueError):
                    pass
    return out


def _range_to_list(mr: Dict[str, Any]) -> List[int]:
    lo = mr.get("min")
    hi = mr.get("max")
    if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)):
        return []
    lo, hi = int(lo), int(hi)
    common = [1, 2, 5, 10, 20, 40, 50, 100, 200, 400, 500, 1000, 2000]
    out = [x for x in common if lo <= x <= hi]
    if out:
        return out
    step = max(1, (hi - lo) // 10)
    return list(range(lo, hi + 1, step))


def pick_best_multiplier(
    allowed: List[int],
    preferred: int,
    *,
    prefer_moderate: bool = True,
) -> int:
    """
    Pick the best multiplier from the allowed list.
    - If preferred is in allowed, use it.
    - Else use the closest allowed value; if prefer_moderate, avoid the very high end (e.g. 1000, 2000)
      so TP is more reachable.
    """
    if not allowed:
        return max(1, preferred)

    if preferred in allowed:
        return preferred

    # Prefer a "moderate" multiplier so TP can be reached (user asked for option that can reach TP and win)
    if prefer_moderate and len(allowed) > 1:
        # Exclude top 25% (very high leverage) when choosing fallback
        cap_idx = max(0, len(allowed) - 1 - max(1, len(allowed) // 4))
        moderate = allowed[: cap_idx + 1]
        if moderate:
            # Closest to preferred within moderate range
            best = min(moderate, key=lambda x: abs(x - preferred))
            return best

    return min(allowed, key=lambda x: abs(x - preferred))


async def fetch_and_cache_multipliers(
    client: DerivWSClient,
    symbol: str,
    currency: str,
    preferred: int,
) -> Dict[str, Any]:
    """
    Call Deriv, get allowed multipliers for one symbol, pick best, write to cache file.
    Returns { "allowed": [...], "resolved": int, "symbol": str } for API/frontend.
    """
    allowed = await get_allowed_multipliers(client, symbol, currency)
    resolved = pick_best_multiplier(allowed, preferred, prefer_moderate=True) if allowed else preferred
    payload = {
        "symbol": symbol,
        "allowed": allowed,
        "resolved": resolved,
    }
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        log.info("multiplier_cache_written", symbol=symbol, allowed=allowed[:15] if allowed else [], resolved=resolved)
    except Exception as e:
        log.warning("multiplier_cache_write_failed", path=str(CACHE_PATH), error=str(e))
    return payload


async def fetch_and_cache_multipliers_all(
    client: DerivWSClient,
    symbols: List[str],
    currency: str,
    preferred: int,
) -> Dict[str, Any]:
    """
    Fetch allowed multipliers from Deriv for each symbol (R_50, R_75, R_100, etc. have different allowed values).
    Write cache as { "symbols": { "R_50": { "allowed": [...], "resolved": int }, ... } } so UI and execution use per-market lever.
    """
    result: Dict[str, Any] = {"symbols": {}}
    for symbol in symbols:
        allowed = await get_allowed_multipliers(client, symbol, currency)
        resolved = pick_best_multiplier(allowed, preferred, prefer_moderate=True) if allowed else preferred
        result["symbols"][symbol] = {"allowed": allowed, "resolved": resolved}
        log.info(
            "multiplier_per_market",
            symbol=symbol,
            allowed=allowed[:12] if allowed else [],
            resolved=resolved,
        )
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    except Exception as e:
        log.warning("multiplier_cache_write_failed", path=str(CACHE_PATH), error=str(e))
    return result


def read_multiplier_cache() -> Optional[Dict[str, Any]]:
    """Read cached multiplier data (written by engine). Supports per-symbol format and legacy single-symbol format."""
    if not CACHE_PATH.exists():
        return None
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        # New format: { "symbols": { "R_50": { "allowed": [...], "resolved": 50 }, ... } }
        if "symbols" in data and isinstance(data["symbols"], dict):
            return data
        # Legacy: { "symbol": "R_75", "allowed": [...], "resolved": 10 }
        if "resolved" in data:
            return data
    except Exception:
        pass
    return None
