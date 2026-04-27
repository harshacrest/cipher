"use client";

import { useMemo } from "react";
import { useFetch } from "@/hooks/use-fetch";
import type { MonthlyRow } from "@/types";

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * Monthly Returns Calendar — year × month grid, colored by total_pnl.
 * Mirrors the Research Framework's Heatmap component: each row is a year,
 * each column is a month. Positive green, negative red, intensity scales
 * with magnitude. Secondary line in the cell shows the trade count.
 */
export default function Heatmap({ apiBase = "/api" }: { apiBase?: string }) {
  const { data } = useFetch<MonthlyRow[]>(`${apiBase}/monthly`);

  const { grid, years, maxAbs } = useMemo(() => {
    if (!data) return { grid: new Map<string, MonthlyRow>(), years: [] as number[], maxAbs: 1 };
    const grid = new Map<string, MonthlyRow>();
    const yearSet = new Set<number>();
    let maxAbs = 1;
    for (const r of data) {
      grid.set(`${r.year}-${r.month}`, r);
      yearSet.add(r.year);
      const m = Math.abs(r.total_pnl);
      if (m > maxAbs) maxAbs = m;
    }
    const years = Array.from(yearSet).sort();
    return { grid, years, maxAbs };
  }, [data]);

  if (!data) return <div className="muted" style={{ padding: 16 }}>Loading…</div>;
  if (!years.length) return <div className="muted" style={{ padding: 16 }}>No monthly data.</div>;

  function cellStyle(pnl: number): React.CSSProperties {
    const intensity = Math.min(1, Math.abs(pnl) / maxAbs);
    const alpha = 0.12 + intensity * 0.55;
    const color = pnl >= 0
      ? `rgba(110, 195, 143, ${alpha})`
      : `rgba(224, 123, 118, ${alpha})`;
    return { background: color };
  }

  return (
    <div className="table-wrap" style={{ maxHeight: "none", overflow: "auto" }}>
      <table
        className="data"
        style={{ tableLayout: "fixed", minWidth: 780 }}
      >
        <thead>
          <tr>
            <th style={{ width: 60 }}>Year</th>
            {MONTH_NAMES.map((m) => (
              <th key={m} style={{ textAlign: "center" }}>{m}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {years.map((y) => (
            <tr key={y}>
              <td style={{ color: "var(--ink-2)", fontWeight: 600 }}>{y}</td>
              {MONTH_NAMES.map((_, i) => {
                const m = i + 1;
                const cell = grid.get(`${y}-${m}`);
                if (!cell) {
                  return <td key={m} style={{ background: "transparent", color: "var(--ink-3)", textAlign: "center" }}>—</td>;
                }
                const cls = cell.total_pnl >= 0 ? "num-pos" : "num-neg";
                return (
                  <td
                    key={m}
                    title={`${y}-${String(m).padStart(2,"0")} · ${cell.total_pnl.toFixed(2)} pts · ${cell.trades} trades · ${cell.win_rate.toFixed(1)}% WR`}
                    style={{ ...cellStyle(cell.total_pnl), textAlign: "center", padding: "6px 4px", lineHeight: 1.2 }}
                  >
                    <div className={cls} style={{ fontSize: 11.5 }}>
                      {cell.total_pnl >= 0 ? "+" : ""}{cell.total_pnl.toFixed(0)}
                    </div>
                    <div style={{ fontSize: 9, color: "var(--ink-3)", marginTop: 1 }}>
                      {cell.trades}t
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
