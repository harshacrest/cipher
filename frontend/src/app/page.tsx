"use client";

import { useState } from "react";
import LiveDashboard from "@/components/LiveDashboard";
import Documentation from "@/components/Documentation";
import ResearchDashboard, {
  strategySubtitle,
  type Strategy,
} from "@/components/ResearchDashboard";

type Tab = "research" | "live" | "docs";

const TAB_LABELS: Record<Tab, string> = {
  research: "Backtesting Research",
  live:     "Live",
  docs:     "Documentation",
};

export default function Home() {
  const [tab, setTab] = useState<Tab>("research");
  const [strategy, setStrategy] = useState<Strategy>("atm");

  const subtitle =
    tab === "research" ? strategySubtitle(strategy) :
    tab === "live"     ? "Live OTM1 Strangle Sell" :
                          "Strategy Documentation";

  return (
    <div className="shell">
      <header className="topbar">
        <h1>
          Cipher
          <span className="meta" style={{ marginLeft: 18 }}>
            / {subtitle}
          </span>
        </h1>
        <div className="meta">BACKTEST · NIFTY 50 · NSE</div>
      </header>

      <nav className="tabs">
        {(Object.keys(TAB_LABELS) as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`tab ${tab === t ? "active" : ""}`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </nav>

      <main className="content">
        {tab === "research" && (
          <ResearchDashboard strategy={strategy} onStrategyChange={setStrategy} />
        )}
        {tab === "live" && <LiveDashboard />}
        {tab === "docs" && <Documentation />}
      </main>

      <footer className="footer">
        Cipher · Backtesting Dashboard · NIFTY 50 Index Options · NSE
      </footer>
    </div>
  );
}
