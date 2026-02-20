import Card from "../components/Card";
import { getSymbolDisplay, fmt } from "../utils/deriv";

const cardStyle = { padding: 14, border: "1px solid #2d2d2d", borderRadius: 12, background: "#1a1a1a" };

function getMultiplierSummary(config) {
  const m = config?.multiplier_from_deriv;
  const symbols = m?.symbols && typeof m.symbols === "object" ? m.symbols : null;
  if (symbols && Object.keys(symbols).length > 0) {
    return Object.entries(symbols).map(([sym, data]) => {
      const res = data?.resolved ?? data?.allowed?.[0];
      return res != null ? `${sym}: ${res}x` : null;
    }).filter(Boolean);
  }
  if (m?.resolved != null) return [`${m.resolved}x`];
  if (config?.multiplier?.multiplier != null) return [`${config.multiplier.multiplier}x (config)`];
  return [];
}

export default function MetricasTab({ health, metrics, config }) {
  const balance = metrics?.balance != null ? Number(metrics.balance).toLocaleString("en-US", { minimumFractionDigits: 2 }) : null;
  const isReal = health?.env === "REAL";
  const contractType = config?.contract_type ?? health?.contract_type ?? "rise_fall";
  const isMultiplier = contractType === "multiplier";
  const multiMarket = config?.multi_market === true && Array.isArray(config?.symbols) && config.symbols.length >= 2;
  const marketDisplay = multiMarket
    ? `Multi-mercado (${(config.symbols || []).join(", ")})`
    : getSymbolDisplay(metrics?.symbol ?? config?.symbol);
  const duration = config?.multiplier?.duration != null && config?.multiplier?.duration_unit
    ? (() => {
        const d = Number(config.multiplier.duration);
        const u = String(config.multiplier.duration_unit).toLowerCase();
        if (u === "m") return d === 1 ? "1 min" : `${d} min`;
        if (u === "s") return d === 60 ? "1 min" : `${d} s`;
        if (u === "h") return `${d} h`;
        return `${d} ${u}`;
      })()
    : null;
  const multiplierLines = getMultiplierSummary(config);
  const currentSymbolLever = metrics?.symbol && config?.multiplier_from_deriv?.symbols?.[metrics.symbol]
    ? config.multiplier_from_deriv.symbols[metrics.symbol].resolved
    : null;

  return (
    <div style={{ marginTop: 0 }}>
      {balance != null && (
        <div style={{ ...cardStyle, marginBottom: 20, padding: "16px 20px", borderLeft: `4px solid ${isReal ? "#f59e0b" : "#06b6d4"}` }}>
          <div style={{ fontSize: 11, color: "#a1a1aa", textTransform: "uppercase", letterSpacing: "0.02em" }}>Resumen</div>
          <div style={{ fontSize: 24, fontWeight: 800, color: "#e4e4e7", marginTop: 6 }}>
            Saldo actual: <span style={{ color: isReal ? "#f59e0b" : "#22d3ee" }}>{balance} USD</span>
          </div>
          <div style={{ fontSize: 12, color: "#71717a", marginTop: 4 }}>
            {marketDisplay} · {metrics?.connected ? "Conectado a Deriv" : "Desconectado"}
          </div>
        </div>
      )}

      <div style={{ fontSize: 14, fontWeight: 700, color: "#f4f4f5", marginBottom: 14 }}>Estado y conexión</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12, marginBottom: 24 }}>
        <Card dark title="Entorno" value={health?.env ?? "-"} sub="DEMO o REAL" />
        <Card dark title="Motor conectado" value={metrics?.connected ? "Sí" : "No"} sub="Conexión a Deriv" />
        <Card dark title="Mercado operado" value={marketDisplay} sub={multiMarket ? "Varios símbolos" : (metrics?.symbol ? "Código: " + metrics.symbol : undefined)} />
      </div>

      {isMultiplier && (duration || multiplierLines.length > 0) && (
        <div style={{ fontSize: 14, fontWeight: 700, color: "#f4f4f5", marginBottom: 14 }}>Contrato multiplicador</div>
      )}
      {isMultiplier && (duration || multiplierLines.length > 0) && (
        <div style={{ ...cardStyle, marginBottom: 24, padding: "16px 20px" }}>
          {duration && (
            <div style={{ marginBottom: multiplierLines.length ? 12 : 0 }}>
              <div style={{ fontSize: 11, color: "#a1a1aa", textTransform: "uppercase", letterSpacing: "0.02em" }}>Duración máxima del contrato</div>
              <div style={{ fontSize: 16, fontWeight: 600, color: "#22d3ee", marginTop: 4 }}>{duration}</div>
            </div>
          )}
          {multiplierLines.length > 0 && (
            <div>
              <div style={{ fontSize: 11, color: "#a1a1aa", textTransform: "uppercase", letterSpacing: "0.02em" }}>Lever por mercado (según Deriv)</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: "#e4e4e7", marginTop: 4 }}>
                {multiplierLines.join(" · ")}
              </div>
              {currentSymbolLever != null && metrics?.symbol && (
                <div style={{ fontSize: 12, color: "#71717a", marginTop: 6 }}>
                  Símbolo actual en métricas ({metrics.symbol}): <strong style={{ color: "#22d3ee" }}>{currentSymbolLever}x</strong>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div style={{ fontSize: 14, fontWeight: 700, color: "#f4f4f5", marginBottom: 14 }}>Mercado</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12, marginBottom: 24 }}>
        <Card dark title="Saldo (Deriv)" value={balance != null ? balance : "-"} sub="Actualizado ~60 s" />
        <Card dark title="Último precio" value={fmt(metrics?.last_tick_price)} sub="Tick actual" />
        <Card dark title="Velas cerradas (1 min)" value={metrics?.candles_closed ?? 0} sub="Contador" />
      </div>

      <div style={{ fontSize: 14, fontWeight: 700, color: "#f4f4f5", marginBottom: 14 }}>Indicadores técnicos</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
        <Card dark title="EMA rápida" value={fmt(metrics?.ema_fast)} />
        <Card dark title="EMA lenta" value={fmt(metrics?.ema_slow)} />
        <Card dark title="ATR (volatilidad)" value={fmt(metrics?.atr)} />
        <Card dark title="RSI" value={fmt(metrics?.rsi)} />
      </div>
    </div>
  );
}
