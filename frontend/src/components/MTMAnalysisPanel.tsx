"use client";

/**
 * MTM Analysis Panel — proper distribution analysis for daily mark-to-market PnL.
 *
 * Shows:
 *  1. Daily MTM OHLC candlestick chart (one candle per trading day, in PnL points)
 *  2. KPI strip — n days, mean close, win-rate, intraday DD, path shapes
 *  3. Distribution histograms (Close / High / Low / Range / Intraday DD)
 *  4. Quantile table for each series
 *  5. Per-DTE breakdown table
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import { useFetch } from "@/hooks/use-fetch";

const DEFAULT_API_BASE = "/api/multilegdm";

// ─── types ───────────────────────────────────────────────────────────────

interface OhlcRow {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  range: number;
  n_trades: number;
  dte: number | null;
}

interface SeriesStats {
  mean: number;
  std: number;
  min?: number;
  max?: number;
  skew?: number;
  kurt?: number;
  positive_pct?: number;
  zero_days?: number;
  p1: number;
  p5: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
  p95: number;
  p99: number;
}

interface DTEBreakdown {
  dte: number;
  n_days: number;
  close_mean: number;
  close_std: number;
  high_mean: number;
  low_mean: number;
  win_rate: number;
}

interface MtmStats {
  n_days: number;
  close: SeriesStats;
  high: SeriesStats;
  low: SeriesStats;
  range: SeriesStats;
  intraday_dd: SeriesStats;
  intraday_runup: SeriesStats;
  mae_recoveries: number;
  mfe_giveaways: number;
  all_red: number;
  all_green: number;
  by_dte?: DTEBreakdown[];
}

interface HistBin {
  lo: number;
  hi: number;
  count: number;
}

interface MtmDistribution {
  close: HistBin[];
  high: HistBin[];
  low: HistBin[];
  range: HistBin[];
  intraday_dd: HistBin[];
}

interface PathBin {
  lo: number;
  hi: number;
  count: number;
  pct: number;
  cum_pct: number;
  mean_close: number | null;
  median_close: number | null;
}

interface PathSection {
  n: number;
  summary: Record<string, number | null>;
  bins: PathBin[];
}

interface PathDistribution {
  recovery_lows: PathSection;
  giveaway_highs: PathSection;
}

// ─── component ───────────────────────────────────────────────────────────

export default function MTMAnalysisPanel({ apiBase = DEFAULT_API_BASE }: { apiBase?: string } = {}) {
  const { data: ohlc } = useFetch<OhlcRow[]>(`${apiBase}/mtm-ohlc`);
  const { data: stats } = useFetch<MtmStats>(`${apiBase}/mtm-stats`);
  const { data: dist } = useFetch<MtmDistribution>(`${apiBase}/mtm-distribution`);
  const { data: pathDist } = useFetch<PathDistribution>(`${apiBase}/path-distribution`);

  if (!ohlc || !stats || !dist) {
    return (
      <div className="panel">
        <div className="muted" style={{ padding: 20 }}>Loading MTM analysis…</div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <KpiStrip stats={stats} />
      <OhlcChart rows={ohlc} />
      <div className="grid-2">
        <Histogram title="Daily Close PnL (pts)" bins={dist.close} stat={stats.close} accent="#10b981" />
        <Histogram title="Intraday Drawdown (Low − Close, pts)" bins={dist.intraday_dd} stat={stats.intraday_dd} accent="#ef4444" />
      </div>
      <div className="grid-2">
        <Histogram title="Intraday High (pts)" bins={dist.high} stat={stats.high} accent="#22c55e" />
        <Histogram title="Intraday Low (pts)" bins={dist.low} stat={stats.low} accent="#f59e0b" />
      </div>
      <Histogram title="Daily Range (High − Low, pts)" bins={dist.range} stat={stats.range} accent="#a855f7" />
      {pathDist && (
        <div className="grid-2">
          <PathDistributionTable
            title="Recovery days (red → green)"
            subtitle="How deep did the intraday red get on days that closed positive?"
            unitLabel="Max red reached (|low|, pts)"
            section={pathDist.recovery_lows}
            tone="pos"
          />
          <PathDistributionTable
            title="Giveaway days (green → red)"
            subtitle="How high did the intraday green get on days that closed negative?"
            unitLabel="Max green reached (high, pts)"
            section={pathDist.giveaway_highs}
            tone="neg"
          />
        </div>
      )}
      <QuantileTable stats={stats} />
      {stats.by_dte && stats.by_dte.length > 0 && <DTETable rows={stats.by_dte} />}
    </div>
  );
}

// ─── KPI strip ───────────────────────────────────────────────────────────

function KpiStrip({ stats }: { stats: MtmStats }) {
  const items: { label: string; value: string; color?: string; hint?: string }[] = [
    { label: "Days analyzed", value: stats.n_days.toLocaleString() },
    {
      label: "Mean close (pts)",
      value: fmtNum(stats.close.mean),
      color: stats.close.mean >= 0 ? "var(--pos)" : "var(--neg)",
    },
    { label: "Day-level win %", value: `${stats.close.positive_pct?.toFixed(1)}%` },
    {
      label: "Mean intraday DD",
      value: fmtNum(stats.intraday_dd.mean),
      color: "var(--neg)",
      hint: "Avg drop from close to intraday low",
    },
    {
      label: "p5 close",
      value: fmtNum(stats.close.p5),
      color: "var(--neg)",
      hint: "5% of days closed worse than this",
    },
    {
      label: "p95 close",
      value: fmtNum(stats.close.p95),
      color: "var(--pos)",
      hint: "5% of days closed better than this",
    },
    {
      label: "Worst day",
      value: fmtNum(stats.close.min ?? 0),
      color: "var(--neg)",
    },
    {
      label: "Best day",
      value: fmtNum(stats.close.max ?? 0),
      color: "var(--pos)",
    },
    {
      label: "Red→green",
      value: stats.mae_recoveries.toString(),
      hint: "Days that went red intraday but closed green",
    },
    {
      label: "Green→red",
      value: stats.mfe_giveaways.toString(),
      color: "var(--neg)",
      hint: "Days that went green intraday but closed red",
    },
    {
      label: "All-green",
      value: stats.all_green.toString(),
      color: "var(--pos)",
      hint: "Days that never dipped below 0",
    },
    {
      label: "All-red",
      value: stats.all_red.toString(),
      color: "var(--neg)",
      hint: "Days that never went above 0",
    },
  ];

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
        gap: 8,
      }}
    >
      {items.map((it) => (
        <div
          key={it.label}
          className="panel"
          title={it.hint}
          style={{ padding: "10px 12px" }}
        >
          <div style={{ fontSize: 10, color: "var(--ink-3)", marginBottom: 2 }}>
            {it.label}
          </div>
          <div
            style={{
              fontSize: 18,
              fontFamily: "var(--font-geist-mono), monospace",
              color: it.color ?? "var(--ink)",
              fontWeight: 600,
            }}
          >
            {it.value}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── OHLC chart ──────────────────────────────────────────────────────────

function OhlcChart({ rows }: { rows: OhlcRow[] }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const legendRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  // Sort + dedup by date
  const candles = useMemo(() => {
    const sorted = [...rows].sort((a, b) => a.date.localeCompare(b.date));
    return sorted.map((r) => ({
      time: r.date as Time,
      open: r.open,
      high: r.high,
      low: r.low,
      close: r.close,
    }));
  }, [rows]);

  // Quick lookup of the full row by date for legend display (n_trades, dte, range)
  const rowByDate = useMemo(() => {
    const m = new Map<string, OhlcRow>();
    for (const r of rows) m.set(r.date, r);
    return m;
  }, [rows]);

  useEffect(() => {
    if (!hostRef.current) return;
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(hostRef.current, {
      width: hostRef.current.clientWidth,
      height: 380,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#a1a1aa",
        fontFamily: "var(--font-geist-mono), monospace",
      },
      grid: {
        vertLines: { color: "#27272a" },
        horzLines: { color: "#27272a" },
      },
      timeScale: { timeVisible: false, borderColor: "#3f3f46" },
      rightPriceScale: { borderColor: "#3f3f46" },
      crosshair: {
        horzLine: { color: "#71717a", style: 2 },
        vertLine: { color: "#71717a", style: 2 },
      },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });
    series.setData(candles);

    // Zero baseline
    series.createPriceLine({
      price: 0,
      color: "#71717a",
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: "0",
    });

    // Hover legend — TradingView style. Renders OHLC of the hovered candle
    // in a fixed pill at the top-center of the chart, plus extras (date, dte, n_trades, range).
    const renderLegend = (
      o: number, h: number, l: number, c: number,
      date: string | null, extras: { dte?: number | null; n_trades?: number; range?: number } = {},
    ) => {
      if (!legendRef.current) return;
      const sign = (v: number) => (v >= 0 ? "+" : "");
      const fmt = (v: number) =>
        sign(v) + v.toLocaleString(undefined, { maximumFractionDigits: 1 });
      const cColor = c >= 0 ? "#10b981" : "#ef4444";
      legendRef.current.innerHTML = `
        <div style="display:flex; gap:14px; align-items:baseline; flex-wrap:wrap;">
          ${date ? `<span style="color:#a1a1aa;font-size:11px;">${date}</span>` : ""}
          <span><span style="color:#71717a;">O</span> ${fmt(o)}</span>
          <span><span style="color:#71717a;">H</span> <span style="color:#22c55e">${fmt(h)}</span></span>
          <span><span style="color:#71717a;">L</span> <span style="color:#ef4444">${fmt(l)}</span></span>
          <span><span style="color:#71717a;">C</span> <span style="color:${cColor}">${fmt(c)}</span></span>
          ${extras.range != null ? `<span style="color:#71717a;font-size:11px;">range ${fmt(extras.range)}</span>` : ""}
          ${extras.n_trades != null ? `<span style="color:#71717a;font-size:11px;">${extras.n_trades} trade${extras.n_trades === 1 ? "" : "s"}</span>` : ""}
          ${extras.dte != null ? `<span style="color:#71717a;font-size:11px;">DTE ${extras.dte}</span>` : ""}
        </div>`;
    };

    // Default: show last candle on first render
    const last = candles[candles.length - 1];
    if (last) {
      const r = rowByDate.get(last.time as string);
      renderLegend(last.open, last.high, last.low, last.close, last.time as string, {
        dte: r?.dte ?? null, n_trades: r?.n_trades, range: r?.range,
      });
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    chart.subscribeCrosshairMove((param: any) => {
      const data = param.seriesData?.get(series);
      if (data && "open" in data) {
        const dateStr = (param.time as string) ?? null;
        const r = dateStr ? rowByDate.get(dateStr) : undefined;
        renderLegend(data.open, data.high, data.low, data.close, dateStr, {
          dte: r?.dte ?? null, n_trades: r?.n_trades, range: r?.range,
        });
      } else if (last) {
        // Fall back to last candle when crosshair leaves the chart
        const r = rowByDate.get(last.time as string);
        renderLegend(last.open, last.high, last.low, last.close, last.time as string, {
          dte: r?.dte ?? null, n_trades: r?.n_trades, range: r?.range,
        });
      }
    });

    chart.timeScale().fitContent();
    chartRef.current = chart;

    const ro = new ResizeObserver((entries) => {
      for (const e of entries) chart.applyOptions({ width: e.contentRect.width });
    });
    ro.observe(hostRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, rowByDate]);

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Daily MTM OHLC (PnL points)</h2>
        <span className="meta" style={{ fontSize: 11 }}>
          Open is always 0 (intraday strategy). High/Low = intraday peak / trough of running PnL.
          Close = realized day PnL.
        </span>
      </div>
      <div className="panel-body" style={{ padding: "12px 14px" }}>
        <div style={{ position: "relative", width: "100%" }}>
          {/* Floating OHLC legend at top-center of the chart */}
          <div
            ref={legendRef}
            style={{
              position: "absolute",
              top: 6,
              left: "50%",
              transform: "translateX(-50%)",
              zIndex: 4,
              padding: "6px 14px",
              borderRadius: 6,
              border: "1px solid var(--border)",
              background: "rgba(15,15,17,0.85)",
              backdropFilter: "blur(6px)",
              fontFamily: "var(--font-geist-mono), monospace",
              fontSize: 13,
              color: "var(--ink)",
              pointerEvents: "none",
              whiteSpace: "nowrap",
            }}
          />
          <div ref={hostRef} style={{ width: "100%" }} />
        </div>
      </div>
    </div>
  );
}

