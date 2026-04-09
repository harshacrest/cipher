"""
Pre-process backtest output into JSON files for the frontend.
Reads xlsx/csv and options parquets, writes static JSON to output/<strategy>/api/.

Supports OTM1 CE + OTM1 PE with separate strikes, per-leg SL, and per-leg exit info.
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
    """Generate per-day intraday JSON with spot + separate CE/PE prices at their respective strikes."""
    trades = pd.read_excel(OUTPUT_DIR / "trades.xlsx")

    available_dates = []
    DAYS_DIR.mkdir(parents=True, exist_ok=True)

    for _, trade in tqdm(trades.iterrows(), total=len(trades), desc="  Intraday JSON"):
        day_str = trade["date"]
        ce_strike = int(trade["ce_strike"])
        pe_strike = int(trade["pe_strike"])

        try:
            # Load spot
            spot_df = load_spot(day_str)
            spot_df = spot_df.sort_values("datetime").reset_index(drop=True)

            # Load CE options at OTM1 CE strike
            ce_opts = load_options_at_strike(day_str, ce_strike)
            pe_opts = load_options_at_strike(day_str, pe_strike)

            # Build merged dataframe
            merged = spot_df.copy()

            if ce_opts is not None and not ce_opts.empty:
                ce_col = ce_opts[["datetime", "ce_ltp"]].rename(columns={"ce_ltp": "ce_price"})
                merged = merged.merge(ce_col, on="datetime", how="left")
            else:
                merged["ce_price"] = None

            if pe_opts is not None and not pe_opts.empty:
                pe_col = pe_opts[["datetime", "pe_ltp"]].rename(columns={"pe_ltp": "pe_price"})
                merged = merged.merge(pe_col, on="datetime", how="left")
            else:
                merged["pe_price"] = None

            merged = merged.sort_values("datetime").reset_index(drop=True)

            # Downsample to ~1 per minute
            sampled = merged.iloc[::60].copy()

            # Ensure entry/exit ticks are included
            merged["time_str"] = merged["datetime"].dt.strftime("%H:%M:%S")

            entry_time_raw = trade.get("entry_time")
            if pd.notna(entry_time_raw):
                entry_ts = pd.Timestamp(entry_time_raw)
                entry_hm = entry_ts.strftime("%H:%M:%S")
                entry_rows = merged[merged["time_str"] >= entry_hm].head(1)
                sampled = pd.concat([sampled, entry_rows]).drop_duplicates(subset=["datetime"]).sort_values("datetime")
            else:
                entry_hm = "09:21:00"

            # Include CE exit time
            ce_exit_raw = trade.get("ce_exit_time")
            if pd.notna(ce_exit_raw):
                ce_exit_ts = pd.Timestamp(ce_exit_raw)
                ce_exit_hm = ce_exit_ts.strftime("%H:%M:%S")
                ce_exit_rows = merged[merged["time_str"] >= ce_exit_hm].head(1)
                sampled = pd.concat([sampled, ce_exit_rows]).drop_duplicates(subset=["datetime"]).sort_values("datetime")
            else:
                ce_exit_hm = "15:00:00"

            # Include PE exit time
            pe_exit_raw = trade.get("pe_exit_time")
            if pd.notna(pe_exit_raw):
                pe_exit_ts = pd.Timestamp(pe_exit_raw)
                pe_exit_hm = pe_exit_ts.strftime("%H:%M:%S")
                pe_exit_rows = merged[merged["time_str"] >= pe_exit_hm].head(1)
                sampled = pd.concat([sampled, pe_exit_rows]).drop_duplicates(subset=["datetime"]).sort_values("datetime")
            else:
                pe_exit_hm = "15:00:00"

            ticks = []
            for _, row in sampled.iterrows():
                tick = {
                    "time": row["datetime"].strftime("%H:%M"),
                    "spot": round(float(row["spot"]), 2),
                }
                tick["ce_price"] = round(float(row["ce_price"]), 2) if pd.notna(row.get("ce_price")) else None
                tick["pe_price"] = round(float(row["pe_price"]), 2) if pd.notna(row.get("pe_price")) else None
                ticks.append(tick)

            # Build per-leg info
            ce_sl = round(float(trade["ce_sl"]), 2) if pd.notna(trade.get("ce_sl")) else None
            pe_sl = round(float(trade["pe_sl"]), 2) if pd.notna(trade.get("pe_sl")) else None

            day_data = {
                "ticks": ticks,
                "entry_time": entry_hm[:5],
                "ce_strike": ce_strike,
                "pe_strike": pe_strike,
                "ce_sl": ce_sl,
                "pe_sl": pe_sl,
                "entry_ce": round(float(trade["entry_ce"]), 2) if pd.notna(trade.get("entry_ce")) else None,
                "entry_pe": round(float(trade["entry_pe"]), 2) if pd.notna(trade.get("entry_pe")) else None,
                "exit_ce": round(float(trade["exit_ce"]), 2) if pd.notna(trade.get("exit_ce")) else None,
                "exit_pe": round(float(trade["exit_pe"]), 2) if pd.notna(trade.get("exit_pe")) else None,
                "ce_exit_time": ce_exit_hm[:5],
                "pe_exit_time": pe_exit_hm[:5],
                "ce_exit_reason": trade.get("ce_exit_reason", "EOD"),
                "pe_exit_reason": trade.get("pe_exit_reason", "EOD"),
                "ce_pnl": round(float(trade["ce_pnl"]), 2) if pd.notna(trade.get("ce_pnl")) else None,
                "pe_pnl": round(float(trade["pe_pnl"]), 2) if pd.notna(trade.get("pe_pnl")) else None,
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
