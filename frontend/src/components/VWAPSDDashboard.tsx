"use client";

import { useState } from "react";
import { useFetch } from "@/hooks/use-fetch";
import StrategyDashboard from "./StrategyDashboard";
import VWAPSDChartsPanel from "./VWAPSDChartsPanel";

const API_BASE = "/api/vwap-sd";

interface VWAPSDTrade {
  date: string;
  trade_num: number;
  entry_time: string;
  exit_time: string;
  exit_reason: string;
  base_strike: number;
  spot_at_entry: number;
  spot_at_exit: number;
  entry_sclose: number;
  exit_sclose: number;
  entry_vwap: number;
  exit_vwap: number;
  num_legs: number;
  pnl_points: number;
  pnl_premium: number;
  pnl: number;
  cumulative_pnl: number;
}

type SortKey = keyof VWAPSDTrade;

export default function VWAPSDDashboard() {
  return (
    <StrategyDashboard
      apiBase={API_BASE}
      renderTransactions={() => <VWAPSDTradesTable />}
      renderIntraday={() => <ExitReasonsPanel />}
      renderCharts={() => <VWAPSDChartsPanel />}
    />
  );
}

function ExitReasonsPanel() {
  const { data: exits, loading } = useFetch<any[]>(`${API_BASE}/exit-reasons`);
  if (loading) return <div className="panel"><div className="muted" style={{ padding: 20 }}>Loading…</div></div>;
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Exit Reasons</h2>
        <span className="meta" style={{ fontSize: 11 }}>SL / Forced / EOD breakdown</span>
      </div>
      <div className="panel-body tight">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Reason</th>
                <th>Count</th>
                <th>Total PnL (prem)</th>
                <th>Avg PnL (prem)</th>
                <th>Win Rate %</th>
              </tr>
            </thead>
            <tbody>
              {(exits || []).map((e: any) => (
                <tr key={e.exit_reason}>
                  <td>
                    <span className={`pill ${
                      e.exit_reason === "FORCED" || e.exit_reason === "EOD_HARD" ? "" :
                      e.exit_reason === "TARGET" ? "good" : "neg"
                    }`}>{e.exit_reason}</span>
                  </td>
                  <td>{e.count}</td>
                  <td className={e.total_pnl_premium >= 0 ? "num-pos" : "num-neg"}>
                    {e.total_pnl_premium >= 0 ? "+" : ""}{e.total_pnl_premium?.toLocaleString()}
                  </td>
                  <td className={e.avg_pnl_premium >= 0 ? "num-pos" : "num-neg"}>
                    {e.avg_pnl_premium >= 0 ? "+" : ""}{e.avg_pnl_premium?.toFixed(0)}
                  </td>
                  <td>{e.win_rate?.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function VWAPSDTradesTable() {
  const { data, loading } = useFetch<VWAPSDTrade[]>(`${API_BASE}/trades`);
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [sortAsc, setSortAsc] = useState(false);
  const [showAll, setShowAll] = useState(false);

  if (loading || !data) return <div className="panel"><div className="muted" style={{ padding: 20 }}>Loading…</div></div>;

  const sorted = [...data].sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey];
    if (typeof va === "string") return sortAsc ? (va as string).localeCompare(vb as string) : (vb as string).localeCompare(va as string);
    return sortAsc ? (va as number) - (vb as number) : (vb as number) - (va as number);
  });
  const displayed = showAll ? sorted : sorted.slice(0, 50);

  const cols: { key: SortKey; label: string; fmt?: (v: any) => string }[] = [
    { key: "date", label: "Date" },
    { key: "trade_num", label: "#" },
    { key: "entry_time", label: "Entry" },
    { key: "exit_time", label: "Exit" },
    { key: "base_strike", label: "Base" },
    { key: "spot_at_entry", label: "Spot In", fmt: (v) => v?.toFixed(1) },
    { key: "entry_sclose", label: "sClose In", fmt: (v) => v?.toFixed(1) },
    { key: "entry_vwap", label: "VWAP In", fmt: (v) => v?.toFixed(1) },
    { key: "exit_sclose", label: "sClose Out", fmt: (v) => v?.toFixed(1) },
    { key: "pnl_points", label: "PnL (pts)", fmt: (v) => (v >= 0 ? "+" : "") + v?.toFixed(1) },
    { key: "pnl_premium", label: "PnL (prem)", fmt: (v) => (v >= 0 ? "+" : "") + v?.toLocaleString() },
    { key: "exit_reason", label: "Exit" },
  ];

  const handleSort = (k: SortKey) => {
    if (sortKey === k) setSortAsc(!sortAsc);
    else { setSortKey(k); setSortAsc(false); }
  };

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>All Trades ({data.length})</h2>
        {!showAll && data.length > 50 && (
          <button onClick={() => setShowAll(true)} className="subtab" style={{ margin: 0 }}>
            Show all {data.length}
          </button>
        )}
      </div>
      <div className="panel-body tight">
        <div className="table-wrap" style={{ maxHeight: 520 }}>
          <table className="data">
            <thead>
              <tr>
                {cols.map((c) => (
                  <th key={c.key} onClick={() => handleSort(c.key)}>
                    {c.label}
                    {sortKey === c.key && <span style={{ marginLeft: 4, color: "var(--accent)" }}>{sortAsc ? "▲" : "▼"}</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {displayed.map((t, i) => (
                <tr key={i}>
                  {cols.map((c) => {
                    const v = t[c.key];
                    const display = c.fmt ? c.fmt(v) : String(v);
                    const isPnl = c.key === "pnl_points" || c.key === "pnl_premium";
                    const cls = isPnl ? ((v as number) >= 0 ? "num-pos" : "num-neg") : undefined;
                    return (
                      <td key={c.key} className={cls}>
                        {c.key === "exit_reason" ? (
                          <span className={`pill ${
                            v === "FORCED" || v === "EOD_HARD" ? "" :
                            v === "TARGET" ? "good" : "neg"
                          }`}>{display}</span>
                        ) : display}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