// ─── histogram ───────────────────────────────────────────────────────────

function Histogram({
  title,
  bins,
  stat,
  accent,
}: {
  title: string;
  bins: HistBin[];
  stat: SeriesStats;
  accent: string;
}) {
  if (!bins?.length) return null;
  const maxCount = Math.max(...bins.map((b) => b.count));
  // Find the bin containing zero (if any) for emphasis
  const zeroIdx = bins.findIndex((b) => b.lo <= 0 && b.hi > 0);

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>{title}</h2>
        <span className="meta" style={{ fontSize: 11 }}>
          μ={fmtNum(stat.mean)} · σ={fmtNum(stat.std)} ·
          p5={fmtNum(stat.p5)} · p50={fmtNum(stat.p50)} · p95={fmtNum(stat.p95)}
        </span>
      </div>
      <div className="panel-body" style={{ padding: "12px 14px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            gap: 1,
            height: 160,
            borderBottom: "1px solid var(--border)",
            paddingBottom: 2,
          }}
        >
          {bins.map((b, i) => (
            <div
              key={i}
              title={`[${b.lo}, ${b.hi})  count=${b.count}`}
              style={{
                flex: 1,
                height: `${(b.count / maxCount) * 100}%`,
                background: i === zeroIdx ? "#71717a" : accent,
                opacity: 0.85,
                minHeight: b.count > 0 ? 1 : 0,
              }}
            />
          ))}
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: 10,
            color: "var(--ink-3)",
            marginTop: 4,
            fontFamily: "var(--font-geist-mono), monospace",
          }}
        >
          <span>{bins[0].lo.toFixed(0)}</span>
          <span>{bins[Math.floor(bins.length / 2)].lo.toFixed(0)}</span>
          <span>{bins[bins.length - 1].hi.toFixed(0)}</span>
        </div>
      </div>
    </div>
  );
}

