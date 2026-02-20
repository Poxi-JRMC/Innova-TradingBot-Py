"""Incremental indicators (EMA, ATR, RSI) with warm-up handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.models.market_models import Candle, Indicators


def _ema(prev: Optional[float], value: float, period: int) -> float:
    alpha = 2.0 / (period + 1.0)
    return value if prev is None else (alpha * value + (1 - alpha) * prev)


@dataclass
class IndicatorEngine:
    ema_fast_period: int = 20
    ema_slow_period: int = 50
    atr_period: int = 14
    rsi_period: int = 14

    _bars: int = 0
    _ema_fast: Optional[float] = None
    _ema_slow: Optional[float] = None
    _prev_close: Optional[float] = None
    _atr: Optional[float] = None
    _avg_gain: Optional[float] = None
    _avg_loss: Optional[float] = None

    def _validate_periods(self) -> None:
        if self.ema_fast_period <= 1:
            raise ValueError("ema_fast_period must be > 1")
        if self.ema_slow_period <= 1:
            raise ValueError("ema_slow_period must be > 1")
        if self.atr_period <= 1:
            raise ValueError("atr_period must be > 1")
        if self.rsi_period <= 1:
            raise ValueError("rsi_period must be > 1")

    def is_ready(self) -> bool:
        """True when indicators are reasonably stable (warm-up complete)."""
        warmup = max(self.ema_slow_period, self.atr_period, self.rsi_period)
        return self._bars >= warmup

    def update(self, candle: Candle) -> Indicators:
        self._validate_periods()
        self._bars += 1

        close = float(candle.close)

        # EMA
        self._ema_fast = _ema(self._ema_fast, close, self.ema_fast_period)
        self._ema_slow = _ema(self._ema_slow, close, self.ema_slow_period)

        # True Range (TR) for ATR
        if self._prev_close is None:
            tr = float(candle.high - candle.low)
        else:
            tr = float(
                max(
                    candle.high - candle.low,
                    abs(candle.high - self._prev_close),
                    abs(candle.low - self._prev_close),
                )
            )

        # ATR (Wilder smoothing)
        if self._atr is None:
            self._atr = tr
        else:
            self._atr = (self._atr * (self.atr_period - 1) + tr) / self.atr_period

        # RSI (Wilder smoothing)
        if self._prev_close is None:
            change = 0.0
        else:
            change = close - self._prev_close

        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        if self._avg_gain is None:
            self._avg_gain = gain
            self._avg_loss = loss
        else:
            self._avg_gain = (self._avg_gain * (self.rsi_period - 1) + gain) / self.rsi_period
            self._avg_loss = (self._avg_loss * (self.rsi_period - 1) + loss) / self.rsi_period

        # During warm-up, keep RSI neutral to avoid "fake 100" early signals
        if self._bars < self.rsi_period:
            rsi = 50.0
        else:
            avg_loss = (self._avg_loss or 0.0)
            if avg_loss == 0.0:
                rsi = 100.0
            else:
                rs = (self._avg_gain or 0.0) / max(avg_loss, 1e-12)
                rsi = 100.0 - (100.0 / (1.0 + rs))

        self._prev_close = close

        return Indicators(
            ema_fast=self._ema_fast,
            ema_slow=self._ema_slow,
            atr=self._atr,
            rsi=float(rsi),
        )
