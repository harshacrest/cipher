"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  createChart,
  ColorType,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";

/**
 * Side-by-side comparison of every cipher strategy that has backtest data.
 * Mirrors the Research Framework's Comparison component:
 *   - multi-series overlay of equity curves
 *   - compact KPI table with per-metric best-value highlighting
 *   - toggleable per-series checkboxes
 *
 * Color palette is spread across the gold-band so strategies are
 * distinguishable while staying inside the Research Framework theme.
 */

type StrategyKey = "atm" | "vanilla" | "allrounder" | "day-high";

interface StrategyDef {
  key: StrategyKey;
  label: string;
  apiBase: string;
  color: string;
}

const STRATEGIES: StrategyDef[] = [
  { key: "atm",        label: "ATM Strangle",   apiBase: "/api",            color: "#d4b06a" }, // gold
  { key: "vanilla",    label: "Vanilla",        apiBase: "/api/vanilla",    color: "#8faab7" }, // slate-blue
  { key: "allrounder", label: "All Rounder",    apiBase: "/api/allrounder", color: "#bd9a97" }, // warm taupe
  { key: "day-high",   label: "Day High OTM",   apiBase: "/api/day-high",   color: "#a8b893" }, // muted olive
];

/** Metrics shown in the side-by-side table, with "better = high/low"
 *  annotation so the winner can be highlighted per column. */
const KPI_COLS: {
  key: string;
  label: string;
  suffix?: string;
  precision?: number;
  better?: "high" | "low" | "abs-low";
}[] = [
  { key: "Total PnL (pts)",         label: "Total",     suffix: " pts", precision: 1, better: "high" },
  { key: "Annualized Return (pts)", label: "Ann.",      suffix: " pts", precision: 1, better: "high" },
  { key: "Sharpe Ratio (ann.)",     label: "Sharpe",    precision: 2, better: "high" },
  { key: "Sortino Ratio (ann.)",    label: "Sortino",   precision: 2, better: "high" },
  { key: "Calmar Ratio",            label: "Calmar",    precision: 2, better: "high" },
  { key: "Profit Factor",           label: "PF",        precision: 2, better: "high" },
  { key: "Win Rate (%)",            label: "Win %",     suffix: "%", precision: 1, better: "high" },
  { key: "Expectancy (pts)",        label: "Expect.",   suffix: " pts", precision: 2, better: "high" },
  { key: "Max Drawdown (pts)",      label: "Max DD",    suffix: " pts", precision: 2, better: "abs-low" },
  { key: "Max DD Duration (days)",  label: "DD Days",   suffix: "d", precision: 0, better: "low" },
  { key: "Std Dev (daily)",         label: "Daily σ",   precision: 2, better: "low" },
  { key: "Max Loss Streak",         label: "Loss Stk",  suffix: "d", precision: 0, better: "low" },
  { key: "Total Trades",            label: "Trades",    precision: 0 },
  { key: "Profitable Months (%)",   label: "Win M %",   suffix: "%", precision: 1, better: "high" },
];

interface EquityPoint { date: string; cumulative_pnl: number }
interface MetricRow { Metric: string; Value: number | string }

const PALETTE = {
  bg:   "#1d2026",
  text: "#b3b6bd",
  grid: "#2a2e35",
};

function fmt(v: number | string | undefined, suffix = "", precision = 2): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  if (Number.isNaN(v)) return "—";
  return v.toLocaleString(undefined, {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  }) + suffix;
}

