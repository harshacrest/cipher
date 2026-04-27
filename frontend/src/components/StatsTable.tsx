"use client";

interface Row {
  name: string;
  value: string | number;
}

interface Group {
  title: string;
  from: number;
  to: number;
}

interface Props {
  rows: Row[];
  groups?: Group[];
}

function isNegative(v: string): boolean {
  return /(^|\s)[-−]/.test(v.trim());
}

function Item({ name, value }: { name: string; value: string }) {
  const v = (value || "").trim();
  const neg = isNegative(v);
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr auto",
        alignItems: "baseline",
        padding: "9px 16px",
        gap: 12,
        borderBottom: "1px solid var(--rule-2)",
        minWidth: 0,
      }}
    >
      <span
        style={{
          fontSize: 11,
          color: "var(--ink-2)",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
          minWidth: 0,
        }}
        title={name}
      >
        {name}
      </span>
      <span
        style={{
          fontSize: 12.5,
          fontFamily: "SF Mono, JetBrains Mono, ui-monospace, monospace",
          color: neg ? "var(--neg)" : "var(--ink)",
          fontWeight: 600,
          whiteSpace: "nowrap",
        }}
      >
        {v || "—"}
      </span>
    </div>
  );
}

/**
 * Two-column label/value grid with optional grouping.
 * Ported from Research Framework — vertical hairline divides columns,
 * horizontal hairlines divide rows.
 */
export default function StatsTable({ rows, groups }: Props) {
  if (!rows || rows.length === 0) {
    return <div className="muted" style={{ padding: 14 }}>No statistics.</div>;
  }

  const sections = groups && groups.length > 0
    ? groups
    : [{ title: "", from: 0, to: rows.length }];

  return (
    <div>
      {sections.map((g, gi) => (
        <div key={(g.title || "") + gi}>
          {g.title && (
            <div
              style={{
                padding: "11px 16px 7px",
                fontSize: 9.5,
                letterSpacing: "0.18em",
                textTransform: "uppercase",
                color: "var(--ink-3)",
                borderTop: gi === 0 ? "none" : "1px solid var(--rule)",
                background: "var(--bg-2)",
              }}
            >
              {g.title}
            </div>
          )}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
              backgroundImage:
                "linear-gradient(to right, transparent calc(50% - 0.5px), var(--rule) calc(50% - 0.5px), var(--rule) calc(50% + 0.5px), transparent calc(50% + 0.5px))",
            }}
          >
            {rows.slice(g.from, g.to).map((r, i) => (
              <Item key={`${g.title}-${i}-${r.name}`} name={r.name} value={String(r.value)} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
