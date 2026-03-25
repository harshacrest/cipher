"use client";

import { useState, useEffect } from "react";
import { useFetch } from "@/hooks/use-fetch";
import DatePicker from "./DatePicker";
import IntradayChart from "./IntradayChart";

interface Props {
  externalDate?: string | null;
}

export default function IntradayExplorer({ externalDate }: Props) {
  const { data: dates } = useFetch<string[]>("/api/available-dates");
  const [selectedDate, setSelectedDate] = useState<string>("");

  // Set initial date to last available
  useEffect(() => {
    if (dates && dates.length > 0 && !selectedDate) {
      setSelectedDate(dates[dates.length - 1]);
    }
  }, [dates, selectedDate]);

  // Respond to external date selection (e.g. clicking a trade row)
  useEffect(() => {
    if (externalDate && dates?.includes(externalDate)) {
      setSelectedDate(externalDate);
      // Scroll intraday section into view
      document.getElementById("intraday-explorer")?.scrollIntoView({ behavior: "smooth" });
    }
  }, [externalDate, dates]);

  if (!selectedDate) {
    return (
      <div className="animate-pulse h-[500px] bg-zinc-800/50 rounded-lg" />
    );
  }

  return (
    <div id="intraday-explorer" className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-400">
          Intraday Explorer
        </h2>
        <DatePicker
          selectedDate={selectedDate}
          onDateChange={setSelectedDate}
        />
      </div>
      <IntradayChart date={selectedDate} />
    </div>
  );
}