export default function Comparison() {
  const [selected, setSelected] = useState<Record<StrategyKey, boolean>>({
    atm: true, vanilla: true, allrounder: true, "day-high": true,
  });
  const [equity, setEquity]   = useState<Record<StrategyKey, EquityPoint[] | null>>({
    atm: null, vanilla: null, allrounder: null, "day-high": null,
  });
  const [metrics, setMetrics] = useState<Record<StrategyKey, Map<string, number | string> | null>>({
    atm: null, vanilla: null, allrounder: null, "day-high": null,
  });

  // Fetch all 4 strategies once
  useEffect(() => {
    let cancelled = false;
    Promise.all(
      STRATEGIES.map(async (s) => {
        const [eRes, mRes] = await Promise.all([
          fetch(`${s.apiBase}/equity`).then((r) => (r.ok ? r.json() : [])),
          fetch(`${s.apiBase}/metrics`).then((r) => (r.ok ? r.json() : [])),
        ]);
        return { key: s.key, equity: eRes as EquityPoint[], metrics: mRes as MetricRow[] };
      })
    ).then((results) => {
      if (cancelled) return;
      const nextE: any = {};
      const nextM: any = {};
      for (const r of results) {
        nextE[r.key] = r.equity;
        const map = new Map<string, number | string>();
        for (const row of r.metrics) map.set(row.Metric, row.Value);
        nextM[r.key] = map;
      }
      setEquity(nextE);
      setMetrics(nextM);
    });
    return () => { cancelled = true; };
  }, []);

  // Per-metric winner lookup for highlighting
  const winners = useMemo(() => {
    const out = new Map<string, StrategyKey>();
    for (const col of KPI_COLS) {
      if (!col.better) continue;
      let best: { key: StrategyKey; v: number } | null = null;
      for (const s of STRATEGIES) {
        const m = metrics[s.key];
        if (!m) continue;
        const raw = m.get(col.key);
        if (typeof raw !== "number") continue;
        const score = col.better === "abs-low" ? -Math.abs(raw)
                    : col.better === "low"     ? -raw
                    : raw;
        if (!best || score > best.v) best = { key: s.key, v: score };
      }
      if (best) out.set(col.key, best.key);
    }
    return out;
  }, [metrics]);

  return (
    <div>
      {/* Series toggle row */}
      <div className="subtabs" style={{ marginBottom: 14 }}>
        {STRATEGIES.map((s) => {
          const on = selected[s.key];
          return (
            <button
              key={s.key}
              onClick={() => setSelected((prev) => ({ ...prev, [s.key]: !prev[s.key] }))}
              className={`subtab ${on ? "active" : ""}`}
              style={on ? { borderColor: s.color, color: s.color } : undefined}
            >
              <span
                style={{
                  display: "inline-block",
                  width: 8, height: 8, borderRadius: "50%",
                  background: s.color,
                  marginRight: 7,
                  verticalAlign: 0,
                  opacity: on ? 1 : 0.3,
                }}
              />
              {s.label}
            </button>
          );
        })}
      </div>

      {/* Multi-series equity overlay */}
      <div className="panel">
        <div className="panel-head"><h2>Equity Curves · Overlay</h2></div>
        <div className="panel-body" style={{ padding: "12px 14px" }}>
          <MultiEquityChart
            series={STRATEGIES
              .filter((s) => selected[s.key] && equity[s.key])
              .map((s) => ({ key: s.key, label: s.label, color: s.color, data: equity[s.key]! }))}
            height={360}
          />
        </div>
      </div>

      {/* Side-by-side metrics table */}
      <div className="panel">
        <div className="panel-head"><h2>Performance · Side-by-Side</h2></div>
        <div className="panel-body tight">
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Strategy</th>
                  {KPI_COLS.map((c) => (
                    <th key={c.key} title={c.key}>{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {STRATEGIES.map((s) => {
                  const m = metrics[s.key];
                  return (
                    <tr key={s.key}>
                      <td style={{ color: s.color, fontWeight: 600 }}>
                        <span
                          style={{
                            display: "inline-block",
                            width: 8, height: 8, borderRadius: "50%",
                            background: s.color,
                            marginRight: 7,
                            verticalAlign: "middle",
                          }}
                        />
                        {s.label}
                      </td>
                      {KPI_COLS.map((c) => {
                        const raw = m?.get(c.key);
                        const isWinner = winners.get(c.key) === s.key;
                        const isNum = typeof raw === "number";
                        const cls =
                          !isNum ? undefined
                          : c.key === "Max Drawdown (pts)" || c.key === "Max Loss Streak" ? "num-neg"
                          : (raw as number) > 0 ? "num-pos"
                          : (raw as number) < 0 ? "num-neg"
                          : undefined;
                        return (
                          <td
                            key={c.key}
                            className={cls}
                            style={isWinner ? {
                              background: "var(--gold-tint)",
                              borderLeft: "1px solid rgba(212,176,106,0.3)",
                              borderRight: "1px solid rgba(212,176,106,0.3)",
                              fontWeight: 600,
                            } : undefined}
                          >
                            {fmt(raw, c.suffix ?? "", c.precision ?? 2)}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="muted" style={{ padding: "10px 14px", fontSize: 10 }}>
            Highlighted cells = best value for that metric across strategies
            (lower-is-better handled for drawdown, duration, streaks, σ).
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Multi-series equity overlay chart ───────────────────────────────── */
function MultiEquityChart({
  series,
  height = 360,
}: {
  series: { key: string; label: string; color: string; data: EquityPoint[] }[];
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());

  useEffect(() => {
    if (!ref.current) return;

    const chart = createChart(ref.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: PALETTE.bg },
        textColor: PALETTE.text,
        fontFamily: "var(--font-mono)",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: PALETTE.grid, style: LineStyle.Dotted },
        horzLines: { color: PALETTE.grid, style: LineStyle.Dotted },
      },
      rightPriceScale: { borderColor: PALETTE.grid },
      timeScale: { borderColor: PALETTE.grid, timeVisible: false },
      crosshair: {
        horzLine: { color: PALETTE.text, style: 2 },
        vertLine: { color: PALETTE.text, style: 2 },
      },
    });
    chartRef.current = chart;

    const ro = new ResizeObserver((entries) => {
      for (const e of entries) chart.applyOptions({ width: e.contentRect.width });
    });
    ro.observe(ref.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current.clear();
    };
  }, [height]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    // Remove dropped series
    const keepKeys = new Set(series.map((s) => s.key));
    for (const [k, s] of seriesRef.current.entries()) {
      if (!keepKeys.has(k)) {
        chart.removeSeries(s);
        seriesRef.current.delete(k);
      }
    }

    // Add / update remaining
    for (const def of series) {
      let s = seriesRef.current.get(def.key);
      if (!s) {
        s = chart.addSeries(LineSeries, {
          color: def.color,
          lineWidth: 2,
          priceLineVisible: false,
          title: def.label,
        });
        seriesRef.current.set(def.key, s);
      } else {
        s.applyOptions({ color: def.color });
      }
      // Deduplicate by day
      const byDate = new Map<number, number>();
      for (const p of def.data) {
        const ts = Math.floor(new Date(p.date).getTime() / 1000);
        byDate.set(ts, p.cumulative_pnl);
      }
      const rows = Array.from(byDate.entries())
        .sort((a, b) => a[0] - b[0])
        .map(([ts, v]) => ({ time: ts as UTCTimestamp, value: v }));
      s.setData(rows);
    }

    chart.timeScale().fitContent();
  }, [series]);

  return <div ref={ref} style={{ width: "100%" }} />;
}