// ─── quantile table ──────────────────────────────────────────────────────

function QuantileTable({ stats }: { stats: MtmStats }) {
  const series: { key: keyof MtmStats; label: string }[] = [
    { key: "close", label: "Close" },
    { key: "high", label: "High" },
    { key: "low", label: "Low" },
    { key: "range", label: "Range" },
    { key: "intraday_dd", label: "Intraday DD" },
    { key: "intraday_runup", label: "Intraday Run-up" },
  ];
  const cols: (keyof SeriesStats)[] = [
    "mean", "std", "p1", "p5", "p25", "p50", "p75", "p95", "p99",
  ];

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Per-Series Quantiles (PnL points)</h2>
      </div>
      <div className="panel-body tight">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Series</th>
                {cols.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {series.map(({ key, label }) => {
                const s = stats[key] as SeriesStats | undefined;
                if (!s) return null;
                return (
                  <tr key={key}>
                    <td><strong>{label}</strong></td>
                    {cols.map((c) => {
                      const v = s[c];
                      const num = typeof v === "number" ? v : 0;
                      return (
                        <td key={c} className={num >= 0 ? "num-pos" : "num-neg"}>
                          {fmtNum(num)}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─── DTE table ───────────────────────────────────────────────────────────

function DTETable({ rows }: { rows: DTEBreakdown[] }) {
  const sorted = [...rows].sort((a, b) => a.dte - b.dte);
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>By DTE Bucket</h2>
        <span className="meta" style={{ fontSize: 11 }}>
          How daily MTM behaves across days-to-expiry
        </span>
      </div>
      <div className="panel-body tight">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>DTE</th>
                <th># days</th>
                <th>Mean close</th>
                <th>Close σ</th>
                <th>Mean high</th>
                <th>Mean low</th>
                <th>Day win %</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.dte}>
                  <td>
                    <span
                      className="pill"
                      style={{
                        background:
                          r.dte === 0
                            ? "rgba(239,68,68,0.18)"
                            : r.dte <= 2
                              ? "rgba(245,158,11,0.18)"
                              : "rgba(59,130,246,0.18)",
                        fontWeight: 600,
                      }}
                    >
                      {r.dte < 0 ? "—" : r.dte}
                    </span>
                  </td>
                  <td>{r.n_days}</td>
                  <td className={r.close_mean >= 0 ? "num-pos" : "num-neg"}>
                    {fmtNum(r.close_mean)}
                  </td>
                  <td>{fmtNum(r.close_std)}</td>
                  <td className="num-pos">{fmtNum(r.high_mean)}</td>
                  <td className="num-neg">{fmtNum(r.low_mean)}</td>
                  <td>{r.win_rate.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─── path distribution table ─────────────────────────────────────────────

function PathDistributionTable({
  title,
  subtitle,
  unitLabel,
  section,
  tone,
}: {
  title: string;
  subtitle: string;
  unitLabel: string;
  section: PathSection;
  tone: "pos" | "neg";
}) {
  // Drop empty bins from the tail to keep the table compact
  const lastNonEmpty = (() => {
    for (let i = section.bins.length - 1; i >= 0; i--) {
      if (section.bins[i].count > 0) return i;
    }
    return -1;
  })();
  const bins = lastNonEmpty >= 0 ? section.bins.slice(0, lastNonEmpty + 1) : section.bins;
  const maxCount = Math.max(1, ...bins.map((b) => b.count));
  const accent = tone === "pos" ? "#10b981" : "#ef4444";

  // Pull a couple of summary numbers to header
  const meanLabel = tone === "pos" ? "mean depth" : "mean peak";
  const medianLabel = tone === "pos" ? "median depth" : "median peak";
  const maxLabel = tone === "pos" ? "deepest" : "highest";
  const closeLabel = tone === "pos" ? "mean recovery close" : "mean giveaway close";

  const summaryMean =
    section.summary[tone === "pos" ? "mean_depth" : "mean_peak"];
  const summaryMedian =
    section.summary[tone === "pos" ? "median_depth" : "median_peak"];
  const summaryMax =
    section.summary[tone === "pos" ? "max_depth" : "max_peak"];
  const summaryClose =
    section.summary[tone === "pos" ? "mean_recovery_close" : "mean_giveaway_close"];

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>{title}</h2>
        <span className="meta" style={{ fontSize: 11 }}>
          {section.n.toLocaleString()} days · {meanLabel} {fmtNum(summaryMean ?? 0)} ·
          {" "}
          {medianLabel} {fmtNum(summaryMedian ?? 0)} ·
          {" "}
          {maxLabel} {fmtNum(summaryMax ?? 0)} ·
          {" "}
          {closeLabel}{" "}
          <span className={(summaryClose ?? 0) >= 0 ? "num-pos" : "num-neg"}>
            {fmtNum(summaryClose ?? 0)}
          </span>
        </span>
      </div>
      <div className="panel-body" style={{ padding: "4px 6px" }}>
        <div className="muted" style={{ fontSize: 11, padding: "4px 8px 8px" }}>
          {subtitle}
        </div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>{unitLabel}</th>
                <th>Days</th>
                <th>%</th>
                <th>Cum %</th>
                <th>Mean close (pts)</th>
                <th>Median close</th>
                <th style={{ width: "30%" }}>Frequency</th>
              </tr>
            </thead>
            <tbody>
              {bins.map((b, i) => (
                <tr key={i}>
                  <td style={{ fontFamily: "var(--font-geist-mono), monospace" }}>
                    [{b.lo}, {b.hi})
                  </td>
                  <td>{b.count}</td>
                  <td>{b.pct.toFixed(1)}%</td>
                  <td>{b.cum_pct.toFixed(1)}%</td>
                  <td className={(b.mean_close ?? 0) >= 0 ? "num-pos" : "num-neg"}>
                    {b.mean_close == null ? "—" : fmtNum(b.mean_close)}
                  </td>
                  <td className={(b.median_close ?? 0) >= 0 ? "num-pos" : "num-neg"}>
                    {b.median_close == null ? "—" : fmtNum(b.median_close)}
                  </td>
                  <td>
                    <div
                      style={{
                        background: accent,
                        opacity: 0.85,
                        height: 10,
                        width: `${(b.count / maxCount) * 100}%`,
                        borderRadius: 1,
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─── helpers ─────────────────────────────────────────────────────────────

function fmtNum(v: number): string {
  if (!Number.isFinite(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return sign + v.toLocaleString(undefined, { maximumFractionDigits: 1 });
}
