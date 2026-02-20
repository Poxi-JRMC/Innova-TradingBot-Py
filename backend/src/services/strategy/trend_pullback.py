"""Trend Pullback strategy with scoring (0..1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.models.market_models import Candle, Indicators


@dataclass(frozen=True)
class Signal:
    side: str              # "CALL" | "PUT" | "NONE"
    score: float           # 0..1
    reason: str


class TrendPullbackStrategy:
    """
    Trend + pullback strategy:
    - Trend: EMA fast above/below EMA slow
    - Pullback: RSI returns to a favorable zone
    - Volatility filter: ATR must be above threshold (relative to price)
    """

    def __init__(
        self,
        *,
        min_atr_pct: float = 0.001,          # 0.10% of price
        min_ema_spread_pct: float = 0.0005,  # 0.05% of price
        rsi_long_zone=(45.0, 60.0),
        rsi_short_zone=(40.0, 55.0),
        rsi_overbought: float = 70.0,
        rsi_oversold: float = 30.0,
    ) -> None:
        self.min_atr_pct = float(min_atr_pct)
        self.min_ema_spread_pct = float(min_ema_spread_pct)
        self.rsi_long_zone = rsi_long_zone
        self.rsi_short_zone = rsi_short_zone
        self.rsi_overbought = float(rsi_overbought)
        self.rsi_oversold = float(rsi_oversold)

    def generate(self, candle: Candle, ind: Indicators) -> Signal:
        # Need indicators
        if ind.ema_fast is None or ind.ema_slow is None or ind.atr is None or ind.rsi is None:
            return Signal("NONE", 0.0, "indicators_not_ready")

        price = float(candle.close)
        if price <= 0:
            return Signal("NONE", 0.0, "invalid_price")

        ema_fast = float(ind.ema_fast)
        ema_slow = float(ind.ema_slow)
        atr = float(ind.atr)
        rsi = float(ind.rsi)

        # Trend direction
        uptrend = ema_fast > ema_slow
        downtrend = ema_fast < ema_slow
        if not (uptrend or downtrend):
            return Signal("NONE", 0.0, "no_trend")

        # Filters: ATR must be meaningful
        atr_pct = atr / price
        if atr_pct < self.min_atr_pct:
            return Signal("NONE", 0.0, f"atr_too_low atr_pct={atr_pct:.4f}")

        # Filters: EMA spread must be meaningful
        ema_spread_pct = abs(ema_fast - ema_slow) / price
        if ema_spread_pct < self.min_ema_spread_pct:
            return Signal("NONE", 0.0, f"ema_spread_too_low spread={ema_spread_pct:.4f}")

        # Avoid extremes (often late entries)
        if rsi >= self.rsi_overbought and uptrend:
            return Signal("NONE", 0.0, "rsi_overbought_skip")
        if rsi <= self.rsi_oversold and downtrend:
            return Signal("NONE", 0.0, "rsi_oversold_skip")

        # Pullback zones
        if uptrend:
            lo, hi = self.rsi_long_zone
            if not (lo <= rsi <= hi):
                return Signal("NONE", 0.0, "rsi_not_in_long_zone")
            side = "CALL"
        else:
            lo, hi = self.rsi_short_zone
            if not (lo <= rsi <= hi):
                return Signal("NONE", 0.0, "rsi_not_in_short_zone")
            side = "PUT"

        # Score components (0..1)
        # Trend strength: normalize by a reasonable cap
        trend_strength = min(1.0, ema_spread_pct / (self.min_ema_spread_pct * 4.0))
        # Volatility: normalize similarly
        vol_strength = min(1.0, atr_pct / (self.min_atr_pct * 4.0))

        # RSI "sweet spot": closer to middle of zone gets higher score
        zone_mid = (lo + hi) / 2.0
        zone_half = max((hi - lo) / 2.0, 1e-9)
        rsi_score = max(0.0, 1.0 - (abs(rsi - zone_mid) / zone_half))  # 1 at mid, 0 at edges

        # Weighted final score
        score = (0.45 * trend_strength) + (0.35 * rsi_score) + (0.20 * vol_strength)
        score = max(0.0, min(1.0, score))

        return Signal(side, score, "ok")
