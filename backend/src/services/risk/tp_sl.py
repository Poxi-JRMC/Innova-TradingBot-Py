"""Take profit / Stop loss amounts for multiplier contracts (in USD)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TpSlAmounts:
    take_profit_usd: float
    stop_loss_usd: float


def compute_tp_sl_from_stake(
    stake: float,
    take_profit_percent: float,
    stop_loss_percent: float,
) -> TpSlAmounts:
    """Compute TP and SL as monetary amounts (USD) from stake and percentages.

    Deriv API limit_order expects take_profit and stop_loss as absolute profit/loss
    amounts (e.g. close when profit >= X USD, or when loss >= Y USD).
    """
    stake = max(0.01, float(stake))
    tp = stake * float(take_profit_percent)
    sl = stake * float(stop_loss_percent)
    tp = max(0.01, round(tp, 2))
    sl = max(0.01, round(sl, 2))
    return TpSlAmounts(take_profit_usd=tp, stop_loss_usd=sl)
