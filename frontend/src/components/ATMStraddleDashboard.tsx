"use client";

import { useState } from "react";
import StrategyDashboard from "./StrategyDashboard";
import IntradayExplorer from "./IntradayExplorer";
import TradesTable from "./TradesTable";

/**
 * ATM OTM1 Strangle Sell — uses root `/api/*` endpoints (wired via
 * `DATA_DIR` in `next.config.ts`). Transactions and Intraday panels are
 * strategy-specific since each strategy has its own trade shape.
 */
export default function ATMStraddleDashboard() {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  return (
    <StrategyDashboard
      apiBase="/api"
      renderTransactions={() => <TradesTable onDateSelect={setSelectedDate} />}
      renderIntraday={() => <IntradayExplorer externalDate={selectedDate} />}
    />
  );
}
