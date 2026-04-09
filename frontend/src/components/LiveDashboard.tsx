"use client";

import { useCallback, useEffect, useState } from "react";
import { useLiveWebSocket } from "@/hooks/use-live-ws";
import LivePnLChart from "./LivePnLChart";

interface LiveConfig {
  dhan: { access_token: string; client_id: string };
  strategy: { entry_time: string; exit_time: string; num_lots: number };
}

const DEFAULT_CONFIG: LiveConfig = {
  dhan: { access_token: "", client_id: "" },
  strategy: { entry_time: "09:21:00", exit_time: "15:00:00", num_lots: 1 },
};

export default function LiveDashboard() {
  const [config, setConfig] = useState<LiveConfig>(DEFAULT_CONFIG);
  const [processRunning, setProcessRunning] = useState(false);
  const [loading, setLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [configLoaded, setConfigLoaded] = useState(false);

  const { connected, spotPrice, positions, logs, pnlHistory } =
    useLiveWebSocket(processRunning);

  // Load config on mount
  useEffect(() => {
    fetch("/api/live/config")
      .then((r) => r.json())
      .then((data) => {
        if (data.dhan) {
          setConfig(data);
          setConfigLoaded(true);
        }
      })
      .catch(() => setConfigLoaded(true));

    // Check if process is already running
    fetch("/api/live/control")
      .then((r) => r.json())
      .then((data) => setProcessRunning(data.running || false))
      .catch(() => {});
  }, []);

  const saveConfig = useCallback(async () => {
    setLoading(true);
    try {
      await fetch("/api/live/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      setStatusMsg("Config saved");
      setTimeout(() => setStatusMsg(""), 2000);
    } catch {
      setStatusMsg("Save failed");
    }
    setLoading(false);
  }, [config]);

  const toggleProcess = useCallback(async () => {
    setLoading(true);
    const action = processRunning ? "stop" : "start";

    if (action === "start") {
      // Save config first
      await fetch("/api/live/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
    }

    try {
      const res = await fetch("/api/live/control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const data = await res.json();
      setProcessRunning(action === "start");
      setStatusMsg(data.status || action);
      setTimeout(() => setStatusMsg(""), 3000);
    } catch {
      setStatusMsg(`${action} failed`);
    }
    setLoading(false);
  }, [processRunning, config]);

  const updateDhan = (field: string, value: string) =>
    setConfig((prev) => ({
      ...prev,
      dhan: { ...prev.dhan, [field]: value },
    }));

  const updateStrategy = (field: string, value: string | number) =>
    setConfig((prev) => ({
      ...prev,
      strategy: { ...prev.strategy, [field]: value },
    }));

  return (
    <div className="space-y-6">
      {/* --- Status bar --- */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span
            className={`inline-block w-2.5 h-2.5 rounded-full ${
              processRunning && connected
                ? "bg-emerald-400 animate-pulse"
                : processRunning
                  ? "bg-yellow-400 animate-pulse"
                  : "bg-zinc-600"
            }`}
          />
          <span className="text-sm text-zinc-400">
            {processRunning && connected
              ? "Connected"
              : processRunning
                ? "Starting..."
                : "Stopped"}
          </span>
        </div>

        {spotPrice > 0 && (
          <span className="text-sm font-mono text-zinc-300">
            NIFTY: {spotPrice.toFixed(2)}
          </span>
        )}

        {statusMsg && (
          <span className="text-xs text-zinc-500 ml-auto">{statusMsg}</span>
        )}
      </div>

      {/* --- Config + Controls --- */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Dhan credentials */}
        <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-lg p-4 space-y-3">
          <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
            Dhan Credentials
          </h3>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Access Token</label>
            <input
              type="password"
              value={config.dhan.access_token}
              onChange={(e) => updateDhan("access_token", e.target.value)}
              disabled={processRunning}
              className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-xs font-mono text-zinc-300 focus:outline-none focus:border-zinc-500 disabled:opacity-50"
              placeholder="eyJ..."
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Client ID</label>
            <input
              type="text"
              value={config.dhan.client_id}
              onChange={(e) => updateDhan("client_id", e.target.value)}
              disabled={processRunning}
              className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-xs font-mono text-zinc-300 focus:outline-none focus:border-zinc-500 disabled:opacity-50"
              placeholder="100xxxxxxx"
            />
          </div>
        </div>

        {/* Strategy config */}
        <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-lg p-4 space-y-3">
          <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
            Strategy Config
          </h3>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Entry Time</label>
              <input
                type="text"
                value={config.strategy.entry_time}
                onChange={(e) => updateStrategy("entry_time", e.target.value)}
                disabled={processRunning}
                className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-xs font-mono text-zinc-300 focus:outline-none focus:border-zinc-500 disabled:opacity-50"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Exit Time</label>
              <input
                type="text"
                value={config.strategy.exit_time}
                onChange={(e) => updateStrategy("exit_time", e.target.value)}
                disabled={processRunning}
                className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-xs font-mono text-zinc-300 focus:outline-none focus:border-zinc-500 disabled:opacity-50"
              />
            </div>
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Lots</label>
              <input
                type="number"
                min={0}
                value={config.strategy.num_lots}
                onChange={(e) =>
                  updateStrategy("num_lots", parseInt(e.target.value) || 0)
                }
                disabled={processRunning}
                className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-xs font-mono text-zinc-300 focus:outline-none focus:border-zinc-500 disabled:opacity-50"
              />
            </div>
          </div>

          <div className="flex gap-2 pt-1">
            <button
              onClick={saveConfig}
              disabled={processRunning || loading}
              className="px-3 py-1.5 text-xs rounded bg-zinc-700 hover:bg-zinc-600 text-zinc-300 disabled:opacity-40 transition-colors"
            >
              Save Config
            </button>
            <button
              onClick={toggleProcess}
              disabled={loading}
              className={`px-4 py-1.5 text-xs rounded font-medium transition-colors ${
                processRunning
                  ? "bg-red-600/80 hover:bg-red-600 text-white"
                  : "bg-emerald-600/80 hover:bg-emerald-600 text-white"
              } disabled:opacity-40`}
            >
              {loading ? "..." : processRunning ? "Stop" : "Start"}
            </button>
          </div>
        </div>
      </div>

      {/* --- Live data (only when running) --- */}
      {processRunning && (
        <>
          {/* Spot price chart */}
          {pnlHistory.length > 0 && (
            <LivePnLChart data={pnlHistory} title="NIFTY Spot (Live)" />
          )}

          {/* Positions */}
          {positions.length > 0 && (
            <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-lg p-4">
              <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3">
                Open Positions
              </h3>
              <div className="space-y-2">
                {positions.map((pos, i) => (
                  <div
                    key={pos.instrument || i}
                    className="flex items-center justify-between text-xs font-mono"
                  >
                    <span className="text-zinc-300">{pos.instrument}</span>
                    <span className="text-zinc-500">
                      {pos.side} x {pos.qty}
                    </span>
                    <span className="text-zinc-400">
                      Entry: {pos.avg_entry?.toFixed(2) || "-"}
                    </span>
                    <span
                      className={
                        (pos.unrealized_pnl || 0) >= 0
                          ? "text-emerald-400"
                          : "text-red-400"
                      }
                    >
                      PnL: {pos.unrealized_pnl?.toFixed(2) || "0.00"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Log viewer */}
          <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-lg p-4">
            <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider mb-3">
              Engine Logs
            </h3>
            <div className="max-h-[300px] overflow-auto space-y-0.5 font-mono text-[11px]">
              {logs.length === 0 ? (
                <p className="text-zinc-600">Waiting for events...</p>
              ) : (
                logs.map((log, i) => (
                  <div key={i} className="flex gap-2">
                    <span className="text-zinc-600 shrink-0">
                      {new Date(log.ts).toLocaleTimeString()}
                    </span>
                    <span
                      className={
                        log.level === "ERROR"
                          ? "text-red-400"
                          : log.level === "WARNING"
                            ? "text-yellow-400"
                            : "text-zinc-400"
                      }
                    >
                      {log.msg}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
