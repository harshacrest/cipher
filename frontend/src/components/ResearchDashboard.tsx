"use client";

import { lazy, Suspense } from "react";
import ComingSoonPanel from "./ComingSoonPanel";

// Lazy-load strategy dashboards — each only compiles when its tab is selected.
// Previously all were eagerly imported which made the initial page load slow
// because every chart/table library was parsed upfront.
const ATMStraddleDashboard = lazy(() => import("./ATMStraddleDashboard"));
const VanillaDashboard     = lazy(() => import("./VanillaDashboard"));
const AllRounderDashboard  = lazy(() => import("./AllRounderDashboard"));
const DayHighDashboard     = lazy(() => import("./DayHighDashboard"));
const MultiLegDMDashboard  = lazy(() => import("./MultiLegDMDashboard"));
const VWAPSDDashboard      = lazy(() => import("./VWAPSDDashboard"));
const Comparison           = lazy(() => import("./Comparison"));

type Strategy =
  | "atm"
  | "vanilla"
  | "allrounder"
  | "day-high"
  | "day-high-v4"
  | "day-high-v5"
  | "day-high-v6"
  | "day-high-v7"
  | "day-high-spot"
  | "day-high-vix"
  | "directional-op"
  | "mv3"
  | "multilegdm"
  | "multilegdm-v2"
  | "multilegdm-v3"
  | "multilegdm-v4"
  | "vwap-sd"
  | "comparison";

interface StrategyMeta {
  id: Strategy;
  label: string;
  subtitle: string;
}

const STRATEGIES: StrategyMeta[] = [
  { id: "atm",            label: "ATM Strangle",    subtitle: "OTM1 Strangle Sell" },
  { id: "vanilla",        label: "Vanilla",         subtitle: "Vanilla ATM Straddle" },
  { id: "allrounder",     label: "All Rounder",     subtitle: "Index All Rounder" },
  { id: "day-high",       label: "Day High OTM v3", subtitle: "Day High OTM v3 (close DH + maturity lock)" },
  { id: "day-high-v4",    label: "Day High OTM v4", subtitle: "Day High OTM v4 (phantom skip + costs)" },
  { id: "day-high-v5",    label: "Day High OTM v5", subtitle: "Day High OTM v5 (whole-day DH)" },
  { id: "day-high-v6",    label: "Day High OTM v6", subtitle: "Day High OTM v6 (whole-day DH + fresh cross)" },
  { id: "day-high-v7",    label: "Day High OTM v7", subtitle: "Day High OTM v7 (v6 base + max 3 trades/day)" },
  { id: "day-high-spot",  label: "Day High Spot",   subtitle: "Day High Spot Sell" },
  { id: "day-high-vix",   label: "Day High VIX",    subtitle: "Day High VIX Straddle" },
  { id: "directional-op", label: "Directional OP",  subtitle: "Directional Credit Spread" },
  { id: "mv3",            label: "MV3 Spread",      subtitle: "MV3 v33 Credit Spread" },
  { id: "multilegdm",     label: "MultiLeg DM",     subtitle: "MultiLegDM — 6 strangles ATM+OTM_1..5 with re-entry" },
  { id: "multilegdm-v2",  label: "MultiLeg DM v2",  subtitle: "MultiLegDM v2 — same structure, tighter SLs (trade −155, daily −550) @ 30s ticks" },
  { id: "multilegdm-v3",  label: "MultiLeg DM v3",  subtitle: "MultiLegDM v3 — same SLs as v2, finer 5s tick resolution" },
  { id: "multilegdm-v4",  label: "MultiLeg DM v4",  subtitle: "MultiLegDM v4 — same SLs as v2/v3, native 1s tick resolution" },
  { id: "vwap-sd",        label: "VWAP SD 15-Str",  subtitle: "Aggregate 15-straddle short on VWAP-1SD mean reversion" },
  { id: "comparison",     label: "Comparison",      subtitle: "Side-by-side" },
];

export interface ResearchDashboardProps {
  strategy: Strategy;
  onStrategyChange: (s: Strategy) => void;
}

