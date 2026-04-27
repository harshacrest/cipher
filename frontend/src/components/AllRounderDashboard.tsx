"use client";

import { useState } from "react";
import { useFetch } from "@/hooks/use-fetch";
import StrategyDashboard from "./StrategyDashboard";
import DatePicker from "./DatePicker";

const API_BASE = "/api/allrounder";

interface AllRounderTrade {
  date: string;
  atm_strike: number;
  entry_ce: number;
  entry_pe: number;
  exit_ce: number;
  exit_pe: number;
  low_ce: number;
  low_pe: number;
  ce_pnl: number;
  pe_pnl: number;
  pnl: number;
  pnl_pct: number;
  ce_exit_reason: string;
  pe_exit_reason: string;
  spot_at_entry: number;
  spot_at_exit: number;
  cumulative_pnl: number;
}

type SortKey = keyof AllRounderTrade;

function exitPill(reason: string): string {
  if (reason === "EOD") return "pill";
  if (reason === "TSL") return "pill warn";
  return "pill neg";
}

export default function AllRounderDashboard() {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  return (
    <StrategyDashboard
      apiBase={API_BASE}
      renderTransactions={() => <AllRounderTradesTable onDateSelect={setSelectedDate} />}
      renderIntraday={() => <AllRounderIntraday externalDate={selectedDate} />}
    />
  );
}

function AllRounderIntraday({ externalDate }: { externalDate?: string | null }) {
  const { data: dates } = useFetch<string[]>(`${API_BASE}/available-dates`);
  const [selectedDate, setSelectedDate] = useState("");

  if (dates && dates.length > 0 && !selectedDate) setSelectedDate(dates[dates.length - 1]);
  if (externalDate && dates?.includes(externalDate) && externalDate !== selectedDate) setSelectedDate(externalDate);

  if (!selectedDate) return <div className="panel"><div className="muted" style={{ padding: 20 }}>Loading…</div></div>;

  return (
    <div id="allrounder-intraday" className="panel">
      <div className="panel-head">
        <h2>Intraday Explorer</h2>
        <DatePicker selectedDate={selectedDate} onDateChange={setSelectedDate} apiUrl={`${API_BASE}/available-dates`} />
      </div>
      <div className="panel-body">
        <AllRounderDayView date={selectedDate} />
      </div>
    </div>
  );
}

function AllRounderDayView({ date }: { date: string }) {
  const { data, loading, error } = useFetch<any>(`${API_BASE}/intraday/${date}`);

  if (loading) return <div className="muted">Loading…</div>;
  if (error || !data) return <div className="muted" style={{ color: "var(--neg)" }}>No data for {date}</div>;

  return (
    <div className="flex items-center gap-4 flex-wrap" style={{ fontSize: 11, color: "var(--ink-3)" }}>
      <span>Strike: <span className="mono" style={{ color: "var(--ink)" }}>{data.atm_strike}</span></span>
      <span>
        CE: <span className="mono" style={{ color: "var(--ink)" }}>{data.entry_ce} → {data.exit_ce}</span>{" "}
        <span className={exitPill(data.ce_exit_reason)}>{data.ce_exit_reason}</span>
      </span>
      <span>
        PE: <span className="mono" style={{ color: "var(--ink)" }}>{data.entry_pe} → {data.exit_pe}</span>{" "}
        <span className={exitPill(data.pe_exit_reason)}>{data.pe_exit_reason}</span>
      </span>
      <span>Low CE: <span className="mono" style={{ color: "var(--accent)" }}>{data.low_ce}</span></span>
      <span>Low PE: <span className="mono" style={{ color: "var(--accent)" }}>{data.low_pe}</span></span>
      <span className={`ml-auto mono ${data.pnl >= 0 ? "num-pos" : "num-neg"}`} style={{ fontWeight: 600 }}>
        PnL: {data.pnl >= 0 ? "+" : ""}{data.pnl?.toFixed(2)} pts
      </span>
    </div>
  );
}

function AllRounderTradesTable({ onDateSelect }: { onDateSelect?: (d: string) => void }) {
  const { data, loading } = useFetch<AllRounderTrade[]>(`${API_BASE}/trades`);
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
    { key: "atm_strike", label: "Strike" },
    { key: "entry_ce", label: "CE In", fmt: (v) => v.toFixed(2) },
    { key: "entry_pe", label: "PE In", fmt: (v) => v.toFixed(2) },
    { key: "low_ce", label: "Low CE", fmt: (v) => v.toFixed(2) },
    { key: "low_pe", label: "Low PE", fmt: (v) => v.toFixed(2) },
    { key: "ce_exit_reason", label: "CE Exit" },
    { key: "pe_exit_reason", label: "PE Exit" },
    { key: "pnl", label: "PnL", fmt: (v) => v.toFixed(2) },
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
          <button onClick={() => setShowAll(true)} className="subtab" style={{ margin: 0 }}>Show all</button>
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
                    const isExitCol = c.key === "ce_exit_reason" || c.key === "pe_exit_reason";
                    const cls = c.key === "pnl" ? ((v as number) >= 0 ? "num-pos" : "num-neg") : undefined;
                    return (
                      <td key={c.key} className={cls}>
                        {isExitCol ? (
                          <span className={exitPill(String(v))}>{display}</span>
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
