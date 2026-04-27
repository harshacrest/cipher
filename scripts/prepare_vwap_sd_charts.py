"""Reconstruct per-day sClose + spot time series for the Charts subtab.

For each date that has trades in vwap_sd_straddles output, read the raw spot
and option parquet, build 1-minute aggregate straddle (sum of CE+PE mids for
baseStrike ± 350 step 50), compute cumulative VWAP/VAH/VAL since day start,
and emit JSON with trade entry/exit markers.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from datetime import date as _date

from lib.data_utils import DATA_ROOT, get_nearest_expiry_file


def _expiry_info(date_str: str) -> tuple[str | None, int | None]:
    """Return (YYYY-MM-DD expiry, DTE in calendar days) for the nearest expiry on date_str."""
    path = get_nearest_expiry_file(date_str)
    if path is None:
        return None, None
    # Filename format: Cleaned_YYYYMMDD.parquet
    stem = path.stem
    parts = stem.split("_")
    if len(parts) < 2 or len(parts[1]) != 8:
        return None, None
    yy, mm, dd = int(parts[1][:4]), int(parts[1][4:6]), int(parts[1][6:8])
    exp = _date(yy, mm, dd)
    tr_y, tr_m, tr_d = (int(x) for x in date_str.split("-"))
    tr = _date(tr_y, tr_m, tr_d)
    dte = (exp - tr).days
    return exp.isoformat(), dte

STRATEGY = "vwap_sd_straddles"
OUTPUT_DIR = PROJECT_ROOT / "output" / STRATEGY
API_DIR = OUTPUT_DIR / "api"
INTRADAY_DIR = API_DIR / "intraday"

STRIKE_STEP = 50
N_SIDE = 7          # ATM ± 7 -> 15 strikes
SD_MULT = 1.0


def _load_spot_minute(date_str: str) -> pd.DataFrame | None:
    p = DATA_ROOT / date_str / "Index" / "Cleaned_Spot.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p, columns=["datetime", "ltp"])
    df = df.dropna(subset=["ltp"])
    df = df[df["ltp"] > 0]
    df["minute"] = df["datetime"].dt.floor("1min")
    # last tick in each minute wins (simple close)
    df = df.sort_values("datetime").drop_duplicates(subset=["minute"], keep="last")
    return df[["minute", "ltp"]].rename(columns={"ltp": "spot"}).reset_index(drop=True)


def _load_options_minute(date_str: str, base_strike: int) -> pd.DataFrame | None:
    path = get_nearest_expiry_file(date_str)
    if path is None:
        return None
    df = pd.read_parquet(
        path,
        columns=[
            "datetime", "option_type", "strike_price",
            "ltp", "buy_price", "sell_price",
        ],
    )
    if df["option_type"].dtype == object:
        df["option_type"] = df["option_type"].apply(
            lambda x: x.decode() if isinstance(x, bytes) else x
        )

    low = base_strike - N_SIDE * STRIKE_STEP
    high = base_strike + N_SIDE * STRIKE_STEP
    df = df[(df["strike_price"] >= low) & (df["strike_price"] <= high)].copy()
    if df.empty:
        return None

    # mid = (bid+ask)/2 with ltp fallback — mirrors live strategy
    bid = df["buy_price"].astype(float).to_numpy()
    ask = df["sell_price"].astype(float).to_numpy()
    ltp = df["ltp"].astype(float).to_numpy()
    bad_bid = (bid <= 0) | np.isnan(bid)
    bad_ask = (ask <= 0) | np.isnan(ask)
    bid = np.where(bad_bid, ltp, bid)
    ask = np.where(bad_ask, ltp, ask)
    swap = ask < bid
    old_bid = bid.copy()
    bid = np.where(swap, ask, bid)
    ask = np.where(swap, old_bid, ask)
    df["mid"] = (bid + ask) / 2.0
    df = df[df["mid"] > 0]
    if df.empty:
        return None

    df["minute"] = df["datetime"].dt.floor("1min")
    # last mid in each minute per (strike, type)
    df = df.sort_values("datetime").drop_duplicates(
        subset=["minute", "strike_price", "option_type"], keep="last"
    )

    # sClose per minute = sum of mids across all legs present in that minute.
    # Forward-fill per leg so an absent tick keeps the last known mid.
    pivot = df.pivot_table(
        index="minute",
        columns=["strike_price", "option_type"],
        values="mid",
        aggfunc="last",
    ).sort_index().ffill()
    sclose = pivot.sum(axis=1, skipna=True)
    n_legs = pivot.notna().sum(axis=1)
    out = pd.DataFrame({
        "minute": pivot.index,
        "sclose": sclose.values,
        "n_legs": n_legs.values.astype(int),
    }).reset_index(drop=True)
    return out


def _bands(sclose: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cumulative expanding mean + population stdev, mirroring strategy."""
    n = len(sclose)
    cum = np.cumsum(sclose)
    cum_sq = np.cumsum(sclose ** 2)
    counts = np.arange(1, n + 1)
    mean = cum / counts
    var = cum_sq / counts - mean ** 2
    var = np.maximum(var, 0.0)
    sd = np.sqrt(var)
    return mean, mean + SD_MULT * sd, mean - SD_MULT * sd


