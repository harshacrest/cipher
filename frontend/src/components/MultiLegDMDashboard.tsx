"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  ColorType,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type UTCTimestamp,
} from "lightweight-charts";
import { useFetch } from "@/hooks/use-fetch";
import StrategyDashboard from "./StrategyDashboard";
import DatePicker from "./DatePicker";
import MTMAnalysisPanel from "./MTMAnalysisPanel";

const API_BASE = "/api/multilegdm";

interface MultiLegTrade {
  date: string;
  trade_num: number;
  entry_time: string;
  exit_time: string;
  exit_reason: string;
  spot_at_entry: number;
  spot_at_exit: number;
  spot_move: number;
  atm_strike: number;
  atm_straddle: number;
  band_half: number;
  num_legs: number;
  pnl_points: number;
  pnl_premium: number;
  cumulative_daily_pnl_premium: number;
  cumulative_pnl: number;
}

interface Leg {
  strike: number;
  side: "CE" | "PE";
  entry_px: number | null;
  exit_px: number | null;
  pnl_premium: number;
}

interface DayTrade {
  trade_num: number;
  entry_time: string;
  exit_time: string;
  entry_ms: number;
  exit_ms: number;
  exit_reason: string;
  atm_strike: number;
  atm_straddle: number;
  band_half: number;
  spot_at_entry: number;
  spot_at_exit: number;
  pnl_premium: number;
  premium_at_entry: number | null;
  premium_at_exit: number | null;
  premium_series: [number, number][]; // [ms, combined premium]
  legs: Leg[];
}

interface IntradayPayload {
  date: string;
  expiry: string | null;
  dte: number | null;
  spot: [number, number][]; // [ms, price]
  trades: DayTrade[];
}

type SortKey = keyof MultiLegTrade;

