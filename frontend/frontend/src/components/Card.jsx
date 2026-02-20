export default function Card({ title, value, sub, dark }) {
  if (dark) {
    return (
      <div style={{ padding: 12, border: "1px solid #2d2d2d", borderRadius: 12, background: "#1a1a1a" }}>
        <div style={{ fontSize: 12, color: "#a1a1aa" }}>{title}</div>
        <div style={{ fontSize: 18, fontWeight: 700, color: "#e4e4e7" }}>{String(value)}</div>
        {sub != null && <div style={{ fontSize: 11, color: "#71717a", marginTop: 4 }}>{sub}</div>}
      </div>
    );
  }
  return (
    <div style={{ padding: 12, border: "1px solid #eee", borderRadius: 12 }}>
      <div style={{ fontSize: 12, color: "#666" }}>{title}</div>
      <div style={{ fontSize: 18, fontWeight: 700 }}>{String(value)}</div>
      {sub != null && <div style={{ fontSize: 11, color: "#888", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}