def build_day_payload(date_str: str, trades_for_day: list[dict]) -> dict | None:
    if not trades_for_day:
        return None
    base_strike = int(trades_for_day[0]["base_strike"])

    spot_df = _load_spot_minute(date_str)
    opts_df = _load_options_minute(date_str, base_strike)
    if spot_df is None or opts_df is None:
        return None

    merged = pd.merge(opts_df, spot_df, on="minute", how="inner")
    # restrict to session hours
    merged = merged[
        (merged["minute"].dt.time >= pd.Timestamp("09:15").time())
        & (merged["minute"].dt.time <= pd.Timestamp("15:30").time())
    ].reset_index(drop=True)
    if merged.empty:
        return None

    # Bands computed from 09:16 onward, but include pre-entry bars for display
    sclose_arr = merged["sclose"].to_numpy(dtype=float)
    vwap, vah, val = _bands(sclose_arr)
    merged["vwap"] = vwap
    merged["vah"] = vah
    merged["val"] = val

    ticks = [
        {
            "time": row["minute"].strftime("%H:%M"),
            "spot": round(float(row["spot"]), 2),
            "sclose": round(float(row["sclose"]), 2),
            "vwap": round(float(row["vwap"]), 2),
            "vah": round(float(row["vah"]), 2),
            "val": round(float(row["val"]), 2),
            "n_legs": int(row["n_legs"]),
        }
        for _, row in merged.iterrows()
    ]

    trades_out = []
    for t in trades_for_day:
        trades_out.append({
            "trade_num": int(t["trade_num"]),
            "entry_time": str(t["entry_time"])[:5],
            "exit_time": str(t["exit_time"])[:5],
            "entry_sclose": float(t["entry_sclose"]),
            "exit_sclose": float(t["exit_sclose"]),
            "spot_at_entry": float(t["spot_at_entry"]),
            "spot_at_exit": float(t["spot_at_exit"]),
            "exit_reason": str(t["exit_reason"]),
            "pnl_points": float(t["pnl_points"]),
            "pnl_premium": float(t["pnl_premium"]),
        })

    expiry, dte = _expiry_info(date_str)
    return {
        "date": date_str,
        "base_strike": base_strike,
        "expiry": expiry,
        "dte": dte,
        "ticks": ticks,
        "trades": trades_out,
    }


def _sanitize(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    return obj


def main() -> None:
    trades_xlsx = OUTPUT_DIR / "trades.xlsx"
    if not trades_xlsx.exists():
        print(f"  trades.xlsx not found at {trades_xlsx}")
        return
    trades_df = pd.read_excel(trades_xlsx)
    if "date" not in trades_df.columns:
        print("  no 'date' column in trades.xlsx")
        return
    trades_df["date"] = pd.to_datetime(trades_df["date"]).dt.strftime("%Y-%m-%d")

    INTRADAY_DIR.mkdir(parents=True, exist_ok=True)

    dates: list[str] = []
    for date_str, g in trades_df.groupby("date"):
        payload = build_day_payload(date_str, g.to_dict("records"))
        if payload is None:
            print(f"  skip {date_str} (no data)")
            continue
        out = INTRADAY_DIR / f"{date_str}.json"
        with open(out, "w") as f:
            json.dump(_sanitize(payload), f)
        dates.append(date_str)
        print(f"  {date_str}: {len(payload['ticks'])} bars, {len(payload['trades'])} trades")

    # dates index
    with open(INTRADAY_DIR / "_dates.json", "w") as f:
        json.dump(sorted(dates), f)
    print(f"Done: {len(dates)} days -> {INTRADAY_DIR}")


if __name__ == "__main__":
    main()
