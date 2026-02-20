"""Position sizing (stake) based on risk % and signal score."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SizeDecision:
    allowed: bool
    stake: float
    risk_percent: float
    reason: str


class PositionSizer:
    """Compute stake to use on Deriv based on balance and signal score.

    Notes:
    - For Deriv contracts, 'stake' is the amount you invest per trade.
    - We avoid martingale. Stake depends only on balance + score, capped by config.
    """

    def __init__(
        self,
        *,
        min_stake: float,
        max_stake: float,
        risk_per_trade_percent: float,
        risk_per_trade_percent_high_score: float,
        max_risk_per_trade_percent: float,
        score_high_threshold: float = 0.75,
        score_min_threshold: float = 0.55,
    ) -> None:
        self.min_stake = float(min_stake)
        self.max_stake = float(max_stake)
        self.risk_base = float(risk_per_trade_percent)
        self.risk_high = float(risk_per_trade_percent_high_score)
        self.risk_cap = float(max_risk_per_trade_percent)

        self.score_high = float(score_high_threshold)
        self.score_min = float(score_min_threshold)

    def compute(self, *, balance: float, score: float) -> SizeDecision:
        """Return stake based on score [0..1]."""

        balance = float(balance)
        score = float(score)

        if balance <= 0:
            return SizeDecision(False, 0.0, 0.0, "invalid_balance")

        # If score too low, skip or go minimal
        if score < self.score_min:
            return SizeDecision(False, 0.0, 0.0, f"score_too_low score={score:.2f}")

        # Interpolate risk between base and high, capped
        if score >= self.score_high:
            risk_pct = min(self.risk_high, self.risk_cap)
        else:
            # Linear scaling between score_min and score_high
            t = (score - self.score_min) / max((self.score_high - self.score_min), 1e-9)
            risk_pct = self.risk_base + t * (self.risk_high - self.risk_base)
            risk_pct = min(risk_pct, self.risk_cap)

        stake = balance * risk_pct

        # Clamp to min/max stake
        stake = max(self.min_stake, min(self.max_stake, stake))

        return SizeDecision(True, round(stake, 2), risk_pct, "ok")
