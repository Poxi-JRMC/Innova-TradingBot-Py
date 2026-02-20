from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.infrastructure.utils.config import load_config, load_runtime_overrides, save_runtime_overrides, get_effective_contract_type
from src.services.execution.deriv_multiplier_resolver import read_multiplier_cache
from src.services.risk.killswitch import KillSwitch
from src.services.monitoring.metrics_store import read_metrics as read_metrics_file


JsonDict = Dict[str, Any]

# ✅ Config y DB
config = load_config()
db_path = Path(config.database.sqlite.path)
db_path.parent.mkdir(parents=True, exist_ok=True)

# ✅ KillSwitch persistente
ks = KillSwitch(Path("data/killswitch.json"))

# ✅ App (SOLO UNA VEZ)
app = FastAPI(title="Deriv Trading Bot API", version="0.1.0")

# ✅ CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------- Silenciar ConnectionResetError en Windows (frontend cierra conexiones al hacer polling) ---------
def _api_exception_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    exc = context.get("exception")
    if exc is not None and isinstance(exc, (ConnectionResetError, ConnectionAbortedError)):
        return  # WinError 10054: conexión cerrada por el cliente (navegador) — inofensivo
    loop.default_exception_handler(context)


@app.on_event("startup")
async def _set_loop_exception_handler() -> None:
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_api_exception_handler)


# --------- Schemas ---------
class KillSwitchPayload(BaseModel):
    reason: Optional[str] = None


class ConfigUpdatePayload(BaseModel):
    """Permite cambiar tipo de contrato desde el frontend (aplica en la siguiente operación)."""
    contract_type: Optional[str] = None  # "rise_fall" | "multiplier"


# --------- DB helpers ---------
def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path.as_posix(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts TEXT NOT NULL,
          level TEXT NOT NULL,
          type TEXT NOT NULL,
          message TEXT NOT NULL,
          data_json TEXT
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
          id TEXT PRIMARY KEY,
          symbol TEXT NOT NULL,
          side TEXT NOT NULL,
          entry_time TEXT NOT NULL,
          entry_price REAL NOT NULL,
          exit_time TEXT,
          exit_price REAL,
          pnl REAL,
          stake REAL NOT NULL,
          score INTEGER NOT NULL,
          reasons_json TEXT NOT NULL,
          balance_before REAL NOT NULL,
          balance_after REAL,
          take_profit REAL,
          stop_loss REAL
        );
        """
    )
    conn.commit()
    for col in ("take_profit", "stop_loss"):
        try:
            cur.execute(f"ALTER TABLE trades ADD COLUMN {col} REAL")
            conn.commit()
        except sqlite3.OperationalError:
            pass


def _list_events(limit: int) -> List[JsonDict]:
    conn = _connect()
    try:
        _init_schema(conn)
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT ts, level, type, message, data_json FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

        out: List[JsonDict] = []
        for r in rows:
            out.append(
                {
                    "ts": r["ts"],
                    "level": r["level"],
                    "type": r["type"],
                    "message": r["message"],
                    "data": json.loads(r["data_json"] or "{}"),
                }
            )
        return out
    finally:
        conn.close()


def _list_trades(limit: int) -> List[JsonDict]:
    conn = _connect()
    try:
        _init_schema(conn)
        cur = conn.cursor()
        rows = cur.execute(
            "SELECT * FROM trades ORDER BY entry_time DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _clear_trades() -> int:
    """Borra todos los registros de la tabla trades. Devuelve el número de filas eliminadas."""
    conn = _connect()
    try:
        _init_schema(conn)
        cur = conn.cursor()
        n = cur.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        cur.execute("DELETE FROM trades")
        conn.commit()
        return n
    finally:
        conn.close()


def _clear_trades_by_range(from_date: str, to_date: str) -> int:
    """Borra trades cuya entry_time (solo fecha) está entre from_date y to_date (YYYY-MM-DD)."""
    conn = _connect()
    try:
        _init_schema(conn)
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM trades WHERE date(entry_time) >= ? AND date(entry_time) <= ?",
            (from_date, to_date),
        )
        n = cur.fetchone()[0]
        cur.execute(
            "DELETE FROM trades WHERE date(entry_time) >= ? AND date(entry_time) <= ?",
            (from_date, to_date),
        )
        conn.commit()
        return n
    finally:
        conn.close()


def _latest_metrics() -> JsonDict:
    """Métricas desde la tabla events (el engine escribe cada 5 s). Si no hay ninguna, fallback a data/metrics.json."""
    conn = _connect()
    try:
        _init_schema(conn)
        cur = conn.cursor()
        row = cur.execute(
            """
            SELECT ts, data_json
            FROM events
            WHERE type = 'metrics'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        if row and row["data_json"]:
            return {"ts": row["ts"], "data": json.loads(row["data_json"])}
    finally:
        conn.close()

    # Fallback: engine escribe también en data/metrics.json cada 5 s
    try:
        file_metrics = read_metrics_file()
        if file_metrics:
            return {"ts": None, "data": file_metrics}
    except Exception:
        pass
    return {}


