"""SQLite repository (MVP) for events and trades."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


JsonDict = Dict[str, Any]


@dataclass(frozen=True)
class TradeRow:
    id: str
    symbol: str
    side: str
    entry_time: str
    entry_price: float
    exit_time: Optional[str]
    exit_price: Optional[float]
    pnl: Optional[float]
    stake: float
    score: int
    reasons_json: str
    balance_before: float
    balance_after: Optional[float]
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None


class SQLiteRepository:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path.as_posix(), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
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
        self._conn.commit()
        for col in ("take_profit", "stop_loss"):
            try:
                cur.execute(f"ALTER TABLE trades ADD COLUMN {col} REAL")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass

    def close(self) -> None:
        self._conn.close()

    def log_event(
        self,
        *,
        ts: str,
        level: str,
        type: str,
        message: str,
        data: Optional[JsonDict] = None,
    ) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO events(ts, level, type, message, data_json) VALUES(?,?,?,?,?)",
            (ts, level, type, message, json.dumps(data or {})),
        )
        self._conn.commit()

    def list_events(self, limit: int = 200) -> List[JsonDict]:
        cur = self._conn.cursor()
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

    def insert_trade(self, row: TradeRow) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO trades(
              id, symbol, side, entry_time, entry_price, exit_time, exit_price, pnl,
              stake, score, reasons_json, balance_before, balance_after, take_profit, stop_loss
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row.id,
                row.symbol,
                row.side,
                row.entry_time,
                row.entry_price,
                row.exit_time,
                row.exit_price,
                row.pnl,
                row.stake,
                row.score,
                row.reasons_json,
                row.balance_before,
                row.balance_after,
                row.take_profit,
                row.stop_loss,
            ),
        )
        self._conn.commit()

    def list_trades(self, limit: int = 200) -> List[JsonDict]:
        cur = self._conn.cursor()
        rows = cur.execute(
            "SELECT * FROM trades ORDER BY entry_time DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_trades_today_count(self) -> int:
        """Número de trades con entry_time en el día actual (UTC)."""
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT COUNT(*) FROM trades WHERE date(entry_time) = date('now')"
        ).fetchone()
        return int(row[0]) if row else 0

    def get_daily_pnl(self) -> float:
        """Suma de pnl de trades cerrados hoy (entry_time = hoy)."""
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE date(entry_time) = date('now') AND pnl IS NOT NULL"
        ).fetchone()
        return float(row[0]) if row else 0.0

    def get_consecutive_losses_and_last_close(self) -> tuple[int, Optional[str]]:
        """Cuenta pérdidas consecutivas al final del historial (por exit_time) y devuelve la última fecha de cierre."""
        cur = self._conn.cursor()
        rows = cur.execute(
            "SELECT pnl, exit_time FROM trades WHERE exit_time IS NOT NULL ORDER BY exit_time DESC LIMIT 20"
        ).fetchall()
        consecutive = 0
        last_close: Optional[str] = None
        for r in rows:
            pnl = r[0]
            exit_t = r[1]
            if last_close is None and exit_t:
                last_close = str(exit_t)
            if pnl is None:
                break
            if float(pnl) <= 0:
                consecutive += 1
            else:
                break
        return consecutive, last_close

    def delete_trade(self, trade_id: str) -> None:
        """Elimina un trade por id (p. ej. cuando la ejecución en Deriv falla y no se abrió contrato)."""
        cur = self._conn.cursor()
        cur.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
        self._conn.commit()

    def close_trade(
        self,
        trade_id: str,
        *,
        exit_time: str,
        exit_price: Optional[float],
        pnl: float,
        balance_after: Optional[float],
    ) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            UPDATE trades
            SET exit_time = ?, exit_price = ?, pnl = ?, balance_after = ?
            WHERE id = ?
            """,
            (exit_time, exit_price, pnl, balance_after, trade_id),
        )
        self._conn.commit()

