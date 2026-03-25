"use client";

import { useState } from "react";
import MetricsGrid from "@/components/MetricsGrid";
import EquityCurve from "@/components/EquityCurve";
import IntradayExplorer from "@/components/IntradayExplorer";
import BreakdownTabs from "@/components/BreakdownTabs";
import TradesTable from "@/components/TradesTable";

export default function Home() {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800 px-6 py-4">
        <h1 className="text-lg font-semibold tracking-tight">
          Cipher{" "}
          <span className="text-zinc-500 font-normal">
            / ATM Straddle Sell
          </span>
        </h1>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-10">
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
      </main>
    </div>
  );
}
