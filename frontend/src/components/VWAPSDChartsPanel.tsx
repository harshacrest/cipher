"use client";

import { useEffect, useState } from "react";
import { useFetch } from "@/hooks/use-fetch";
import DatePicker from "./DatePicker";
import VWAPSDChart, { type VWAPSDDayPayload } from "./VWAPSDChart";

export default function VWAPSDChartsPanel() {
  const { data: dates, loading: datesLoading } = useFetch<string[]>(
    "/api/vwap-sd/intraday-dates",
  );
  const [selectedDate, setSelectedDate] = useState<string>("");

  useEffect(() => {
    if (dates && dates.length > 0 && !selectedDate) {
      setSelectedDate(dates[dates.length - 1]);
    }
  }, [dates, selectedDate]);

  if (datesLoading || !dates) {
    return (
      <div className="panel">
        <div className="muted" style={{ padding: 20 }}>Loading…</div>
      </div>
    );
  }
  if (dates.length === 0) {
    return (
      <div className="panel">
        <div className="muted" style={{ padding: 20 }}>
          No intraday chart data. Run <code>scripts/prepare_vwap_sd_charts.py</code>.
        </div>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Intraday Charts</h2>
        <DatePicker
          selectedDate={selectedDate}
          onDateChange={setSelectedDate}
          apiUrl="/api/vwap-sd/intraday-dates"
        />
      </div>
      <div className="panel-body">
        {selectedDate && <ChartForDate date={selectedDate} />}
      </div>
    </div>
  );
}

function ChartForDate({ date }: { date: string }) {
  const { data, loading, error } = useFetch<VWAPSDDayPayload>(
    `/api/vwap-sd/intraday/${date}`,
  );
  if (loading || !data) {
    return (
      <div className="h-[560px] flex items-center justify-center text-zinc-500 text-sm">
        Loading chart…
      </div>
    );
  }
  if (error) {
    return (
      <div className="h-[560px] flex items-center justify-center text-red-400 text-sm">
        No data for {date}
      </div>
    );
  }
  return <VWAPSDChart data={data} />;
}
