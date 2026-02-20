from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict

_METRICS_PATH = Path("data/metrics.json")


def write_metrics(data: Dict[str, Any]) -> None:
    _METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _METRICS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_METRICS_PATH)  # atomic replace


def read_metrics() -> Dict[str, Any]:
    if not _METRICS_PATH.exists():
        return {"connected": False, "message": "metrics not yet available"}
    return json.loads(_METRICS_PATH.read_text(encoding="utf-8"))
