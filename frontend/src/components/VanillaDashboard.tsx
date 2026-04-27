"use client";

import { useState } from "react";
import { useFetch } from "@/hooks/use-fetch";
import StrategyDashboard from "./StrategyDashboard";
import DatePicker from "./DatePicker";

// Vanilla strategy uses a different API base path
const API_BASE = "/api/vanilla";

interface VanillaTrade {
  date: string;
  trade_num: number;
  dte: number;
  atm_strike: number;
  entry_spot: number;
  exit_spot: number;
  entry_ce: number;
  entry_pe: number;
  exit_ce: number;
  exit_pe: number;
  combined_premium: number;
  exit_trigger: number;
  ce_pnl: number;
  pe_pnl: number;
  pnl: number;
  exit_reason: string;
  exit_time: string;
  day_pnl: number;
  cumulative_pnl: number;
}

type SortKey = keyof VanillaTrade;

export default function VanillaDashboard() {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  return (
    <StrategyDashboard
      apiBase={API_BASE}
      renderTransactions={() => <VanillaTradesTable onDateSelect={setSelectedDate} />}
      renderIntraday={() => <VanillaIntradayExplorer externalDate={selectedDate} />}
    />
  );
}

function VanillaIntradayExplorer({ externalDate }: { externalDate?: string | null }) {
  const { data: dates } = useFetch<string[]>(`${API_BASE}/available-dates`);
  const [selectedDate, setSelectedDate] = useState<string>("");

  if (dates && dates.length > 0 && !selectedDate) {
    setSelectedDate(dates[dates.length - 1]);
  }
  if (externalDate && dates?.includes(externalDate) && externalDate !== selectedDate) {
    setSelectedDate(externalDate);
  }

  if (!selectedDate) {
    return <div className="panel"><div className="muted" style={{ padding: 20 }}>Loading…</div></div>;
  }

  return (
    <div id="vanilla-intraday" className="panel">
      <div className="panel-head">
        <h2>Intraday Explorer</h2>
        <DatePicker
          selectedDate={selectedDate}
          onDateChange={setSelectedDate}
          apiUrl={`${API_BASE}/available-dates`}
        />
      </div>
      <div className="panel-body">
        <VanillaIntradayChart date={selectedDate} />
      </div>
    </div>
  );
}

function VanillaIntradayChart({ date }: { date: string }) {
  const { data, loading, error } = useFetch<any>(`${API_BASE}/intraday/${date}`);

  if (loading) return <div className="muted">Loading…</div>;
  if (error || !data) return <div className="muted" style={{ color: "var(--neg)" }}>No data for {date}</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="flex items-center gap-4" style={{ fontSize: 11, color: "var(--ink-3)" }}>
        <span>DTE: <span className="mono" style={{ color: "var(--ink)" }}>{data.dte}</span></span>
        <span>Trades: <span className="mono" style={{ color: "var(--ink)" }}>{data.trades?.length || 0}</span></span>
        <span className={`ml-auto mono ${data.day_pnl >= 0 ? "num-pos" : "num-neg"}`} style={{ fontWeight: 600 }}>
          Day PnL: {data.day_pnl >= 0 ? "+" : ""}{data.day_pnl?.toFixed(2)} pts
        </span>
      </div>

      {data.trades && data.trades.length > 0 && (
        <div className="table-wrap" style={{ maxHeight: 320 }}>
          <table className="data">
            <thead>
              <tr>
                <th>#</th>
                <th>Strike</th>
                <th>CE In</th>
                <th>PE In</th>
                <th>Premium</th>
                <th>Trigger</th>
                <th>PnL</th>
                <th>Exit</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {data.trades.map((t: any) => (
                <tr key={t.trade_num}>
                  <td>{t.trade_num}</td>
                  <td>{t.atm_strike}</td>
                  <td>{t.entry_ce?.toFixed(2)}</td>
                  <td>{t.entry_pe?.toFixed(2)}</td>
                  <td>{t.combined_premium?.toFixed(2)}</td>
                  <td>{t.exit_trigger?.toFixed(2)}</td>
                  <td className={t.pnl >= 0 ? "num-pos" : "num-neg"}>
                    {t.pnl >= 0 ? "+" : ""}{t.pnl?.toFixed(2)}
                  </td>
                  <td>
                    <span className={`pill ${
                      t.exit_reason === "EOD" ? "" :
                      t.exit_reason === "SPOT_MOVE" ? "warn" : "neg"
                    }`}>{t.exit_reason}</span>
                  </td>
                  <td>{t.exit_time}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function VanillaTradesTable({ onDateSelect }: { onDateSelect?: (date: string) => void }) {
  const { data, loading } = useFetch<VanillaTrade[]>(`${API_BASE}/trades`);
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
    { key: "dte", label: "DTE" },
    { key: "atm_strike", label: "Strike" },
    { key: "combined_premium", label: "Premium", fmt: (v) => v.toFixed(2) },
    { key: "exit_trigger", label: "Trigger", fmt: (v) => v.toFixed(2) },
    { key: "pnl", label: "PnL", fmt: (v) => v.toFixed(2) },
    { key: "exit_reason", label: "Exit" },
    { key: "day_pnl", label: "Day PnL", fmt: (v) => v.toFixed(2) },
  ];

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
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
                    {sortKey === c.key && (
                      <span style={{ marginLeft: 4, color: "var(--accent)" }}>
                        {sortAsc ? "▲" : "▼"}
                      </span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {displayed.map((t, i) => (
                <tr key={i} onClick={() => onDateSelect?.(t.date)} className="clickable">
                  {cols.map((c) => {
                    const v = t[c.key];
                    const display = c.fmt ? c.fmt(v) : String(v);
                    const isPnl = c.key === "pnl" || c.key === "day_pnl";
                    const cls = isPnl ? ((v as number) >= 0 ? "num-pos" : "num-neg") : undefined;
                    return (
                      <td key={c.key} className={cls}>
                        {c.key === "exit_reason" ? (
                          <span className={`pill ${
                            v === "EOD" ? "" :
                            v === "SPOT_MOVE" ? "warn" : "neg"
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
