"""Main trading engine loop (MVP + DEMO execution Rise/Fall)."""

from __future__ import annotations
from src.api.state import AppState, set_state

import asyncio
import json
from collections import deque
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.infrastructure.deriv.deriv_ws_client import DerivWSClient
from src.infrastructure.utils.config import load_config, get_effective_contract_type
from src.infrastructure.logging.logging import configure_logging, get_logger
from src.infrastructure.utils.timeutils import utc_now
from src.services.monitoring.metrics_store import write_metrics
from src.services.market.candle_builder import CandleBuilder
from src.services.market.higher_tf_trend import HigherTimeframeTrend
from src.services.market.indicators import IndicatorEngine
from src.services.market.support_resistance import compute_levels, passes_sr_filter
from dataclasses import asdict
from src.models.market_models import Tick

from src.services.monitoring.metrics import MetricsSnapshot

from src.services.risk.killswitch import KillSwitch
from src.services.risk.risk_firewall import RiskFirewall, RiskSnapshot
from src.services.risk.tp_sl import compute_tp_sl_from_stake

from src.services.strategy.trend_pullback import TrendPullbackStrategy
from src.services.risk.position_sizer import PositionSizer

from src.services.execution.deriv_multiplier_resolver import (
    fetch_and_cache_multipliers,
    fetch_and_cache_multipliers_all,
    get_allowed_multipliers,
    pick_best_multiplier,
    read_multiplier_cache,
)
from src.services.execution.order_executor import OrderExecutor

from src.infrastructure.storage.sqlite_repository import SQLiteRepository, TradeRow


@dataclass(frozen=True)
class TradeIntent:
    symbol: str        # Símbolo en el que operar (ej. R_75)
    side: str          # "CALL"/"PUT"
    score: float       # 0..1
    stake: float
    reason: str
    entry_price: float
    take_profit_usd: Optional[float] = None
    stop_loss_usd: Optional[float] = None


