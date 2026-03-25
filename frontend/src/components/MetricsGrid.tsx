"use client";

import { useFetch } from "@/hooks/use-fetch";
import type { Metric } from "@/types";

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
  if (name.includes("Loss") || name === "Max Drawdown (pts)") {
    return v < 0 ? "text-red-400" : "text-zinc-100";
  }
  if (
    name.includes("PnL") ||
    name.includes("Return") ||
    name.includes("Profit") ||
    name.includes("Win")
  ) {
    return v > 0 ? "text-emerald-400" : v < 0 ? "text-red-400" : "text-zinc-100";
  }
  return "text-zinc-100";
}

export default function MetricsGrid() {
  const { data, loading } = useFetch<Metric[]>("/api/metrics");

  if (loading || !data) {
    return (
      <div className="animate-pulse h-48 bg-zinc-800/50 rounded-lg" />
    );
  }

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
                  <div className="text-[11px] text-zinc-500 truncate">
                    {key}
                  </div>
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
