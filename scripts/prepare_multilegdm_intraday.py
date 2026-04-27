"""Build per-day intraday JSON for the MultiLegDM dashboard's Charts tab.

For each trading day that has MultiLegDM trades, writes
  output/multi_leg_dm/api/intraday/<YYYY-MM-DD>.json
with:
  {
    "date": str,
    "spot":      [[ts_ms, price], ...],      # full-day 5-second spot
    "trades": [
      {
        "trade_num", "entry_time", "exit_time", "exit_reason",
        "atm_strike", "pnl_premium",
        "spot_at_entry", "spot_at_exit",
        "premium_at_entry", "premium_at_exit",
        "premium_series": [[ts_ms, combined_mid], ...],  # within active window
        "legs": [{"strike", "side", "entry_px", "exit_px", "pnl_premium"}]
      }
    ]
  }

Also writes output/multi_leg_dm/api/available-dates.json = ["YYYY-MM-DD", ...].
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.data_utils import get_nearest_expiry_file, load_spot  # noqa: E402

STRATEGY = "multi_leg_dm"
OUTPUT_DIR = PROJECT_ROOT / "output" / STRATEGY
API_DIR = OUTPUT_DIR / "api"
INTRADAY_DIR = API_DIR / "intraday"

# Trading-day DTE source. The DTE column counts TRADING days (not calendar)
# until the nearest expiry (Exp1). Indexed by trading date (YYYY-MM-DD).
TRADING_DATES_CSV = Path("/Users/harsha/Desktop/Research/DATA/NSE/trading_dates.csv")


def _load_dte_lookup() -> dict[str, int]:
    """Build {trade_date_str: trading_day_dte} from the NSE trading_dates.csv.

    DTE in the CSV is the canonical, trading-day count — 0 on expiry day,
    typically maxes at 4–5 for NIFTY weeklies.
    """
    if not TRADING_DATES_CSV.exists():
        print(f"  WARN: {TRADING_DATES_CSV} not found — DTE will be None")
        return {}
    df = pd.read_csv(TRADING_DATES_CSV, usecols=["t_date", "DTE"])
    df = df.dropna(subset=["DTE"])
    df["t_date"] = pd.to_datetime(df["t_date"]).dt.strftime("%Y-%m-%d")
    df["DTE"] = df["DTE"].astype(int)
    return dict(zip(df["t_date"], df["DTE"]))


_DTE_LOOKUP: dict[str, int] = _load_dte_lookup()

# Resample interval for charted series (smaller = fatter JSON).
RESAMPLE = "5s"
SESSION_START_HM = "09:15:00"
SESSION_END_HM = "15:30:00"


def _sanitize(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    return obj


def _to_ist(dt_col: pd.Series) -> pd.Series:
    """Source parquet files store IST timestamps labelled as UTC.
    Treat them as naive IST — don't shift, just strip any tz."""
    s = pd.to_datetime(dt_col)
    if getattr(s.dt, "tz", None) is not None:
        s = s.dt.tz_localize(None)
    return s


