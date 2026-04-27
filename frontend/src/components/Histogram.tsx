"use client";

import { useMemo } from "react";
import { useFetch } from "@/hooks/use-fetch";

/**
 * Trade-PnL distribution — SVG histogram + KDE overlay, styled like the
 * Research Framework's Histogram component. Bins auto-computed from the
 * strategy's `/trades` endpoint (uses `pnl` field, which every cipher
 * trades payload exposes).
 *
 * Color convention:
 *   - bars: neutral panel-3 with gold edge
 *   - KDE line: gold
 *   - zero line: soft ink-3
 */
interface TradeRow { pnl?: number; day_pnl?: number }

function quantile(sorted: number[], q: number): number {
  if (!sorted.length) return 0;
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos), rest = pos - base;
  if (sorted[base + 1] !== undefined) return sorted[base] + rest * (sorted[base + 1] - sorted[base]);
  return sorted[base];
}

export default function Histogram({
  apiBase = "/api",
  bins = 40,
  height = 240,
}: {
  apiBase?: string;
  bins?: number;
  height?: number;
}) {
  const { data } = useFetch<TradeRow[]>(`${apiBase}/trades`);

  const model = useMemo(() => {
    if (!data || data.length === 0) return null;
    const vals = data
      .map((t) => (typeof t.pnl === "number" ? t.pnl : typeof t.day_pnl === "number" ? t.day_pnl : NaN))
      .filter((v) => Number.isFinite(v));
    if (!vals.length) return null;

    const sorted = [...vals].sort((a, b) => a - b);
    // Winsorize at 1%/99% to avoid extreme-wings dominating the view
    const lo = quantile(sorted, 0.005);
    const hi = quantile(sorted, 0.995);
    const trimmed = vals.map((v) => Math.min(Math.max(v, lo), hi));

    const min = Math.min(...trimmed);
    const max = Math.max(...trimmed);
    const width = (max - min) || 1;
    const binW = width / bins;
    const counts = new Array(bins).fill(0);
    for (const v of trimmed) {
      const idx = Math.min(bins - 1, Math.floor((v - min) / binW));
      counts[idx]++;
    }
    const maxCount = Math.max(...counts);

    // Simple Gaussian KDE on bin centers
    const mean = trimmed.reduce((s, x) => s + x, 0) / trimmed.length;
    const variance = trimmed.reduce((s, x) => s + (x - mean) * (x - mean), 0) / trimmed.length;
    const std = Math.sqrt(variance) || 1;
    // Silverman's rule-of-thumb bandwidth
    const h = 1.06 * std * Math.pow(trimmed.length, -1 / 5);
    const kde: { x: number; y: number }[] = [];
    const n = trimmed.length;
    for (let i = 0; i < bins; i++) {
      const x = min + (i + 0.5) * binW;
      let sum = 0;
      for (const v of trimmed) {
        const u = (x - v) / h;
        sum += Math.exp(-0.5 * u * u);
      }
      const density = sum / (n * h * Math.sqrt(2 * Math.PI));
      kde.push({ x, y: density });
    }
    // Normalize KDE to histogram peak for easy overlay
    const kdeMax = Math.max(...kde.map((p) => p.y));
    const scale = kdeMax > 0 ? maxCount / kdeMax : 1;

    return {
      min, max, binW, counts, maxCount,
      kde: kde.map((p) => ({ x: p.x, y: p.y * scale })),
      mean,
      median: quantile(sorted, 0.5),
      n: vals.length,
    };
  }, [data, bins]);

  if (!data) return <div className="muted" style={{ padding: 16 }}>Loading…</div>;
  if (!model) return <div className="muted" style={{ padding: 16 }}>No distribution data.</div>;

  const padL = 40, padR = 10, padT = 10, padB = 28;
  const w = 720;
  const h = height;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;

  const x = (v: number) => padL + ((v - model.min) / (model.max - model.min)) * plotW;
  const y = (c: number) => padT + plotH - (c / model.maxCount) * plotH;

  // X ticks ~6 values
  const xTicks = Array.from({ length: 6 }, (_, i) => model.min + (i / 5) * (model.max - model.min));

  // KDE as polyline points
  const kdePoints = model.kde.map((p) => `${x(p.x).toFixed(2)},${y(p.y).toFixed(2)}`).join(" ");

  return (
    <div style={{ width: "100%", overflowX: "auto" }}>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        width="100%"
        height={h}
        style={{ display: "block" }}
      >
        {/* zero line */}
        {0 >= model.min && 0 <= model.max && (
          <line
            x1={x(0)} y1={padT} x2={x(0)} y2={h - padB}
            stroke="var(--ink-3)" strokeDasharray="2,3" strokeWidth={1}
          />
        )}

        {/* histogram bars */}
        {model.counts.map((c, i) => {
          const cx = model.min + i * model.binW;
          const bx1 = x(cx);
          const bx2 = x(cx + model.binW);
          const by = y(c);
          const barH = h - padB - by;
          if (c === 0) return null;
          const barColor = cx + model.binW / 2 >= 0 ? "rgba(110,195,143,0.55)" : "rgba(224,123,118,0.55)";
          const edge = cx + model.binW / 2 >= 0 ? "rgba(110,195,143,0.9)" : "rgba(224,123,118,0.9)";
          return (
            <rect
              key={i}
              x={bx1 + 0.5}
              y={by}
              width={Math.max(0, bx2 - bx1 - 1)}
              height={barH}
              fill={barColor}
              stroke={edge}
              strokeWidth={0.5}
            />
          );
        })}

        {/* KDE curve */}
        <polyline
          points={kdePoints}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={1.5}
        />

        {/* mean marker */}
        <line
          x1={x(model.mean)} y1={padT} x2={x(model.mean)} y2={h - padB}
          stroke="var(--accent-2)" strokeDasharray="4,3" strokeWidth={1}
        />
        <text
          x={x(model.mean) + 4} y={padT + 10}
          fill="var(--accent-2)"
          style={{ fontFamily: "var(--font-mono)", fontSize: 9 }}
        >
          μ {model.mean.toFixed(2)}
        </text>

        {/* x ticks */}
        {xTicks.map((v, i) => (
          <g key={i}>
            <line x1={x(v)} y1={h - padB} x2={x(v)} y2={h - padB + 4} stroke="var(--rule)" />
            <text
              x={x(v)} y={h - padB + 16}
              textAnchor="middle"
              fill="var(--ink-3)"
              style={{ fontFamily: "var(--font-mono)", fontSize: 9 }}
            >
              {v.toFixed(0)}
            </text>
          </g>
        ))}

        {/* axis */}
        <line x1={padL} y1={h - padB} x2={w - padR} y2={h - padB} stroke="var(--rule)" />
      </svg>
      <div className="muted" style={{ marginTop: 6, fontSize: 10, display: "flex", gap: 16 }}>
        <span>n = {model.n.toLocaleString()}</span>
        <span>mean = {model.mean.toFixed(2)}</span>
        <span>median = {model.median.toFixed(2)}</span>
        <span>range = [{model.min.toFixed(1)}, {model.max.toFixed(1)}]</span>
      </div>
    </div>
  );
}
