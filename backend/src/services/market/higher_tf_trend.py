"""Higher-timeframe trend from 1m candles (e.g. 5m trend for trend-aligned entries)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Literal, Optional

from src.models.market_models import Candle


TrendKind = Literal["bullish", "bearish", "neutral"]


@dataclass
class _AggCandle:
    """Aggregated candle (open, high, low, close from N x 1m)."""
    open: float
    high: float
    low: float
    close: float


class HigherTimeframeTrend:
    """
    Builds N-minute candles from 1m candles and exposes the current trend
    (bullish/bearish/neutral) so the strategy only takes 1m signals aligned with it.
    """

    def __init__(self, timeframe_1m_blocks: int = 5) -> None:
        """
        timeframe_1m_blocks: number of 1m candles per higher-TF candle (5 -> 5m).
        """
        self._n = max(1, int(timeframe_1m_blocks))
        self._buffer: Deque[Candle] = deque(maxlen=self._n * 3)  # keep enough for 2+ HTF candles
        self._last_htf: Optional[_AggCandle] = None
        self._prev_htf: Optional[_AggCandle] = None

    def add_1m_candle(self, candle: Candle) -> None:
        """Feed a closed 1m candle. Call this on every 1m close before using get_trend()."""
        self._buffer.append(candle)
        if len(self._buffer) < self._n:
            return
        # Build one HTF candle from the last N x 1m
        chunk = list(self._buffer)[-self._n:]
        agg = _AggCandle(
            open=chunk[0].open,
            high=max(c.high for c in chunk),
            low=min(c.low for c in chunk),
            close=chunk[-1].close,
        )
        self._prev_htf = self._last_htf
        self._last_htf = agg

    def get_trend(self) -> TrendKind:
        """
        Returns bullish if last HTF close > previous HTF close,
        bearish if <, neutral if not enough data or equal.
        """
        if self._last_htf is None or self._prev_htf is None:
            return "neutral"
        if self._last_htf.close > self._prev_htf.close:
            return "bullish"
        if self._last_htf.close < self._prev_htf.close:
            return "bearish"
        return "neutral"

    def is_aligned(self, signal_side: str, allow_neutral: bool = True) -> bool:
        """
        True if the 1m signal is aligned with the higher-TF trend.
        CALL + bullish -> True; PUT + bearish -> True; neutral allowed if allow_neutral.
        """
        trend = self.get_trend()
        if trend == "neutral":
            return allow_neutral
        if signal_side == "CALL" and trend == "bullish":
            return True
        if signal_side == "PUT" and trend == "bearish":
            return True
        return False
