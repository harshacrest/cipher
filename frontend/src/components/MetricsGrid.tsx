"use client";

import { useMemo } from "react";
import { useFetch } from "@/hooks/use-fetch";
import type { Metric } from "@/types";

/**
 * KPI strip — modelled 1:1 on the Research Framework's `<Kpi>` pattern:
 * a single flat grid with `auto-fit minmax(150px, 1fr)` columns, 1 px hairline
 * gap on a rule-colored background, uppercase micro-labels, mono values,
 * positive → green, negative → red, neutral → ink.
 *
 * No group titles or section dividers — Research Framework presents everything
 * as one continuous strip so the eye can scan without the header noise.
 */

interface KpiSpec {
  /** Key as written in cipher's metrics.json */
  key: string;
  /** Display label (kept short like Research Framework) */
  label: string;
  digits?: number;
  suffix?: string;
  /** Prepend `+` for positive values (used for returns-like metrics) */
  signed?: boolean;
  /** Force semantic color */
  color?: "pos" | "neg" | "neutral";
}

/* All 28 metrics from metrics.json, ordered like Research Framework:
     returns/consistency first, then risk/distribution, then streaks.
     Single flat strip — no group headers. */
const ITEMS: KpiSpec[] = [
  // Returns & consistency
  { key: "Total PnL (pts)",          label: "Total PnL",      digits: 1, suffix: " pts", signed: true },
  { key: "Annualized Return (pts)",  label: "Ann. Return",    digits: 1, suffix: " pts", signed: true },
  { key: "Expectancy (pts)",         label: "Expectancy",     digits: 2, suffix: " pts", signed: true },
  { key: "Avg PnL (pts)",            label: "Avg PnL",        digits: 2, suffix: " pts", signed: true },
  { key: "Profit Factor",            label: "Profit Factor",  digits: 2, color: "neutral" },
  { key: "Sharpe Ratio (ann.)",      label: "Sharpe",         digits: 2, color: "neutral" },
  { key: "Sortino Ratio (ann.)",     label: "Sortino",        digits: 2, color: "neutral" },
  { key: "Calmar Ratio",             label: "Calmar",         digits: 2, color: "neutral" },
  { key: "Win Rate (%)",             label: "Win Day %",      digits: 1, suffix: "%",    color: "neutral" },
  { key: "Profitable Months (%)",    label: "Win Month %",    digits: 1, suffix: "%",    color: "neutral" },
  { key: "Risk-Reward Ratio",        label: "R:R",            digits: 2, color: "neutral" },

  // Trade counts
  { key: "Total Trades",             label: "Trades",         digits: 0, color: "neutral" },
  { key: "Winners",                  label: "Winners",        digits: 0, color: "neutral" },
  { key: "Losers",                   label: "Losers",         digits: 0, color: "neutral" },
  { key: "Flat",                     label: "Flat",           digits: 0, color: "neutral" },

  // Risk & drawdown
  { key: "Max Drawdown (pts)",       label: "Max DD",         digits: 2, suffix: " pts", color: "neg" },
  { key: "Max DD Duration (days)",   label: "Max DD Days",    digits: 0, suffix: "d",    color: "neutral" },
  { key: "Std Dev (daily)",          label: "Daily σ",        digits: 2, color: "neutral" },
  { key: "Skewness",                 label: "Skewness",       digits: 2, color: "neutral" },
  { key: "Kurtosis",                 label: "Kurtosis",       digits: 2, color: "neutral" },

  // Distribution
  { key: "Avg Win (pts)",            label: "Avg Win",        digits: 2, suffix: " pts", color: "pos" },
  { key: "Avg Loss (pts)",           label: "Avg Loss",       digits: 2, suffix: " pts", color: "neg" },
  { key: "Max Win (pts)",            label: "Max Win",        digits: 2, suffix: " pts", color: "pos" },
  { key: "Max Loss (pts)",           label: "Max Loss",       digits: 2, suffix: " pts", color: "neg" },
  { key: "Best Month (pts)",         label: "Best Month",     digits: 2, suffix: " pts", color: "pos" },
  { key: "Worst Month (pts)",        label: "Worst Month",    digits: 2, suffix: " pts", color: "neg" },

  // Streaks
  { key: "Max Win Streak",           label: "Win Streak",     digits: 0, suffix: "d", color: "pos" },
  { key: "Max Loss Streak",          label: "Loss Streak",    digits: 0, suffix: "d", color: "neg" },
];

function fmt(
  v: number | string | null | undefined,
  digits = 2,
  suffix = "",
  signed = false,
): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  if (Number.isNaN(v)) return "—";
  const s = v.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return (signed && v > 0 ? "+" : "") + s + suffix;
}

function resolveColor(spec: KpiSpec, v: number | string | undefined): string | undefined {
  if (spec.color === "pos") return "var(--pos)";
  if (spec.color === "neg") return "var(--neg)";
  if (spec.color === "neutral") return undefined;
  if (typeof v !== "number" || Number.isNaN(v)) return undefined;
  if (v > 0) return "var(--pos)";
  if (v < 0) return "var(--neg)";
  return undefined;
}

export default function MetricsGrid({ apiUrl = "/api/metrics" }: { apiUrl?: string }) {
  const { data, loading } = useFetch<Metric[]>(apiUrl);

  const lookup = useMemo(() => {
    const m = new Map<string, number | string>();
    if (data) for (const r of data) m.set(r.Metric, r.Value);
    return m;
  }, [data]);

  if (loading || !data) {
    return (
      <div
        className="rounded-[2px] border border-rule"
        style={{ background: "var(--panel)", height: 260 }}
      />
    );
  }

  return (
    <div className="kpis">
      {ITEMS.map((spec) => {
        const raw = lookup.get(spec.key);
        const color = resolveColor(spec, raw);
        return (
          <div className="kpi" key={spec.key}>
            <div className="label" title={spec.key}>{spec.label}</div>
            <div className="value" style={color ? { color } : undefined}>
              {fmt(raw, spec.digits ?? 2, spec.suffix ?? "", spec.signed ?? false)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
