"""Risk firewall (NO NEGOCIABLE)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional
from src.infrastructure.utils.timeutils import utc_now



@dataclass(frozen=True)
class RiskSnapshot:
    balance: float
    equity: float
    peak_equity: float
    daily_pnl: float
    trades_today: int
    consecutive_losses: int
    last_trade_closed_at_iso: Optional[str] = None


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    cooldown_remaining_sec: int = 0


class RiskFirewall:
    def __init__(
        self,
        *,
        max_drawdown_total: float,
        max_loss_daily: float,
        max_trades_daily: int,
        max_consecutive_losses: int,
        consecutive_loss_cooldown_minutes: int,
    ) -> None:
        self.max_drawdown_total = max_drawdown_total
        self.max_loss_daily = max_loss_daily
        self.max_trades_daily = max_trades_daily
        self.max_consecutive_losses = max_consecutive_losses
        self.cooldown_minutes = consecutive_loss_cooldown_minutes

        self._day: date = utc_now().date()
        self._daily_start_equity: Optional[float] = None

    def reset_daily_if_needed(self, snapshot: RiskSnapshot) -> None:
        today = utc_now().date()
        if today != self._day:
            self._day = today
            self._daily_start_equity = snapshot.equity

        if self._daily_start_equity is None:
            self._daily_start_equity = snapshot.equity

    def check(self, snapshot: RiskSnapshot) -> RiskDecision:
        self.reset_daily_if_needed(snapshot)

        if snapshot.peak_equity <= 0:
            return RiskDecision(False, "invalid_peak_equity")
        dd = (snapshot.peak_equity - snapshot.equity) / snapshot.peak_equity
        if dd >= self.max_drawdown_total:
            return RiskDecision(False, f"max_drawdown_total_reached dd={dd:.4f}")

        assert self._daily_start_equity is not None
        daily_loss = (self._daily_start_equity - snapshot.equity) / max(self._daily_start_equity, 1e-9)
        if daily_loss >= self.max_loss_daily:
            return RiskDecision(False, f"max_loss_daily_reached loss={daily_loss:.4f}")

        if snapshot.trades_today >= self.max_trades_daily:
            return RiskDecision(False, "max_trades_daily_reached")

        if snapshot.consecutive_losses >= self.max_consecutive_losses:
            if snapshot.last_trade_closed_at_iso:
                from datetime import datetime

                try:
                    last = datetime.fromisoformat(snapshot.last_trade_closed_at_iso)
                except Exception:
                    last = utc_now()
                elapsed = (utc_now() - last).total_seconds()
                cooldown_total = self.cooldown_minutes * 60
                remaining = max(0, int(cooldown_total - elapsed))
                if remaining > 0:
                    return RiskDecision(False, "cooldown_after_consecutive_losses", remaining)
            return RiskDecision(False, "max_consecutive_losses_reached")

        return RiskDecision(True, "ok")

