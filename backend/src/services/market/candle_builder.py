"""Build candles from ticks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from src.models.market_models import Candle, Tick


def _floor_time(epoch: int, timeframe_sec: int) -> datetime:
    """Floor an epoch timestamp to the candle open_time for timeframe_sec."""
    floored = epoch - (epoch % timeframe_sec)
    return datetime.fromtimestamp(floored, tz=timezone.utc)


@dataclass
class CandleBuilder:
    """Accumulates ticks into OHLC candles.

    - Builds candles of timeframe_sec (default 60s)
    - Closes current candle when tick moves into next time bucket
    - Calls on_candle_closed callback (if provided) safely
    """

    symbol: str
    timeframe_sec: int = 60
    on_candle_closed: Optional[Callable[[Candle], None]] = None

    _current: Optional[Candle] = None

    def update_with_tick(self, tick: Tick) -> Optional[Candle]:
        """Update candle builder with a new tick.

        Returns the closed candle if a candle closed on this tick, otherwise None.
        """
        if tick.symbol != self.symbol:
            return None

        open_time = _floor_time(tick.epoch, self.timeframe_sec)

        # First tick -> create first candle
        if self._current is None:
            self._current = Candle(
                symbol=self.symbol,
                timeframe_sec=self.timeframe_sec,
                open_time=open_time,
                open=tick.price,
                high=tick.price,
                low=tick.price,
                close=tick.price,
                volume=1,
            )
            return None

        # New candle window -> close previous candle and open a new one
        if open_time > self._current.open_time:
            closed = self._current

            # Safe callback: never let callback errors crash tick processing
            if self.on_candle_closed:
                try:
                    self.on_candle_closed(closed)
                except Exception:
                    pass

            # Start next candle
            self._current = Candle(
                symbol=self.symbol,
                timeframe_sec=self.timeframe_sec,
                open_time=open_time,
                open=tick.price,
                high=tick.price,
                low=tick.price,
                close=tick.price,
                volume=1,
            )
            return closed

        # Same candle -> update OHLC and volume
        c = self._current
        c.close = tick.price
        c.high = max(c.high, tick.price)
        c.low = min(c.low, tick.price)
        c.volume += 1
        return None
