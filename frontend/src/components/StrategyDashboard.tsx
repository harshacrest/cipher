"use client";

import { useState, type ReactNode } from "react";
import MetricsGrid from "./MetricsGrid";
import EquityCurve from "./EquityCurve";
import DrawdownChart from "./DrawdownChart";
import BreakdownTabs from "./BreakdownTabs";
import Heatmap from "./Heatmap";
import Histogram from "./Histogram";
import DailyBars from "./DailyBars";
import RollingChart from "./RollingChart";
import DailyCalendar from "./DailyCalendar";
import Collapsible from "./Collapsible";

/**
 * Reusable strategy dashboard — aligned 1:1 with Research Framework's
 * `StrategyPanel` layout. Every analytical section below the KPI strip
 * is wrapped in `<Collapsible>` so users can fold away noise.
 */
type SubTab = "returns" | "transactions" | "dte" | "intraday" | "charts" | "mtm";

const BASE_SUBTABS: { id: SubTab; label: string }[] = [
  { id: "returns",      label: "Returns" },
  { id: "transactions", label: "Transactions" },
  { id: "dte",          label: "DTE" },
  { id: "intraday",     label: "Intraday" },
];

export interface StrategyDashboardProps {
  apiBase: string;
  equityUrl?: string;
  metricsUrl?: string;
  renderTransactions: () => ReactNode;
  renderIntraday: () => ReactNode;
  /** Optional Charts subtab — when provided, rendered as the last subtab. */
  renderCharts?: () => ReactNode;
  /** Optional label for the Charts subtab (defaults to "Charts"). */
  chartsLabel?: string;
  /** Optional MTM subtab — when provided, rendered after Charts. */
  renderMTM?: () => ReactNode;
  /** Optional label for the MTM subtab (defaults to "MTM"). */
  mtmLabel?: string;
}

export default function StrategyDashboard({
  apiBase,
  equityUrl,
  metricsUrl,
  renderTransactions,
  renderIntraday,
  renderCharts,
  chartsLabel = "Charts",
  renderMTM,
  mtmLabel = "MTM",
}: StrategyDashboardProps) {
  const [sub, setSub] = useState<SubTab>("returns");
  const SUBTABS = [
    ...BASE_SUBTABS,
    ...(renderCharts ? [{ id: "charts" as SubTab, label: chartsLabel }] : []),
    ...(renderMTM ? [{ id: "mtm" as SubTab, label: mtmLabel }] : []),
  ];

  const mUrl = metricsUrl ?? `${apiBase}/metrics`;
  const eUrl = equityUrl  ?? `${apiBase}/equity`;

  return (
    <div>
      {/* Sub-tab strip */}
      <div className="subtabs">
        {SUBTABS.map((t) => (
          <button
            key={t.id}
            className={`subtab ${sub === t.id ? "active" : ""}`}
            onClick={() => setSub(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {sub === "returns" && (
        <>
          {/* KPI strip rendered directly — no Collapsible (Framework pattern) */}
          <MetricsGrid apiUrl={mUrl} />

          {/* Equity + Drawdown — grid-2, each in Collapsible */}
          <div className="grid-2">
            <Collapsible title="Equity Curve">
              <div className="panel-body" style={{ padding: "12px 14px" }}>
                <EquityCurve apiUrl={eUrl} />
              </div>
            </Collapsible>
            <Collapsible title="Drawdown">
              <div className="panel-body" style={{ padding: "12px 14px" }}>
                <DrawdownChart apiUrl={eUrl} />
              </div>
            </Collapsible>
          </div>

          {/* Monthly returns calendar heatmap */}
          <Collapsible title="Monthly Returns Calendar" subtitle="% per month (trade count below)">
            <div className="panel-body tight"><Heatmap apiBase={apiBase} /></div>
          </Collapsible>

          {/* Distribution + Daily Bars — grid-2 */}
          <div className="grid-2">
            <Collapsible title="Trade PnL Distribution" subtitle="Histogram + KDE">
              <div className="panel-body"><Histogram apiBase={apiBase} /></div>
            </Collapsible>
            <Collapsible title="Daily PnL" subtitle="green = up day, red = down day">
              <div className="panel-body tight"><DailyBars apiUrl={eUrl} /></div>
            </Collapsible>
          </div>

          {/* Rolling Sharpe (20d & 60d) */}
          <Collapsible title="Rolling Metrics" subtitle="20-day / 60-day rolling Sharpe (ann.)">
            <div className="panel-body tight">
              <div className="grid-2" style={{ gap: 0 }}>
                <RollingChart
                  apiUrl={eUrl}
                  window={20}
                  title="Rolling Sharpe · 20d"
                  height={200}
                />
                <RollingChart
                  apiUrl={eUrl}
                  window={60}
                  title="Rolling Sharpe · 60d"
                  color="#e07b76"
                  height={200}
                />
              </div>
            </div>
          </Collapsible>

          {/* Time-based breakdowns (Monthly / Yearly / Day of Week) — DTE moved to its own sub-tab */}
          <BreakdownTabs
            apiBase={apiBase}
            include={["Monthly", "Yearly", "Day of Week"]}
            title="Returns Breakdown"
          />

          {/* Per-year daily calendar — collapsed by default (large section) */}
          <Collapsible
            title="Daily Returns Calendar · per year"
            defaultOpen={false}
          >
            <div className="panel-body tight"><DailyCalendar apiUrl={eUrl} /></div>
          </Collapsible>
        </>
      )}

      {sub === "transactions" && renderTransactions()}

      {sub === "dte" && (
        <BreakdownTabs
          apiBase={apiBase}
          include={["By DTE"]}
          title="DTE Breakdown"
        />
      )}

      {sub === "intraday" && renderIntraday()}

      {sub === "charts" && renderCharts?.()}
      {sub === "mtm" && renderMTM?.()}
    </div>
  );
}
