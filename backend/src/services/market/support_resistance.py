"""Soportes y resistencias: niveles desde velas recientes y filtro para entradas (CALL cerca de soporte, PUT cerca de resistencia)."""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from src.models.market_models import Candle


def compute_levels(recent_candles: List[Any], min_candles: int = 2) -> Tuple[Optional[float], Optional[float]]:
    """
    Calcula soporte (mínimo de mínimos) y resistencia (máximo de máximos) de las velas recientes.
    Returns (support, resistance). Si hay menos de min_candles, retorna (None, None).
    """
    if not recent_candles or len(recent_candles) < min_candles:
        return (None, None)
    lows = [float(getattr(c, "low", 0)) for c in recent_candles if getattr(c, "low", None) is not None]
    highs = [float(getattr(c, "high", 0)) for c in recent_candles if getattr(c, "high", None) is not None]
    if not lows or not highs:
        return (None, None)
    support = min(lows)
    resistance = max(highs)
    return (support, resistance)


def passes_sr_filter(
    side: str,
    close_price: float,
    support: Optional[float],
    resistance: Optional[float],
    near_pct: float,
    min_candles_met: bool,
) -> bool:
    """
    True si la señal pasa el filtro S/R: CALL solo cuando el precio está cerca de un soporte,
    PUT solo cuando está cerca de una resistencia.
    Si no hay niveles suficientes (min_candles_met=False), retorna True para no bloquear.
    """
    if not min_candles_met or close_price <= 0:
        return True
    if support is None and resistance is None:
        return True

    ref = max(close_price, 1e-9)

    if side == "CALL":
        if support is None:
            return True
        dist_pct = abs(close_price - support) / ref
        return dist_pct <= near_pct

    if side == "PUT":
        if resistance is None:
            return True
        dist_pct = abs(close_price - resistance) / ref
        return dist_pct <= near_pct

    return True