def _ts_ms(series) -> list[int]:
    """Convert a DatetimeIndex/Series to epoch-ms, regardless of source precision.
    Source parquet is datetime64[ms]; forcing to [ns] first makes the divide
    uniform across potential precisions."""
    return (pd.DatetimeIndex(series).astype("datetime64[ns]").astype("int64") // 1_000_000).tolist()


def build_day(date_str: str, day_trades: pd.DataFrame, day_legs: pd.DataFrame) -> dict | None:
    """Build the intraday JSON for one day. Returns None if data unavailable.

    Both spot and combined premium are resampled onto a single session-anchored
    5-second grid (09:15:00 → 15:30:00 IST) so every timestamp on one series
    exists on the other. Entry/exit markers are snapped to the 5s bucket that
    contains the event, so they always land on a data point of the premium
    curve — never floating between points.
    """
    session_start = pd.Timestamp(f"{date_str} {SESSION_START_HM}")
    session_end = pd.Timestamp(f"{date_str} {SESSION_END_HM}")
    session_grid = pd.date_range(session_start, session_end, freq=RESAMPLE)

    # Spot
    try:
        spot = load_spot(date_str)
    except Exception as e:
        print(f"  [{date_str}] spot load failed: {e}")
        return None

    spot["datetime"] = _to_ist(spot["datetime"])
    spot = spot.set_index("datetime").sort_index()
    # Clip to the trading session and resample on the common grid.
    spot_in_session = spot.loc[session_start:session_end, "spot"]
    spot_bucketed = (
        spot_in_session.resample(RESAMPLE, origin=session_start).last().reindex(session_grid).ffill()
    )

    # Options
    opts_path = get_nearest_expiry_file(date_str)
    if opts_path is None:
        print(f"  [{date_str}] no option file")
        return None

    # Expiry date is parsed from the option filename (Cleaned_YYYYMMDD.parquet).
    # DTE is the canonical TRADING-DAY count from NSE/trading_dates.csv —
    # NOT a calendar diff (which inflates Friday/Monday cycles by the weekend).
    expiry_str: str | None = None
    dte: int | None = _DTE_LOOKUP.get(date_str)
    try:
        stem = opts_path.stem  # e.g. "Cleaned_20251202"
        date_part = stem.split("_")[-1]
        exp_ts = pd.Timestamp(f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}")
        expiry_str = exp_ts.strftime("%Y-%m-%d")
    except Exception:
        pass

    opt_cols = ["datetime", "strike_price", "option_type", "buy_price", "sell_price", "ltp"]
    opts = pd.read_parquet(opts_path, columns=opt_cols)
    opts["datetime"] = _to_ist(opts["datetime"])
    # mid = (bid + ask)/2, fall back to LTP if either side missing
    bid = opts["buy_price"]
    ask = opts["sell_price"]
    mid = (bid + ask) / 2.0
    mid = mid.where((bid > 0) & (ask > 0), opts["ltp"])
    opts["mid"] = mid
    opts["strike_price"] = opts["strike_price"].astype(int)
    if opts["option_type"].dtype == object:
        opts["option_type"] = opts["option_type"].apply(
            lambda x: x.decode() if isinstance(x, bytes) else x
        )
    # Clip options to the session once — per-leg filters reuse this.
    opts = opts[(opts["datetime"] >= session_start) & (opts["datetime"] <= session_end)]

    trades_out: list[dict] = []
    for _, trow in day_trades.iterrows():
        tn = int(trow["trade_num"])
        entry_t = pd.Timestamp(f"{date_str} {trow['entry_time']}")
        exit_t = pd.Timestamp(f"{date_str} {trow['exit_time']}")
        if exit_t <= entry_t:
            exit_t = entry_t + pd.Timedelta(seconds=1)

        # Snap entry/exit to the shared 5s grid (ceil for entry to avoid showing
        # premium before the trade existed; floor for exit to avoid showing
        # premium after the trade closed).
        entry_bucket = entry_t.ceil(RESAMPLE)
        exit_bucket = exit_t.floor(RESAMPLE)
        if exit_bucket < entry_bucket:
            exit_bucket = entry_bucket

        legs_df = day_legs[day_legs["trade_num"] == tn]
        if legs_df.empty:
            continue

        # Build per-leg mid on the SAME session grid, then sum across legs.
        leg_series: list[pd.Series] = []
        for _, lrow in legs_df.iterrows():
            s = (
                opts[(opts["strike_price"] == int(lrow["strike"]))
                     & (opts["option_type"] == lrow["side"])]
                .set_index("datetime")["mid"]
                .sort_index()
            )
            if s.empty:
                continue
            # Resample to 5s (last of bucket), project onto session grid with ffill
            # so each leg has a value at every grid tick.
            s_on_grid = s.resample(RESAMPLE, origin=session_start).last().reindex(session_grid).ffill()
            leg_series.append(s_on_grid)

        premium_series_list: list[list] = []
        premium_at_entry = None
        premium_at_exit = None
        if leg_series:
            combined = pd.concat(leg_series, axis=1).sum(axis=1, min_count=len(leg_series))
            # Keep only the trade window buckets — premium does not exist outside [entry, exit].
            combined = combined.loc[entry_bucket:exit_bucket].dropna()
            if not combined.empty:
                premium_series_list = list(zip(_ts_ms(combined.index), combined.round(2).tolist()))
                premium_at_entry = float(combined.iloc[0])
                premium_at_exit = float(combined.iloc[-1])

        legs_out = [
            {
                "strike": int(l["strike"]),
                "side": l["side"],
                "entry_px": round(float(l["entry_px"]), 2) if pd.notna(l["entry_px"]) else None,
                "exit_px": round(float(l["exit_px"]), 2) if pd.notna(l["exit_px"]) else None,
                "pnl_premium": round(float(l["pnl_premium"]), 2),
            }
            for _, l in legs_df.iterrows()
        ]

        trades_out.append({
            "trade_num": tn,
            "entry_time": str(trow["entry_time"]),
            "exit_time": str(trow["exit_time"]),
            # entry_ms / exit_ms are the SNAPPED bucket timestamps so markers
            # always coincide with actual data points on the premium series.
            "entry_ms": int(entry_bucket.value // 1_000_000),
            "exit_ms": int(exit_bucket.value // 1_000_000),
            "exit_reason": str(trow["exit_reason"]),
            "atm_strike": int(trow["atm_strike"]),
            "atm_straddle": round(float(trow["atm_straddle"]), 2),
            "band_half": round(float(trow["band_half"]), 2),
            "spot_at_entry": round(float(trow["spot_at_entry"]), 2),
            "spot_at_exit": round(float(trow["spot_at_exit"]), 2),
            "pnl_premium": round(float(trow["pnl_premium"]), 2),
            "premium_at_entry": round(premium_at_entry, 2) if premium_at_entry is not None else None,
            "premium_at_exit": round(premium_at_exit, 2) if premium_at_exit is not None else None,
            "premium_series": premium_series_list,
            "legs": legs_out,
        })

    spot_out = list(zip(_ts_ms(spot_bucketed.index), spot_bucketed.round(2).tolist()))

    return {
        "date": date_str,
        "expiry": expiry_str,
        "dte": dte,
        "spot": spot_out,
        "trades": trades_out,
    }


def main() -> None:
    trades_path = OUTPUT_DIR / "trades.xlsx"
    legs_path = OUTPUT_DIR / "legs.csv"
    if not trades_path.exists() or not legs_path.exists():
        print("trades.xlsx or legs.csv missing — run the backtest first.")
        return

    trades = pd.read_excel(trades_path)
    legs = pd.read_csv(legs_path)

    trades["date"] = pd.to_datetime(trades["date"]).dt.strftime("%Y-%m-%d")
    legs["date"] = pd.to_datetime(legs["date"]).dt.strftime("%Y-%m-%d")

    dates = sorted(trades["date"].unique())
    INTRADAY_DIR.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for d in dates:
        day_trades = trades[trades["date"] == d].copy()
        day_legs = legs[legs["date"] == d].copy()
        payload = build_day(d, day_trades, day_legs)
        if payload is None:
            continue
        out = INTRADAY_DIR / f"{d}.json"
        with open(out, "w") as f:
            json.dump(_sanitize(payload), f)
        written.append(d)
        print(f"  wrote {out.name} ({len(payload['trades'])} trades, {len(payload['spot'])} spot pts)")

    # available-dates.json
    with open(API_DIR / "available-dates.json", "w") as f:
        json.dump(written, f)

    print(f"\nDone. {len(written)} days written to {INTRADAY_DIR}")


if __name__ == "__main__":
    main()
