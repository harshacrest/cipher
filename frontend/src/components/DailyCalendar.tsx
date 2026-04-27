"use client";

import { useMemo } from "react";
import { useFetch } from "@/hooks/use-fetch";
import type { EquityPoint } from "@/types";

interface Props {
  apiUrl?: string;
}

interface DayCell {
  date: string;
  day: number;
  weekday: number;
  value: number;
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const WEEKDAYS = ["M", "T", "W", "T", "F", "S", "S"];

function colorFor(v: number, max: number): string {
  if (!Number.isFinite(v)) return "var(--rule-2)";
  const t = Math.min(1, Math.abs(v) / (max || 1));
  const a = 0.18 + t * 0.7;
  return v >= 0
    ? `rgba(110, 195, 143, ${a.toFixed(2)})`
    : `rgba(224, 123, 118, ${a.toFixed(2)})`;
}

function fmt(v: number): string {
  if (!Number.isFinite(v)) return "";
  const abs = Math.abs(v);
  if (abs >= 100) return v.toFixed(0);
  if (abs >= 10) return v.toFixed(1);
  return v.toFixed(2);
}

function buildMonthGrid(year: number, month: number, cells: DayCell[]) {
  const byDay = new Map(cells.map((c) => [c.day, c]));
  const firstWeekday = (new Date(year, month - 1, 1).getDay() + 6) % 7;
  const daysInMonth = new Date(year, month, 0).getDate();
  const grid: (DayCell | null)[] = [];
  for (let i = 0; i < firstWeekday; i++) grid.push(null);
  for (let d = 1; d <= daysInMonth; d++) grid.push(byDay.get(d) ?? null);
  while (grid.length % 7 !== 0) grid.push(null);
  return grid;
}

/**
 * Per-year calendar grid of daily PnL.
 * Reads cipher's equity endpoint, aggregates to daily, and renders
 * a 12-month grid per year with PnL coloring.
 */
export default function DailyCalendar({ apiUrl = "/api/equity" }: Props) {
  const { data, loading, error } = useFetch<EquityPoint[]>(apiUrl);

  const { byYear, max } = useMemo(() => {
    if (!data) return { byYear: {} as Record<string, Record<string, DayCell[]>>, max: 0 };
    // Aggregate to daily PnL first
    const daily = new Map<string, number>();
    for (const p of data) {
      daily.set(p.date, (daily.get(p.date) ?? 0) + p.pnl);
    }
    const byYear: Record<string, Record<string, DayCell[]>> = {};
    let max = 0;
    for (const [date, value] of daily) {
      const d = new Date(date);
      if (isNaN(d.getTime())) continue;
      const y = String(d.getFullYear());
      const m = String(d.getMonth() + 1);
      const day = d.getDate();
      const weekday = (d.getDay() + 6) % 7;
      if (!byYear[y]) byYear[y] = {};
      if (!byYear[y][m]) byYear[y][m] = [];
      byYear[y][m].push({ date, day, weekday, value });
      if (Math.abs(value) > max) max = Math.abs(value);
    }
    return { byYear, max };
  }, [data]);

  if (loading) return <div className="muted" style={{ padding: 14 }}><span className="spinner" /> loading…</div>;
  if (error) return <div className="error">{error}</div>;

  const years = Object.keys(byYear).sort();
  if (years.length === 0) return <div className="muted" style={{ padding: 14 }}>No daily data.</div>;

  return (
    <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 24 }}>
      {years.map((y) => (
        <div key={y}>
          <div
            style={{
              fontSize: 11,
              letterSpacing: "0.2em",
              textTransform: "uppercase",
              color: "var(--accent)",
              marginBottom: 12,
              paddingBottom: 6,
              borderBottom: "1px solid var(--rule)",
            }}
          >
            {y} · Daily PnL
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: 14,
            }}
          >
            {Array.from({ length: 12 }, (_, i) => i + 1).map((mNum) => {
              const cells = byYear[y][String(mNum)] ?? [];
              const grid = buildMonthGrid(Number(y), mNum, cells);
              return (
                <div key={mNum}>
                  <div
                    style={{
                      fontSize: 10.5,
                      letterSpacing: "0.14em",
                      textTransform: "uppercase",
                      color: "var(--ink-2)",
                      marginBottom: 6,
                    }}
                  >
                    {MONTH_NAMES[mNum - 1]}
                  </div>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(7, 1fr)",
                      gap: 2,
                      fontSize: 8.5,
                      color: "var(--ink-3)",
                      marginBottom: 4,
                    }}
                  >
                    {WEEKDAYS.map((d, i) => (
                      <div
                        key={i}
                        style={{
                          textAlign: "center",
                          color: i >= 5 ? "var(--ink-3)" : "var(--ink-2)",
                        }}
                      >
                        {d}
                      </div>
                    ))}
                  </div>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(7, 1fr)",
                      gap: 2,
                    }}
                  >
                    {grid.map((cell, idx) => (
                      <div
                        key={idx}
                        title={cell ? `${cell.date}: ${fmt(cell.value)}` : ""}
                        style={{
                          aspectRatio: "1.4 / 1",
                          background: cell ? colorFor(cell.value, max) : "var(--panel-2)",
                          border: "1px solid var(--rule-2)",
                          borderRadius: 1,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 8.5,
                          color: "var(--ink)",
                          fontFamily: "SF Mono, ui-monospace, monospace",
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                        }}
                      >
                        {cell ? fmt(cell.value) : ""}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