export default function MultiLegDMDashboard() {
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  return (
    <StrategyDashboard
      apiBase={API_BASE}
      renderTransactions={() => (
        <MultiLegTradesTable onDateSelect={setSelectedDate} />
      )}
      renderIntraday={() => (
        <IntradayPanel externalDate={selectedDate} onDateChange={setSelectedDate} />
      )}
      renderCharts={() => (
        <ChartsPanel externalDate={selectedDate} onDateChange={setSelectedDate} />
      )}
      chartsLabel="Charts"
      renderMTM={() => <MTMAnalysisPanel />}
      mtmLabel="MTM"
    />
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────

function useLatestDate(externalDate: string | null | undefined) {
  const { data: dates } = useFetch<string[]>(`${API_BASE}/available-dates`);
  const [selected, setSelected] = useState<string>("");

  useEffect(() => {
    if (!dates || dates.length === 0) return;
    if (externalDate && dates.includes(externalDate)) {
      setSelected(externalDate);
    } else if (!selected) {
      setSelected(dates[dates.length - 1]);
    }
  }, [dates, externalDate, selected]);

  return { dates, selected, setSelected };
}

function fmtNum(v: number | null | undefined, digits = 2, sign = false): string {
  if (v == null || Number.isNaN(v)) return "—";
  const s = v.toFixed(digits);
  return sign && v > 0 ? `+${s}` : s;
}

// ─── Intraday (day detail) ────────────────────────────────────────────────

function IntradayPanel({
  externalDate,
  onDateChange,
}: {
  externalDate: string | null;
  onDateChange?: (d: string) => void;
}) {
  const { dates, selected, setSelected } = useLatestDate(externalDate);

  const handleDateChange = (d: string) => {
    setSelected(d);
    onDateChange?.(d);
  };

  const { data: exits } = useFetch<ExitReasonRow[]>(`${API_BASE}/exit-reasons`);

  const { data: day, loading } = useFetch<IntradayPayload>(
    `${API_BASE}/intraday/${selected || "__none__"}`,
  );

  // Day-level aggregates (must be declared before any early return to keep hook order stable)
  const dayStats = useMemo(() => {
    if (!day) return null;
    const total = day.trades.reduce((a, t) => a + t.pnl_premium, 0);
    const spotRange = day.spot.length
      ? day.spot.reduce(
          (acc, [, v]) => ({ lo: Math.min(acc.lo, v), hi: Math.max(acc.hi, v) }),
          { lo: Infinity, hi: -Infinity },
        )
      : { lo: 0, hi: 0 };
    return {
      count: day.trades.length,
      total,
      winners: day.trades.filter((t) => t.pnl_premium > 0).length,
      spotRange,
    };
  }, [day]);

  if (!selected || !dates) {
    return (
      <div className="panel">
        <div className="muted" style={{ padding: 20 }}>Loading…</div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Day selector + day summary */}
      <div className="panel">
        <div className="panel-head">
          <h2>Day Detail</h2>
          <DatePicker
            selectedDate={selected}
            onDateChange={handleDateChange}
            apiUrl={`${API_BASE}/available-dates`}
          />
        </div>
        <div className="panel-body tight">
          {loading || !day ? (
            <div className="muted" style={{ padding: 12 }}>Loading…</div>
          ) : (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                gap: 10,
                padding: "8px 12px",
              }}
            >
              <Stat
                label="DTE"
                value={day?.dte != null ? String(day.dte) : "—"}
                tone={day?.dte === 0 ? "neg" : undefined}
              />
              <Stat label="Trades" value={String(dayStats?.count ?? 0)} />
              <Stat
                label="Day PnL (prem)"
                value={fmtNum(dayStats?.total ?? 0, 2, true)}
                tone={(dayStats?.total ?? 0) >= 0 ? "pos" : "neg"}
              />
              <Stat
                label="Winners"
                value={`${dayStats?.winners ?? 0} / ${dayStats?.count ?? 0}`}
              />
              <Stat
                label="Spot Range"
                value={`${dayStats?.spotRange.lo?.toFixed(0)} – ${dayStats?.spotRange.hi?.toFixed(0)}`}
              />
              <Stat
                label="Spot Move"
                value={`${((dayStats?.spotRange.hi ?? 0) - (dayStats?.spotRange.lo ?? 0)).toFixed(0)}`}
              />
            </div>
          )}
        </div>
      </div>

      {/* Trades for the day with leg breakdown */}
      {day && (
        <div className="panel">
          <div className="panel-head">
            <h2>Trades ({day.trades.length})</h2>
            <span className="meta" style={{ fontSize: 11 }}>
              Click a trade row to expand its 12 legs
            </span>
          </div>
          <div className="panel-body tight">
            <DayTradesAccordion trades={day.trades} />
          </div>
        </div>
      )}

      {/* Exit reason summary (moved here from the old Intraday tab) */}
      <ExitReasonsTable exits={exits || []} />
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "pos" | "neg";
}) {
  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: 6,
        padding: "8px 10px",
        background: "var(--panel-2, rgba(255,255,255,0.02))",
      }}
    >
      <div
        className="muted"
        style={{
          fontSize: 10,
          textTransform: "uppercase",
          letterSpacing: 0.5,
          marginBottom: 4,
        }}
      >
        {label}
      </div>
      <div
        className={tone === "pos" ? "num-pos" : tone === "neg" ? "num-neg" : undefined}
        style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 15, fontWeight: 600 }}
      >
        {value}
      </div>
    </div>
  );
}

