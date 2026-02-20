# src/api/state.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.services.monitoring.metrics import MetricsSnapshot
from src.services.risk.killswitch import KillSwitch
from src.infrastructure.storage.sqlite_repository import SQLiteRepository


@dataclass
class AppState:
    repo: SQLiteRepository
    metrics: MetricsSnapshot
    killswitch: KillSwitch


_state: Optional[AppState] = None


def set_state(state: AppState) -> None:
    global _state
    _state = state


def get_state() -> AppState:
    if _state is None:
        raise RuntimeError("API state not initialized. Start engine first (or init state).")
    return _state
