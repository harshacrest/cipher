"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import {
  createChart,
  createSeriesMarkers,
  ColorType,
  LineSeries,
} from "lightweight-charts";
import type { UTCTimestamp } from "lightweight-charts";
import { useFetch } from "@/hooks/use-fetch";
import type {
  Metric,
  EquityPoint,
  DayHighTrade,
  DayHighIntradayData,
  MonthlyRow,
  YearlyRow,
  DowRow,
  DteRow,
} from "@/types";

const API = "/api/day-high";

// ─── Metrics Grid ──────────────────────────────────────────────

const GROUPS: Record<string, string[]> = {
  Performance: [
    "Total PnL (pts)",
    "Annualized Return (pts)",
    "Profit Factor",
    "Expectancy (pts)",
  ],
  "Trade Stats": [
    "Total Trades",
    "Winners",
    "Losers",
    "Flat",
    "Win Rate (%)",
  ],
  Risk: [
    "Max Drawdown (pts)",
    "Max DD Duration (days)",
    "Sharpe Ratio (ann.)",
    "Sortino Ratio (ann.)",
    "Calmar Ratio",
  ],
  Distribution: [
    "Avg PnL (pts)",
    "Avg Win (pts)",
    "Avg Loss (pts)",
    "Max Win (pts)",
    "Max Loss (pts)",
    "Risk-Reward Ratio",
    "Std Dev (daily)",
    "Skewness",
    "Kurtosis",
  ],
  "Streaks & Monthly": [
    "Max Win Streak",
    "Max Loss Streak",
    "Best Month (pts)",
    "Worst Month (pts)",
    "Profitable Months (%)",
  ],
};

