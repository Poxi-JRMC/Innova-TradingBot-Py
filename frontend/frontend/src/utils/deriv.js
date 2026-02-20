/** Nombres legibles de símbolos Deriv (código API → nombre en la plataforma) */
export const DERIV_SYMBOL_NAMES = {
  R_10: "Volatility 10 Index",
  R_25: "Volatility 25 Index",
  R_50: "Volatility 50 Index",
  R_75: "Volatility 75 Index",
  R_100: "Volatility 100 Index",
  R_CRASH_500: "Crash 500 Index",
  R_BOOM_500: "Boom 500 Index",
  R_CRASH_1000: "Crash 1000 Index",
  R_BOOM_1000: "Boom 1000 Index",
  JDX50: "Jump 50 Index",
  JDX75: "Jump 75 Index",
  JDX100: "Jump 100 Index",
  RDBULL: "Step Index (Bull)",
  RDBEAR: "Step Index (Bear)",
  RNG30: "Range Break 30",
  RNG50: "Range Break 50",
  RNG75: "Range Break 75",
  RNG100: "Range Break 100",
  FRXEURUSD: "EUR/USD",
  FRXGBPUSD: "GBP/USD",
  FRXUSDJPY: "USD/JPY",
  FRXAUDUSD: "AUD/USD",
};

export function getSymbolDisplay(symbol) {
  if (!symbol) return "-";
  const name = DERIV_SYMBOL_NAMES[symbol];
  return name ? `${name} (${symbol})` : symbol;
}

export function fmt(v) {
  if (v === null || v === undefined) return "-";
  if (typeof v === "number") return v.toFixed(4);
  return String(v);
}
