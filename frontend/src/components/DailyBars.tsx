"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  IChartApi,
  LineStyle,
  ColorType,
  HistogramData,
  HistogramSeries,
  UTCTimestamp,
} from "lightweight-charts";
import { useFetch } from "@/hooks/use-fetch";
import type { EquityPoint } from "@/types";

interface Props {
  apiUrl?: string;
  height?: number;
}

const PALETTE = {
  bg: "#1d2026",
  text: "#b3b6bd",
  grid: "#2a2e35",
  pos: "#6ec38f",
  neg: "#e07b76",
};

/**
 * Daily PnL bars — green for positive days, red for negative.
 * Reads the same equity endpoint used by EquityCurve/DrawdownChart
 * and renders per-trade (or per-day) PnL as a histogram series.
 */
export default function DailyBars({
  apiUrl = "/api/equity",
  height = 240,
}: Props) {
  const { data, loading, error } = useFetch<EquityPoint[]>(apiUrl);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || !data || data.length === 0) return;

    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: PALETTE.bg },
        textColor: PALETTE.text,
        fontFamily: "SF Mono, JetBrains Mono, ui-monospace, Menlo, Consolas, monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: PALETTE.grid, style: LineStyle.Dotted },
        horzLines: { color: PALETTE.grid, style: LineStyle.Dotted },
      },
      rightPriceScale: { borderColor: PALETTE.grid },
      timeScale: { borderColor: PALETTE.grid },
    });
    chartRef.current = chart;

    const series = chart.addSeries(HistogramSeries, {
      base: 0,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });

    // Aggregate by date (equity points may include multiple trades per day)
    const byDate = new Map<number, number>();
    for (const p of data) {
      const ts = Math.floor(new Date(p.date).getTime() / 1000);
      byDate.set(ts, (byDate.get(ts) ?? 0) + p.pnl);
    }
    const bars: HistogramData[] = Array.from(byDate.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([ts, v]) => ({
        time: ts as UTCTimestamp,
        value: v,
        color: v >= 0 ? PALETTE.pos : PALETTE.neg,
      }));

    series.setData(bars);
    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [data, height]);

  if (loading) return <div className="muted" style={{ padding: 14 }}><span className="spinner" /> loading…</div>;
  if (error) return <div className="error">{error}</div>;
  if (!data || data.length === 0) return <div className="muted" style={{ padding: 14 }}>No data.</div>;

  return <div ref={containerRef} className="chart-box" style={{ height }} />;
}
