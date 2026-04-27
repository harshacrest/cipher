"""Compute MTM (mark-to-market) analysis for MultiLegDM.

Reads the per-day intraday JSONs (which contain trade-by-trade premium series)
and produces:

- mtm_ohlc.json        — per-day {date, open, high, low, close, range, n_trades, dte}
- mtm_stats.json       — summary statistics for close / high / low / range / intraday DD
- mtm_distribution.json — histogram bins for close / high / low / range

Methodology
-----------
For each day we reconstruct the full intraday MTM curve by stitching together
realized + unrealized PnL across all trades:

    mtm(t) = sum( pnl(closed trades) ) + ( entry_premium - current_premium ) for any active trade

Trades are sequential (no overlap in this strategy), so at most one trade is
active at a time. The min/max of the MTM curve give the day's intraday low/high.
The close = sum of realized PnL across all trades for the day.

Note: PnL is in "premium points" (sum of leg prices). For a 12-leg short
strangle, 1 point of premium move = 1 point of MTM PnL per contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INTRADAY_DIR = PROJECT_ROOT / "output" / "multi_leg_dm" / "api" / "intraday"
API_DIR = PROJECT_ROOT / "output" / "multi_leg_dm" / "api"


def compute_day_mtm(d: dict) -> dict | None:
    """Reconstruct intraday MTM curve for one day; return OHLC summary."""
    trades = d.get("trades", [])
    if not trades:
        return None

    trades = sorted(trades, key=lambda t: t["entry_ms"])

    # Open is the MTM at start of day = 0 (no positions before first entry)
    open_mtm = 0.0
    high_mtm = 0.0
    low_mtm = 0.0
    closed_pnl = 0.0  # cumulative realized PnL

    for t in trades:
        entry_p = float(t["premium_at_entry"])
        exit_p = float(t["premium_at_exit"])

        # During this trade: mtm(s) = closed_pnl + (entry_p - current_p)
        # The intra-trade min/max:
        #   max_mtm = closed_pnl + entry_p - min_premium_during_trade
        #   min_mtm = closed_pnl + entry_p - max_premium_during_trade
        ps = t.get("premium_series") or []
        if ps:
            prices = [float(p[1]) for p in ps]
            min_p = min(prices)
            max_p = max(prices)
            in_trade_max = closed_pnl + (entry_p - min_p)
            in_trade_min = closed_pnl + (entry_p - max_p)
        else:
            # Fallback: use entry/exit only
            in_trade_max = closed_pnl + (entry_p - min(entry_p, exit_p))
            in_trade_min = closed_pnl + (entry_p - max(entry_p, exit_p))

        high_mtm = max(high_mtm, in_trade_max)
        low_mtm = min(low_mtm, in_trade_min)

        # Trade closes — realize PnL
        closed_pnl += entry_p - exit_p
        # Touch the close-of-trade point on the curve
        high_mtm = max(high_mtm, closed_pnl)
        low_mtm = min(low_mtm, closed_pnl)

    return {
        "date": d["date"],
        "open": round(open_mtm, 2),
        "high": round(high_mtm, 2),
        "low": round(low_mtm, 2),
        "close": round(closed_pnl, 2),
        "range": round(high_mtm - low_mtm, 2),
        "n_trades": len(trades),
        "dte": d.get("dte"),
    }


def percentile_dict(s: pd.Series) -> dict:
    return {
        f"p{p}": round(float(np.percentile(s, p)), 2)
        for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]
    }


def histogram(values: np.ndarray, bins: int = 40) -> list[dict]:
    counts, edges = np.histogram(values, bins=bins)
    return [
        {
            "lo": round(float(edges[i]), 2),
            "hi": round(float(edges[i + 1]), 2),
            "count": int(counts[i]),
        }
        for i in range(len(counts))
    ]


def main() -> None:
    files = sorted(INTRADAY_DIR.glob("*.json"))
    print(f"Reading {len(files)} intraday files...")

    rows: list[dict] = []
    for fp in files:
        try:
            with open(fp) as f:
                d = json.load(f)
        except Exception as e:
            print(f"  fail {fp.name}: {e}")
            continue
        row = compute_day_mtm(d)
        if row is not None:
            rows.append(row)

    if not rows:
        print("No data — nothing to write.")
        return

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # ---------------- mtm_ohlc.json ----------------
    ohlc = df.copy()
    ohlc["date"] = ohlc["date"].dt.strftime("%Y-%m-%d")
    with open(API_DIR / "mtm_ohlc.json", "w") as f:
        json.dump(ohlc.to_dict("records"), f)

    # ---------------- mtm_stats.json ---------------
    # Intraday drawdown = how far below close the trough went
    df["intraday_dd"] = df["low"] - df["close"]    # ≤ 0
    df["intraday_runup"] = df["high"] - df["close"]  # ≥ 0

    stats = {
        "n_days": int(len(df)),
        "close": {
            "mean": round(float(df["close"].mean()), 2),
            "std": round(float(df["close"].std()), 2),
            "min": round(float(df["close"].min()), 2),
            "max": round(float(df["close"].max()), 2),
            "skew": round(float(df["close"].skew()), 3),
            "kurt": round(float(df["close"].kurt()), 3),
            "positive_pct": round(float((df["close"] > 0).mean() * 100), 2),
            "zero_days": int((df["close"] == 0).sum()),
            **percentile_dict(df["close"]),
        },
        "high": {
            "mean": round(float(df["high"].mean()), 2),
            "std": round(float(df["high"].std()), 2),
            "max": round(float(df["high"].max()), 2),
            **percentile_dict(df["high"]),
        },
        "low": {
            "mean": round(float(df["low"].mean()), 2),
            "std": round(float(df["low"].std()), 2),
            "min": round(float(df["low"].min()), 2),
            **percentile_dict(df["low"]),
        },
        "range": {
            "mean": round(float(df["range"].mean()), 2),
            "std": round(float(df["range"].std()), 2),
            **percentile_dict(df["range"]),
        },
        "intraday_dd": {
            "mean": round(float(df["intraday_dd"].mean()), 2),
            "min": round(float(df["intraday_dd"].min()), 2),
            **percentile_dict(df["intraday_dd"]),
        },
        "intraday_runup": {
            "mean": round(float(df["intraday_runup"].mean()), 2),
            "max": round(float(df["intraday_runup"].max()), 2),
            **percentile_dict(df["intraday_runup"]),
        },
        # Path-shape counts:
        "mae_recoveries": int(((df["low"] < 0) & (df["close"] > 0)).sum()),  # red→green
        "mfe_giveaways": int(((df["high"] > 0) & (df["close"] < 0)).sum()),  # green→red
        "all_red": int(((df["high"] <= 0) & (df["close"] < 0)).sum()),       # never green
        "all_green": int(((df["low"] >= 0) & (df["close"] > 0)).sum()),      # never red
    }

    # Per-DTE breakdown
    if "dte" in df.columns:
        dte_groups = df.groupby(df["dte"].fillna(-1).astype(int))
        stats["by_dte"] = []
        for dte, g in dte_groups:
            stats["by_dte"].append({
                "dte": int(dte),
                "n_days": int(len(g)),
                "close_mean": round(float(g["close"].mean()), 2),
                "close_std": round(float(g["close"].std()), 2),
                "high_mean": round(float(g["high"].mean()), 2),
                "low_mean": round(float(g["low"].mean()), 2),
                "win_rate": round(float((g["close"] > 0).mean() * 100), 2),
            })

    with open(API_DIR / "mtm_stats.json", "w") as f:
        json.dump(stats, f, indent=2)

    # ---------------- mtm_distribution.json --------
    distribution = {
        "close": histogram(df["close"].values),
        "high": histogram(df["high"].values),
        "low": histogram(df["low"].values),
        "range": histogram(df["range"].values),
        "intraday_dd": histogram(df["intraday_dd"].values),
    }
    with open(API_DIR / "mtm_distribution.json", "w") as f:
        json.dump(distribution, f)

    # ---------------- path_distribution.json -------
    # Frequency distribution tables for the two interesting path shapes:
    #
    #   recovery_lows  → days that went red intraday but closed green (low<0, close>0).
    #                    "How deep was the red on those days?" — bin |low|
    #
    #   giveaway_highs → days that went green intraday but closed red (high>0, close<0).
    #                    "How high was the green on those days?" — bin high
    #
    # Fixed point-based bins so the buckets read naturally to a trader.
    BIN_EDGES = [0, 25, 50, 75, 100, 150, 200, 300, 500, 1000, 5000]

    def banded_distribution(values: np.ndarray, closes: np.ndarray) -> list[dict]:
        """Return per-bin {lo, hi, count, pct, cum_pct, mean_close, median_close}."""
        if len(values) == 0:
            return []
        total = len(values)
        rows = []
        cum = 0
        for i in range(len(BIN_EDGES) - 1):
            lo, hi = BIN_EDGES[i], BIN_EDGES[i + 1]
            mask = (values >= lo) & (values < hi)
            cnt = int(mask.sum())
            cum += cnt
            in_closes = closes[mask]
            rows.append({
                "lo": lo,
                "hi": hi,
                "count": cnt,
                "pct": round(100 * cnt / total, 2),
                "cum_pct": round(100 * cum / total, 2),
                "mean_close": (round(float(in_closes.mean()), 2) if cnt else None),
                "median_close": (round(float(np.median(in_closes)), 2) if cnt else None),
            })
        return rows

    recovery_mask = (df["low"] < 0) & (df["close"] > 0)
    giveaway_mask = (df["high"] > 0) & (df["close"] < 0)

    rec_depths = (-df.loc[recovery_mask, "low"]).values  # |low| in points
    rec_closes = df.loc[recovery_mask, "close"].values
    gv_peaks = df.loc[giveaway_mask, "high"].values
    gv_closes = df.loc[giveaway_mask, "close"].values

    path_dist = {
        "recovery_lows": {
            "n": int(recovery_mask.sum()),
            "summary": {
                "mean_depth": round(float(rec_depths.mean()), 2) if len(rec_depths) else None,
                "median_depth": round(float(np.median(rec_depths)), 2) if len(rec_depths) else None,
                "max_depth": round(float(rec_depths.max()), 2) if len(rec_depths) else None,
                "mean_recovery_close": round(float(rec_closes.mean()), 2) if len(rec_closes) else None,
            },
            "bins": banded_distribution(rec_depths, rec_closes),
        },
        "giveaway_highs": {
            "n": int(giveaway_mask.sum()),
            "summary": {
                "mean_peak": round(float(gv_peaks.mean()), 2) if len(gv_peaks) else None,
                "median_peak": round(float(np.median(gv_peaks)), 2) if len(gv_peaks) else None,
                "max_peak": round(float(gv_peaks.max()), 2) if len(gv_peaks) else None,
                "mean_giveaway_close": round(float(gv_closes.mean()), 2) if len(gv_closes) else None,
            },
            "bins": banded_distribution(gv_peaks, gv_closes),
        },
    }
    with open(API_DIR / "path_distribution.json", "w") as f:
        json.dump(path_dist, f, indent=2)

    # ---------------- console summary --------------
    print(f"\nWrote {len(rows)} day OHLC records.")
    print(
        f"  Close: mean={stats['close']['mean']:>7.1f}  std={stats['close']['std']:>6.1f}  "
        f"p5={stats['close']['p5']:>7.1f}  p95={stats['close']['p95']:>7.1f}  win%={stats['close']['positive_pct']:.1f}"
    )
    print(
        f"  High : mean={stats['high']['mean']:>7.1f}  p95={stats['high']['p95']:>7.1f}  max={stats['high']['max']:.1f}"
    )
    print(
        f"  Low  : mean={stats['low']['mean']:>7.1f}  p5={stats['low']['p5']:>7.1f}   min={stats['low']['min']:.1f}"
    )
    print(
        f"  Intraday DD (low-close): mean={stats['intraday_dd']['mean']:.1f}  p5={stats['intraday_dd']['p5']:.1f}  min={stats['intraday_dd']['min']:.1f}"
    )
    print(
        f"  Path shapes: red→green={stats['mae_recoveries']}  green→red={stats['mfe_giveaways']}  all-red={stats['all_red']}  all-green={stats['all_green']}"
    )
    # Path-distribution preview
    print("\n  Recovery days (red→green) — depth of intraday red:")
    for b in path_dist["recovery_lows"]["bins"]:
        if b["count"] > 0:
            print(f"    [{b['lo']:>4}, {b['hi']:>4})  n={b['count']:>4}  ({b['pct']:>5.1f}%)  mean_close={b['mean_close']:>+7.1f}")
    print("\n  Giveaway days (green→red) — peak of intraday green:")
    for b in path_dist["giveaway_highs"]["bins"]:
        if b["count"] > 0:
            print(f"    [{b['lo']:>4}, {b['hi']:>4})  n={b['count']:>4}  ({b['pct']:>5.1f}%)  mean_close={b['mean_close']:>+7.1f}")


if __name__ == "__main__":
    main()
