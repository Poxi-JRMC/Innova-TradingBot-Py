"""
Backtest de la estrategia (Trend Pullback + HTF) sobre historial Deriv.

Uso:
  python -m src.app.backtest [--symbols R_50 R_75 R_100] [--count 5000]

Descarga ticks históricos vía API Deriv, construye velas 1m, aplica la misma
lógica que el engine (indicadores, estrategia, filtro HTF) y simula operaciones
Rise/Fall (ganada si el cierre de la vela siguiente va en la dirección de la señal).
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.infrastructure.deriv.deriv_ws_client import DerivWSClient
from src.infrastructure.utils.config import load_config
from src.infrastructure.logging.logging import configure_logging, get_logger
from src.models.market_models import Candle
from src.services.market.deriv_history import fetch_ticks_history
from src.services.market.higher_tf_trend import HigherTimeframeTrend
from src.services.market.indicators import IndicatorEngine
from src.services.market.support_resistance import compute_levels, passes_sr_filter
from src.services.strategy.trend_pullback import TrendPullbackStrategy

log = get_logger("backtest")


@dataclass
class SimTrade:
    symbol: str
    side: str
    entry_time: str
    entry_price: float
    exit_price: float
    win: bool
    pnl: float
    score: float


def _active_symbols(config: Any) -> List[str]:
    syms = getattr(config.trading, "symbols", None)
    if syms and len(syms) >= 2:
        return list(syms)
    return [config.trading.symbol]


def _run_backtest(
    candles_by_symbol: Dict[str, List[Candle]],
    config: Any,
    stake_per_trade: float = 1.0,
    payout_ratio: float = 0.95,
) -> tuple[List[SimTrade], Dict[str, Any]]:
    """
    Ejecuta el backtest: por cada minuto con vela cerrada en todos los símbolos,
    actualiza indicadores y HTF, obtiene señales, elige la mejor y simula resultado
    con la vela siguiente (Rise/Fall: CALL gana si close_siguiente > entry, PUT si <).
    """
    strategy = TrendPullbackStrategy(
        min_atr_pct=0.001,
        min_ema_spread_pct=0.0005,
    )
    htf_cfg = config.trading.strategy.higher_tf_trend
    indicator_cfg = config.trading.strategy.trend_pullback
    sr_cfg = config.trading.strategy.support_resistance

    symbols = list(candles_by_symbol.keys())
    if not symbols:
        return [], {"error": "no candles"}

    # Índice: por símbolo, mapa open_epoch -> Candle (para buscar "siguiente" vela)
    by_sym_epoch: Dict[str, Dict[int, Candle]] = {}
    all_epochs: set[int] = set()
    for sym, candles in candles_by_symbol.items():
        by_sym_epoch[sym] = {}
        for c in candles:
            ep = int(c.open_time.timestamp())
            by_sym_epoch[sym][ep] = c
            all_epochs.add(ep)

    sorted_epochs = sorted(all_epochs)
    if len(sorted_epochs) < 2:
        return [], {"error": "not enough candles"}

    # Estado por símbolo
    inds: Dict[str, IndicatorEngine] = {
        s: IndicatorEngine(
            ema_fast_period=indicator_cfg.ema_fast_period,
            ema_slow_period=indicator_cfg.ema_slow_period,
            atr_period=indicator_cfg.atr_period,
            rsi_period=indicator_cfg.rsi_period,
        )
        for s in symbols
    }
    htf_trends: Dict[str, HigherTimeframeTrend] = {
        s: HigherTimeframeTrend(timeframe_1m_blocks=htf_cfg.timeframe_minutes)
        for s in symbols
    }
    last_indicators: Dict[str, Any] = {}

    trades: List[SimTrade] = []
    for t_epoch in sorted_epochs:
        next_epoch = t_epoch + 60

        # 1) Alimentar cada símbolo con la vela que cierra en t_epoch (una sola vez por vela)
        for sym in symbols:
            c = by_sym_epoch.get(sym, {}).get(t_epoch)
            if not c:
                continue
            last_indicators[sym] = inds[sym].update(c)
            htf_trends[sym].add_1m_candle(c)

        # 2) Candidatos: símbolos con indicadores listos, señal != NONE, HTF alineado, S/R si aplica
        candidates: List[tuple] = []
        for sym in symbols:
            c = by_sym_epoch.get(sym, {}).get(t_epoch)
            if not c:
                continue
            ind = last_indicators.get(sym)
            if ind is None:
                continue
            if not inds[sym].is_ready():
                continue
            signal = strategy.generate(c, ind)
            if signal.side == "NONE":
                continue
            if htf_cfg.enabled and not htf_trends[sym].is_aligned(signal.side, allow_neutral=htf_cfg.allow_neutral):
                continue
            if sr_cfg.enabled:
                sym_epochs = sorted(by_sym_epoch[sym].keys())
                idx = next((i for i, ep in enumerate(sym_epochs) if ep == t_epoch), None)
                if idx is not None and idx >= sr_cfg.min_candles - 1:
                    start = max(0, idx + 1 - sr_cfg.lookback_candles)
                    recent = [by_sym_epoch[sym][sym_epochs[i]] for i in range(start, idx + 1)]
                    support, resistance = compute_levels(recent, sr_cfg.min_candles)
                    min_candles_met = len(recent) >= sr_cfg.min_candles
                    if not passes_sr_filter(
                        signal.side, float(c.close), support, resistance, sr_cfg.near_pct, min_candles_met
                    ):
                        continue
            candidates.append((sym, signal, c))

        if not candidates:
            continue

        # 3) Mejor señal por score
        best_sym, best_signal, best_candle = max(candidates, key=lambda x: x[1].score)

        # 4) Siguiente vela para resultado (contrato 1m: se cierra al final del siguiente minuto)
        next_candle = by_sym_epoch.get(best_sym, {}).get(next_epoch)
        if not next_candle:
            continue

        entry = best_candle.close
        settle = next_candle.close
        if best_signal.side == "CALL":
            win = settle > entry
        else:
            win = settle < entry

        pnl = stake_per_trade * payout_ratio if win else -stake_per_trade
        trades.append(
            SimTrade(
                symbol=best_sym,
                side=best_signal.side,
                entry_time=best_candle.open_time.isoformat(),
                entry_price=entry,
                exit_price=settle,
                win=win,
                pnl=pnl,
                score=best_signal.score,
            )
        )

    # Métricas
    total = len(trades)
    wins = sum(1 for t in trades if t.win)
    losses = total - wins
    win_rate = (wins / total * 100) if total else 0.0
    total_pnl = sum(t.pnl for t in trades)
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        eq += t.pnl
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)
    expectancy = total_pnl / total if total else 0.0

    metrics = {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(win_rate, 2),
        "total_pnl": round(total_pnl, 2),
        "expectancy_per_trade": round(expectancy, 4),
        "max_drawdown": round(max_dd, 2),
    }
    return trades, metrics


async def _fetch_all_candles(
    client: DerivWSClient,
    symbols: List[str],
    count: int,
) -> Dict[str, List[Candle]]:
    out: Dict[str, List[Candle]] = {}
    for sym in symbols:
        try:
            candles = await fetch_ticks_history(client, sym, count=count)
            if candles:
                out[sym] = candles
        except Exception as e:
            log.warning("fetch_symbol_failed", symbol=sym, error=str(e))
    return out


def _print_report(metrics: Dict[str, Any], trades: List[SimTrade]) -> None:
    print("\n" + "=" * 60)
    print("BACKTEST - Rise/Fall 1m (misma estrategia que el engine)")
    print("=" * 60)
    print(f"  Total operaciones: {metrics.get('total_trades', 0)}")
    print(f"  Ganadas:           {metrics.get('wins', 0)}")
    print(f"  Perdidas:         {metrics.get('losses', 0)}")
    print(f"  Win rate:         {metrics.get('win_rate_pct', 0)}%")
    print(f"  PnL total:        {metrics.get('total_pnl', 0):.2f} USD (stake 1 USD/trade)")
    print(f"  Expectativa/trade:{metrics.get('expectancy_per_trade', 0):.4f} USD")
    print(f"  Max drawdown:     {metrics.get('max_drawdown', 0):.2f} USD")
    print("=" * 60)
    if trades:
        print("\nÚltimas 10 operaciones:")
        for t in trades[-10:]:
            res = "WIN" if t.win else "LOSS"
            print(f"  {t.entry_time[:19]} {t.symbol} {t.side} entry={t.entry_price:.2f} exit={t.exit_price:.2f} -> {res} pnl={t.pnl:+.2f}")
    print()


async def run_backtest(
    config_path: Optional[Path] = None,
    symbols_override: Optional[List[str]] = None,
    count: int = 5000,
) -> None:
    config = load_config(config_path)
    configure_logging(config.log_level)

    symbols = symbols_override or _active_symbols(config)
    log.info("backtest_start", symbols=symbols, count=count)

    client = DerivWSClient(
        websocket_url=config.deriv.websocket_url,
        app_id=config.deriv.app_id,
        api_token=config.deriv.api_token,
    )
    try:
        await client.start()
        await client.wait_until_connected(timeout=15.0)
        candles_by_symbol = await _fetch_all_candles(client, symbols, count)
    finally:
        await client.stop()

    if not candles_by_symbol:
        log.error("no_data", message="No se pudo descargar historial para ningún símbolo")
        print("Error: No se obtuvo historial. Revisa token Deriv y símbolos.")
        return

    trades, metrics = _run_backtest(candles_by_symbol, config, stake_per_trade=1.0, payout_ratio=0.95)
    _print_report(metrics, trades)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest estrategia con historial Deriv")
    parser.add_argument("--config", type=Path, default=None, help="Ruta a config YAML")
    parser.add_argument("--symbols", nargs="+", default=None, help="Símbolos (ej: R_50 R_75 R_100). Por defecto usa config.")
    parser.add_argument("--count", type=int, default=5000, help="Ticks a pedir por símbolo (máx ~5000)")
    args = parser.parse_args()
    asyncio.run(run_backtest(config_path=args.config, symbols_override=args.symbols, count=args.count))


if __name__ == "__main__":
    main()
