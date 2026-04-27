"use client";

interface MatrixRow {
  name: string;
  values: (number | null)[];
}

interface Props {
  names: string[];
  rows: MatrixRow[];
}

function bg(v: number | null): string {
  if (v === null) return "transparent";
  const t = Math.min(1, Math.abs(v));
  const a = 0.12 + t * 0.55;
  if (v >= 0) return `rgba(110, 195, 143, ${a.toFixed(2)})`;
  return `rgba(224, 123, 118, ${a.toFixed(2)})`;
}

/**
 * N×N correlation matrix renderer.
 * Framework-aligned styling: diverging colors (green/red) by sign,
 * intensity by magnitude. Pass `names` (column headers) and `rows`
 * (one per series, with aligned `values` array).
 */
export default function CorrelationMatrix({ names, rows }: Props) {
  if (!rows || rows.length === 0) {
    return <div className="muted" style={{ padding: 14 }}>No correlation data.</div>;
  }

  return (
    <div className="table-wrap" style={{ maxHeight: "none" }}>
      <table className="data">
        <thead>
          <tr>
            <th></th>
            {names.map((n) => (
              <th key={n} style={{ textAlign: "center" }}>{n}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name}>
              <td style={{ fontWeight: 600 }}>{r.name}</td>
              {r.values.map((v, i) => (
                <td
                  key={i}
                  style={{
                    textAlign: "center",
                    background: typeof v === "number" ? bg(v) : "transparent",
                    fontWeight: r.name === names[i] ? 700 : 500,
                  }}
                >
                  {typeof v === "number" ? v.toFixed(3) : "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
