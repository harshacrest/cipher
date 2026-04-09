"use client";

import { useState } from "react";
import MetricsGrid from "@/components/MetricsGrid";
import EquityCurve from "@/components/EquityCurve";
import IntradayExplorer from "@/components/IntradayExplorer";
import BreakdownTabs from "@/components/BreakdownTabs";
import TradesTable from "@/components/TradesTable";
import LiveDashboard from "@/components/LiveDashboard";
import DayHighDashboard from "@/components/DayHighDashboard";

type Tab = "backtest" | "day-high" | "live";

const TAB_LABELS: Record<Tab, string> = {
  backtest: "Backtest",
  "day-high": "Day High",
  live: "Live",
};

const TAB_SUBTITLES: Record<Tab, string> = {
  backtest: "OTM1 Strangle Sell",
  "day-high": "Day High OTM Sell",
  live: "OTM1 Strangle Sell",
};

export default function Home() {
  const [tab, setTab] = useState<Tab>("backtest");
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800 px-6 py-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold tracking-tight">
          Cipher{" "}
          <span className="text-zinc-500 font-normal">
            / {TAB_SUBTITLES[tab]}
          </span>
        </h1>
        <div className="flex gap-1 bg-zinc-800/60 rounded-lg p-0.5">
          {(Object.keys(TAB_LABELS) as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-1.5 text-xs font-medium rounded-md transition-colors ${
                tab === t
                  ? "bg-zinc-700 text-zinc-100"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {TAB_LABELS[t]}
            </button>
          ))}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-10">
        {tab === "backtest" && (
          <>
            <section>
              <MetricsGrid />
            </section>
            <section>
              <EquityCurve />
            </section>
            <section>
              <IntradayExplorer externalDate={selectedDate} />
            </section>
            <section>
              <BreakdownTabs />
            </section>
            <section>
              <TradesTable onDateSelect={setSelectedDate} />
            </section>
          </>
        )}
        {tab === "day-high" && <DayHighDashboard />}
        {tab === "live" && <LiveDashboard />}
      </main>
    </div>
  );
}
