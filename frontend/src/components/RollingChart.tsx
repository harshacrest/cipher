"use client";

import { useEffect, useMemo, useRef } from "react";
import {
  createChart,
  IChartApi,
  LineStyle,
  ColorType,
  LineSeries,
  UTCTimestamp,
} from "lightweight-charts";
import { useFetch } from "@/hooks/use-fetch";
import type { EquityPoint } from "@/types";

interface Props {
  apiUrl?: string;
  window?: number;
  title?: string;
  color?: string;
  height?: number;
}

const PALETTE = {
  bg: "#1d2026",
  text: "#b3b6bd",
  grid: "#2a2e35",
  accent: "#d4b06a",
};

const TRADING_DAYS = 252;

/**
 * Rolling Sharpe (annualized) computed from daily aggregated PnL.
 * Cipher's equity endpoint exposes `{ date, pnl, cumulative_pnl }` rows;
 * this component reduces to per-day sums and rolls a `window`-day Sharpe.
 */
export default function RollingChart({
  apiUrl = "/api/equity",
  window = 20,
  title,
  color = PALETTE.accent,
  height = 200,
}: Props) {
  const { data, loading, error } = useFetch<EquityPoint[]>(apiUrl);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  const series = useMemo(() => {
    if (!data || data.length === 0) return [] as { time: UTCTimestamp; value: number }[];
    // Aggregate to daily PnL
    const byDate = new Map<number, number>();
    for (const p of data) {
      const ts = Math.floor(new Date(p.date).getTime() / 1000);
      byDate.set(ts, (byDate.get(ts) ?? 0) + p.pnl);
    }
    const daily = Array.from(byDate.entries()).sort((a, b) => a[0] - b[0]);

    const out: { time: UTCTimestamp; value: number }[] = [];
    for (let i = window - 1; i < daily.length; i++) {
      let sum = 0;
      let sqsum = 0;
      for (let j = i - window + 1; j <= i; j++) {
        sum += daily[j][1];
        sqsum += daily[j][1] * daily[j][1];
      }
      const mean = sum / window;
      const variance = sqsum / window - mean * mean;
      const std = variance > 0 ? Math.sqrt(variance) : 0;
      const sharpe = std > 0 ? (mean / std) * Math.sqrt(TRADING_DAYS) : 0;
      out.push({ time: daily[i][0] as UTCTimestamp, value: sharpe });
    }
    return out;
  }, [data, window]);

  useEffect(() => {
    if (!containerRef.current || series.length === 0) return;

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

    const line = chart.addSeries(LineSeries, { color, lineWidth: 1 });
    line.setData(series);
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
  }, [series, color, height]);

  if (loading) return <div className="muted" style={{ padding: 14 }}><span className="spinner" /> loading…</div>;
  if (error) return <div className="error">{error}</div>;
  if (series.length === 0) return <div className="muted" style={{ padding: 14 }}>Not enough data for {window}-day window.</div>;

  return (
    <div>
      {title && (
        <div
          style={{
            padding: "6px 14px",
            fontSize: 10,
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            color: "var(--ink-3)",
            background: "var(--panel)",
          }}
        >
          {title}
        </div>
      )}
      <div ref={containerRef} className="chart-box" style={{ height }} />
    </div>
  );
}