# --------- Routes ---------
@app.get("/health")
def health() -> JsonDict:
    return {
        "ok": True,
        "env": config.environment,
        "contract_type": get_effective_contract_type(config),
    }


def _active_symbols() -> List[str]:
    """Misma lógica que en engine: lista activa de símbolos (multi o single)."""
    syms = getattr(config.trading, "symbols", None)
    if syms and len(syms) >= 2:
        return list(syms)
    return [config.trading.symbol]


@app.get("/config")
def get_config_endpoint() -> JsonDict:
    """Configuración actual (símbolo/símbolos, tipo de contrato efectivo, parámetros multiplier). Para cambiar mercado: editar config/default.yaml → trading.symbol o trading.symbols y reiniciar."""
    mc = config.trading.multiplier
    htf = config.trading.strategy.higher_tf_trend
    active = _active_symbols()
    out: JsonDict = {
        "ok": True,
        "symbol": config.trading.symbol,
        "symbols": active,
        "multi_market": len(active) >= 2,
        "contract_type": get_effective_contract_type(config),
        "dry_run": getattr(config.development, "dry_run", True),
        "multiplier": {
            "duration": mc.duration,
            "duration_unit": mc.duration_unit,
            "multiplier": mc.multiplier,
            "take_profit_percent_of_stake": mc.take_profit_percent_of_stake,
            "stop_loss_percent_of_stake": mc.stop_loss_percent_of_stake,
        },
        "higher_tf_trend": {
            "enabled": htf.enabled,
            "timeframe_minutes": htf.timeframe_minutes,
            "allow_neutral": htf.allow_neutral,
        },
        "support_resistance": {
            "enabled": getattr(config.trading.strategy.support_resistance, "enabled", True),
            "lookback_candles": getattr(config.trading.strategy.support_resistance, "lookback_candles", 30),
            "near_pct": getattr(config.trading.strategy.support_resistance, "near_pct", 0.003),
        },
    }
    # Multiplicadores por mercado (R_50, R_75, R_100 tienen distintos levers permitidos en Deriv)
    multiplier_from_deriv = read_multiplier_cache()
    if multiplier_from_deriv and "symbols" in multiplier_from_deriv and isinstance(multiplier_from_deriv.get("symbols"), dict):
        out["multiplier_from_deriv"] = {"symbols": multiplier_from_deriv["symbols"]}
    elif multiplier_from_deriv and multiplier_from_deriv.get("symbol"):
        out["multiplier_from_deriv"] = {
            "allowed": multiplier_from_deriv.get("allowed", []),
            "resolved": multiplier_from_deriv.get("resolved"),
            "symbol": multiplier_from_deriv.get("symbol"),
        }
    return out


@app.post("/config")
def update_config(payload: ConfigUpdatePayload) -> JsonDict:
    """Actualiza solo lo permitido (p. ej. contract_type). Cambios aplican en la siguiente operación."""
    if payload.contract_type is not None:
        v = str(payload.contract_type).lower()
        if v not in ("rise_fall", "multiplier"):
            raise HTTPException(status_code=400, detail="contract_type debe ser 'rise_fall' o 'multiplier'")
        save_runtime_overrides({"contract_type": v})
    return {"ok": True, "config": {**load_runtime_overrides()}}


@app.get("/metrics")
def metrics() -> JsonDict:
    try:
        m = _latest_metrics()
        return {"ok": True, "metrics": m}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/metrics failed: {e}")


@app.get("/events")
def events(limit: int = 200) -> JsonDict:
    try:
        return {"ok": True, "events": _list_events(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/events failed: {e}")


@app.get("/trades")
def trades(limit: int = 200) -> JsonDict:
    try:
        return {"ok": True, "trades": _list_trades(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/trades failed: {e}")


@app.delete("/trades")
def clear_trades(from_date: Optional[str] = None, to_date: Optional[str] = None) -> JsonDict:
    """Borra trades. Sin params: todo. Con from_date y to_date (YYYY-MM-DD): solo ese rango."""
    try:
        if from_date and to_date:
            deleted = _clear_trades_by_range(from_date, to_date)
        else:
            deleted = _clear_trades()
        return {"ok": True, "deleted": deleted}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/trades clear failed: {e}")


@app.get("/killswitch")
def get_killswitch() -> JsonDict:
    try:
        ks.load()
        s = ks.state
        return {
            "ok": True,
            "enabled": s.enabled,
            "reason": s.reason,
            "activated_at_iso": s.activated_at_iso,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/killswitch failed: {e}")


@app.post("/killswitch/enable")
def enable_killswitch(payload: Optional[KillSwitchPayload] = None) -> JsonDict:
    try:
        reason = payload.reason if payload else None
        ks.enable(reason=reason)
        return {"ok": True, "enabled": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/killswitch/enable failed: {e}")


@app.post("/killswitch/disable")
def disable_killswitch(payload: Optional[KillSwitchPayload] = None) -> JsonDict:
    try:
        reason = payload.reason if payload else None
        ks.disable(reason=reason)
        return {"ok": True, "enabled": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/killswitch/disable failed: {e}")
