"use client";

import { useState } from "react";
import { useFetch } from "@/hooks/use-fetch";
import type { MonthlyRow, YearlyRow, DowRow, DteRow } from "@/types";

const ALL_TABS = ["Monthly", "Yearly", "Day of Week", "By DTE"] as const;
type Tab = (typeof ALL_TABS)[number];

function Table({
  headers,
  rows,
  pnlCols = [],
}: {
  headers: string[];
  rows: (string | number | null)[][];
  /** Column indexes whose values are PnL-like (get green/red coloring) */
  pnlCols?: number[];
}) {
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            {headers.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => {
                const isPnl =
                  pnlCols.includes(j) ||
                  headers[j]?.toLowerCase().includes("pnl") ||
                  headers[j]?.toLowerCase().includes("win") && headers[j]?.includes("Max") ||
                  headers[j]?.toLowerCase().includes("loss") && headers[j]?.includes("Max");
                const n = typeof cell === "number" ? cell : null;
                const cls =
                  isPnl && n !== null
                    ? n >= 0
                      ? "num-pos"
                      : "num-neg"
                    : undefined;
                return (
                  <td key={j} className={cls}>
                    {cell ?? "—"}
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

const MONTH_NAMES = [
  "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function MonthlyTable({ apiBase = "/api" }: { apiBase?: string }) {
  const { data } = useFetch<MonthlyRow[]>(`${apiBase}/monthly`);
  if (!data) return <div className="muted" style={{ padding: 16 }}>Loading…</div>;
  return (
    <Table
      headers={["Year", "Month", "Trades", "Total PnL", "Avg PnL", "Win Rate %", "Max Win", "Max Loss"]}
      rows={data.map((r) => [
        r.year,
        MONTH_NAMES[r.month] || r.month,
        r.trades,
        r.total_pnl,
        r.avg_pnl,
        r.win_rate,
        r.max_win,
        r.max_loss,
      ])}
      pnlCols={[3, 4, 6, 7]}
    />
  );
}

function YearlyTable({ apiBase = "/api" }: { apiBase?: string }) {
  const { data } = useFetch<YearlyRow[]>(`${apiBase}/yearly`);
  if (!data) return <div className="muted" style={{ padding: 16 }}>Loading…</div>;
  return (
    <Table
      headers={["Year", "Trades", "Total PnL", "Avg PnL", "Win Rate %", "Max Win", "Max Loss", "Sharpe"]}
      rows={data.map((r) => [
        r.year,
        r.trades,
        r.total_pnl,
        r.avg_pnl,
        r.win_rate,
        r.max_win,
        r.max_loss,
        r.sharpe,
      ])}
      pnlCols={[2, 3, 5, 6]}
    />
  );
}

function DowTable({ apiBase = "/api" }: { apiBase?: string }) {
  const { data } = useFetch<DowRow[]>(`${apiBase}/dow`);
  if (!data) return <div className="muted" style={{ padding: 16 }}>Loading…</div>;
  return (
    <Table
      headers={["Day", "Trades", "Total PnL", "Avg PnL", "Win Rate %"]}
      rows={data.map((r) => [r.day_of_week, r.trades, r.total_pnl, r.avg_pnl, r.win_rate])}
      pnlCols={[2, 3]}
    />
  );
}

function DteTable({ apiBase = "/api" }: { apiBase?: string }) {
  const { data } = useFetch<DteRow[]>(`${apiBase}/dte`);
  if (!data) return <div className="muted" style={{ padding: 16 }}>Loading…</div>;
  return (
    <Table
      headers={["DTE", "Trades", "Total PnL", "Avg PnL", "Win Rate %"]}
      rows={data.map((r) => [r.dte, r.trades, r.total_pnl, r.avg_pnl, r.win_rate])}
      pnlCols={[2, 3]}
    />
  );
}

interface BreakdownTabsProps {
  apiBase?: string;
  /** Which breakdown views to show. Defaults to all four. */
  include?: Tab[];
  /** Panel header title. */
  title?: string;
}

export default function BreakdownTabs({
  apiBase = "/api",
  include,
  title = "Breakdown",
}: BreakdownTabsProps) {
  const tabs = (include && include.length > 0 ? include : [...ALL_TABS]) as Tab[];
  const [active, setActive] = useState<Tab>(tabs[0]);

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>{title}</h2>
        <div style={{ display: "flex", gap: 4 }}>
          {tabs.map((tab) => (
            <button
              key={tab}
              onClick={() => setActive(tab)}
              className={`subtab ${active === tab ? "active" : ""}`}
              style={{ margin: 0 }}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>
      <div className="panel-body tight">
        {active === "Monthly" && <MonthlyTable apiBase={apiBase} />}
        {active === "Yearly" && <YearlyTable apiBase={apiBase} />}
        {active === "Day of Week" && <DowTable apiBase={apiBase} />}
        {active === "By DTE" && <DteTable apiBase={apiBase} />}
      </div>
    </div>
  );
}
