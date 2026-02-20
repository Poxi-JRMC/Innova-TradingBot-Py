import { useMemo, useState, useEffect } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { getSymbolDisplay } from "../utils/deriv";

export default function InicioTab({ rentabilidad, killswitch, health, config, metrics, trades, onEnableKillSwitch, onDisableKillSwitch, onSaveConfig }) {
  const [chartKey, setChartKey] = useState(0);
  const [contractTypeSelect, setContractTypeSelect] = useState(null);
  const [savingConfig, setSavingConfig] = useState(false);
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "visible") setChartKey((k) => k + 1);
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);
  const balance = metrics?.balance != null ? Number(metrics.balance).toLocaleString("en-US", { minimumFractionDigits: 2 }) : "-";
  const lastStake = trades?.length > 0 && trades[0].stake != null ? Number(trades[0].stake).toFixed(2) : "-";
  const lastTrade = trades?.length > 0 ? trades[0] : null;
  const effectiveContractType = config?.contract_type ?? health?.contract_type ?? "rise_fall";
  const contractTypeLabel = effectiveContractType === "multiplier" ? "Multiplicador" : "Rise/Fall 1m";
  const marketSymbol = config?.symbol ?? metrics?.symbol;
  const multiMarket = config?.multi_market === true && Array.isArray(config?.symbols) && config.symbols.length >= 2;
  const marketDisplay = multiMarket
    ? `Multi-mercado (${config.symbols.join(", ")})`
    : getSymbolDisplay(marketSymbol);
  const accountType = health?.env === "REAL" ? "Real" : health?.env === "DEMO" ? "Demo" : health?.env ?? "-";

  const currentSelectValue = contractTypeSelect !== null ? contractTypeSelect : effectiveContractType;

  // Duración del multiplicador: ej. 60 + "s" → "1 min", 2 + "m" → "2 min"
  const multiplierConfig = config?.multiplier;
  const durationLabel =
    multiplierConfig?.duration != null && multiplierConfig?.duration_unit
      ? (() => {
          const d = Number(multiplierConfig.duration);
          const u = String(multiplierConfig.duration_unit).toLowerCase();
          if (u === "s") return d === 60 ? "1 min" : d < 60 ? `${d} s` : `${d / 60} min`;
          if (u === "m") return d === 1 ? "1 min" : `${d} min`;
          if (u === "h") return d === 1 ? "1 h" : `${d} h`;
          return `${d} ${u}`;
        })()
      : null;
  // Lever por mercado: Deriv permite distintos multiplicadores por símbolo (R_50, R_75, R_100, etc.)
  const multiplierFromDeriv = config?.multiplier_from_deriv;
  const symbolsLever = multiplierFromDeriv?.symbols && typeof multiplierFromDeriv.symbols === "object" ? multiplierFromDeriv.symbols : null;
  const resolvedMult = multiplierFromDeriv?.resolved != null ? Number(multiplierFromDeriv.resolved) : multiplierConfig?.multiplier != null ? Number(multiplierConfig.multiplier) : null;
  const leverageLabel = symbolsLever && Object.keys(symbolsLever).length > 0
    ? Object.entries(symbolsLever).map(([sym, d]) => (d?.resolved != null ? `${sym}: ${d.resolved}x` : null)).filter(Boolean).join(" · ")
    : resolvedMult != null ? `${resolvedMult}x` : null;
  const leverageSubLabel = symbolsLever
    ? "Según Deriv (cada mercado tiene sus levers permitidos)"
    : multiplierFromDeriv ? (Array.isArray(multiplierFromDeriv.allowed) && multiplierFromDeriv.allowed.length ? `Desde Deriv · Permitidos: ${multiplierFromDeriv.allowed.slice(0, 10).join(", ")}${multiplierFromDeriv.allowed.length > 10 ? "…" : ""}` : "Desde Deriv") : "Config";

  async function handleSaveConfig() {
    if (!onSaveConfig) return;
    setSavingConfig(true);
    try {
      await onSaveConfig({ contract_type: currentSelectValue });
      setContractTypeSelect(null);
    } finally {
      setSavingConfig(false);
    }
  }

  const cardStyle = { background: "#1a1a1a", border: "1px solid #2d2d2d", color: "#e4e4e7" };
  const labelStyle = { fontSize: 11, color: "#a1a1aa", textTransform: "uppercase", letterSpacing: "0.02em" };
  const valueGreen = "#22c55e";
  const valueRed = "#ef4444";

  const equityData = useMemo(() => {
    const cerrados = (trades || []).filter((t) => t.pnl != null && t.pnl !== "");
    if (cerrados.length === 0) return [];
    const sorted = [...cerrados].sort((a, b) => new Date(a.entry_time) - new Date(b.entry_time));
    let cum = 0;
    return sorted.map((t) => {
      cum += Number(t.pnl) || 0;
      return {
        date: (t.entry_time || "").slice(0, 10),
        pnl: Number(t.pnl) || 0,
        cumulative: cum,
      };
    });
  }, [trades]);

  const dryRun = config?.dry_run === true;
  const canOperate = !dryRun && !killswitch?.enabled;
  const noTradesYet = (rentabilidad?.total ?? 0) === 0;

  return (
    <>
      {/* Estado: simulación vs listo para operar + hint si no hay operaciones */}
      {config != null && (
        <div
          style={{
            marginBottom: 16,
            padding: "12px 16px",
            borderRadius: 10,
            border: "1px solid #2d2d2d",
            background: canOperate ? "rgba(34,197,94,0.1)" : "rgba(113,113,122,0.15)",
            fontSize: 13,
            color: "#e4e4e7",
          }}
        >
          <strong style={{ color: canOperate ? "#22c55e" : "#a1a1aa" }}>
            {canOperate ? "Listo para operar" : dryRun ? "Modo simulación (no se abren operaciones)" : killswitch?.enabled ? "Pausado (interruptor de emergencia)" : "Estado"}
          </strong>
          {dryRun && (
            <span style={{ marginLeft: 8, color: "#a1a1aa" }}>
              Para abrir operaciones: pon <code style={{ background: "#2d2d2d", padding: "2px 6px", borderRadius: 4 }}>development.dry_run: false</code> en <code style={{ background: "#2d2d2d", padding: "2px 6px", borderRadius: 4 }}>config/default.yaml</code> o <code style={{ background: "#2d2d2d", padding: "2px 6px", borderRadius: 4 }}>DEVELOPMENT__DRY_RUN=0</code> en <code>.env</code> y reinicia el motor.
            </span>
          )}
          {noTradesYet && canOperate && (
            <div style={{ marginTop: 8, color: "#a1a1aa" }}>
              Aún no hay operaciones. El motor abrirá una cuando la estrategia genere una señal (puede tardar varios minutos). Revisa la pestaña <strong>Eventos</strong> para ver <code>trade_open</code> o <code>dry_run_skip</code>.
            </div>
          )}
          {noTradesYet && dryRun && (
            <div style={{ marginTop: 8, color: "#a1a1aa" }}>
              En Eventos verás <code>dry_run_skip</code> cuando haya una señal que no se ejecuta por estar en simulación.
            </div>
          )}
        </div>
      )}

      {/* Fila: Resumen de rentabilidad + Interruptor de emergencia a la misma altura */}
      <div style={{ display: "flex", gap: 20, alignItems: "flex-start", flexWrap: "wrap", marginTop: 0 }}>
        {/* Resumen de rentabilidad */}
        <div
          style={{
            padding: "20px 24px",
            borderRadius: 12,
            border: "1px solid #2d2d2d",
            background: "#1a1a1a",
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 18,
            alignItems: "stretch",
            flex: "1 1 600px",
            minWidth: 0,
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 700, color: "#f4f4f5", gridColumn: "1 / -1", marginBottom: 4 }}>Resumen de rentabilidad</div>

          {/* Columna izquierda: 3 bloques */}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ ...cardStyle, padding: 14, borderRadius: 10 }}>
              <div style={labelStyle}>Mercado operado</div>
              <div style={{ fontSize: 15, fontWeight: 600, color: "#22d3ee", marginTop: 6 }}>{marketDisplay}</div>
            </div>
            <div style={{ ...cardStyle, padding: 14, borderRadius: 10 }}>
              <div style={labelStyle}>Cuenta</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: accountType === "Real" ? "#f59e0b" : "#22d3ee", marginTop: 6 }}>{accountType}</div>
              <div style={{ fontSize: 11, color: "#71717a", marginTop: 2 }}>{accountType === "Real" ? "Dinero real" : "Prueba"}</div>
            </div>
            <div style={{ ...cardStyle, padding: 14, borderRadius: 10 }}>
              <div style={labelStyle}>Saldo actual</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: "#22d3ee", marginTop: 6 }}>{balance}{balance !== "-" ? " USD" : ""}</div>
            </div>
          </div>

          {/* Columna derecha: 6 bloques en grid */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gridTemplateRows: "auto auto auto auto", gap: 12 }}>
            <div style={{ ...cardStyle, padding: 14, borderRadius: 10 }}>
              <div style={labelStyle}>Capital por operación</div>
              <div style={{ fontSize: 17, fontWeight: 700, color: "#e4e4e7", marginTop: 6 }}>{lastStake}{lastStake !== "-" ? " USD" : ""}</div>
              <div style={{ fontSize: 10, color: "#71717a", marginTop: 2 }}>Stake usado · Tipo: {contractTypeLabel}</div>
              {lastTrade && (lastTrade.take_profit != null || lastTrade.stop_loss != null) && (
                <div style={{ fontSize: 10, color: "#a1a1aa", marginTop: 6 }}>
                  TP: {lastTrade.take_profit != null ? Number(lastTrade.take_profit).toFixed(2) + " USD" : "-"} · SL: {lastTrade.stop_loss != null ? Number(lastTrade.stop_loss).toFixed(2) + " USD" : "-"}
                </div>
              )}
            </div>
            <div style={{ ...cardStyle, padding: 14, borderRadius: 10 }}>
              <div style={labelStyle}>PnL total</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: rentabilidad.totalPnl >= 0 ? valueGreen : valueRed, marginTop: 6 }}>
                {rentabilidad.total > 0 ? (rentabilidad.totalPnl >= 0 ? "+" : "") + Number(rentabilidad.totalPnl).toFixed(2) + " USD" : "0.00 USD"}
              </div>
            </div>
            <div style={{ ...cardStyle, padding: 14, borderRadius: 10, gridColumn: "1 / -1" }}>
              <div style={labelStyle}>Win rate</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: "#e4e4e7", marginTop: 4 }}>{rentabilidad.total > 0 ? rentabilidad.winRate + "%" : "-"}</div>
            </div>
            <div style={{ ...cardStyle, padding: 14, borderRadius: 10, gridColumn: "1 / -1" }}>
              <div style={labelStyle}>Estado</div>
              <span
                style={{
                  display: "inline-block",
                  marginTop: 6,
                  padding: "6px 12px",
                  borderRadius: 8,
                  fontSize: 14,
                  fontWeight: 700,
                  background: rentabilidad.totalPnl >= 0 ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)",
                  color: rentabilidad.totalPnl >= 0 ? valueGreen : valueRed,
                }}
              >
                {rentabilidad.total === 0 ? "Sin operaciones aún" : rentabilidad.totalPnl >= 0 ? "En profit" : "En pérdida"}
              </span>
              <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid #2d2d2d", fontSize: 12, color: "#a1a1aa" }}>
                Total operaciones: <strong style={{ color: "#e4e4e7" }}>{rentabilidad.total}</strong>
              </div>
            </div>
            <div style={{ ...cardStyle, padding: 14, borderRadius: 10 }}>
              <div style={labelStyle}>Ganadas</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: valueGreen, marginTop: 6 }}>{rentabilidad.ganadas}</div>
            </div>
            <div style={{ ...cardStyle, padding: 14, borderRadius: 10 }}>
              <div style={labelStyle}>Perdidas</div>
              <div style={{ fontSize: 22, fontWeight: 700, color: valueRed, marginTop: 6 }}>{rentabilidad.perdidas}</div>
            </div>
          </div>
        </div>

        {/* Interruptor de emergencia: misma altura, botones siempre visibles */}
        <div
          style={{
            padding: "20px 20px",
            borderRadius: 12,
            border: "1px solid #2d2d2d",
            background: "#1a1a1a",
            color: "#e4e4e7",
            flex: "0 0 auto",
            minWidth: 260,
          }}
        >
          <div style={{ fontSize: 11, color: "#a1a1aa", textTransform: "uppercase", letterSpacing: "0.02em", marginBottom: 10 }}>Interruptor de emergencia</div>
          <div style={{ fontSize: 15, fontWeight: 700, color: "#f4f4f5", marginBottom: 6 }}>
            {killswitch?.enabled ? "Pausado (no abre operaciones)" : "Activo (puede operar)"}
          </div>
          {killswitch?.reason && <div style={{ fontSize: 12, color: "#71717a", marginBottom: 12 }}>{killswitch.reason}</div>}
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 14 }}>
            <button onClick={onEnableKillSwitch} className="btn-kill-enable" style={{ width: "100%" }}>Pausar bot</button>
            <button onClick={onDisableKillSwitch} className="btn-kill-disable" style={{ width: "100%" }}>Reanudar bot</button>
          </div>
        </div>
      </div>

      {/* Mercado y tipo de contrato: se puede cambiar Multiplicador / Rise-Fall desde aquí */}
      <div
        style={{
          marginTop: 20,
          padding: "20px 24px",
          borderRadius: 12,
          border: "1px solid #2d2d2d",
          background: "#1a1a1a",
          display: "flex",
          flexWrap: "wrap",
          gap: 20,
          alignItems: "flex-end",
        }}
      >
        <div style={{ fontSize: 14, fontWeight: 700, color: "#f4f4f5", width: "100%", marginBottom: 4 }}>Configuración de operación</div>
        <div style={{ minWidth: 200 }}>
          <div style={{ ...labelStyle, marginBottom: 6 }}>Mercado actual</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: "#22d3ee" }}>{marketDisplay}</div>
          <div style={{ fontSize: 11, color: "#71717a", marginTop: 6 }}>
            {multiMarket
              ? "Modo multi-mercado: el bot elige cada minuto el símbolo con mejor señal entre los listados. Para cambiar: edita trading.symbols en config/default.yaml y reinicia."
              : "Para cambiar el mercado edita config/default.yaml → trading.symbol (o trading.symbols para multi-mercado) y reinicia el motor."}
          </div>
        </div>
        <div style={{ minWidth: 220 }}>
          <div style={{ ...labelStyle, marginBottom: 6 }}>Tipo de contrato</div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <select
              value={currentSelectValue}
              onChange={(e) => setContractTypeSelect(e.target.value)}
              style={{
                padding: "8px 12px",
                borderRadius: 8,
                border: "1px solid #2d2d2d",
                background: "#0d0d0d",
                color: "#e4e4e7",
                fontSize: 14,
                minWidth: 160,
              }}
            >
              <option value="rise_fall">Rise/Fall 1m</option>
              <option value="multiplier">Multiplicador</option>
            </select>
            <button
              type="button"
              onClick={handleSaveConfig}
              disabled={savingConfig || currentSelectValue === effectiveContractType}
              style={{
                padding: "8px 16px",
                borderRadius: 8,
                border: "1px solid #22d3ee",
                background: currentSelectValue !== effectiveContractType ? "rgba(34,211,238,0.15)" : "#2d2d2d",
                color: "#22d3ee",
                fontSize: 14,
                fontWeight: 600,
                cursor: savingConfig || currentSelectValue === effectiveContractType ? "not-allowed" : "pointer",
              }}
            >
              {savingConfig ? "Guardando…" : "Guardar"}
            </button>
          </div>
          <div style={{ fontSize: 11, color: "#71717a", marginTop: 6 }}>
            Aplica en la siguiente operación. Con Multiplicador se usan TP/SL según la config.
          </div>
        </div>
        {effectiveContractType === "multiplier" && (durationLabel || leverageLabel) && (
          <>
            {durationLabel && (
              <div style={{ minWidth: 140 }}>
                <div style={{ ...labelStyle, marginBottom: 6 }}>Duración del contrato</div>
                <div style={{ fontSize: 15, fontWeight: 600, color: "#e4e4e7" }}>{durationLabel}</div>
                <div style={{ fontSize: 11, color: "#71717a", marginTop: 4 }}>Alineado al análisis (ej. 1 min)</div>
              </div>
            )}
            {leverageLabel && (
              <div style={{ minWidth: 200 }}>
                <div style={{ ...labelStyle, marginBottom: 6 }}>Multiplicador (apalancamiento)</div>
                <div style={{ fontSize: 15, fontWeight: 600, color: "#e4e4e7" }}>{leverageLabel}</div>
                <div style={{ fontSize: 11, color: "#71717a", marginTop: 4 }}>{leverageSubLabel}</div>
              </div>
            )}
          </>
        )}
        {config?.higher_tf_trend?.enabled && (
          <div style={{ minWidth: 180 }}>
            <div style={{ ...labelStyle, marginBottom: 6 }}>Tendencia en temporalidad superior</div>
            <div style={{ fontSize: 14, fontWeight: 600, color: "#22c55e" }}>
              {config.higher_tf_trend.timeframe_minutes}m activo
            </div>
            <div style={{ fontSize: 11, color: "#71717a", marginTop: 4 }}>
              Solo opera cuando la señal 1m coincide con la tendencia {config.higher_tf_trend.timeframe_minutes}m (alcista/bajista).
            </div>
          </div>
        )}
      </div>

      {equityData.length > 0 && (
        <div style={{ marginTop: 20, padding: "16px 20px", borderRadius: 12, border: "1px solid #2d2d2d", background: "#1a1a1a", minHeight: 260 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#f4f4f5", marginBottom: 12 }}>Curva de PnL acumulado</div>
          <div key={chartKey} style={{ width: "100%", minWidth: 200, height: 220, minHeight: 220, position: "relative", overflow: "hidden" }}>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={equityData} margin={{ top: 8, right: 12, left: 8, bottom: 8 }}>
                <defs>
                  <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#06b6d4" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#06b6d4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#71717a" }} stroke="#2d2d2d" />
                <YAxis tick={{ fontSize: 10, fill: "#71717a" }} stroke="#2d2d2d" tickFormatter={(v) => v.toFixed(0)} />
                <Tooltip
                  contentStyle={{ background: "#1a1a1a", border: "1px solid #2d2d2d", borderRadius: 8 }}
                  labelStyle={{ color: "#e4e4e7" }}
                  formatter={(value) => { const v = Array.isArray(value) ? value[0] : value; return ["PnL acumulado: " + (v != null ? Number(v).toFixed(2) + " USD" : "-"), ""]; }}
                  labelFormatter={(label) => "Fecha: " + (label || "-")}
                />
                <Area type="monotone" dataKey="cumulative" stroke="#06b6d4" strokeWidth={2} fill="url(#pnlGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div style={{ marginTop: 20, padding: "12px 14px", background: "rgba(6,182,212,0.1)", border: "1px solid #2d2d2d", borderRadius: 8, fontSize: 13, color: "#a1a1aa" }}>
        <strong style={{ color: "#e4e4e7" }}>Referencia de símbolos Deriv:</strong> Volatilidad = R_10, R_25, R_50, R_75, R_100 · Crash/Boom = R_CRASH_500, R_BOOM_500 · Jump = JDX50, JDX75, JDX100 · Step = RDBULL, RDBEAR · Range Break = RNG30–RNG100 · Forex = FRXEURUSD, FRXGBPUSD. Símbolo en <code style={{ background: "#2d2d2d", padding: "2px 6px", borderRadius: 4 }}>backend/config/default.yaml</code> → <code style={{ background: "#2d2d2d", padding: "2px 6px", borderRadius: 4 }}>trading.symbol</code>.
      </div>
    </>
  );
}
