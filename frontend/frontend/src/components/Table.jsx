export default function Table({ cols, rows, dark }) {
  if (dark) {
    return (
      <div style={{ border: "1px solid #2d2d2d", borderRadius: 12, overflow: "hidden", background: "#1a1a1a" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, color: "#e4e4e7" }}>
          <thead style={{ background: "#262626" }}>
            <tr>
              {cols.map((c) => (
                <th key={c} style={{ textAlign: "left", padding: 10, borderBottom: "1px solid #2d2d2d", color: "#a1a1aa" }}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} style={{ background: i % 2 === 0 ? "#1a1a1a" : "#222" }}>
                {cols.map((c) => (
                  <td key={c} style={{ padding: 10, borderBottom: "1px solid #2d2d2d", verticalAlign: "top", color: "#e4e4e7" }}>
                    {typeof r?.[c] === "object" ? JSON.stringify(r?.[c]) : String(r?.[c] ?? "-")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <div style={{ border: "1px solid #eee", borderRadius: 12, overflow: "hidden" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead style={{ background: "#fafafa" }}>
          <tr>
            {cols.map((c) => (
              <th key={c} style={{ textAlign: "left", padding: 10, borderBottom: "1px solid #eee" }}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td key={c} style={{ padding: 10, borderBottom: "1px solid #f2f2f2", verticalAlign: "top" }}>
                  {typeof r?.[c] === "object" ? JSON.stringify(r?.[c]) : String(r?.[c] ?? "-")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
