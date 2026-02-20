import { useState } from "react";
import Table from "../components/Table";

const INITIAL_COUNT = 50;
const LOAD_MORE_STEP = 50;

export default function EventosTab({ events }) {
  const [visibleCount, setVisibleCount] = useState(INITIAL_COUNT);
  const total = (events || []).length;
  const rows = (events || []).slice(0, visibleCount);
  const hasMore = visibleCount < total;

  function loadMore() {
    setVisibleCount((c) => Math.min(c + LOAD_MORE_STEP, total));
  }

  return (
    <div style={{ marginTop: 0 }}>
      <h3 style={{ margin: "0 0 12px 0", color: "#f4f4f5" }}>Eventos del bot</h3>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 12,
          marginBottom: 12,
          padding: "12px 14px",
          background: "#1a1a1a",
          border: "1px solid #2d2d2d",
          borderRadius: 10,
        }}
      >
        <span style={{ fontSize: 13, color: "#a1a1aa" }}>
          Mostrando <strong style={{ color: "#e4e4e7" }}>{rows.length}</strong> de <strong style={{ color: "#e4e4e7" }}>{total}</strong> eventos
        </span>
        {hasMore && (
          <button
            type="button"
            onClick={loadMore}
            style={{
              padding: "8px 16px",
              fontSize: 13,
              fontWeight: 600,
              color: "#22d3ee",
              background: "rgba(6,182,212,0.15)",
              border: "1px solid #06b6d4",
              borderRadius: 8,
              cursor: "pointer",
            }}
          >
            Cargar más (+{Math.min(LOAD_MORE_STEP, total - visibleCount)})
          </button>
        )}
      </div>

      <Table dark cols={["ts", "level", "type", "message"]} rows={rows} />

      {hasMore && total > INITIAL_COUNT && (
        <div style={{ marginTop: 12, textAlign: "center" }}>
          <button
            type="button"
            onClick={loadMore}
            style={{
              padding: "8px 20px",
              fontSize: 13,
              fontWeight: 600,
              color: "#22d3ee",
              background: "rgba(6,182,212,0.15)",
              border: "1px solid #06b6d4",
              borderRadius: 8,
              cursor: "pointer",
            }}
          >
            Cargar más eventos
          </button>
        </div>
      )}
    </div>
  );
}