function DayTradesAccordion({ trades }: { trades: DayTrade[] }) {
  const [open, setOpen] = useState<number | null>(null);

  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th style={{ width: 28 }}></th>
            <th>#</th>
            <th>Entry</th>
            <th>Exit</th>
            <th>ATM</th>
            <th>Straddle</th>
            <th>Band/2</th>
            <th>Spot Δ</th>
            <th>Prem In → Out</th>
            <th>PnL (prem)</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => {
            const isOpen = open === t.trade_num;
            const premDelta =
              t.premium_at_entry != null && t.premium_at_exit != null
                ? t.premium_at_exit - t.premium_at_entry
                : null;
            return (
              <Fragment key={t.trade_num}>
                <tr
                  className="clickable"
                  onClick={() => setOpen(isOpen ? null : t.trade_num)}
                >
                  <td style={{ color: "var(--ink-3)" }}>{isOpen ? "▼" : "▶"}</td>
                  <td>{t.trade_num}</td>
                  <td>{t.entry_time}</td>
                  <td>{t.exit_time}</td>
                  <td>{t.atm_strike}</td>
                  <td>{fmtNum(t.atm_straddle)}</td>
                  <td>{fmtNum(t.band_half, 0)}</td>
                  <td>{fmtNum(t.spot_at_exit - t.spot_at_entry, 0, true)}</td>
                  <td className="mono">
                    {fmtNum(t.premium_at_entry)} → {fmtNum(t.premium_at_exit)}{" "}
                    {premDelta != null && (
                      <span
                        className={premDelta <= 0 ? "num-pos" : "num-neg"}
                        style={{ fontSize: 10 }}
                      >
                        ({fmtNum(premDelta, 2, true)})
                      </span>
                    )}
                  </td>
                  <td className={t.pnl_premium >= 0 ? "num-pos" : "num-neg"}>
                    {fmtNum(t.pnl_premium, 2, true)}
                  </td>
                  <td>
                    <span
                      className={`pill ${
                        t.exit_reason === "EOD"
                          ? ""
                          : t.exit_reason === "SPOT_BAND"
                            ? "warn"
                            : "neg"
                      }`}
                    >
                      {t.exit_reason}
                    </span>
                  </td>
                </tr>
                {isOpen && <LegsDetailRow legs={t.legs} />}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function LegsDetailRow({ legs }: { legs: Leg[] }) {
  // Sort by strike ascending for a natural look
  const sorted = [...legs].sort((a, b) => a.strike - b.strike);
  const totalPnl = legs.reduce((a, l) => a + l.pnl_premium, 0);

  return (
    <tr>
      <td colSpan={11} style={{ background: "rgba(255,255,255,0.02)", padding: "8px 14px" }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
            gap: 8,
          }}
        >
          {sorted.map((l, i) => (
            <div
              key={i}
              style={{
                border: "1px solid var(--border)",
                borderRadius: 5,
                padding: "6px 8px",
                fontSize: 11,
                fontFamily: "var(--font-mono, monospace)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  color: "var(--ink-3)",
                  marginBottom: 3,
                }}
              >
                <span>
                  {l.strike}{" "}
                  <span
                    className="pill"
                    style={{
                      fontSize: 9,
                      padding: "1px 5px",
                      background: l.side === "CE" ? "rgba(59,130,246,0.18)" : "rgba(168,85,247,0.18)",
                    }}
                  >
                    {l.side}
                  </span>
                </span>
                <span className={l.pnl_premium >= 0 ? "num-pos" : "num-neg"}>
                  {fmtNum(l.pnl_premium, 2, true)}
                </span>
              </div>
              <div style={{ color: "var(--ink-2)" }}>
                {fmtNum(l.entry_px)} → {fmtNum(l.exit_px)}
              </div>
            </div>
          ))}
        </div>
        <div
          style={{
            marginTop: 8,
            textAlign: "right",
            fontSize: 11,
            color: "var(--ink-3)",
          }}
        >
          Σ legs ={" "}
          <span className={totalPnl >= 0 ? "num-pos" : "num-neg"}>
            {fmtNum(totalPnl, 2, true)}
          </span>
        </div>
      </td>
    </tr>
  );
}

interface ExitReasonRow {
  exit_reason: string;
  count: number;
  total_pnl_premium: number;
  avg_pnl_premium: number;
  win_rate: number;
}

function ExitReasonsTable({ exits }: { exits: ExitReasonRow[] }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <h2>Exit Reason Summary</h2>
        <span className="meta" style={{ fontSize: 11 }}>
          Daily SL / Spot Band / EOD breakdown (all days)
        </span>
      </div>
      <div className="panel-body tight">
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Reason</th>
                <th>Count</th>
                <th>Total PnL (prem)</th>
                <th>Avg PnL (prem)</th>
                <th>Win Rate %</th>
              </tr>
            </thead>
            <tbody>
              {exits.map((e) => (
                <tr key={e.exit_reason}>
                  <td>
                    <span
                      className={`pill ${
                        e.exit_reason === "EOD"
                          ? ""
                          : e.exit_reason === "SPOT_BAND"
                            ? "warn"
                            : "neg"
                      }`}
                    >
                      {e.exit_reason}
                    </span>
                  </td>
                  <td>{e.count}</td>
                  <td
                    className={e.total_pnl_premium >= 0 ? "num-pos" : "num-neg"}
                  >
                    {e.total_pnl_premium >= 0 ? "+" : ""}
                    {e.total_pnl_premium?.toLocaleString()}
                  </td>
                  <td className={e.avg_pnl_premium >= 0 ? "num-pos" : "num-neg"}>
                    {e.avg_pnl_premium >= 0 ? "+" : ""}
                    {e.avg_pnl_premium?.toFixed(0)}
                  </td>
                  <td>{e.win_rate?.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─── Charts tab ───────────────────────────────────────────────────────────

function ChartsPanel({
  externalDate,
  onDateChange,
}: {
  externalDate: string | null;
  onDateChange?: (d: string) => void;
}) {
  const { dates, selected, setSelected } = useLatestDate(externalDate);
  const handle = (d: string) => {
    setSelected(d);
    onDateChange?.(d);
  };

  const { data: day, loading } = useFetch<IntradayPayload>(
    `${API_BASE}/intraday/${selected || "__none__"}`,
  );

  if (!selected || !dates) {
    return <div className="panel"><div className="muted" style={{ padding: 20 }}>Loading…</div></div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="panel">
        <div className="panel-head">
          <h2>
            Spot vs Combined Premium
            {day && day.dte != null && (
              <span
                className="pill"
                style={{
                  marginLeft: 10,
                  fontSize: 10,
                  padding: "2px 8px",
                  background:
                    day.dte === 0
                      ? "rgba(239,68,68,0.18)"
                      : day.dte <= 2
                        ? "rgba(245,158,11,0.18)"
                        : "rgba(59,130,246,0.18)",
                  color: "var(--ink)",
                  fontWeight: 600,
                }}
                title={day.expiry ? `Expiry ${day.expiry}` : undefined}
              >
                DTE {day.dte}
                {day.expiry && (
                  <span style={{ marginLeft: 6, opacity: 0.7, fontWeight: 400 }}>
                    · exp {day.expiry}
                  </span>
                )}
              </span>
            )}
          </h2>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Legend color="#3b82f6" label="Spot (LHS)" />
            <Legend color="#f59e0b" label="Combined Prem (RHS)" />
            <Legend color="#a855f7" label="MTM pts (overlay)" />
            <DatePicker
              selectedDate={selected}
              onDateChange={handle}
              apiUrl={`${API_BASE}/available-dates`}
            />
          </div>
        </div>
        <div className="panel-body" style={{ padding: "12px 14px" }}>
          {loading || !day ? (
            <div className="muted" style={{ padding: 20 }}>Loading…</div>
          ) : day.trades.length === 0 ? (
            <div className="muted" style={{ padding: 20 }}>No trades on this day.</div>
          ) : (
            <>
              <SpotPremiumChart data={day} />
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 10,
                  marginTop: 12,
                  fontSize: 11,
                  color: "var(--ink-3)",
                }}
              >
                {day.trades.map((t) => (
                  <div
                    key={t.trade_num}
                    style={{
                      border: "1px solid var(--border)",
                      borderRadius: 5,
                      padding: "4px 8px",
                      display: "flex",
                      gap: 8,
                      alignItems: "center",
                    }}
                  >
                    <span
                      style={{
                        display: "inline-block",
                        width: 8,
                        height: 8,
                        background: TRADE_COLORS[(t.trade_num - 1) % TRADE_COLORS.length],
                      }}
                    />
                    <span>#{t.trade_num}</span>
                    <span>
                      {t.entry_time} → {t.exit_time}
                    </span>
                    <span>
                      ATM {t.atm_strike} · band ±{t.band_half.toFixed(0)}
                    </span>
                    <span
                      className={t.pnl_premium >= 0 ? "num-pos" : "num-neg"}
                    >
                      {fmtNum(t.pnl_premium, 2, true)}
                    </span>
                    <span
                      className={`pill ${
                        t.exit_reason === "EOD"
                          ? ""
                          : t.exit_reason === "SPOT_BAND"
                            ? "warn"
                            : "neg"
                      }`}
                      style={{ fontSize: 9, padding: "1px 5px" }}
                    >
                      {t.exit_reason}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--ink-3)" }}>
      <span style={{ display: "inline-block", width: 10, height: 2, background: color }} />
      {label}
    </span>
  );
}

const TRADE_COLORS = [
  "#f59e0b", // amber
  "#10b981", // emerald
  "#ec4899", // pink
  "#8b5cf6", // violet
  "#ef4444", // red
  "#14b8a6", // teal
  "#f97316", // orange
];

function SpotPremiumChart({ data }: { data: IntradayPayload }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);

  useEffect(() => {
    if (!hostRef.current) return;
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(hostRef.current, {
      width: hostRef.current.clientWidth,
      height: 420,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#a1a1aa",
        fontFamily: "var(--font-geist-mono), monospace",
      },
      grid: { vertLines: { visible: false }, horzLines: { color: "#27272a" } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: "#3f3f46" },
      crosshair: {
        horzLine: { color: "#71717a", style: 2 },
        vertLine: { color: "#71717a", style: 2 },
      },
      leftPriceScale: { visible: true, borderColor: "#3f3f46", scaleMargins: { top: 0.1, bottom: 0.1 } },
      rightPriceScale: { visible: true, borderColor: "#3f3f46", scaleMargins: { top: 0.1, bottom: 0.1 } },
    });

    // Spot on LHS
    const spotSeries = chart.addSeries(LineSeries, {
      priceScaleId: "left",
      color: "#3b82f6",
      lineWidth: 2,
      title: "Spot",
      priceLineVisible: false,
    });
    spotSeries.setData(
      dedupByTime(
        data.spot.map(([ms, v]) => ({
          time: msToUtc(ms),
          value: v,
        })),
      ),
    );

    // Combined premium on RHS — one series per trade (so each trade's active
    // window shows as its own segment, colored per-trade).
    for (const trade of data.trades) {
      if (!trade.premium_series || trade.premium_series.length === 0) continue;
      const color = TRADE_COLORS[(trade.trade_num - 1) % TRADE_COLORS.length];
      const premSeries = chart.addSeries(LineSeries, {
        priceScaleId: "right",
        color,
        lineWidth: 2,
        title: `#${trade.trade_num} Premium`,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      premSeries.setData(
        dedupByTime(
          trade.premium_series.map(([ms, v]) => ({
            time: msToUtc(ms),
            value: v,
          })),
        ),
      );

      // Entry/exit markers on the premium series itself (floats with RHS)
      const markers = [
        {
          time: msToUtc(trade.entry_ms),
          position: "aboveBar" as const,
          color: "#22c55e",
          shape: "arrowDown" as const,
          text: `E${trade.trade_num} SELL ${trade.premium_at_entry?.toFixed(0) ?? ""}`,
        },
        {
          time: msToUtc(trade.exit_ms),
          position: "belowBar" as const,
          color:
            trade.exit_reason === "SPOT_BAND"
              ? "#f59e0b"
              : trade.exit_reason === "EOD"
                ? "#a1a1aa"
                : "#ef4444",
          shape: "arrowUp" as const,
          text: `X${trade.trade_num} ${trade.exit_reason} ${trade.premium_at_exit?.toFixed(0) ?? ""}`,
        },
      ].sort((a, b) => (a.time as number) - (b.time as number));
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      createSeriesMarkers(premSeries as any, markers);
    }

    // ── MTM curve (overlay, points) ───────────────────────────────────────
    // Reconstruct intraday MTM at each premium tick:
    //   active trade: closed_pnl + (premium_at_entry - current_premium)
    //   between trades: flat at closed_pnl
    // Trades are non-overlapping by design.
    const mtmPoints: { time: UTCTimestamp; value: number }[] = [];
    const sortedTrades = [...data.trades].sort((a, b) => a.entry_ms - b.entry_ms);
    let closed = 0;
    // Anchor at session start so the line begins at 0
    if (data.spot.length > 0) {
      mtmPoints.push({ time: msToUtc(data.spot[0][0]), value: 0 });
    }
    for (const trade of sortedTrades) {
      const entryP = trade.premium_at_entry;
      const exitP = trade.premium_at_exit;
      if (entryP == null || !trade.premium_series?.length) continue;
      // Hold-flat point right before this trade's entry
      mtmPoints.push({ time: msToUtc(trade.entry_ms - 1), value: closed });
      // MTM through the trade window
      for (const [ms, prem] of trade.premium_series) {
        mtmPoints.push({ time: msToUtc(ms), value: closed + (entryP - prem) });
      }
      // Realize at exit
      if (exitP != null) {
        closed += entryP - exitP;
        mtmPoints.push({ time: msToUtc(trade.exit_ms), value: closed });
      }
    }
    // Carry final closed PnL flat to end of session
    if (data.spot.length > 0 && mtmPoints.length > 0) {
      const lastSpotMs = data.spot[data.spot.length - 1][0];
      const lastT = mtmPoints[mtmPoints.length - 1].time as unknown as number;
      if (msToUtc(lastSpotMs) > lastT) {
        mtmPoints.push({ time: msToUtc(lastSpotMs), value: closed });
      }
    }
    if (mtmPoints.length > 0) {
      const mtmSeries = chart.addSeries(LineSeries, {
        // Overlay scale (anything not "left"/"right" creates a new overlay)
        priceScaleId: "mtm",
        color: "#a855f7",
        lineWidth: 2,
        title: "MTM (pts)",
        priceLineVisible: false,
        lastValueVisible: true,
      });
      mtmSeries.setData(dedupByTime(mtmPoints));
      // Place the overlay scale on the right side, separated from the premium scale
      chart.priceScale("mtm").applyOptions({
        scaleMargins: { top: 0.05, bottom: 0.55 },
        borderColor: "#3f3f46",
      });
    }

    chart.timeScale().fitContent();
    chartRef.current = chart;

    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        chart.applyOptions({ width: e.contentRect.width });
      }
    });
    ro.observe(hostRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [data]);

  return <div ref={hostRef} style={{ width: "100%" }} />;
}

function msToUtc(ms: number): UTCTimestamp {
  return Math.floor(ms / 1000) as UTCTimestamp;
}

function dedupByTime<T extends { time: UTCTimestamp }>(arr: T[]): T[] {
  const out: T[] = [];
  let last: number | null = null;
  for (const a of arr) {
    const t = a.time as unknown as number;
    if (t === last) continue;
    last = t;
    out.push(a);
  }
  return out.sort((a, b) => (a.time as number) - (b.time as number));
}

// ─── Transactions table ───────────────────────────────────────────────────

function MultiLegTradesTable({
  onDateSelect,
}: {
  onDateSelect?: (date: string) => void;
}) {
  const { data, loading } = useFetch<MultiLegTrade[]>(`${API_BASE}/trades`);
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [sortAsc, setSortAsc] = useState(false);
  const [showAll, setShowAll] = useState(false);

  if (loading || !data)
    return (
      <div className="panel">
        <div className="muted" style={{ padding: 20 }}>Loading…</div>
      </div>
    );

  const sorted = [...data].sort((a, b) => {
    const va = a[sortKey],
      vb = b[sortKey];
    if (typeof va === "string")
      return sortAsc
        ? (va as string).localeCompare(vb as string)
        : (vb as string).localeCompare(va as string);
    return sortAsc
      ? (va as number) - (vb as number)
      : (vb as number) - (va as number);
  });
  const displayed = showAll ? sorted : sorted.slice(0, 50);

  const cols: { key: SortKey; label: string; fmt?: (v: unknown) => string }[] = [
    { key: "date", label: "Date" },
    { key: "trade_num", label: "#" },
    { key: "entry_time", label: "Entry" },
    { key: "exit_time", label: "Exit" },
    { key: "atm_strike", label: "Strike" },
    { key: "atm_straddle", label: "ATM Str", fmt: (v) => Number(v).toFixed(2) },
    { key: "band_half", label: "Band/2", fmt: (v) => Number(v).toFixed(0) },
    {
      key: "spot_move",
      label: "Spot Δ",
      fmt: (v) => (Number(v) >= 0 ? "+" : "") + Number(v).toFixed(0),
    },
    { key: "num_legs", label: "Legs" },
    {
      key: "pnl_premium",
      label: "PnL (prem)",
      fmt: (v) => (Number(v) >= 0 ? "+" : "") + Number(v).toLocaleString(),
    },
    {
      key: "cumulative_daily_pnl_premium",
      label: "Day Cum (prem)",
      fmt: (v) => (Number(v) >= 0 ? "+" : "") + Number(v).toLocaleString(),
    },
    { key: "exit_reason", label: "Exit" },
  ];

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else {
      setSortKey(key);
      setSortAsc(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-head">
        <h2>All Trades ({data.length})</h2>
        {!showAll && data.length > 50 && (
          <button
            onClick={() => setShowAll(true)}
            className="subtab"
            style={{ margin: 0 }}
          >
            Show all {data.length}
          </button>
        )}
      </div>
      <div className="panel-body tight">
        <div className="table-wrap" style={{ maxHeight: 520 }}>
          <table className="data">
            <thead>
              <tr>
                {cols.map((c) => (
                  <th key={c.key} onClick={() => handleSort(c.key)}>
                    {c.label}
                    {sortKey === c.key && (
                      <span style={{ marginLeft: 4, color: "var(--accent)" }}>
                        {sortAsc ? "▲" : "▼"}
                      </span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {displayed.map((t, i) => (
                <tr
                  key={i}
                  className="clickable"
                  onClick={() => onDateSelect?.(t.date)}
                >
                  {cols.map((c) => {
                    const v = t[c.key];
                    const display = c.fmt ? c.fmt(v) : String(v);
                    const isPnl =
                      c.key === "pnl_premium" ||
                      c.key === "cumulative_daily_pnl_premium";
                    const cls = isPnl
                      ? (v as number) >= 0
                        ? "num-pos"
                        : "num-neg"
                      : undefined;
                    return (
                      <td key={c.key} className={cls}>
                        {c.key === "exit_reason" ? (
                          <span
                            className={`pill ${
                              v === "EOD"
                                ? ""
                                : v === "SPOT_BAND"
                                  ? "warn"
                                  : "neg"
                            }`}
                          >
                            {display}
                          </span>
                        ) : (
                          display
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
