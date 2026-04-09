"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  createSeriesMarkers,
  ColorType,
  LineSeries,
} from "lightweight-charts";
import type { UTCTimestamp } from "lightweight-charts";
import { useFetch } from "@/hooks/use-fetch";
import type { IntradayData } from "@/types";

function timeToUnix(timeStr: string): UTCTimestamp {
  return Math.floor(
    new Date(`2024-01-01T${timeStr}:00Z`).getTime() / 1000
  ) as UTCTimestamp;
}

export default function IntradayChart({ date }: { date: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const { data, loading, error } = useFetch<IntradayData>(
    `/api/intraday/${date}`
  );

  useEffect(() => {
    if (!containerRef.current || !data || data.ticks.length === 0) return;

    const container = containerRef.current;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 500,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#a1a1aa",
        fontFamily: "var(--font-geist-mono), monospace",
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: "#27272a" },
      },
      leftPriceScale: { visible: true, borderColor: "#3f3f46" },
      rightPriceScale: { visible: true, borderColor: "#3f3f46" },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: "#3f3f46",
      },
      crosshair: {
        horzLine: { color: "#71717a", style: 2 },
        vertLine: { color: "#71717a", style: 2 },
      },
    });

    // ── Spot price (LEFT axis) ──
    const spotSeries = chart.addSeries(LineSeries, {
      priceScaleId: "left",
      color: "#3b82f6",
      lineWidth: 2,
      title: "Spot",
      priceLineVisible: false,
    });

    // ── CE price (RIGHT axis) ──
    const ceSeries = chart.addSeries(LineSeries, {
      priceScaleId: "right",
      color: "#f59e0b",
      lineWidth: 2,
      title: `CE ${data.ce_strike}`,
      priceLineVisible: false,
    });

    // ── PE price (RIGHT axis) ──
    const peSeries = chart.addSeries(LineSeries, {
      priceScaleId: "right",
      color: "#a855f7",
      lineWidth: 2,
      title: `PE ${data.pe_strike}`,
      priceLineVisible: false,
    });

    // Deduplicate tick times for flat SL lines
    const uniqueTimes: UTCTimestamp[] = [];
    const seenTimes = new Set<number>();
    for (const t of data.ticks) {
      const ts = timeToUnix(t.time);
      if (!seenTimes.has(ts as number)) {
        seenTimes.add(ts as number);
        uniqueTimes.push(ts);
      }
    }

    // ── CE SL line (RIGHT axis, dashed red) ──
    if (data.ce_sl != null) {
      const ceSlSeries = chart.addSeries(LineSeries, {
        priceScaleId: "right",
        color: "#ef4444",
        lineWidth: 1,
        lineStyle: 2,
        title: `CE SL ${data.ce_sl}`,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
      });
      ceSlSeries.setData(
        uniqueTimes.map((ts) => ({ time: ts, value: data.ce_sl! }))
      );
    }

    // ── PE SL line (RIGHT axis, dashed pink) ──
    if (data.pe_sl != null) {
      const peSlSeries = chart.addSeries(LineSeries, {
        priceScaleId: "right",
        color: "#f87171",
        lineWidth: 1,
        lineStyle: 2,
        title: `PE SL ${data.pe_sl}`,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
      });
      peSlSeries.setData(
        uniqueTimes.map((ts) => ({ time: ts, value: data.pe_sl! }))
      );
    }

    // Set data — deduplicate by time
    const dedup = <T,>(arr: { time: UTCTimestamp; value: T }[]) => {
      const seen = new Set<number>();
      return arr.filter((d) => {
        if (seen.has(d.time as number)) return false;
        seen.add(d.time as number);
        return true;
      });
    };

    spotSeries.setData(
      dedup(data.ticks.map((t) => ({ time: timeToUnix(t.time), value: t.spot })))
    );
    ceSeries.setData(
      dedup(
        data.ticks
          .filter((t) => t.ce_price != null)
          .map((t) => ({ time: timeToUnix(t.time), value: t.ce_price! }))
      )
    );
    peSeries.setData(
      dedup(
        data.ticks
          .filter((t) => t.pe_price != null)
          .map((t) => ({ time: timeToUnix(t.time), value: t.pe_price! }))
      )
    );

    // ── CE entry/exit markers ──
    const ceMarkers: Parameters<typeof createSeriesMarkers>[1] = [];
    if (data.entry_time) {
      ceMarkers.push({
        time: timeToUnix(data.entry_time),
        position: "aboveBar",
        color: "#22c55e",
        shape: "arrowDown",
        text: `SELL CE ${data.ce_strike}`,
      });
    }
    if (data.ce_exit_time) {
      ceMarkers.push({
        time: timeToUnix(data.ce_exit_time),
        position: "belowBar",
        color: data.ce_exit_reason === "SL" ? "#ef4444" : "#f59e0b",
        shape: "arrowUp",
        text: `CE ${data.ce_exit_reason} ${data.ce_exit_time}`,
      });
    }
    ceMarkers.sort((a, b) => (a.time as number) - (b.time as number));
    if (ceMarkers.length > 0) createSeriesMarkers(ceSeries, ceMarkers);

    // ── PE entry/exit markers ──
    const peMarkers: Parameters<typeof createSeriesMarkers>[1] = [];
    if (data.entry_time) {
      peMarkers.push({
        time: timeToUnix(data.entry_time),
        position: "aboveBar",
        color: "#22c55e",
        shape: "arrowDown",
        text: `SELL PE ${data.pe_strike}`,
      });
    }
    if (data.pe_exit_time) {
      peMarkers.push({
        time: timeToUnix(data.pe_exit_time),
        position: "belowBar",
        color: data.pe_exit_reason === "SL" ? "#ef4444" : "#f59e0b",
        shape: "arrowUp",
        text: `PE ${data.pe_exit_reason} ${data.pe_exit_time}`,
      });
    }
    peMarkers.sort((a, b) => (a.time as number) - (b.time as number));
    if (peMarkers.length > 0) createSeriesMarkers(peSeries, peMarkers);

    chart.timeScale().fitContent();
    chartRef.current = chart;

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [data]);

  if (loading) {
    return (
      <div className="animate-pulse h-[500px] bg-zinc-800/50 rounded-lg" />
    );
  }

  if (error) {
    return (
      <div className="h-[500px] flex items-center justify-center text-red-400 text-sm bg-zinc-800/50 rounded-lg">
        No data for {date}
      </div>
    );
  }

  return (
    <div>
      {/* Legend */}
      <div className="flex items-center gap-4 mb-2 text-xs text-zinc-500 flex-wrap">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-blue-500 rounded" />
          Spot (LHS)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-amber-500 rounded" />
          CE {data?.ce_strike} (RHS)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-purple-500 rounded" />
          PE {data?.pe_strike} (RHS)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-red-500 rounded" style={{ borderTop: "1px dashed #ef4444" }} />
          SL Lines (RHS)
        </span>
      </div>

      {/* Chart */}
      <div
        ref={containerRef}
        className="w-full rounded-lg border border-zinc-700/50 overflow-hidden"
      />

      {/* Per-leg detail panel */}
      {data && (
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
          {/* CE leg */}
          <div className="flex items-center gap-3 text-xs font-mono px-3 py-2 bg-zinc-800/40 rounded border border-zinc-800">
            <span className="text-amber-500 font-semibold">CE {data.ce_strike}</span>
            <span className="text-zinc-500">
              In: {data.entry_ce?.toFixed(2) ?? "-"} → Out: {data.exit_ce?.toFixed(2) ?? "-"}
            </span>
            <span className="text-zinc-500">SL: {data.ce_sl?.toFixed(2) ?? "-"}</span>
            <span className={data.ce_exit_reason === "SL" ? "text-red-400" : "text-amber-400"}>
              {data.ce_exit_reason}
            </span>
            {data.ce_pnl != null && (
              <span className={`ml-auto font-semibold ${data.ce_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {data.ce_pnl >= 0 ? "+" : ""}{data.ce_pnl.toFixed(2)}
              </span>
            )}
          </div>
          {/* PE leg */}
          <div className="flex items-center gap-3 text-xs font-mono px-3 py-2 bg-zinc-800/40 rounded border border-zinc-800">
            <span className="text-purple-500 font-semibold">PE {data.pe_strike}</span>
            <span className="text-zinc-500">
              In: {data.entry_pe?.toFixed(2) ?? "-"} → Out: {data.exit_pe?.toFixed(2) ?? "-"}
            </span>
            <span className="text-zinc-500">SL: {data.pe_sl?.toFixed(2) ?? "-"}</span>
            <span className={data.pe_exit_reason === "SL" ? "text-red-400" : "text-amber-400"}>
              {data.pe_exit_reason}
            </span>
            {data.pe_pnl != null && (
              <span className={`ml-auto font-semibold ${data.pe_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {data.pe_pnl >= 0 ? "+" : ""}{data.pe_pnl.toFixed(2)}
              </span>
            )}
          </div>
          {/* Total */}
          <div className="sm:col-span-2 flex items-center justify-end text-xs font-mono px-3 py-1.5">
            <span className="text-zinc-500 mr-2">Total PnL:</span>
            <span className={`font-semibold text-sm ${data.pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
              {data.pnl >= 0 ? "+" : ""}{data.pnl.toFixed(2)} pts
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
