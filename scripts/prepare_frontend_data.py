"""
Pre-process backtest output into JSON files for the frontend.
Reads xlsx/csv and options parquets, writes static JSON to output/<strategy>/api/.
"""

import json
import math
import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.data_utils import load_spot, load_options_at_strike

STRATEGY = "atm_straddle_sell"
OUTPUT_DIR = PROJECT_ROOT / "output" / STRATEGY
API_DIR = OUTPUT_DIR / "api"
DAYS_DIR = API_DIR / "days"


def sanitize(obj):
    """Replace NaN/Inf with None for valid JSON."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj


def write_json(data, filename: str):
    path = API_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(sanitize(data), f, separators=(",", ":"))


def process_performance():
    """Read performance.xlsx sheets into separate JSON files."""
    xls = pd.ExcelFile(OUTPUT_DIR / "performance.xlsx")

    df = pd.read_excel(xls, "Summary")
    write_json(df.to_dict("records"), "metrics.json")

    df = pd.read_excel(xls, "Monthly")
    write_json(df.to_dict("records"), "monthly.json")

    df = pd.read_excel(xls, "Yearly")
    write_json(df.to_dict("records"), "yearly.json")

    df = pd.read_excel(xls, "DayOfWeek")
    write_json(df.to_dict("records"), "dow.json")

    # ByDTE may not exist anymore
    if "ByDTE" in xls.sheet_names:
        df = pd.read_excel(xls, "ByDTE")
        write_json(df.to_dict("records"), "dte.json")
    else:
        write_json([], "dte.json")

    print("  Performance sheets -> JSON")


def process_trades():
    """Read trades.xlsx into JSON."""
    df = pd.read_excel(OUTPUT_DIR / "trades.xlsx")
    write_json(df.to_dict("records"), "trades.json")
    print(f"  Trades ({len(df)} rows) -> JSON")


def process_equity():
    """Read equity_curve.csv into JSON."""
    df = pd.read_csv(OUTPUT_DIR / "equity_curve.csv")
    write_json(df.to_dict("records"), "equity.json")
    print(f"  Equity curve ({len(df)} rows) -> JSON")


def process_intraday():
    """Generate per-day intraday JSON with spot + straddle price at locked strike."""
    trades = pd.read_excel(OUTPUT_DIR / "trades.xlsx")

    available_dates = []
    DAYS_DIR.mkdir(parents=True, exist_ok=True)

    for _, trade in tqdm(trades.iterrows(), total=len(trades), desc="  Intraday JSON"):
        day_str = trade["date"]
        atm_strike = int(trade["atm_strike"])

        try:
            # Load spot
            spot_df = load_spot(day_str)
            spot_df = spot_df.sort_values("datetime").reset_index(drop=True)

            # Load options at the locked-in strike
            opts = load_options_at_strike(day_str, atm_strike)
            if opts is None or opts.empty:
                continue

            # Merge spot and options on datetime
            merged = spot_df.merge(opts, on="datetime", how="inner")
            merged = merged.sort_values("datetime").reset_index(drop=True)

            # Downsample to ~1 per minute
            sampled = merged.iloc[::60].copy()

            # Ensure entry/exit ticks are included
            merged["time_str"] = merged["datetime"].dt.strftime("%H:%M:%S")
            entry_rows = merged[merged["time_str"] >= "09:21:00"].head(1)
            exit_rows = merged[merged["time_str"] >= "15:00:00"].head(1)
            sampled = pd.concat([sampled, entry_rows, exit_rows]).drop_duplicates(subset=["datetime"]).sort_values("datetime")

            ticks = []
            for _, row in sampled.iterrows():
                ticks.append({
                    "time": row["datetime"].strftime("%H:%M"),
                    "spot": round(float(row["spot"]), 2),
                    "atm_price": round(float(row["straddle_price"]), 2),
                    "ce_price": round(float(row["ce_ltp"]), 2),
                    "pe_price": round(float(row["pe_ltp"]), 2),
                })

            entry_time = "09:21"
            exit_time = "15:00"
            if len(entry_rows) > 0:
                entry_time = entry_rows.iloc[0]["datetime"].strftime("%H:%M")
            if len(exit_rows) > 0:
                exit_time = exit_rows.iloc[0]["datetime"].strftime("%H:%M")

            day_data = {
                "ticks": ticks,
                "entry_time": entry_time,
                "exit_time": exit_time,
                "atm_strike": atm_strike,
                "pnl": round(float(trade["pnl"]), 2),
            }

            with open(DAYS_DIR / f"{day_str}.json", "w") as f:
                json.dump(sanitize(day_data), f, separators=(",", ":"))

            available_dates.append(day_str)

        except Exception as e:
            print(f"    Skipped {day_str}: {e}")
            continue

    available_dates.sort()
    write_json(available_dates, "available_dates.json")
    print(f"  Intraday: {len(available_dates)} day files written")


def main():
    print(f"Preparing frontend data for: {STRATEGY}")
    process_performance()
    process_trades()
    process_equity()
    process_intraday()
    print(f"\nDone! Output in: {API_DIR}")


if __name__ == "__main__":
    main()
