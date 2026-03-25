"use client";

import { useEffect, useState } from "react";
import { useFetch } from "@/hooks/use-fetch";

interface DatePickerProps {
  selectedDate: string;
  onDateChange: (date: string) => void;
}

export default function DatePicker({
  selectedDate,
  onDateChange,
}: DatePickerProps) {
  const { data: dates } = useFetch<string[]>("/api/available-dates");
  const [dateSet, setDateSet] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (dates) setDateSet(new Set(dates));
  }, [dates]);

  const currentIdx = dates?.indexOf(selectedDate) ?? -1;
  const hasPrev = currentIdx > 0;
  const hasNext = dates ? currentIdx < dates.length - 1 : false;

  function goPrev() {
    if (hasPrev && dates) onDateChange(dates[currentIdx - 1]);
  }

  function goNext() {
    if (hasNext && dates) onDateChange(dates[currentIdx + 1]);
  }

  function handleInput(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value;
    if (dateSet.has(val)) {
      onDateChange(val);
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={goPrev}
        disabled={!hasPrev}
        className="px-2.5 py-1.5 text-sm bg-zinc-800 border border-zinc-700 rounded-md hover:bg-zinc-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        Prev
      </button>
      <input
        type="date"
        value={selectedDate}
        onChange={handleInput}
        className="bg-zinc-800 border border-zinc-700 rounded-md px-3 py-1.5 text-sm font-mono text-zinc-200 focus:outline-none focus:ring-1 focus:ring-zinc-500"
      />
      <button
        onClick={goNext}
        disabled={!hasNext}
        className="px-2.5 py-1.5 text-sm bg-zinc-800 border border-zinc-700 rounded-md hover:bg-zinc-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
      >
        Next
      </button>
      {dates && (
        <span className="text-xs text-zinc-600 ml-2">
          {currentIdx + 1} / {dates.length} trading days
        </span>
      )}
    </div>
  );
}
