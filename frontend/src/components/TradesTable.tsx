"use client";

import { useMemo, useState } from "react";
import { useFetch } from "@/hooks/use-fetch";
import type { Trade } from "@/types";

interface TradesTableProps {
  onDateSelect?: (date: string) => void;
}

type SortKey = keyof Trade;

export default function TradesTable({ onDateSelect }: TradesTableProps) {
  const { data, loading } = useFetch<Trade[]>("/api/trades");
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [sortAsc, setSortAsc] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const sorted = useMemo(() => {
    if (!data) return [];
    return [...data].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av == null) return 1;
      if (bv == null) return -1;
      if (av < bv) return sortAsc ? -1 : 1;
      if (av > bv) return sortAsc ? 1 : -1;
      return 0;
    });
  }, [data, sortKey, sortAsc]);

  if (loading || !data) {
    return (
      <div className="animate-pulse h-64 bg-zinc-800/50 rounded-lg" />
    );
  }

  const displayed = showAll ? sorted : sorted.slice(0, 50);

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  const cols: { key: SortKey; label: string; fmt?: (v: number) => string }[] = [
    { key: "date", label: "Date" },
    { key: "ce_strike", label: "CE Strike" },
    { key: "pe_strike", label: "PE Strike" },
    { key: "entry_ce", label: "CE In", fmt: (v) => v.toFixed(2) },
    { key: "exit_ce", label: "CE Out", fmt: (v) => v.toFixed(2) },
    { key: "ce_exit_reason", label: "CE Exit" },
    { key: "ce_pnl", label: "CE PnL", fmt: (v) => v.toFixed(2) },
    { key: "entry_pe", label: "PE In", fmt: (v) => v.toFixed(2) },
    { key: "exit_pe", label: "PE Out", fmt: (v) => v.toFixed(2) },
    { key: "pe_exit_reason", label: "PE Exit" },
    { key: "pe_pnl", label: "PE PnL", fmt: (v) => v.toFixed(2) },
    { key: "pnl", label: "Total PnL", fmt: (v) => v.toFixed(2) },
    { key: "spot_at_entry", label: "Spot In", fmt: (v) => v.toFixed(1) },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-zinc-400">
          All Trades ({data.length})
        </h2>
        {!showAll && data.length > 50 && (
          <button
            onClick={() => setShowAll(true)}
            className="text-xs text-blue-400 hover:text-blue-300"
          >
            Show all {data.length} trades
          </button>
        )}
      </div>
      <div className="overflow-auto max-h-[500px] rounded-lg border border-zinc-700/50">
        <table className="w-full text-xs font-mono">
          <thead className="bg-zinc-800/80 sticky top-0">
            <tr>
              {cols.map((col) => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  className="px-3 py-2 text-left text-zinc-500 font-medium cursor-pointer hover:text-zinc-300 select-none whitespace-nowrap"
                >
                  {col.label}
                  {sortKey === col.key && (
                    <span className="ml-1">{sortAsc ? "▲" : "▼"}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayed.map((trade, i) => (
              <tr
                key={trade.date}
                onClick={() => onDateSelect?.(trade.date)}
                className="border-t border-zinc-800 hover:bg-zinc-800/60 cursor-pointer transition-colors"
              >
                {cols.map((col) => {
                  const raw = trade[col.key];
                  let display: string;
                  if (raw == null) {
                    display = "-";
                  } else if (col.fmt && typeof raw === "number") {
                    display = col.fmt(raw);
                  } else {
                    display = String(raw);
                  }

                  const isPnl = col.key === "pnl" || col.key === "pnl_pct" || col.key === "ce_pnl" || col.key === "pe_pnl";
                  const isExit = col.key === "ce_exit_reason" || col.key === "pe_exit_reason";
                  let color = "text-zinc-300";
                  if (isPnl) {
                    color = typeof raw === "number" && raw >= 0 ? "text-emerald-400" : "text-red-400";
                  } else if (isExit) {
                    color = raw === "SL" ? "text-red-400" : "text-amber-400";
                  }

                  return (
                    <td key={col.key} className={`px-3 py-1.5 ${color} whitespace-nowrap`}>
                      {display}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