function formatValue(v: number | string): string {
  if (typeof v === "string") return v;
  if (Number.isInteger(v)) return v.toLocaleString();
  return v.toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function valueColor(name: string, v: number | string): string {
  if (typeof v !== "number") return "text-zinc-100";
  if (name.includes("Loss") || name === "Max Drawdown (pts)")
    return v < 0 ? "text-red-400" : "text-zinc-100";
  if (
    name.includes("PnL") ||
    name.includes("Return") ||
    name.includes("Profit") ||
    name.includes("Win")
  )
    return v > 0 ? "text-emerald-400" : v < 0 ? "text-red-400" : "text-zinc-100";
  return "text-zinc-100";
}

function DhMetrics() {
  const { data, loading } = useFetch<Metric[]>(`${API}/metrics`);
  if (loading || !data)
    return <div className="animate-pulse h-48 bg-zinc-800/50 rounded-lg" />;

  const lookup = new Map(data.map((m) => [m.Metric, m.Value]));

  return (
    <div className="space-y-6">
      {Object.entries(GROUPS).map(([group, keys]) => (
        <div key={group}>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-3">
            {group}
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
            {keys.map((key) => {
              const val = lookup.get(key);
              if (val === undefined) return null;
              return (
                <div
                  key={key}
                  className="bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-4 py-3"
                >
                  <div className="text-[11px] text-zinc-500 truncate">{key}</div>
                  <div
                    className={`text-lg font-mono font-semibold mt-0.5 ${valueColor(key, val)}`}
                  >
                    {formatValue(val)}
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

// ─── Equity Curve ──────────────────────────────────────────────

function DhEquityCurve() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const { data } = useFetch<EquityPoint[]>(`${API}/equity`);

  useEffect(() => {
    if (!containerRef.current || !data || data.length === 0) return;
    const container = containerRef.current;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 350,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#a1a1aa",
        fontFamily: "var(--font-geist-mono), monospace",
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: "#27272a" },
      },
      timeScale: { timeVisible: false, borderColor: "#3f3f46" },
      rightPriceScale: { borderColor: "#3f3f46" },
      crosshair: {
        horzLine: { color: "#71717a", style: 2 },
        vertLine: { color: "#71717a", style: 2 },
      },
    });

    const series = chart.addSeries(LineSeries, {
      color: "#22c55e",
      lineWidth: 2,
      priceLineVisible: false,
    });

    // Deduplicate by date — keep last entry per date (highest cumulative_pnl index)
    const byDate = new Map<number, number>();
    for (const p of data) {
      const ts = Math.floor(new Date(p.date).getTime() / 1000);
      byDate.set(ts, p.cumulative_pnl);
    }
    const eqData = Array.from(byDate.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([ts, val]) => ({ time: ts as UTCTimestamp, value: val }));
    series.setData(eqData);
    chart.timeScale().fitContent();
    chartRef.current = chart;

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) chart.applyOptions({ width: entry.contentRect.width });
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [data]);

  return (
    <div>
      <h2 className="text-sm font-semibold text-zinc-400 mb-3">Equity Curve</h2>
      <div
        ref={containerRef}
        className="w-full rounded-lg border border-zinc-700/50 overflow-hidden"
      />
    </div>
  );
}

// ─── Intraday Chart (supports multiple trades per day) ─────────

function timeToUnix(timeStr: string): UTCTimestamp {
  return Math.floor(
    new Date(`2024-01-01T${timeStr}:00Z`).getTime() / 1000
  ) as UTCTimestamp;
}

const ENTRY_COLORS = ["#22c55e", "#06b6d4", "#84cc16"];
const EXIT_SL_COLOR = "#ef4444";
const EXIT_EOD_COLOR = "#f59e0b";

function DhIntradayChart({ date }: { date: string }) {
  const spotRef = useRef<HTMLDivElement>(null);
  const optRef = useRef<HTMLDivElement>(null);
  const spotChartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const optChartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const { data, loading, error } = useFetch<DayHighIntradayData>(
    `${API}/intraday/${date}`
  );

  useEffect(() => {
    if (!spotRef.current || !optRef.current || !data || data.ticks.length === 0) return;

    // Cleanup
    if (spotChartRef.current) { spotChartRef.current.remove(); spotChartRef.current = null; }
    if (optChartRef.current) { optChartRef.current.remove(); optChartRef.current = null; }

    const dedup = <T,>(arr: { time: UTCTimestamp; value: T }[]) => {
      const seen = new Set<number>();
      return arr.filter((d) => {
        if (seen.has(d.time as number)) return false;
        seen.add(d.time as number);
        return true;
      });
    };

    const chartOpts = (h: number) => ({
      width: spotRef.current!.clientWidth,
      height: h,
      layout: {
        background: { type: ColorType.Solid as const, color: "transparent" },
        textColor: "#a1a1aa",
        fontFamily: "var(--font-geist-mono), monospace",
      },
      grid: { vertLines: { visible: false }, horzLines: { color: "#27272a" } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: "#3f3f46" },
      crosshair: { horzLine: { color: "#71717a", style: 2 as const }, vertLine: { color: "#71717a", style: 2 as const } },
    });

    // ── SPOT CHART ──
    const spotChart = createChart(spotRef.current, {
      ...chartOpts(300),
      leftPriceScale: { visible: true, borderColor: "#3f3f46" },
      rightPriceScale: { visible: false },
    });
    const spotSeries = spotChart.addSeries(LineSeries, {
      priceScaleId: "left", color: "#3b82f6", lineWidth: 2, title: "Spot", priceLineVisible: false,
    });
    spotSeries.setData(
      dedup(data.ticks.map((t) => ({ time: timeToUnix(t.time), value: t.spot })))
    );

    // Entry/exit markers on spot
    const markers: Parameters<typeof createSeriesMarkers>[1] = [];
    for (const trade of data.trades) {
      const colorIdx = (trade.trade_num - 1) % ENTRY_COLORS.length;
      if (trade.entry_time) {
        markers.push({
          time: timeToUnix(trade.entry_time), position: "aboveBar",
          color: ENTRY_COLORS[colorIdx], shape: "arrowDown",
          text: `#${trade.trade_num} ${trade.side} ${trade.strike}`,
        });
      }
      if (trade.exit_time) {
        markers.push({
          time: timeToUnix(trade.exit_time), position: "belowBar",
          color: trade.exit_reason === "SL" ? EXIT_SL_COLOR : EXIT_EOD_COLOR, shape: "arrowUp",
          text: `#${trade.trade_num} ${trade.exit_reason}`,
        });
      }
    }
    markers.sort((a, b) => (a.time as number) - (b.time as number));
    if (markers.length > 0) createSeriesMarkers(spotSeries, markers);
    spotChart.timeScale().fitContent();
    spotChartRef.current = spotChart;

    // ── OPTIONS CHART (CE on RHS, PE on LHS) ──
    const optChart = createChart(optRef.current, {
      ...chartOpts(350),
      leftPriceScale: { visible: true, borderColor: "#3f3f46" },
      rightPriceScale: { visible: true, borderColor: "#3f3f46" },
    });

    const CE_COLORS = ["#f59e0b", "#fb923c", "#fbbf24"];
    const PE_COLORS = ["#a855f7", "#c084fc", "#d8b4fe"];

    let ceIdx = 0;
    let peIdx = 0;

    for (const trade of data.trades) {
      if (!trade.price_ticks || trade.price_ticks.length === 0) continue;

      const isCe = trade.side === "CE";
      const color = isCe ? CE_COLORS[ceIdx % CE_COLORS.length] : PE_COLORS[peIdx % PE_COLORS.length];
      const scaleId = isCe ? "right" : "left";

      const series = optChart.addSeries(LineSeries, {
        priceScaleId: scaleId,
        color,
        lineWidth: 2,
        title: `${trade.side} ${trade.strike}`,
        priceLineVisible: false,
      });

      series.setData(
        dedup(trade.price_ticks.map((t) => ({ time: timeToUnix(t.time), value: t.price })))
      );

      // SL line for this trade
      if (trade.sl_level > 0) {
        const slSeries = optChart.addSeries(LineSeries, {
          priceScaleId: scaleId,
          color: "#ef4444",
          lineWidth: 1,
          lineStyle: 2,
          title: `SL ${trade.sl_level.toFixed(0)}`,
          priceLineVisible: false,
          crosshairMarkerVisible: false,
        });

        // Draw SL only during the trade duration
        const ticks = trade.price_ticks;
        if (ticks.length >= 2) {
          const startTime = trade.entry_time ? timeToUnix(trade.entry_time) : timeToUnix(ticks[0].time);
          const endTime = trade.exit_time ? timeToUnix(trade.exit_time) : timeToUnix(ticks[ticks.length - 1].time);
          slSeries.setData([
            { time: startTime, value: trade.sl_level },
            { time: endTime, value: trade.sl_level },
          ]);
        }
      }

      // Entry/exit markers on option series
      const optMarkers: Parameters<typeof createSeriesMarkers>[1] = [];
      if (trade.entry_time) {
        optMarkers.push({
          time: timeToUnix(trade.entry_time), position: "aboveBar",
          color: "#22c55e", shape: "arrowDown",
          text: `SELL @${trade.entry_px}`,
        });
      }
      if (trade.exit_time) {
        optMarkers.push({
          time: timeToUnix(trade.exit_time), position: "belowBar",
          color: trade.exit_reason === "SL" ? "#ef4444" : "#f59e0b", shape: "arrowUp",
          text: `${trade.exit_reason} @${trade.exit_px}`,
        });
      }
      optMarkers.sort((a, b) => (a.time as number) - (b.time as number));
      if (optMarkers.length > 0) createSeriesMarkers(series, optMarkers);

      if (isCe) ceIdx++;
      else peIdx++;
    }

    optChart.timeScale().fitContent();
    optChartRef.current = optChart;

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        spotChart.applyOptions({ width: entry.contentRect.width });
        optChart.applyOptions({ width: entry.contentRect.width });
      }
    });
    ro.observe(spotRef.current);

    return () => {
      ro.disconnect();
      spotChart.remove(); spotChartRef.current = null;
      optChart.remove(); optChartRef.current = null;
    };
  }, [data]);

  if (loading)
    return <div className="animate-pulse h-[700px] bg-zinc-800/50 rounded-lg" />;
  if (error)
    return (
      <div className="h-[700px] flex items-center justify-center text-red-400 text-sm bg-zinc-800/50 rounded-lg">
        No data for {date}
      </div>
    );

  return (
    <div>
      <div className="flex items-center gap-4 mb-2 text-xs text-zinc-500 flex-wrap">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-blue-500 rounded" />
          Spot
        </span>
        {data && (
          <span
            className={`ml-auto font-mono font-semibold ${data.total_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}
          >
            Day PnL: {data.total_pnl >= 0 ? "+" : ""}
            {data.total_pnl.toFixed(2)} pts ({data.trades.length} trade
            {data.trades.length !== 1 ? "s" : ""})
          </span>
        )}
      </div>
      <div ref={spotRef} className="w-full rounded-lg border border-zinc-700/50 overflow-hidden" />

      <div className="flex items-center gap-4 mt-4 mb-2 text-xs text-zinc-500 flex-wrap">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-amber-500 rounded" />
          CE (RHS)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-purple-500 rounded" />
          PE (LHS)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-red-500 rounded" />
          SL Lines
        </span>
      </div>
      <div ref={optRef} className="w-full rounded-lg border border-zinc-700/50 overflow-hidden" />

      {/* Per-trade details */}
      {data && data.trades.length > 0 && (
        <div className="mt-3 space-y-1">
          {data.trades.map((t) => (
            <div
              key={t.trade_num}
              className="flex items-center gap-4 text-xs font-mono px-3 py-1.5 bg-zinc-800/40 rounded border border-zinc-800"
            >
              <span className="text-zinc-500">#{t.trade_num}</span>
              <span className={t.side === "CE" ? "text-amber-400" : "text-purple-400"}>
                {t.side} {t.strike}
              </span>
              <span className="text-zinc-500">
                {t.entry_time ?? "?"} → {t.exit_time ?? "?"}
              </span>
              <span className="text-zinc-400">
                In: {t.entry_px} → Out: {t.exit_px} | DH: {t.day_high} | SL: {t.sl_level}
              </span>
              <span className={t.exit_reason === "SL" ? "text-red-400" : "text-amber-400"}>
                {t.exit_reason}
              </span>
              <span className={`ml-auto font-semibold ${t.pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {t.pnl >= 0 ? "+" : ""}{t.pnl.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Intraday Explorer with Date Dropdown ──────────────────────

function DhIntradayExplorer({ externalDate }: { externalDate?: string | null }) {
  const { data: dates } = useFetch<string[]>(`${API}/available-dates`);
  const [selectedDate, setSelectedDate] = useState<string>("");

  useEffect(() => {
    if (dates && dates.length > 0 && !selectedDate) {
      setSelectedDate(dates[dates.length - 1]);
    }
  }, [dates, selectedDate]);

  useEffect(() => {
    if (externalDate && dates?.includes(externalDate)) {
      setSelectedDate(externalDate);
      document
        .getElementById("dh-intraday-explorer")
        ?.scrollIntoView({ behavior: "smooth" });
    }
  }, [externalDate, dates]);

  if (!selectedDate)
    return <div className="animate-pulse h-[500px] bg-zinc-800/50 rounded-lg" />;

  return (
    <div id="dh-intraday-explorer" className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-400">
          Intraday Explorer
        </h2>
        <div className="flex items-center gap-3">
          <select
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm font-mono text-zinc-200 focus:outline-none focus:ring-1 focus:ring-zinc-500"
          >
            {dates?.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          {dates && (
            <span className="text-xs text-zinc-600">
              {(dates.indexOf(selectedDate) ?? 0) + 1} / {dates.length} trading
              days
            </span>
          )}
        </div>
      </div>
      <DhIntradayChart date={selectedDate} />
    </div>
  );
}

// ─── Trades Table ──────────────────────────────────────────────

type SortKey = keyof DayHighTrade;

function DhTradesTable({
  onDateSelect,
}: {
  onDateSelect?: (date: string) => void;
}) {
  const { data, loading } = useFetch<DayHighTrade[]>(`${API}/trades`);
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

  if (loading || !data)
    return <div className="animate-pulse h-64 bg-zinc-800/50 rounded-lg" />;

  const displayed = showAll ? sorted : sorted.slice(0, 50);

  function handleSort(key: SortKey) {
    if (key === sortKey) setSortAsc(!sortAsc);
    else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  const cols: { key: SortKey; label: string; fmt?: (v: number) => string }[] = [
    { key: "date", label: "Date" },
    { key: "trade_num", label: "#" },
    { key: "side", label: "Side" },
    { key: "strike", label: "Strike" },
    { key: "entry_px", label: "Entry", fmt: (v) => v.toFixed(2) },
    { key: "exit_px", label: "Exit", fmt: (v) => v.toFixed(2) },
    { key: "day_high", label: "Opt DH", fmt: (v) => v.toFixed(2) },
    { key: "sl_level", label: "SL", fmt: (v) => v.toFixed(2) },
    { key: "exit_reason", label: "Exit Type" },
    { key: "pnl", label: "PnL", fmt: (v) => v.toFixed(2) },
    { key: "pnl_pct", label: "PnL %", fmt: (v) => v.toFixed(2) + "%" },
    { key: "spot_at_entry", label: "Spot", fmt: (v) => v.toFixed(1) },
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
                key={`${trade.date}-${trade.trade_num}`}
                onClick={() => onDateSelect?.(trade.date)}
                className="border-t border-zinc-800 hover:bg-zinc-800/60 cursor-pointer transition-colors"
              >
                {cols.map((col) => {
                  const raw = trade[col.key];
                  let display: string;
                  if (raw == null) display = "-";
                  else if (col.fmt && typeof raw === "number") display = col.fmt(raw);
                  else display = String(raw);

                  const isPnl = col.key === "pnl" || col.key === "pnl_pct";
                  const isExit = col.key === "exit_reason";
                  let color = "text-zinc-300";
                  if (isPnl) {
                    color =
                      typeof raw === "number" && raw >= 0
                        ? "text-emerald-400"
                        : "text-red-400";
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

// ─── Breakdown Tabs ────────────────────────────────────────────

const MONTH_NAMES = [
  "",
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function BTable({
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
                  <td key={j} className={`px-3 py-1.5 ${color} whitespace-nowrap`}>
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

const BTABS = ["Monthly", "Yearly", "Day of Week", "By DTE"] as const;
type BTab = (typeof BTABS)[number];

function DhBreakdownTabs() {
  const [active, setActive] = useState<BTab>("Monthly");
  const { data: monthly } = useFetch<MonthlyRow[]>(`${API}/monthly`);
  const { data: yearly } = useFetch<YearlyRow[]>(`${API}/yearly`);
  const { data: dow } = useFetch<DowRow[]>(`${API}/dow`);
  const { data: dte } = useFetch<DteRow[]>(`${API}/dte`);

  return (
    <div>
      <div className="flex items-center gap-1 mb-4">
        {BTABS.map((tab) => (
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
      {active === "Monthly" &&
        (monthly ? (
          <BTable
            headers={["Year", "Month", "Trades", "Total PnL", "Avg PnL", "Win Rate %", "Max Win", "Max Loss"]}
            rows={monthly.map((r) => [r.year, MONTH_NAMES[r.month] || r.month, r.trades, r.total_pnl, r.avg_pnl, r.win_rate, r.max_win, r.max_loss])}
          />
        ) : (
          <div className="animate-pulse h-48 bg-zinc-800/50 rounded-lg" />
        ))}
      {active === "Yearly" &&
        (yearly ? (
          <BTable
            headers={["Year", "Trades", "Total PnL", "Avg PnL", "Win Rate %", "Max Win", "Max Loss", "Sharpe"]}
            rows={yearly.map((r) => [r.year, r.trades, r.total_pnl, r.avg_pnl, r.win_rate, r.max_win, r.max_loss, r.sharpe])}
          />
        ) : (
          <div className="animate-pulse h-48 bg-zinc-800/50 rounded-lg" />
        ))}
      {active === "Day of Week" &&
        (dow ? (
          <BTable
            headers={["Day", "Trades", "Total PnL", "Avg PnL", "Win Rate %"]}
            rows={dow.map((r) => [r.day_of_week, r.trades, r.total_pnl, r.avg_pnl, r.win_rate])}
          />
        ) : (
          <div className="animate-pulse h-48 bg-zinc-800/50 rounded-lg" />
        ))}
      {active === "By DTE" &&
        (dte ? (
          <BTable
            headers={["DTE", "Trades", "Total PnL", "Avg PnL", "Win Rate %"]}
            rows={dte.map((r) => [r.dte, r.trades, r.total_pnl, r.avg_pnl, r.win_rate])}
          />
        ) : (
          <div className="animate-pulse h-48 bg-zinc-800/50 rounded-lg" />
        ))}
    </div>
  );
}


// ─── PnL Distribution Histogram (frequency buckets) ──────────

function DhPnlHistogram() {
  const { data } = useFetch<DayHighTrade[]>(`${API}/trades`);

  const { buckets, stats } = useMemo(() => {
    if (!data || data.length === 0) return { buckets: [], stats: null };

    const pnls = data.map((t) => t.pnl);
    const minPnl = Math.min(...pnls);
    const maxPnl = Math.max(...pnls);

    // Create ~30 buckets
    const bucketSize = Math.max(5, Math.ceil((maxPnl - minPnl) / 30 / 5) * 5);
    const bucketStart = Math.floor(minPnl / bucketSize) * bucketSize;
    const bucketEnd = Math.ceil(maxPnl / bucketSize) * bucketSize;

    const bMap = new Map<number, number>();
    for (let b = bucketStart; b <= bucketEnd; b += bucketSize) {
      bMap.set(b, 0);
    }
    for (const p of pnls) {
      const b = Math.floor(p / bucketSize) * bucketSize;
      bMap.set(b, (bMap.get(b) || 0) + 1);
    }

    const bucketArr = Array.from(bMap.entries())
      .map(([lower, count]) => ({ lower, upper: lower + bucketSize, count }))
      .sort((a, b) => a.lower - b.lower);

    const wins = data.filter((t) => t.pnl > 0);
    const losses = data.filter((t) => t.pnl < 0);
    const totalWin = wins.reduce((s, t) => s + t.pnl, 0);
    const totalLoss = losses.reduce((s, t) => s + t.pnl, 0);

    return {
      buckets: bucketArr,
      stats: {
        wins: wins.length,
        losses: losses.length,
        totalWin,
        totalLoss,
        avgWin: wins.length > 0 ? totalWin / wins.length : 0,
        avgLoss: losses.length > 0 ? totalLoss / losses.length : 0,
        maxWin: wins.length > 0 ? Math.max(...wins.map((t) => t.pnl)) : 0,
        maxLoss: losses.length > 0 ? Math.min(...losses.map((t) => t.pnl)) : 0,
        median: pnls.sort((a, b) => a - b)[Math.floor(pnls.length / 2)],
      },
    };
  }, [data]);

  if (!data || buckets.length === 0)
    return <div className="animate-pulse h-64 bg-zinc-800/50 rounded-lg" />;

  const maxCount = Math.max(...buckets.map((b) => b.count));

  return (
    <div>
      <h2 className="text-sm font-semibold text-zinc-400 mb-3">
        PnL Distribution
      </h2>

      {/* Frequency histogram */}
      <div className="rounded-lg border border-zinc-700/50 bg-zinc-900/30 px-4 py-4">
        <div className="flex items-end gap-[2px]" style={{ height: 200 }}>
          {buckets.map((b) => {
            const pct = maxCount > 0 ? (b.count / maxCount) * 100 : 0;
            const isWin = b.lower >= 0;
            const isZeroBucket = b.lower <= 0 && b.upper > 0;
            return (
              <div
                key={b.lower}
                className="flex-1 group relative"
                style={{ height: "100%", display: "flex", alignItems: "flex-end" }}
              >
                <div
                  className={`w-full rounded-t-sm transition-opacity ${
                    isWin ? "bg-emerald-500" : "bg-red-500"
                  } ${isZeroBucket ? "bg-gradient-to-t from-red-500 to-emerald-500" : ""}`}
                  style={{
                    height: `${pct}%`,
                    minHeight: b.count > 0 ? 2 : 0,
                    opacity: 0.8,
                  }}
                />
                {/* Tooltip on hover */}
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block z-10">
                  <div className="bg-zinc-800 border border-zinc-600 rounded px-2 py-1 text-[10px] font-mono text-zinc-300 whitespace-nowrap shadow-lg">
                    <div>{b.lower} to {b.upper}</div>
                    <div className="font-semibold">{b.count} trades</div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        {/* X-axis labels */}
        <div className="flex justify-between mt-1 text-[9px] font-mono text-zinc-600">
          <span>{buckets[0]?.lower}</span>
          <span className="text-zinc-500">0</span>
          <span>{buckets[buckets.length - 1]?.upper}</span>
        </div>
        <div className="text-center text-[10px] text-zinc-600 mt-0.5">PnL (pts)</div>
      </div>

      {/* Summary stats */}
      {stats && (
        <div className="mt-3 grid grid-cols-2 sm:grid-cols-5 gap-2">
          <div className="bg-zinc-800/40 rounded border border-zinc-800 px-3 py-2">
            <div className="text-[10px] text-zinc-500">Total Win Pts</div>
            <div className="text-sm font-mono font-semibold text-emerald-400">
              +{stats.totalWin.toFixed(1)}
            </div>
            <div className="text-[9px] text-zinc-600">
              {stats.wins} trades | avg +{stats.avgWin.toFixed(1)}
            </div>
          </div>
          <div className="bg-zinc-800/40 rounded border border-zinc-800 px-3 py-2">
            <div className="text-[10px] text-zinc-500">Total Loss Pts</div>
            <div className="text-sm font-mono font-semibold text-red-400">
              {stats.totalLoss.toFixed(1)}
            </div>
            <div className="text-[9px] text-zinc-600">
              {stats.losses} trades | avg {stats.avgLoss.toFixed(1)}
            </div>
          </div>
          <div className="bg-zinc-800/40 rounded border border-zinc-800 px-3 py-2">
            <div className="text-[10px] text-zinc-500">Max Win</div>
            <div className="text-sm font-mono font-semibold text-emerald-400">
              +{stats.maxWin.toFixed(1)}
            </div>
          </div>
          <div className="bg-zinc-800/40 rounded border border-zinc-800 px-3 py-2">
            <div className="text-[10px] text-zinc-500">Max Loss</div>
            <div className="text-sm font-mono font-semibold text-red-400">
              {stats.maxLoss.toFixed(1)}
            </div>
          </div>
          <div className="bg-zinc-800/40 rounded border border-zinc-800 px-3 py-2">
            <div className="text-[10px] text-zinc-500">Median PnL</div>
            <div className={`text-sm font-mono font-semibold ${stats.median >= 0 ? "text-emerald-400" : "text-red-400"}`}>
              {stats.median >= 0 ? "+" : ""}{stats.median.toFixed(1)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main Dashboard ────────────────────────────────────────────

export default function DayHighDashboard() {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  return (
    <div className="space-y-10">
      <section>
        <DhMetrics />
      </section>
      <section>
        <DhEquityCurve />
      </section>
      <section>
        <DhIntradayExplorer externalDate={selectedDate} />
      </section>
      <section>
        <DhBreakdownTabs />
      </section>
      <section>
        <DhPnlHistogram />
      </section>
      <section>
        <DhTradesTable onDateSelect={setSelectedDate} />
      </section>
    </div>
  );
}
