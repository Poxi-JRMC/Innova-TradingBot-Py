"""Obtener historial de ticks desde Deriv y convertirlo en velas 1m para backtest."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.infrastructure.logging.logging import get_logger
from src.models.market_models import Candle

log = get_logger("deriv_history")


def _floor_epoch(epoch: int, timeframe_sec: int = 60) -> int:
    return epoch - (epoch % timeframe_sec)


def ticks_to_candles(
    symbol: str,
    times: List[int],
    prices: List[float],
    timeframe_sec: int = 60,
) -> List[Candle]:
    """
    Agrupa ticks por ventana temporal y construye velas OHLC.
    times y prices deben estar alineados por índice (mismo orden).
    """
    if not times or not prices or len(times) != len(prices):
        return []

    # Ordenar por tiempo (por si la API no viene ordenada)
    pairs = sorted(zip(times, prices), key=lambda x: x[0])
    buckets: Dict[int, List[float]] = defaultdict(list)
    for epoch, price in pairs:
        bucket = _floor_epoch(epoch, timeframe_sec)
        buckets[bucket].append(price)

    candles: List[Candle] = []
    for open_epoch in sorted(buckets.keys()):
        vals = buckets[open_epoch]
        if not vals:
            continue
        open_time = datetime.fromtimestamp(open_epoch, tz=timezone.utc)
        candles.append(
            Candle(
                symbol=symbol,
                timeframe_sec=timeframe_sec,
                open_time=open_time,
                open=vals[0],
                high=max(vals),
                low=min(vals),
                close=vals[-1],
                volume=len(vals),
            )
        )
    return candles


async def fetch_ticks_history(
    client: Any,
    symbol: str,
    count: int = 5000,
    end: Optional[int] = None,
) -> List[Candle]:
    """
    Llama a la API Deriv ticks_history (subscribe=0), parsea la respuesta
    y devuelve velas 1m. client debe tener método request(payload) -> response.
    """
    # API Deriv (app 1089): rechaza "subscribe", "count" y "end" en algunos contextos.
    # Probamos sin subscribe y sin count; solo end + style para ticks_history. Para "ticks" solo symbol.
    end_val = "latest" if end is None else end
    resp: Optional[Dict[str, Any]] = None

    for attempt, (use_ticks_key, pl) in enumerate([
        (False, {"ticks_history": symbol, "end": end_val, "style": "candles", "granularity": 60}),
        (False, {"ticks_history": symbol, "end": end_val, "style": "ticks"}),
        (True, {"ticks": symbol, "subscribe": 0}),
    ]):
        try:
            resp = await client.request(pl)
        except Exception as e:
            log.debug("fetch_attempt_failed", attempt=attempt, symbol=symbol, error=str(e))
            continue
        if resp.get("error"):
            msg = resp.get("error", {}).get("message", "")
            log.debug("fetch_attempt_error", attempt=attempt, symbol=symbol, error=msg)
            continue
        if use_ticks_key and resp.get("history"):
            break
        if not use_ticks_key and (resp.get("candles") or resp.get("history")):
            break
    else:
        msg = (resp or {}).get("error", {}).get("message", "No data after all attempts") if resp else "No response"
        log.error("ticks_history_error", symbol=symbol, error=msg)
        raise RuntimeError(f"Deriv ticks_history error: {msg}")

    # Respuesta tipo candles (style candles)
    if resp.get("candles"):
        candles_raw = resp.get("candles") or []
        candles = []
        for c in candles_raw:
            if isinstance(c, dict):
                ep = c.get("epoch")
                if ep is None:
                    continue
                open_time = datetime.fromtimestamp(int(ep), tz=timezone.utc)
                candles.append(
                    Candle(
                        symbol=symbol,
                        timeframe_sec=60,
                        open_time=open_time,
                        open=float(c.get("open", 0)),
                        high=float(c.get("high", 0)),
                        low=float(c.get("low", 0)),
                        close=float(c.get("close", 0)),
                        volume=0,
                    )
                )
        if candles:
            log.info("ticks_history_loaded", symbol=symbol, style="candles", candles=len(candles))
            return candles

    # Respuesta tipo history (prices / times)
    history = resp.get("history") or {}
    prices_raw = history.get("prices") or []
    times_raw = history.get("times") or []
    times = [int(t) for t in times_raw]
    prices = [float(p) for p in prices_raw]
    if len(times) != len(prices):
        n = min(len(times), len(prices))
        times, prices = times[:n], prices[:n]
    candles = ticks_to_candles(symbol, times, prices, timeframe_sec=60)
    log.info("ticks_history_loaded", symbol=symbol, ticks=len(times), candles=len(candles))
    return candles