async def run_engine(config_path: Path | None = None) -> None:
    config = load_config(config_path)
    configure_logging(config.log_level)
    log = get_logger("engine")
    log.info("config_loaded", app_id=config.deriv.app_id, token_len=len(config.deriv.api_token))
    repo = SQLiteRepository(Path(config.database.sqlite.path))
    ks = KillSwitch(Path("data/killswitch.json"))
    metrics = MetricsSnapshot(symbol=config.trading.symbol)


    rf = RiskFirewall(
        max_drawdown_total=config.trading.risk.max_drawdown_total,
        max_loss_daily=config.trading.risk.max_loss_daily,
        max_trades_daily=config.trading.risk.max_trades_daily,
        max_consecutive_losses=config.trading.risk.max_consecutive_losses,
        consecutive_loss_cooldown_minutes=config.trading.risk.consecutive_loss_cooldown_minutes,
    )

    client = DerivWSClient(
        websocket_url=config.deriv.websocket_url,
        app_id=config.deriv.app_id,
        api_token=config.deriv.api_token,
    )

    metrics = MetricsSnapshot(symbol=config.trading.symbol)

    # Indicators
    ind = IndicatorEngine(
        ema_fast_period=config.trading.strategy.trend_pullback.ema_fast_period,
        ema_slow_period=config.trading.strategy.trend_pullback.ema_slow_period,
        atr_period=config.trading.strategy.trend_pullback.atr_period,
        rsi_period=config.trading.strategy.trend_pullback.rsi_period,
    )

    # Strategy (signal + score)
    strategy = TrendPullbackStrategy(
        min_atr_pct=0.001,          # 0.10% of price
        min_ema_spread_pct=0.0005,  # 0.05% of price
    )

    # Higher-timeframe trend filter: only take 1m signals aligned with e.g. 5m trend
    htf_cfg = config.trading.strategy.higher_tf_trend
    htf_trend = HigherTimeframeTrend(timeframe_1m_blocks=htf_cfg.timeframe_minutes)

    # Filtro de calidad: min_score, RSI dentro de banda, ATR máximo opcional
    qf_cfg = config.trading.strategy.quality_filter
    sr_cfg = config.trading.strategy.support_resistance
    recent_candles_single: deque = deque(maxlen=max(5, sr_cfg.lookback_candles))

    def passes_quality_filter(signal_side: str, signal_score: float, ind: Any, candle: Any, qf: Any) -> bool:
        if not getattr(qf, "enabled", True):
            return True
        if signal_score < getattr(qf, "min_score", 0.0):
            return False
        rsi = getattr(ind, "rsi", None)
        if rsi is not None:
            if signal_side == "CALL" and rsi > getattr(qf, "rsi_call_max", 70.0):
                return False
            if signal_side == "PUT" and rsi < getattr(qf, "rsi_put_min", 30.0):
                return False
        max_atr = getattr(qf, "max_atr_pct", None)
        if max_atr is not None and getattr(ind, "atr", None) is not None:
            price = getattr(candle, "close", 0) or 0
            if price > 0:
                atr_pct = float(ind.atr) / price
                if atr_pct > float(max_atr):
                    return False
        return True

    # Position sizing (stake) based on score
    sizer = PositionSizer(
        min_stake=config.trading.risk.min_stake,
        max_stake=config.trading.risk.max_stake,
        risk_per_trade_percent=config.trading.risk.risk_per_trade_percent,
        risk_per_trade_percent_high_score=config.trading.risk.risk_per_trade_percent_high_score,
        max_risk_per_trade_percent=config.trading.risk.max_risk_per_trade_percent,
    )

    # Executor (Rise/Fall DEMO)
    executor = OrderExecutor(
        client,
        symbol=config.trading.symbol,
        currency=config.trading.stake_currency,
    )

    # Trade queue + single-trade lock
    trade_queue: asyncio.Queue[TradeIntent] = asyncio.Queue(maxsize=3)
    trade_in_flight = asyncio.Event()
    trade_in_flight.clear()

    # Multi-mercado (Fase 2): si hay 2+ símbolos, se elige la mejor señal cada minuto
    symbols_config = getattr(config.trading, "symbols", None)
    if symbols_config and len(symbols_config) >= 2:
        active_symbols: List[str] = list(symbols_config)
        use_multi_market = True
    else:
        active_symbols = [config.trading.symbol]
        use_multi_market = False

    # ---- Worker to execute trades async ----
    async def trade_worker() -> None:
        nonlocal metrics
        while True:
            intent = await trade_queue.get()
            trade_id: Optional[str] = None
            
            try:
                ks.load()
                if ks.state.enabled:
                    log.warning("killswitch_enabled_skip_trade", reason=ks.state.reason)
                    continue

                # Risk firewall check (límite pérdida diaria, máx operaciones, racha de pérdidas)
                equity = float(metrics.balance or 0.0)
                peak = max(float(getattr(metrics, "peak_equity", equity) or 0.0), equity)
                setattr(metrics, "peak_equity", peak)
                trades_today = repo.get_trades_today_count()
                consecutive_losses, last_close_iso = repo.get_consecutive_losses_and_last_close()
                daily_pnl = repo.get_daily_pnl()

                decision = rf.check(
                    RiskSnapshot(
                        balance=equity,
                        equity=equity,
                        peak_equity=peak,
                        daily_pnl=daily_pnl,
                        trades_today=trades_today,
                        consecutive_losses=consecutive_losses,
                        last_trade_closed_at_iso=last_close_iso,
                    )
                )
                if not decision.allowed:
                    log.warning("risk_block_skip_trade", reason=decision.reason)
                    continue

                # Only one trade at a time
                if trade_in_flight.is_set():
                    log.info("trade_in_flight_skip")
                    continue

                trade_in_flight.set()

                # dry_run: no ejecutar en Deriv ni guardar trade (solo simular en logs)
                if getattr(config.development, "dry_run", True):
                    log.info(
                        "dry_run_skip_execution",
                        symbol=intent.symbol,
                        side=intent.side,
                        stake=intent.stake,
                        message="Set development.dry_run to false (or DEVELOPMENT__DRY_RUN=0 in .env) to execute real trades",
                    )
                    repo.log_event(
                        ts=utc_now().isoformat(),
                        level="INFO",
                        type="dry_run_skip",
                        message="Operación no ejecutada (dry_run activo)",
                        data={
                            "symbol": intent.symbol,
                            "side": intent.side,
                            "stake": intent.stake,
                            "score": intent.score,
                            "hint": "Pon development.dry_run: false en config o DEVELOPMENT__DRY_RUN=0 en .env para ejecutar en Deriv",
                        },
                    )
                    trade_in_flight.clear()
                    trade_queue.task_done()
                    continue

                # Build trade_id and store OPEN row
                trade_id = utc_now().isoformat().replace(":", "").replace(".", "")
                score_int = int(max(0.0, min(1.0, intent.score)) * 100)

                balance_before = float(metrics.balance or 0.0)

                repo.insert_trade(
                    TradeRow(
                        id=trade_id,
                        symbol=intent.symbol,
                        side=intent.side,
                        entry_time=utc_now().isoformat(),
                        entry_price=float(intent.entry_price),
                        exit_time=None,
                        exit_price=None,
                        pnl=None,
                        stake=float(intent.stake),
                        score=int(score_int),
                        reasons_json=json.dumps({"reason": intent.reason, "score": float(intent.score)}),
                        balance_before=balance_before,
                        balance_after=None,
                        take_profit=intent.take_profit_usd,
                        stop_loss=intent.stop_loss_usd,
                    )
                )

                contract_label = "Multiplier" if get_effective_contract_type(config) == "multiplier" else "Rise/Fall 1m"
                repo.log_event(
                    ts=utc_now().isoformat(),
                    level="INFO",
                    type="trade_open",
                    message=f"Trade opened ({contract_label})",
                    data={
                        "trade_id": trade_id,
                        "side": intent.side,
                        "stake": intent.stake,
                        "score": intent.score,
                        "take_profit": intent.take_profit_usd,
                        "stop_loss": intent.stop_loss_usd,
                        "contract_type": get_effective_contract_type(config),
                    },
                )

                log.info(
                    "trade_execute_start",
                    trade_id=trade_id,
                    side=intent.side,
                    stake=intent.stake,
                    take_profit=intent.take_profit_usd,
                    stop_loss=intent.stop_loss_usd,
                )

                if get_effective_contract_type(config) == "multiplier":
                    mc = config.trading.multiplier
                    # Usar multiplicador según el mercado: R_50, R_75, R_100 tienen distintos levers permitidos
                    cache = read_multiplier_cache()
                    allowed: Optional[List[int]] = None
                    if cache and "symbols" in cache and isinstance(cache.get("symbols"), dict):
                        per_sym = cache["symbols"].get(intent.symbol)
                        if per_sym and isinstance(per_sym.get("allowed"), list):
                            allowed = per_sym["allowed"]
                            mult = per_sym.get("resolved") or mc.multiplier
                    if allowed is None:
                        allowed = await get_allowed_multipliers(
                            client, intent.symbol, config.trading.stake_currency
                        )
                        mult = (
                            pick_best_multiplier(allowed, mc.multiplier, prefer_moderate=True)
                            if allowed
                            else mc.multiplier
                        )
                    if allowed and mult != mc.multiplier:
                        log.info(
                            "multiplier_resolved_from_deriv",
                            symbol=intent.symbol,
                            preferred=mc.multiplier,
                            used=mult,
                            allowed=allowed[:20],
                        )
                    result = await executor.execute_multiplier(
                        side=intent.side,
                        stake=float(intent.stake),
                        take_profit_usd=float(intent.take_profit_usd or 0),
                        stop_loss_usd=float(intent.stop_loss_usd or 0),
                        duration=mc.duration,
                        duration_unit=mc.duration_unit,
                        multiplier=mult,
                        symbol=intent.symbol,
                    )
                else:
                    result = await executor.execute_rise_fall(
                        side=intent.side,
                        stake=float(intent.stake),
                        duration=1,
                        duration_unit="m",
                        symbol=intent.symbol,
                    )

                # Update balance locally (MVP). Later you can fetch balance again.
                if metrics.balance is not None:
                    metrics.balance = float(metrics.balance) + float(result.profit)

                repo.close_trade(
                    trade_id,
                    exit_time=utc_now().isoformat(),
                    exit_price=None,  # Deriv RF doesn't always give a clean spot exit
                    pnl=float(result.profit),
                    balance_after=float(metrics.balance or 0.0),
                )

                repo.log_event(
                    ts=utc_now().isoformat(),
                    level="INFO",
                    type="trade_close",
                    message="Trade closed (DEMO)",
                    data={
                        "trade_id": trade_id,
                        "contract_id": result.contract_id,
                        "profit": result.profit,
                        "is_win": result.is_win,
                        "payout": result.payout,
                    },
                )

                log.info(
                    "trade_execute_done",
                    trade_id=trade_id,
                    contract_id=result.contract_id,
                    profit=result.profit,
                    is_win=result.is_win,
                )

                # Simple winrate (last 200 trades)
                trades = repo.list_trades(limit=200)
                wins = sum(1 for t in trades if (t.get("pnl") is not None and float(t["pnl"]) > 0))
                losses = sum(1 for t in trades if (t.get("pnl") is not None and float(t["pnl"]) <= 0))
                total = wins + losses
                winrate = (wins / total) * 100.0 if total > 0 else 0.0
                log.info("performance", trades=total, wins=wins, losses=losses, winrate=round(winrate, 2))

            except Exception as e:
                log.error("trade_worker_error", error=str(e))
                # Quitar de historial el trade que no llegó a ejecutarse en Deriv (evitar "operaciones fantasma")
                if trade_id is not None:
                    try:
                        repo.delete_trade(trade_id)
                    except Exception:
                        pass
                repo.log_event(
                    ts=utc_now().isoformat(),
                    level="ERROR",
                    type="trade_error",
                    message="Trade execution error",
                    data={"error": str(e), "trade_id": trade_id, "side": intent.side, "stake": intent.stake},
                )
            finally:
                trade_in_flight.clear()
                trade_queue.task_done()

    # ---- Candle close callback (sync) ----
    def on_candle(c) -> None:
        nonlocal metrics

        try:
            indicators = ind.update(c)
            if indicators is None:
                log.warning("indicators_none", symbol=getattr(c, "symbol", "?"))
                return

            metrics.candles_closed += 1
            metrics.ema_fast = indicators.ema_fast
            metrics.ema_slow = indicators.ema_slow
            metrics.atr = indicators.atr
            metrics.rsi = indicators.rsi

            recent_candles_single.append(c)

            log.info(
                "candle_closed",
                symbol=c.symbol,
                open_time=c.open_time.isoformat() if getattr(c, "open_time", None) else None,
                o=c.open,
                h=c.high,
                l=c.low,
                close=c.close,
                ema_fast=indicators.ema_fast,
                ema_slow=indicators.ema_slow,
                atr=indicators.atr,
                rsi=indicators.rsi,
            )

            # Optional warm-up check if your IndicatorEngine supports it
            ready = True
            if hasattr(ind, "is_ready") and callable(getattr(ind, "is_ready")):
                ready = bool(ind.is_ready())
            if not ready:
                log.info("strategy_warmup", candles=metrics.candles_closed)
                return

            ks.load()
            if ks.state.enabled:
                log.warning("killswitch_enabled_skip_signal", reason=ks.state.reason)
                return

            # Feed 1m candle to higher-TF trend (5m) so we can filter by trend
            htf_trend.add_1m_candle(c)

            # Generate signal + score
            signal = strategy.generate(c, indicators)
            if signal.side == "NONE":
                return

            # Only take signals aligned with higher-timeframe trend (e.g. CALL when 5m bullish)
            if htf_cfg.enabled and not htf_trend.is_aligned(signal.side, allow_neutral=htf_cfg.allow_neutral):
                log.info(
                    "trend_filter_skip",
                    side=signal.side,
                    htf_trend=htf_trend.get_trend(),
                    reason="signal_not_aligned_with_higher_tf",
                )
                return

            # Filtro de calidad: score mínimo, RSI no en extremos, ATR opcional
            if not passes_quality_filter(signal.side, signal.score, indicators, c, qf_cfg):
                log.info("quality_filter_skip", side=signal.side, score=signal.score, rsi=indicators.rsi)
                return

            # Soportes/resistencias: CALL solo cerca de soporte, PUT solo cerca de resistencia (estrategia unificada)
            if sr_cfg.enabled:
                recent_list = list(recent_candles_single)
                support, resistance = compute_levels(recent_list, sr_cfg.min_candles)
                min_candles_met = len(recent_list) >= sr_cfg.min_candles
                if not passes_sr_filter(
                    signal.side, float(c.close), support, resistance, sr_cfg.near_pct, min_candles_met
                ):
                    log.info(
                        "sr_filter_skip",
                        side=signal.side,
                        close=round(float(c.close), 4),
                        support=round(support, 4) if support is not None else None,
                        resistance=round(resistance, 4) if resistance is not None else None,
                    )
                    return

            # Position size
            bal = float(metrics.balance or 0.0)
            size = sizer.compute(balance=bal, score=signal.score)
            if not size.allowed:
                log.info("signal_but_no_size", side=signal.side, score=signal.score, reason=size.reason)
                return

            take_profit_usd: Optional[float] = None
            stop_loss_usd: Optional[float] = None
            if get_effective_contract_type(config) == "multiplier":
                mc = config.trading.multiplier
                tp_sl = compute_tp_sl_from_stake(
                    float(size.stake),
                    mc.take_profit_percent_of_stake,
                    mc.stop_loss_percent_of_stake,
                )
                take_profit_usd = tp_sl.take_profit_usd
                stop_loss_usd = tp_sl.stop_loss_usd

            intent = TradeIntent(
                symbol=c.symbol,
                side=signal.side,
                score=float(signal.score),
                stake=float(size.stake),
                reason=signal.reason,
                entry_price=float(c.close),
                take_profit_usd=take_profit_usd,
                stop_loss_usd=stop_loss_usd,
            )

            try:
                trade_queue.put_nowait(intent)
                log.info(
                    "trade_intent_enqueued",
                    side=intent.side,
                    score=round(intent.score, 3),
                    stake=intent.stake,
                )
            except asyncio.QueueFull:
                log.warning("trade_queue_full_skip")

        except Exception as e:
            log.error("on_candle_error", error=str(e), symbol=getattr(c, "symbol", "?"))
            repo.log_event(
                ts=utc_now().isoformat(),
                level="ERROR",
                type="on_candle",
                message="Exception in on_candle",
                data={"error": str(e)},
            )

    if use_multi_market:
        # Multi-mercado: un CandleBuilder, indicadores y tendencia 5m por símbolo
        # Actualizamos también el objeto global metrics para que la API/dashboard muestre indicadores y velas
        last_closed: Dict[str, Any] = {}
        last_indicators: Dict[str, Any] = {}
        recent_candles_buffers: Dict[str, deque] = {
            s: deque(maxlen=max(5, sr_cfg.lookback_candles)) for s in active_symbols
        }
        inds: Dict[str, IndicatorEngine] = {
            s: IndicatorEngine(
                ema_fast_period=config.trading.strategy.trend_pullback.ema_fast_period,
                ema_slow_period=config.trading.strategy.trend_pullback.ema_slow_period,
                atr_period=config.trading.strategy.trend_pullback.atr_period,
                rsi_period=config.trading.strategy.trend_pullback.rsi_period,
            )
            for s in active_symbols
        }
        htf_trends: Dict[str, HigherTimeframeTrend] = {
            s: HigherTimeframeTrend(timeframe_1m_blocks=htf_cfg.timeframe_minutes)
            for s in active_symbols
        }

        def on_candle_close_multi(c, sym: str) -> None:
            nonlocal metrics
            last_closed[sym] = c
            recent_candles_buffers[sym].append(c)
            upd = inds[sym].update(c)
            last_indicators[sym] = upd
            if upd is not None:
                htf_trends[sym].add_1m_candle(c)
                # Actualizar métricas globales para que la API y el dashboard muestren indicadores
                metrics.symbol = sym
                metrics.candles_closed += 1
                metrics.ema_fast = getattr(upd, "ema_fast", None)
                metrics.ema_slow = getattr(upd, "ema_slow", None)
                metrics.atr = getattr(upd, "atr", None)
                metrics.rsi = getattr(upd, "rsi", None)

        builders: Dict[str, CandleBuilder] = {}
        for sym in active_symbols:
            builders[sym] = CandleBuilder(
                symbol=sym,
                timeframe_sec=60,
                on_candle_closed=lambda closed, s=sym: on_candle_close_multi(closed, s),
            )

        async def on_tick_multi(msg: dict, symbol: str) -> None:
            nonlocal metrics
            try:
                tick = msg.get("tick") or {}
                q = tick.get("quote")
                e = tick.get("epoch")
                if q is None or e is None:
                    return
                price = float(q)
                metrics.symbol = symbol
                metrics.last_tick_price = price
                builders[symbol].update_with_tick(Tick(symbol=symbol, epoch=int(e), price=price))
            except Exception as ex:
                log.warning("on_tick_error", error=str(ex), symbol=symbol)

        last_processed_minute: Optional[Any] = None

        async def run_timer() -> None:
            nonlocal last_processed_minute
            while True:
                now = utc_now()
                next_minute = (now.replace(second=0, microsecond=0) + timedelta(minutes=1))
                await asyncio.sleep(max(0.5, (next_minute - now).total_seconds()))
                now = utc_now()
                prev_minute = (now - timedelta(seconds=60)).replace(second=0, microsecond=0)
                if last_processed_minute == prev_minute:
                    continue
                last_processed_minute = prev_minute
                candidates: List[tuple] = []
                for s in active_symbols:
                    c = last_closed.get(s)
                    if not c:
                        continue
                    if c.open_time.replace(second=0, microsecond=0) != prev_minute:
                        continue
                    ind = last_indicators.get(s)
                    if ind is None:
                        continue
                    if hasattr(inds[s], "is_ready") and callable(getattr(inds[s], "is_ready")) and not inds[s].is_ready():
                        continue
                    signal = strategy.generate(c, ind)
                    if signal.side == "NONE":
                        continue
                    if htf_cfg.enabled and not htf_trends[s].is_aligned(signal.side, allow_neutral=htf_cfg.allow_neutral):
                        continue
                    if not passes_quality_filter(signal.side, signal.score, ind, c, qf_cfg):
                        continue
                    if sr_cfg.enabled:
                        buf = list(recent_candles_buffers[s])
                        support, resistance = compute_levels(buf, sr_cfg.min_candles)
                        min_candles_met = len(buf) >= sr_cfg.min_candles
                        if not passes_sr_filter(
                            signal.side, float(c.close), support, resistance, sr_cfg.near_pct, min_candles_met
                        ):
                            continue
                    candidates.append((s, signal, c))
                if not candidates:
                    continue
                ks.load()
                if ks.state.enabled:
                    continue
                best_s, best_signal, best_c = max(candidates, key=lambda x: x[1].score)
                bal = float(metrics.balance or 0.0)
                size = sizer.compute(balance=bal, score=best_signal.score)
                if not size.allowed:
                    log.info("signal_but_no_size", symbol=best_s, side=best_signal.side, score=best_signal.score, reason=size.reason)
                    continue
                take_profit_usd: Optional[float] = None
                stop_loss_usd: Optional[float] = None
                if get_effective_contract_type(config) == "multiplier":
                    mc = config.trading.multiplier
                    tp_sl = compute_tp_sl_from_stake(
                        float(size.stake),
                        mc.take_profit_percent_of_stake,
                        mc.stop_loss_percent_of_stake,
                    )
                    take_profit_usd = tp_sl.take_profit_usd
                    stop_loss_usd = tp_sl.stop_loss_usd
                intent = TradeIntent(
                    symbol=best_s,
                    side=best_signal.side,
                    score=float(best_signal.score),
                    stake=float(size.stake),
                    reason=best_signal.reason,
                    entry_price=float(best_c.close),
                    take_profit_usd=take_profit_usd,
                    stop_loss_usd=stop_loss_usd,
                )
                try:
                    trade_queue.put_nowait(intent)
                    log.info("trade_intent_enqueued", symbol=best_s, side=intent.side, score=round(intent.score, 3), stake=intent.stake)
                except asyncio.QueueFull:
                    log.warning("trade_queue_full_skip")

    else:
        cb = CandleBuilder(
            symbol=config.trading.symbol,
            timeframe_sec=60,
            on_candle_closed=on_candle,
        )

        async def on_tick(msg) -> None:
            nonlocal metrics
            try:
                tick = msg.get("tick") or {}
                q = tick.get("quote")
                e = tick.get("epoch")
                if q is None or e is None:
                    return

                price = float(q)
                epoch = int(e)

                metrics.last_tick_price = price
                cb.update_with_tick(Tick(symbol=config.trading.symbol, epoch=epoch, price=price))

            except Exception as ex:
                log.warning("on_tick_error", error=str(ex))

    # ---- STARTUP ----
    await client.start()
    await client.wait_until_connected()
    metrics.connected = True

    try:
        # Start worker
        asyncio.create_task(trade_worker())

        # Fetch balance at startup and refresh periodically so the dashboard stays in sync with Deriv
        async def refresh_balance_every(interval_sec: float) -> None:
            while True:
                try:
                    balance_resp = await client.request({"balance": 1, "subscribe": 0})
                    bal = (balance_resp.get("balance") or {}).get("balance")
                    if bal is not None:
                        metrics.balance = float(bal)
                        log.debug("balance_refreshed", balance=metrics.balance)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.warning("balance_refresh_failed", error=str(e))
                await asyncio.sleep(interval_sec)

        balance_resp = await client.request({"balance": 1, "subscribe": 0})
        bal = (balance_resp.get("balance") or {}).get("balance")
        if bal is not None:
            metrics.balance = float(bal)
            log.info("balance", balance=metrics.balance)
            repo.log_event(
                ts=utc_now().isoformat(),
                level="INFO",
                type="balance",
                message="Balance fetched",
                data={"balance": metrics.balance, "env": config.environment},
            )
        asyncio.create_task(refresh_balance_every(60.0))  # refresh every 60 seconds

        # Fetch allowed multipliers from Deriv per market (R_50, R_75, R_100 have different allowed levers)
        if get_effective_contract_type(config) == "multiplier":
            try:
                if use_multi_market and len(active_symbols) >= 2:
                    await fetch_and_cache_multipliers_all(
                        client,
                        active_symbols,
                        config.trading.stake_currency,
                        config.trading.multiplier.multiplier,
                    )
                else:
                    symbol_for_mult = active_symbols[0] if active_symbols else config.trading.symbol
                    await fetch_and_cache_multipliers(
                        client,
                        symbol_for_mult,
                        config.trading.stake_currency,
                        config.trading.multiplier.multiplier,
                    )
            except Exception as e:
                log.warning("multiplier_cache_at_startup_failed", error=str(e))

        # Subscribe to ticks (multi: uno por símbolo + timer; single: un solo stream)
        if use_multi_market:
            asyncio.create_task(run_timer())
            for sym in active_symbols:
                await client.subscribe(
                    name=f"ticks_{sym}",
                    request={"ticks": sym, "subscribe": 1},
                    on_message=lambda msg, s=sym: on_tick_multi(msg, s),
                )
            log.info("engine_started", symbols=active_symbols, dry_run=config.development.dry_run)
            repo.log_event(
                ts=utc_now().isoformat(),
                level="INFO",
                type="engine",
                message="Engine started (multi-market)",
                data={"symbols": active_symbols, "dry_run": config.development.dry_run},
            )
        else:
            await client.subscribe(
                name="ticks",
                request={"ticks": config.trading.symbol, "subscribe": 1},
                on_message=on_tick,
            )
            log.info("engine_started", symbol=config.trading.symbol, dry_run=config.development.dry_run)
            repo.log_event(
                ts=utc_now().isoformat(),
                level="INFO",
                type="engine",
                message="Engine started",
                data={"symbol": config.trading.symbol, "dry_run": config.development.dry_run},
            )

        while True:
            # Keep kill-switch refreshed for UI / manual triggers
            ks.load()
            # Detección de caída/reconexión: así sabes en el dashboard y en Eventos si la conexión se cayó
            was_connected = metrics.connected
            metrics.connected = client.is_connected
            if was_connected and not metrics.connected:
                log.warning("ws_disconnected", message="Conexión con Deriv perdida. El cliente intenta reconectar.")
                try:
                    repo.log_event(
                        ts=utc_now().isoformat(),
                        level="WARNING",
                        type="ws_disconnected",
                        message="Conexión con Deriv perdida. Reconectando…",
                        data={"hint": "En Métricas verás 'Motor conectado: No' hasta que vuelva."},
                    )
                except Exception:
                    pass
            if not was_connected and metrics.connected:
                log.info("ws_reconnected", message="Reconectado a Deriv")
                try:
                    repo.log_event(
                        ts=utc_now().isoformat(),
                        level="INFO",
                        type="ws_reconnected",
                        message="Reconectado a Deriv",
                        data={},
                    )
                except Exception:
                    pass
            write_metrics(metrics.to_dict() if hasattr(metrics, "to_dict") else metrics.__dict__)
            try:
               repo.log_event(
               ts=utc_now().isoformat(),
               level="INFO",
               type="metrics",
               message="Metrics snapshot",
               data=asdict(metrics),
        ) 
            except Exception as e:
               log.warning("metrics_persist_failed", error=str(e))
            try:
                await asyncio.sleep(5.0)
            except asyncio.CancelledError:
                break


    finally:
        await client.stop()
        log.info("engine_stopped")
