"""Market domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Tick:
    symbol: str
    epoch: int
    price: float


@dataclass
class Candle:
    symbol: str
    timeframe_sec: int
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


@dataclass
class Indicators:
    ema_fast: Optional[float] = None
    ema_slow: Optional[float] = None
    atr: Optional[float] = None
    rsi: Optional[float] = None