const Fallback = () => (
  <div className="panel"><div className="muted" style={{ padding: 20 }}>Loading dashboard…</div></div>
);

export function ResearchDashboard({ strategy, onStrategyChange }: ResearchDashboardProps) {
  return (
    <div>
      {/* Strategy sub-tabs — mirrors the Research Framework "Backtesting Research" sub-tab row. */}
      <div className="subtabs">
        {STRATEGIES.map((s) => {
          const active = s.id === strategy;
          return (
            <button
              key={s.id}
              onClick={() => onStrategyChange(s.id)}
              className={`subtab ${active ? "active" : ""}`}
            >
              {s.label}
            </button>
          );
        })}
      </div>

      <Suspense fallback={<Fallback />}>
        {strategy === "atm" && <ATMStraddleDashboard />}
        {strategy === "vanilla" && <VanillaDashboard />}
        {strategy === "allrounder" && <AllRounderDashboard />}
        {strategy === "day-high" && <DayHighDashboard />}
        {strategy === "day-high-v4" && <DayHighDashboard api="/api/day-high-v4" />}
        {strategy === "day-high-v5" && <DayHighDashboard api="/api/day-high-v5" />}
        {strategy === "day-high-v6" && <DayHighDashboard api="/api/day-high-v6" />}
        {strategy === "day-high-v7" && <DayHighDashboard api="/api/day-high-v7" />}
        {strategy === "multilegdm" && <MultiLegDMDashboard />}
        {strategy === "multilegdm-v2" && <MultiLegDMDashboard apiBase="/api/multilegdm-v2" />}
        {strategy === "multilegdm-v3" && <MultiLegDMDashboard apiBase="/api/multilegdm-v3" />}
        {strategy === "multilegdm-v4" && <MultiLegDMDashboard apiBase="/api/multilegdm-v4" />}
        {strategy === "vwap-sd" && <VWAPSDDashboard />}
        {strategy === "comparison" && <Comparison />}

        {strategy === "day-high-spot" && (
          <ComingSoonPanel
            title="Day High Spot Sell"
            description="Tracks NIFTY spot rolling day-high on 3-min bars. On a 5% pullback from the spot day-high, sells OTM1 CE + PE together with a fresh strike; SL if spot rises 5% over day-high at signal. Re-enters with new OTM1 after stop-out. EOD flat at 15:15."
            runnerPath="backtest/runner_day_high_spot.py"
          />
        )}

        {strategy === "day-high-vix" && (
          <ComingSoonPanel
            title="Day High VIX Straddle"
            description="India VIX day-high on 3-min bars. When VIX forms a new day-high and pulls back 2%, sells NIFTY ATM straddle. 30% SL on combined premium. Re-entry after exit on next VIX pullback signal. EOD flat at 15:15."
            runnerPath="backtest/runner_day_high_vix.py"
          />
        )}

        {strategy === "directional-op" && (
          <ComingSoonPanel
            title="Directional OP Credit Spread"
            description="9/21 EMA crossover on 15-min NIFTY drives direction — bull → PE credit spread, bear → CE credit spread. Morning vs expiry-afternoon premium filters select strikes. Exits on 55% SL / 70% target on the sold leg or EMA reversal."
            runnerPath="backtest/runner_directional_op.py"
          />
        )}

        {strategy === "mv3" && (
          <ComingSoonPanel
            title="MV3 v33 Credit Spread"
            description="Two independent ORB credit spreads (Set 1 PE + Set 2 CE) triggered after 9:25 when 5-min close of ATM±2 leg breaks its 9:15–9:19 low. Trailing SL activates +20pts, trails every 5pts with 2pt stop; PnL bands at -26.67/+80 (premium units). EOD flat at 15:00."
            runnerPath="backtest/runner_mv3.py"
          />
        )}
      </Suspense>
    </div>
  );
}

export function strategySubtitle(s: Strategy): string {
  return STRATEGIES.find((x) => x.id === s)?.subtitle ?? "";
}

export type { Strategy };
export default ResearchDashboard;
