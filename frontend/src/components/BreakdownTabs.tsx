"use client";

import { useState } from "react";
import { useFetch } from "@/hooks/use-fetch";
import type { MonthlyRow, YearlyRow, DowRow, DteRow } from "@/types";

const TABS = ["Monthly", "Yearly", "Day of Week", "By DTE"] as const;
type Tab = (typeof TABS)[number];

function Table({
  headers,
  rows,
}: {
  headers: string[];
  rows: (string | number | null)[][];
}) {
  return (
    <div className="overflow-auto max-h-[400px] rounded-lg border border-zinc-700/50">
      <table className="w-full text-xs font-mono">
        <thead className="bg-zinc-800/80 sticky top-0">
          <tr>
            {headers.map((h) => (
              <th
                key={h}
                className="px-3 py-2 text-left text-zinc-500 font-medium whitespace-nowrap"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className="border-t border-zinc-800 hover:bg-zinc-800/60 transition-colors"
            >
              {row.map((cell, j) => {
                const isPnl =
                  headers[j]?.includes("PnL") || headers[j]?.includes("pnl");
                const val = typeof cell === "number" ? cell : 0;
                const color = isPnl
                  ? val >= 0
                    ? "text-emerald-400"
                    : "text-red-400"
                  : "text-zinc-300";
                return (
                  <td
                    key={j}
                    className={`px-3 py-1.5 ${color} whitespace-nowrap`}
                  >
                    {cell ?? "-"}
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

function MonthlyTable() {
  const { data } = useFetch<MonthlyRow[]>("/api/monthly");
  if (!data) return <div className="animate-pulse h-48 bg-zinc-800/50 rounded-lg" />;
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
    />
  );
}

function YearlyTable() {
  const { data } = useFetch<YearlyRow[]>("/api/yearly");
  if (!data) return <div className="animate-pulse h-48 bg-zinc-800/50 rounded-lg" />;
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
    />
  );
}

function DowTable() {
  const { data } = useFetch<DowRow[]>("/api/dow");
  if (!data) return <div className="animate-pulse h-48 bg-zinc-800/50 rounded-lg" />;
  return (
    <Table
      headers={["Day", "Trades", "Total PnL", "Avg PnL", "Win Rate %"]}
      rows={data.map((r) => [r.day_of_week, r.trades, r.total_pnl, r.avg_pnl, r.win_rate])}
    />
  );
}

function DteTable() {
  const { data } = useFetch<DteRow[]>("/api/dte");
  if (!data) return <div className="animate-pulse h-48 bg-zinc-800/50 rounded-lg" />;
  return (
    <Table
      headers={["DTE", "Trades", "Total PnL", "Avg PnL", "Win Rate %"]}
      rows={data.map((r) => [r.dte, r.trades, r.total_pnl, r.avg_pnl, r.win_rate])}
    />
  );
}

export default function BreakdownTabs() {
  const [active, setActive] = useState<Tab>("Monthly");

  return (
    <div>
      <div className="flex items-center gap-1 mb-4">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActive(tab)}
            className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
              active === tab
                ? "bg-zinc-700 text-zinc-100"
                : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>
      {active === "Monthly" && <MonthlyTable />}
      {active === "Yearly" && <YearlyTable />}
      {active === "Day of Week" && <DowTable />}
      {active === "By DTE" && <DteTable />}
    </div>
  );
}
