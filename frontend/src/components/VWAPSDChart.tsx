"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  createSeriesMarkers,
  ColorType,
  LineSeries,
} from "lightweight-charts";
import type { UTCTimestamp } from "lightweight-charts";

interface Tick {
  time: string; // HH:MM
  spot: number;
  sclose: number;
  vwap: number;
  vah: number;
  val: number;
  n_legs: number;
}

interface Trade {
  trade_num: number;
  entry_time: string;
  exit_time: string;
  entry_sclose: number;
  exit_sclose: number;
  spot_at_entry: number;
  spot_at_exit: number;
  exit_reason: string;
  pnl_points: number;
  pnl_premium: number;
}

export interface VWAPSDDayPayload {
  date: string;
  base_strike: number;
  expiry?: string | null;
  dte?: number | null;
  ticks: Tick[];
  trades: Trade[];
}

function toUnix(date: string, hhmm: string): UTCTimestamp {
  return Math.floor(new Date(`${date}T${hhmm}:00Z`).getTime() / 1000) as UTCTimestamp;
}

export default function VWAPSDChart({ data }: { data: VWAPSDDayPayload }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);

  useEffect(() => {
    if (!containerRef.current || !data || data.ticks.length === 0) return;
    const container = containerRef.current;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 560,
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

    // Spot — LEFT axis
    const spotSeries = chart.addSeries(LineSeries, {
      priceScaleId: "left",
      color: "#3b82f6",
      lineWidth: 2,
      title: "Spot",
      priceLineVisible: false,
    });

    // sClose (combined premium) — RIGHT axis
    const scloseSeries = chart.addSeries(LineSeries, {
      priceScaleId: "right",
      color: "#f59e0b",
      lineWidth: 2,
      title: "Combined Premium",
      priceLineVisible: false,
    });

    // VWAP — RIGHT axis
    const vwapSeries = chart.addSeries(LineSeries, {
      priceScaleId: "right",
      color: "#a1a1aa",
      lineWidth: 1,
      title: "VWAP",
      priceLineVisible: false,
    });

    // VAH / VAL — RIGHT axis
    const vahSeries = chart.addSeries(LineSeries, {
      priceScaleId: "right",
      color: "#22c55e",
      lineWidth: 1,
      lineStyle: 2,
      title: "VAH",
      priceLineVisible: false,
    });
    const valSeries = chart.addSeries(LineSeries, {
      priceScaleId: "right",
      color: "#ef4444",
      lineWidth: 1,
      lineStyle: 2,
      title: "VAL",
      priceLineVisible: false,
    });

    const dedup = <T,>(arr: { time: UTCTimestamp; value: T }[]) => {
      const seen = new Set<number>();
      return arr.filter((d) => {
        if (seen.has(d.time as number)) return false;
        seen.add(d.time as number);
        return true;
      });
    };

    const base = data.date;
    spotSeries.setData(
      dedup(data.ticks.map((t) => ({ time: toUnix(base, t.time), value: t.spot }))),
    );
    scloseSeries.setData(
      dedup(data.ticks.map((t) => ({ time: toUnix(base, t.time), value: t.sclose }))),
    );
    vwapSeries.setData(
      dedup(data.ticks.map((t) => ({ time: toUnix(base, t.time), value: t.vwap }))),
    );
    vahSeries.setData(
      dedup(data.ticks.map((t) => ({ time: toUnix(base, t.time), value: t.vah }))),
    );
    valSeries.setData(
      dedup(data.ticks.map((t) => ({ time: toUnix(base, t.time), value: t.val }))),
    );

    // Entry / Exit markers on the sClose series (that's what strategy trades)
    const markers: Parameters<typeof createSeriesMarkers>[1] = [];
    for (const t of data.trades) {
      markers.push({
        time: toUnix(base, t.entry_time),
        position: "belowBar",
        color: "#22c55e",
        shape: "arrowUp",
        text: `SHORT #${t.trade_num}`,
      });
      markers.push({
        time: toUnix(base, t.exit_time),
        position: "aboveBar",
        color: t.exit_reason === "SL" ? "#ef4444" : "#f59e0b",
        shape: "arrowDown",
        text: `${t.exit_reason} ${t.pnl_points >= 0 ? "+" : ""}${t.pnl_points.toFixed(1)}`,
      });
    }
    markers.sort((a, b) => (a.time as number) - (b.time as number));
    if (markers.length > 0) createSeriesMarkers(scloseSeries, markers);

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
      <div className="flex items-center gap-4 mb-2 text-xs text-zinc-500 flex-wrap">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-blue-500 rounded" />
          Spot (LHS)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-amber-500 rounded" />
          Combined Premium (RHS)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-zinc-400 rounded" />
          VWAP
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-emerald-500 rounded" style={{ borderTop: "1px dashed #22c55e" }} />
          VAH
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-0.5 bg-red-500 rounded" style={{ borderTop: "1px dashed #ef4444" }} />
          VAL
        </span>
        <span className="ml-auto text-zinc-400">
          Base strike: {data.base_strike}
          {data.expiry != null && (
            <> · Expiry: {data.expiry}{data.dte != null && <> (DTE {data.dte})</>}</>
          )}
        </span>
      </div>

      <div
        ref={containerRef}
        className="w-full rounded-lg border border-zinc-700/50 overflow-hidden"
      />

      {data.trades.length > 0 && (
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2">
          {data.trades.map((t) => (
            <div
              key={t.trade_num}
              className="flex items-center gap-3 text-xs font-mono px-3 py-2 bg-zinc-800/40 rounded border border-zinc-800"
            >
              <span className="text-amber-500 font-semibold">#{t.trade_num}</span>
              <span className="text-zinc-500">
                {t.entry_time} → {t.exit_time}
              </span>
              <span className="text-zinc-500">
                sClose: {t.entry_sclose.toFixed(0)} → {t.exit_sclose.toFixed(0)}
              </span>
              <span className={t.exit_reason === "SL" ? "text-red-400" : "text-amber-400"}>
                {t.exit_reason}
              </span>
              <span className={`ml-auto font-semibold ${t.pnl_points >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {t.pnl_points >= 0 ? "+" : ""}
                {t.pnl_points.toFixed(1)} pts
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
