"use client";

import { useEffect, useRef, useMemo } from "react";
import { createChart, ColorType, LineSeries, AreaSeries } from "lightweight-charts";
import type { UTCTimestamp } from "lightweight-charts";
import { useFetch } from "@/hooks/use-fetch";
import type { EquityPoint } from "@/types";

/**
 * Drawdown chart — derived client-side from the equity curve.
 * At each date: running_max − cumulative_pnl, inverted to negative so
 * losses plot downward. Mirrors Research Framework's `<LineChart fillBaseline/>`
 * pattern for drawdown visualization.
 */
export default function DrawdownChart({ apiUrl = "/api/equity" }: { apiUrl?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const { data } = useFetch<EquityPoint[]>(apiUrl);

  const series = useMemo(() => {
    if (!data || !data.length) return [];
    const byDate = new Map<number, number>();
    for (const p of data) {
      const ts = Math.floor(new Date(p.date).getTime() / 1000);
      byDate.set(ts, p.cumulative_pnl);
    }
    const sorted = [...byDate.entries()].sort((a, b) => a[0] - b[0]);
    let peak = -Infinity;
    return sorted.map(([ts, val]) => {
      if (val > peak) peak = val;
      const dd = val - peak; // <= 0
      return { time: ts as UTCTimestamp, value: dd };
    });
  }, [data]);

  useEffect(() => {
    if (!containerRef.current || !series.length) return;
    const container = containerRef.current;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 240,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#b3b6bd",
        fontFamily: "var(--font-mono)",
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: "#23262c" },
      },
      timeScale: { timeVisible: false, borderColor: "#2a2e35" },
      rightPriceScale: { borderColor: "#2a2e35" },
      crosshair: {
        horzLine: { color: "#767a82", style: 2 },
        vertLine: { color: "#767a82", style: 2 },
      },
    });

    // Area under the drawdown (all negative) filled red
    const area = chart.addSeries(AreaSeries, {
      lineColor: "#e07b76",
      topColor: "rgba(224,123,118,0.08)",
      bottomColor: "rgba(224,123,118,0.32)",
      lineWidth: 2,
      priceLineVisible: false,
    });
    area.setData(series);
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
  }, [series]);

  if (!data) {
    return <div className="muted" style={{ padding: 16 }}>Loading…</div>;
  }

  return <div ref={containerRef} className="w-full" />;
}
