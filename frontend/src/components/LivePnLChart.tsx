"use client";

import { useEffect, useRef } from "react";
import { createChart, LineSeries, UTCTimestamp } from "lightweight-charts";

interface Props {
  data: { time: number; value: number }[];
  title?: string;
}

export default function LivePnLChart({ data, title = "Spot Price" }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const seriesRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 250,
      layout: {
        background: { color: "transparent" },
        textColor: "#71717a",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#27272a40" },
        horzLines: { color: "#27272a40" },
      },
      rightPriceScale: { borderColor: "#27272a" },
      timeScale: {
        borderColor: "#27272a",
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const series = chart.addSeries(LineSeries, {
      color: "#22c55e",
      lineWidth: 2,
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // Update data when new points arrive
  useEffect(() => {
    if (!seriesRef.current || data.length === 0) return;
    const formatted = data.map((d) => ({
      time: Math.floor(d.time) as UTCTimestamp,
      value: d.value,
    }));
    seriesRef.current.setData(formatted);
    chartRef.current?.timeScale().scrollToRealTime();
  }, [data]);

  return (
    <div>
      <h3 className="text-xs font-semibold text-zinc-500 mb-2">{title}</h3>
      <div
        ref={containerRef}
        className="w-full rounded-lg border border-zinc-700/50 overflow-hidden"
      />
    </div>
  );
}
