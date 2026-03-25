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
  // Parse as UTC so chart displays IST times as-is (data is IST labeled as UTC)
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

    // Clean up previous chart
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 450,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#a1a1aa",
        fontFamily: "var(--font-geist-mono), monospace",
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: "#27272a" },
      },
      leftPriceScale: {
        visible: true,
        borderColor: "#3f3f46",
      },
      rightPriceScale: {
        visible: true,
        borderColor: "#3f3f46",
      },
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

    // Spot price on LEFT axis
    const spotSeries = chart.addSeries(LineSeries, {
      priceScaleId: "left",
      color: "#3b82f6",
      lineWidth: 2,
      title: "Spot",
      priceLineVisible: false,
    });

    // ATM straddle price on RIGHT axis
    const atmSeries = chart.addSeries(LineSeries, {
      priceScaleId: "right",
      color: "#f59e0b",
      lineWidth: 2,
      title: "ATM Straddle",
      priceLineVisible: false,
    });

    const spotData = data.ticks.map((t) => ({
      time: timeToUnix(t.time),
      value: t.spot,
    }));

    const atmData = data.ticks.map((t) => ({
      time: timeToUnix(t.time),
      value: t.atm_price,
    }));

    spotSeries.setData(spotData);
    atmSeries.setData(atmData);

    // Entry/exit markers on ATM series
    const entryTime = timeToUnix(data.entry_time);
    const exitTime = timeToUnix(data.exit_time);

    // Find ATM prices at entry/exit for marker positioning
    const entryTick = data.ticks.find((t) => t.time === data.entry_time);
    const exitTick = data.ticks.find((t) => t.time === data.exit_time);

    const markers: Parameters<typeof createSeriesMarkers>[1] = [];

    if (entryTick) {
      markers.push({
        time: entryTime,
        position: "aboveBar",
        color: "#22c55e",
        shape: "arrowDown",
        text: `SELL ${data.entry_time}`,
      });
    }

    if (exitTick) {
      markers.push({
        time: exitTime,
        position: "belowBar",
        color: "#ef4444",
        shape: "arrowUp",
        text: `EXIT ${data.exit_time}`,
      });
    }

    if (markers.length > 0) {
      createSeriesMarkers(atmSeries, markers);
    }

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
      <div className="animate-pulse h-[450px] bg-zinc-800/50 rounded-lg" />
    );
  }

  if (error) {
    return (
      <div className="h-[450px] flex items-center justify-center text-red-400 text-sm bg-zinc-800/50 rounded-lg">
        No data for {date}
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-4 mb-2 text-xs text-zinc-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-blue-500 rounded" />
          Spot (LHS)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-amber-500 rounded" />
          Straddle CE+PE (RHS)
        </span>
        {data?.atm_strike && (
          <span className="font-mono text-zinc-400">
            Strike: {data.atm_strike}
          </span>
        )}
        {data?.pnl !== null && data?.pnl !== undefined && (
          <span
            className={`ml-auto font-mono font-semibold ${data.pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}
          >
            PnL: {data.pnl >= 0 ? "+" : ""}
            {data.pnl.toFixed(2)} pts
          </span>
        )}
      </div>
      <div
        ref={containerRef}
        className="w-full rounded-lg border border-zinc-700/50 overflow-hidden"
      />
    </div>
  );
}
