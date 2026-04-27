"use client";

import { useEffect, useRef } from "react";
import { createChart, ColorType, LineSeries } from "lightweight-charts";
import { useFetch } from "@/hooks/use-fetch";
import type { EquityPoint } from "@/types";

export default function EquityCurve({ apiUrl = "/api/equity" }: { apiUrl?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const { data } = useFetch<EquityPoint[]>(apiUrl);

  useEffect(() => {
    if (!containerRef.current || !data || data.length === 0) return;

    const container = containerRef.current;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 340,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#b3b6bd",
        fontFamily: "var(--font-mono)",
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: "#23262c" },
      },
      timeScale: {
        timeVisible: false,
        borderColor: "#2a2e35",
      },
      rightPriceScale: {
        borderColor: "#2a2e35",
      },
      crosshair: {
        horzLine: { color: "#767a82", style: 2 },
        vertLine: { color: "#767a82", style: 2 },
      },
    });

    const series = chart.addSeries(LineSeries, {
      color: "#d4b06a", // gold line — accent
      lineWidth: 2,
      priceLineVisible: false,
    });

    // Deduplicate by date — take last cumulative_pnl per day
    const byDate = new Map<number, number>();
    for (const p of data) {
      const ts = Math.floor(new Date(p.date).getTime() / 1000);
      byDate.set(ts, p.cumulative_pnl);
    }
    const chartData = Array.from(byDate.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([ts, val]) => ({
        time: ts as import("lightweight-charts").UTCTimestamp,
        value: val,
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

  return <div ref={containerRef} className="w-full" />;
}
