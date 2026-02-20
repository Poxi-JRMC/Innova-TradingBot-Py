"""In-memory metrics snapshot for the API + console."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class MetricsSnapshot:
    connected: bool = False
    symbol: str = ""
    last_tick_price: Optional[float] = None
    candles_closed: int = 0
    ema_fast: Optional[float] = None
    ema_slow: Optional[float] = None
    atr: Optional[float] = None
    rsi: Optional[float] = None
    balance: Optional[float] = None

