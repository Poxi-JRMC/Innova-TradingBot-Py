"""Kill-switch (manual + persistent)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.infrastructure.utils.timeutils import utc_now


@dataclass
class KillSwitchState:
    enabled: bool
    reason: str
    activated_at_iso: Optional[str] = None


class KillSwitch:
    def __init__(self, state_path: Path) -> None:
        self._path = state_path
        self._state = KillSwitchState(enabled=False, reason="")
        self.load()

    @property
    def state(self) -> KillSwitchState:
        return self._state

    def load(self) -> None:
        if not self._path.exists():
            return
        data = json.loads(self._path.read_text(encoding="utf-8"))
        self._state = KillSwitchState(
            enabled=bool(data.get("enabled", False)),
            reason=str(data.get("reason", "")),
            activated_at_iso=data.get("activated_at_iso"),
        )

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._state.__dict__, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def activate(self, reason: str) -> None:
        if self._state.enabled:
            return
        self._state.enabled = True
        self._state.reason = reason
        self._state.activated_at_iso = utc_now().isoformat()
        self.save()

    def deactivate(self, reason: str = "manual_reset") -> None:
        self._state.enabled = False
        self._state.reason = reason
        self._state.activated_at_iso = None
        self.save()

    # ✅ Aliases compatibles con el frontend
    def disable(self, reason: Optional[str] = None) -> None:
        self.deactivate(reason or "manual_reset")

    def enable(self, reason: Optional[str] = None) -> None:
        self.activate(reason or "manual_enable")
