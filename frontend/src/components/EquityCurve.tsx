"use client";

import { useEffect, useRef } from "react";
import { createChart, ColorType, LineSeries } from "lightweight-charts";
import { useFetch } from "@/hooks/use-fetch";
import type { EquityPoint } from "@/types";

export default function EquityCurve() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const { data } = useFetch<EquityPoint[]>("/api/equity");

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
      timeScale: {
        timeVisible: false,
        borderColor: "#3f3f46",
      },
      rightPriceScale: {
        borderColor: "#3f3f46",
      },
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

    const chartData = data.map((p) => ({
      time: Math.floor(new Date(p.date).getTime() / 1000) as import("lightweight-charts").UTCTimestamp,
      value: p.cumulative_pnl,
    }));

    series.setData(chartData);
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

  return (
    <div>
      <h2 className="text-sm font-semibold text-zinc-400 mb-3">
        Equity Curve
      </h2>
      <div
        ref={containerRef}
        className="w-full rounded-lg border border-zinc-700/50 overflow-hidden"
      />
    </div>
  );
}
