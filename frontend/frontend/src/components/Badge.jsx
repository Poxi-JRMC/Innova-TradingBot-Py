export default function Badge({ ok }) {
  return (
    <span
      style={{
        padding: "4px 10px",
        borderRadius: 999,
        fontSize: 12,
        background: ok ? "#18ce07ff" : "#ec0a1dff",
        color: "white",
      }}
    >
      {ok ? "OK" : "ERROR"}
    </span>
  );
}
