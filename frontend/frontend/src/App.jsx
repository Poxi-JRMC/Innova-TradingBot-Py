import "./App.css";
import { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import Badge from "./components/Badge";
import { TABS } from "./config/tabs";
import InicioTab from "./views/InicioTab";
import MetricasTab from "./views/MetricasTab";
import TradesTab from "./views/TradesTab";
import EventosTab from "./views/EventosTab";

const API = import.meta.env.VITE_API_BASE || (import.meta.env.DEV ? "" : "http://127.0.0.1:8000");
const API_BASE_URL = (API === "" ? "" : API) + (import.meta.env.DEV && API === "" ? "/api" : "");

export default function App() {
  const [activeTab, setActiveTab] = useState("inicio");
  const [health, setHealth] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [events, setEvents] = useState([]);
  const [trades, setTrades] = useState([]);
  const [killswitch, setKillswitch] = useState(null);
  const [config, setConfig] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [toastMessage, setToastMessage] = useState("");
  const scrollByTab = useRef({});

  const api = useMemo(() => axios.create({ baseURL: API_BASE_URL || API, timeout: 8000 }), []);

  async function loadAll() {
    try {
      setErr("");
      const [h, m, e, t, k, cfg] = await Promise.all([
        api.get("/health"),
        api.get("/metrics"),
        api.get("/events", { params: { limit: 200 } }),
        api.get("/trades", { params: { limit: 200 } }),
        api.get("/killswitch"),
        api.get("/config").catch(() => ({ data: null })),
      ]);
      setHealth(h.data);
      setMetrics(m.data?.metrics?.data ?? null);
      setEvents(e.data?.events ?? []);
      setTrades(t.data?.trades ?? []);
      setKillswitch(k.data);
      setConfig(cfg?.data ?? null);
      setLastUpdate(Date.now());
    } catch (ex) {
      const msg = ex?.response?.data?.detail || ex.message || "Error";
      const isNetwork = !ex?.response && (msg === "Network Error" || msg.includes("ERR_"));
      setErr(
        isNetwork
          ? "No se puede conectar con la API. ¿Está corriendo? En otra terminal ejecuta: cd backend → .\\.venv\\Scripts\\python.exe -m src.app.main api"
          : msg
      );
    } finally {
      setLoading(false);
    }
  }

  async function enableKillSwitch() {
    const reason = prompt("Reason (optional):", "manual");
    try {
      await api.post("/killswitch/enable", { reason: reason || "manual" });
      await loadAll();
    } catch (ex) {
      setErr(ex?.response?.data?.detail || ex.message || "Error");
    }
  }

  async function disableKillSwitch() {
    try {
      await api.post("/killswitch/disable");
      await loadAll();
    } catch (ex) {
      setErr(ex?.response?.data?.detail || ex.message || "Error");
    }
  }

  async function saveConfig(updates) {
    try {
      await api.post("/config", updates);
      await loadAll();
      setToastMessage("Configuración guardada. Aplica en la siguiente operación.");
    } catch (ex) {
      setErr(ex?.response?.data?.detail || ex.message || "Error");
    }
  }

  async function clearTrades() {
    try {
      await api.delete("/trades");
      await loadAll();
      setToastMessage("Historial borrado");
    } catch (ex) {
      setErr(ex?.response?.data?.detail || ex.message || "Error");
    }
  }

  async function clearTradesInRange(fromDate, toDate) {
    try {
      await api.delete("/trades", { params: { from_date: fromDate, to_date: toDate } });
      await loadAll();
      setToastMessage("Trades del período borrados");
    } catch (ex) {
      setErr(ex?.response?.data?.detail || ex.message || "Error");
    }
  }

  useEffect(() => {
    if (!toastMessage) return;
    const t = setTimeout(() => setToastMessage(""), 3000);
    return () => clearTimeout(t);
  }, [toastMessage]);

  useEffect(() => {
    loadAll();
    const id = setInterval(loadAll, 3000);
    return () => clearInterval(id);
  }, []);

  function handleTabChange(nextTab) {
    scrollByTab.current[activeTab] = window.scrollY;
    setActiveTab(nextTab);
  }

  useEffect(() => {
    const saved = scrollByTab.current[activeTab];
    if (saved != null) {
      const t = requestAnimationFrame(() => window.scrollTo(0, saved));
      return () => cancelAnimationFrame(t);
    }
  }, [activeTab]);

  const rentabilidad = useMemo(() => {
    const cerrados = (trades || []).filter((t) => t.pnl != null && t.pnl !== "");
    const totalPnl = cerrados.reduce((sum, t) => sum + Number(t.pnl) || 0, 0);
    const ganadas = cerrados.filter((t) => Number(t.pnl) > 0).length;
    const perdidas = cerrados.filter((t) => Number(t.pnl) <= 0).length;
    const total = ganadas + perdidas;
    const winRate = total > 0 ? Math.round((ganadas / total) * 100) : 0;
    return { totalPnl, ganadas, perdidas, total, winRate };
  }, [trades]);

  const [secondsAgo, setSecondsAgo] = useState(null);
  useEffect(() => {
    if (lastUpdate == null) return;
    const update = () => setSecondsAgo(Math.max(0, Math.floor((Date.now() - lastUpdate) / 1000)));
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [lastUpdate]);

  return (
    <div className="app-dark" style={{ fontFamily: "system-ui", padding: 16, maxWidth: 1200, margin: "0 auto", background: "#0d0d0d", minHeight: "100vh", color: "#e4e4e7" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
          padding: "12px 16px",
          background: "#1a1a1a",
          border: "1px solid #2d2d2d",
          borderRadius: 12,
          marginBottom: 4,
        }}
      >
        <h2 style={{ margin: 0, fontSize: "1.35rem", color: "#f4f4f5" }}>Deriv Trading Bot Dashboard</h2>
        <Badge ok={!err} />
        {!err && (
          <span className="live-dot" style={{ width: 8, height: 8, borderRadius: "50%", background: "#22c55e", flexShrink: 0 }} title="Conectado" />
        )}
        <span style={{ color: "#a1a1aa", fontSize: 13 }}>{API_BASE_URL || API || "proxy /api"}</span>
        {lastUpdate != null && (
          <span style={{ marginLeft: "auto", fontSize: 12, color: "#71717a" }}>
            Última actualización: {secondsAgo != null ? `hace ${secondsAgo} s` : "—"}
          </span>
        )}
      </div>

      {loading && !err && (
        <div style={{ marginTop: 12, padding: 14, borderRadius: 8, background: "#1a1a1a", border: "1px solid #2d2d2d", color: "#a1a1aa", fontSize: 14 }}>
          Cargando…
        </div>
      )}

      {err && (
        <div style={{ marginTop: 12, padding: 14, borderRadius: 8, background: "rgba(220,38,38,0.2)", border: "1px solid #dc2626", color: "#fca5a5" }}>
          <strong>Error de conexión</strong>
          <p style={{ margin: "8px 0 0 0" }}>{err}</p>
          <p style={{ margin: "8px 0 0 0", fontSize: 13, opacity: 0.9 }}>
            La API debe estar corriendo en el puerto 8000. Abre una terminal, entra en la carpeta <code>botTrading\backend</code> y ejecuta: <code>.\.venv\Scripts\python.exe -m src.app.main api</code> (o ejecuta el script <code>iniciar_api.bat</code> que está en esa carpeta).
          </p>
          <button
            type="button"
            onClick={() => { setLoading(true); loadAll(); }}
            style={{ marginTop: 12, padding: "8px 16px", fontSize: 13, fontWeight: 600, background: "#dc2626", color: "white", border: "none", borderRadius: 8, cursor: "pointer" }}
          >
            Reintentar
          </button>
        </div>
      )}

      <nav style={{ marginTop: 16, display: "flex", gap: 0, borderBottom: "1px solid #2d2d2d", minHeight: 44 }}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => handleTabChange(tab.id)}
            className="tab-btn-dark"
            style={{
              padding: "10px 20px",
              minWidth: 100,
              border: "none",
              borderBottom: activeTab === tab.id ? "2px solid #06b6d4" : "2px solid transparent",
              background: activeTab === tab.id ? "rgba(6,182,212,0.15)" : "transparent",
              color: activeTab === tab.id ? "#22d3ee" : "#a1a1aa",
              fontWeight: activeTab === tab.id ? 600 : 400,
              cursor: "pointer",
              fontSize: 14,
              borderRadius: "8px 8px 0 0",
              flexShrink: 0,
            }}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {toastMessage && (
        <div
          style={{
            position: "fixed",
            bottom: 24,
            left: "50%",
            transform: "translateX(-50%)",
            padding: "12px 20px",
            borderRadius: 10,
            background: "#1a1a1a",
            border: "1px solid #22c55e",
            color: "#22c55e",
            fontSize: 14,
            fontWeight: 600,
            zIndex: 9999,
            boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
          }}
        >
          {toastMessage}
        </div>
      )}

      <div style={{ paddingTop: 20, paddingBottom: 40, width: "100%", maxWidth: 1200, margin: "0 auto" }}>
        {activeTab === "inicio" && (
          <InicioTab
            rentabilidad={rentabilidad}
            killswitch={killswitch}
            health={health}
            config={config}
            metrics={metrics}
            trades={trades}
            onEnableKillSwitch={enableKillSwitch}
            onDisableKillSwitch={disableKillSwitch}
            onSaveConfig={saveConfig}
          />
        )}
        {activeTab === "metricas" && <MetricasTab health={health} metrics={metrics} config={config} />}
        {activeTab === "trades" && <TradesTab trades={trades} onClearTrades={clearTrades} onClearTradesInRange={clearTradesInRange} onShowToast={setToastMessage} />}
        {activeTab === "eventos" && <EventosTab events={events} />}
      </div>
    </div>
  );
}
