import { useMemo, useState, useEffect } from "react";
import { jsPDF } from "jspdf";
import { autoTable } from "jspdf-autotable";

function formatDateTime(isoStr) {
  if (!isoStr) return "-";
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    return d.toLocaleString("es-ES", {
      day: "2-digit",
      month: "2-digit",
      year: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return isoStr;
  }
}

function formatPnl(pnl) {
  if (pnl == null || pnl === "") return "-";
  const n = Number(pnl);
  if (isNaN(n)) return String(pnl);
  const sign = n >= 0 ? "+" : "";
  return sign + n.toFixed(2) + " USD";
}

function dateStr(isoStr) {
  if (!isoStr) return "";
  return isoStr.slice(0, 10);
}

/** Semana actual: los 7 días de la semana en curso (lunes a domingo). */
function getCurrentWeekRange() {
  const today = new Date();
  const dayOfWeek = today.getDay(); // 0 = domingo, 1 = lunes, ...
  const daysFromMonday = dayOfWeek === 0 ? 6 : dayOfWeek - 1;
  const monday = new Date(today);
  monday.setDate(today.getDate() - daysFromMonday);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  return {
    from: monday.toISOString().slice(0, 10),
    to: sunday.toISOString().slice(0, 10),
  };
}

function getMonthRange(year, month) {
  const lastDay = new Date(year, month, 0).getDate();
  return {
    from: `${year}-${String(month).padStart(2, "0")}-01`,
    to: `${year}-${String(month).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`,
  };
}

function getYearRange(year) {
  return { from: `${year}-01-01`, to: `${year}-12-31` };
}

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const PAGE_SIZE_OPTIONS = [25, 50, 100];

export default function TradesTab({ trades, onClearTrades, onClearTradesInRange, onShowToast }) {
  const currentYear = new Date().getFullYear();
  const [periodType, setPeriodType] = useState("all");
  const [selectedYear, setSelectedYear] = useState(currentYear);
  const [selectedMonth, setSelectedMonth] = useState(new Date().getMonth() + 1);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const dateRange = useMemo(() => {
    if (periodType === "all") return null;
    if (periodType === "week") return getCurrentWeekRange();
    if (periodType === "month") return getMonthRange(selectedYear, selectedMonth);
    if (periodType === "year") return getYearRange(selectedYear);
    return null;
  }, [periodType, selectedYear, selectedMonth]);

  const allTrades = useMemo(() => (trades || []).slice(0, 500), [trades]);

  const rows = useMemo(() => {
    if (!dateRange) return allTrades;
    return allTrades.filter((t) => {
      const d = dateStr(t.entry_time);
      return d >= dateRange.from && d <= dateRange.to;
    });
  }, [allTrades, dateRange]);

  const summary = useMemo(() => {
    const cerrados = rows.filter((t) => t.pnl != null && t.pnl !== "");
    const totalPnl = cerrados.reduce((sum, t) => sum + Number(t.pnl) || 0, 0);
    const ganadas = cerrados.filter((t) => Number(t.pnl) > 0).length;
    const perdidas = cerrados.filter((t) => Number(t.pnl) <= 0).length;
    const total = ganadas + perdidas;
    const winRate = total > 0 ? Math.round((ganadas / total) * 100) : 0;
    return { totalPnl, ganadas, perdidas, total, winRate };
  }, [rows]);

  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const rowsForPage = useMemo(
    () => rows.slice((page - 1) * pageSize, page * pageSize),
    [rows, page, pageSize]
  );

  useEffect(() => {
    setPage(1);
  }, [periodType, selectedYear, selectedMonth, rows.length, pageSize]);

  function handleClear() {
    if (dateRange) {
      if (!window.confirm(`¿Eliminar los trades del período ${dateRange.from} a ${dateRange.to}? No se puede deshacer.`)) return;
      onClearTradesInRange?.(dateRange.from, dateRange.to);
    } else {
      if (!window.confirm("¿Borrar todo el historial de trades? Esta acción no se puede deshacer.")) return;
      onClearTrades?.();
    }
  }

  function handleExportPdf() {
    const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
    doc.setFontSize(14);
    doc.text("Historial de trades - Deriv Trading Bot", 14, 12);
    doc.setFontSize(10);
    doc.text(new Date().toLocaleString("es-ES"), 14, 18);

    const periodLabel = dateRange
      ? `Período: ${dateRange.from} a ${dateRange.to}`
      : "Todos los trades";
    doc.text(periodLabel, 14, 24);

    doc.setFontSize(11);
    doc.setFont(undefined, "bold");
    doc.text(`Resumen:  Ganadas: ${summary.ganadas}  |  Perdidas: ${summary.perdidas}  |  Total: ${summary.total}  |  PnL: ${summary.totalPnl >= 0 ? "+" : ""}${summary.totalPnl.toFixed(2)} USD  |  Win rate: ${summary.winRate}%`, 14, 32);
    doc.setFont(undefined, "normal");

    const headers = hasTpSl
      ? ["Fecha / Hora", "Símbolo", "Dirección", "Stake", "TP", "SL", "PnL", "Resultado"]
      : ["Fecha / Hora", "Símbolo", "Dirección", "Stake", "PnL", "Resultado"];
    const data = rows.map((t) => {
      const pnlNum = t.pnl != null && t.pnl !== "" ? Number(t.pnl) : null;
      const res = pnlNum == null ? "-" : pnlNum > 0 ? "Ganada" : "Perdida";
      const base = [
        formatDateTime(t.entry_time),
        t.symbol ?? "-",
        t.side === "CALL" ? "Al alza (CALL)" : t.side === "PUT" ? "A la baja (PUT)" : t.side ?? "-",
        t.stake != null ? Number(t.stake).toFixed(2) : "-",
      ];
      if (hasTpSl) base.push(t.take_profit != null ? Number(t.take_profit).toFixed(2) : "-", t.stop_loss != null ? Number(t.stop_loss).toFixed(2) : "-");
      base.push(formatPnl(t.pnl), res);
      return base;
    });

    autoTable(doc, {
      head: [headers],
      body: data,
      startY: 38,
      styles: { fontSize: 8 },
      headStyles: { fillColor: [45, 45, 45] },
      alternateRowStyles: { fillColor: [245, 245, 245] },
    });

    const fileName = dateRange
      ? `trades_${dateRange.from}_${dateRange.to}.pdf`
      : `trades_${new Date().toISOString().slice(0, 10)}.pdf`;
    doc.save(fileName);
    onShowToast?.("PDF exportado");
  }

  const years = useMemo(() => {
    const arr = [];
    for (let y = currentYear; y >= currentYear - 5; y--) arr.push(y);
    return arr;
  }, [currentYear]);

  const hasFilter = periodType !== "all";
  const canDelete = hasFilter ? rows.length > 0 : allTrades.length > 0;
  const hasTpSl = (rows.length ? rows : allTrades).some((t) => t.take_profit != null || t.stop_loss != null);

  return (
    <div style={{ marginTop: 0 }}>
      <div style={{ marginBottom: 12 }}>
        <h3 style={{ margin: "0 0 12px 0", color: "#f4f4f5" }}>Historial de trades</h3>

        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, marginBottom: 12 }}>
          <span style={{ fontSize: 13, color: "#a1a1aa" }}>Período:</span>
          <select
            value={periodType}
            onChange={(e) => setPeriodType(e.target.value)}
            style={{
              padding: "6px 10px",
              fontSize: 13,
              background: "#1a1a1a",
              border: "1px solid #2d2d2d",
              borderRadius: 8,
              color: "#e4e4e7",
              cursor: "pointer",
            }}
          >
            <option value="all">Todo</option>
            <option value="week">Semana</option>
            <option value="month">Mes</option>
            <option value="year">Año</option>
          </select>

          {periodType === "week" && (
            <span style={{ fontSize: 13, color: "#22d3ee" }}>Esta semana (lun–dom)</span>
          )}

          {periodType === "month" && (
            <>
              <select
                value={selectedYear}
                onChange={(e) => setSelectedYear(Number(e.target.value))}
                style={{ padding: "6px 10px", fontSize: 13, background: "#1a1a1a", border: "1px solid #2d2d2d", borderRadius: 8, color: "#e4e4e7", cursor: "pointer" }}
              >
                {years.map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
              <select
                value={selectedMonth}
                onChange={(e) => setSelectedMonth(Number(e.target.value))}
                style={{ padding: "6px 10px", fontSize: 13, background: "#1a1a1a", border: "1px solid #2d2d2d", borderRadius: 8, color: "#e4e4e7", cursor: "pointer" }}
              >
                {MESES.map((m, i) => (
                  <option key={m} value={i + 1}>{m}</option>
                ))}
              </select>
            </>
          )}

          {periodType === "year" && (
            <select
              value={selectedYear}
              onChange={(e) => setSelectedYear(Number(e.target.value))}
              style={{ padding: "6px 10px", fontSize: 13, background: "#1a1a1a", border: "1px solid #2d2d2d", borderRadius: 8, color: "#e4e4e7", cursor: "pointer" }}
            >
              {years.map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          )}

          {dateRange && (
            <span style={{ fontSize: 12, color: "#71717a" }}>
              {dateRange.from} → {dateRange.to} ({rows.length} trades)
            </span>
          )}
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button
            type="button"
            onClick={handleExportPdf}
            disabled={!rows.length}
            style={{
              padding: "8px 14px",
              fontSize: 13,
              fontWeight: 600,
              color: "#22d3ee",
              background: "rgba(6,182,212,0.15)",
              border: "1px solid #06b6d4",
              borderRadius: 8,
              cursor: rows.length ? "pointer" : "not-allowed",
              opacity: rows.length ? 1 : 0.5,
            }}
          >
            Exportar PDF
          </button>
          <button
            type="button"
            onClick={handleClear}
            disabled={!canDelete}
            style={{
              padding: "8px 14px",
              fontSize: 13,
              fontWeight: 600,
              color: "#fca5a5",
              background: "rgba(239,68,68,0.15)",
              border: "1px solid #dc2626",
              borderRadius: 8,
              cursor: canDelete ? "pointer" : "not-allowed",
              opacity: canDelete ? 1 : 0.5,
            }}
          >
            {hasFilter ? "Eliminar período" : "Limpiar historial"}
          </button>
        </div>
      </div>

      {rows.length > 0 && (
        <div style={{ marginBottom: 10, fontSize: 13, color: "#a1a1aa" }}>
          Resumen (período mostrado): Ganadas: <strong style={{ color: "#22c55e" }}>{summary.ganadas}</strong>
          {" · "}Perdidas: <strong style={{ color: "#ef4444" }}>{summary.perdidas}</strong>
          {" · "}Total: <strong style={{ color: "#e4e4e7" }}>{summary.total}</strong>
          {" · "}PnL: <strong style={{ color: summary.totalPnl >= 0 ? "#22c55e" : "#ef4444" }}>{summary.totalPnl >= 0 ? "+" : ""}{summary.totalPnl.toFixed(2)} USD</strong>
          {" · "}Win rate: <strong style={{ color: "#e4e4e7" }}>{summary.winRate}%</strong>
        </div>
      )}

      <div style={{ border: "1px solid #2d2d2d", borderRadius: 12, overflow: "hidden", background: "#1a1a1a" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, color: "#e4e4e7" }}>
          <thead style={{ background: "#262626" }}>
            <tr>
              <th style={{ textAlign: "left", padding: "12px 10px", borderBottom: "1px solid #2d2d2d", fontWeight: 600, color: "#a1a1aa" }}>Fecha / Hora</th>
              <th style={{ textAlign: "left", padding: "12px 10px", borderBottom: "1px solid #2d2d2d", fontWeight: 600, color: "#a1a1aa" }}>Símbolo</th>
              <th style={{ textAlign: "left", padding: "12px 10px", borderBottom: "1px solid #2d2d2d", fontWeight: 600, color: "#a1a1aa" }}>Dirección</th>
              <th style={{ textAlign: "right", padding: "12px 10px", borderBottom: "1px solid #2d2d2d", fontWeight: 600, color: "#a1a1aa" }}>Stake</th>
              {hasTpSl && (
                <>
                  <th style={{ textAlign: "right", padding: "12px 10px", borderBottom: "1px solid #2d2d2d", fontWeight: 600, color: "#a1a1aa" }}>TP</th>
                  <th style={{ textAlign: "right", padding: "12px 10px", borderBottom: "1px solid #2d2d2d", fontWeight: 600, color: "#a1a1aa" }}>SL</th>
                </>
              )}
              <th style={{ textAlign: "right", padding: "12px 10px", borderBottom: "1px solid #2d2d2d", fontWeight: 600, color: "#a1a1aa" }}>PnL</th>
              <th style={{ textAlign: "center", padding: "12px 10px", borderBottom: "1px solid #2d2d2d", fontWeight: 600, color: "#a1a1aa" }}>Resultado</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={hasTpSl ? 8 : 6} style={{ padding: 24, textAlign: "center", color: "#71717a" }}>
                  {allTrades.length === 0 ? "No hay trades registrados aún." : "No hay trades en el período seleccionado."}
                </td>
              </tr>
            ) : (
              rowsForPage.map((t, i) => {
                const pnlNum = t.pnl != null && t.pnl !== "" ? Number(t.pnl) : null;
                const isWin = pnlNum != null && pnlNum > 0;
                const isLoss = pnlNum != null && pnlNum <= 0;
                const rowIndex = (page - 1) * pageSize + i;
                return (
                  <tr key={t.id || rowIndex} style={{ background: rowIndex % 2 === 0 ? "#1a1a1a" : "#222" }}>
                    <td style={{ padding: "10px", borderBottom: "1px solid #2d2d2d", color: "#e4e4e7" }}>{formatDateTime(t.entry_time)}</td>
                    <td style={{ padding: "10px", borderBottom: "1px solid #2d2d2d", color: "#e4e4e7" }}>{t.symbol ?? "-"}</td>
                    <td style={{ padding: "10px", borderBottom: "1px solid #2d2d2d", color: "#e4e4e7" }}>{t.side === "CALL" ? "Al alza (CALL)" : t.side === "PUT" ? "A la baja (PUT)" : t.side ?? "-"}</td>
                    <td style={{ padding: "10px", borderBottom: "1px solid #2d2d2d", textAlign: "right", color: "#a1a1aa" }}>{t.stake != null ? Number(t.stake).toFixed(2) : "-"}</td>
                    {hasTpSl && (
                      <>
                        <td style={{ padding: "10px", borderBottom: "1px solid #2d2d2d", textAlign: "right", color: "#22c55e" }}>{t.take_profit != null ? Number(t.take_profit).toFixed(2) + " USD" : "-"}</td>
                        <td style={{ padding: "10px", borderBottom: "1px solid #2d2d2d", textAlign: "right", color: "#ef4444" }}>{t.stop_loss != null ? Number(t.stop_loss).toFixed(2) + " USD" : "-"}</td>
                      </>
                    )}
                    <td style={{ padding: "10px", borderBottom: "1px solid #2d2d2d", textAlign: "right", fontWeight: 600, color: isWin ? "#22c55e" : isLoss ? "#ef4444" : "#e4e4e7" }}>{formatPnl(t.pnl)}</td>
                    <td style={{ padding: "10px", borderBottom: "1px solid #2d2d2d", textAlign: "center" }}>
                      {pnlNum == null ? (
                        <span style={{ color: "#71717a" }}>-</span>
                      ) : isWin ? (
                        <span style={{ display: "inline-block", padding: "4px 10px", borderRadius: 6, fontSize: 12, fontWeight: 600, background: "rgba(34,197,94,0.2)", color: "#22c55e" }}>Ganada</span>
                      ) : (
                        <span style={{ display: "inline-block", padding: "4px 10px", borderRadius: 6, fontSize: 12, fontWeight: 600, background: "rgba(239,68,68,0.2)", color: "#ef4444" }}>Perdida</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {rows.length > pageSize && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginTop: 12, padding: "10px 14px", background: "#1a1a1a", border: "1px solid #2d2d2d", borderRadius: 10 }}>
          <span style={{ fontSize: 13, color: "#a1a1aa" }}>
            Mostrando {((page - 1) * pageSize) + 1}-{Math.min(page * pageSize, rows.length)} de {rows.length}
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 12, color: "#71717a" }}>Por página:</span>
            <select
              value={pageSize}
              onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}
              style={{ padding: "4px 8px", fontSize: 13, background: "#262626", border: "1px solid #2d2d2d", borderRadius: 6, color: "#e4e4e7", cursor: "pointer" }}
            >
              {PAGE_SIZE_OPTIONS.map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              style={{
                padding: "6px 12px",
                fontSize: 13,
                background: "#262626",
                border: "1px solid #2d2d2d",
                borderRadius: 8,
                color: "#e4e4e7",
                cursor: page <= 1 ? "not-allowed" : "pointer",
                opacity: page <= 1 ? 0.5 : 1,
              }}
            >
              Anterior
            </button>
            <span style={{ fontSize: 13, color: "#71717a" }}>Página {page} de {totalPages}</span>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              style={{
                padding: "6px 12px",
                fontSize: 13,
                background: "#262626",
                border: "1px solid #2d2d2d",
                borderRadius: 8,
                color: "#e4e4e7",
                cursor: page >= totalPages ? "not-allowed" : "pointer",
                opacity: page >= totalPages ? 0.5 : 1,
              }}
            >
              Siguiente
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
