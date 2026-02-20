from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Trade:
    trade_id: str
    symbol: str
    side: str               # "CALL" | "PUT"
    score: float
    stake: float
    duration: int
    duration_unit: str      # "m" (minutes)
    contract_id: Optional[int] = None

    opened_at: Optional[datetime] = None
    entry_price: Optional[float] = None

    closed_at: Optional[datetime] = None
    exit_price: Optional[float] = None
    profit: Optional[float] = None
    status: str = "OPEN"    # "OPEN" | "CLOSED"
