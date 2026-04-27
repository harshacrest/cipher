"""Pre-process Index All Rounder backtest output into JSON for frontend."""

import json
import math
import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.data_utils import load_spot, load_options_at_strike

STRATEGY = "index_allrounder"
OUTPUT_DIR = PROJECT_ROOT / "output" / STRATEGY
API_DIR = OUTPUT_DIR / "api"
DAYS_DIR = API_DIR / "days"


def sanitize(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj


def write_json(data, filename):
    path = API_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(sanitize(data), f, separators=(",", ":"))


def process_performance():
    xls = pd.ExcelFile(OUTPUT_DIR / "performance.xlsx")
    for sheet, fname in [("Summary", "metrics.json"), ("Monthly", "monthly.json"),
                         ("Yearly", "yearly.json"), ("DayOfWeek", "dow.json")]:
        df = pd.read_excel(xls, sheet)
        write_json(df.to_dict("records"), fname)
    write_json([], "dte.json")
    print("  Performance -> JSON")


def process_trades():
    df = pd.read_excel(OUTPUT_DIR / "trades.xlsx")
    write_json(df.to_dict("records"), "trades.json")
    print(f"  Trades ({len(df)}) -> JSON")


def process_equity():
    df = pd.read_csv(OUTPUT_DIR / "equity_curve.csv")
    write_json(df.to_dict("records"), "equity.json")
    print(f"  Equity ({len(df)}) -> JSON")


def process_intraday():
    trades = pd.read_excel(OUTPUT_DIR / "trades.xlsx")
    available_dates = []
    DAYS_DIR.mkdir(parents=True, exist_ok=True)

    for _, trade in tqdm(trades.iterrows(), total=len(trades), desc="  Intraday"):
        day_str = trade["date"]
        atm_strike = int(trade["atm_strike"])

        try:
            spot_df = load_spot(day_str).sort_values("datetime")
            opts = load_options_at_strike(day_str, atm_strike)

            if opts is not None and not opts.empty:
                merged = spot_df.merge(opts, on="datetime", how="inner").sort_values("datetime")
            else:
                merged = spot_df.copy()
                merged["straddle_price"] = None

            sampled = merged.iloc[::60].copy()
            ticks = []
            for _, r in sampled.iterrows():
                tick = {"time": r["datetime"].strftime("%H:%M"), "spot": round(float(r["spot"]), 2)}
                if "straddle_price" in r and pd.notna(r.get("straddle_price")):
                    tick["straddle"] = round(float(r["straddle_price"]), 2)
                if "ce_ltp" in r and pd.notna(r.get("ce_ltp")):
                    tick["ce_price"] = round(float(r["ce_ltp"]), 2)
                if "pe_ltp" in r and pd.notna(r.get("pe_ltp")):
                    tick["pe_price"] = round(float(r["pe_ltp"]), 2)
                ticks.append(tick)

            day_data = {
                "ticks": ticks,
                "atm_strike": atm_strike,
                "entry_ce": round(float(trade["entry_ce"]), 2),
                "entry_pe": round(float(trade["entry_pe"]), 2),
                "exit_ce": round(float(trade["exit_ce"]), 2),
                "exit_pe": round(float(trade["exit_pe"]), 2),
                "low_ce": round(float(trade["low_ce"]), 2),
                "low_pe": round(float(trade["low_pe"]), 2),
                "ce_exit_reason": trade.get("ce_exit_reason", "EOD"),
                "pe_exit_reason": trade.get("pe_exit_reason", "EOD"),
                "pnl": round(float(trade["pnl"]), 2),
            }

            with open(DAYS_DIR / f"{day_str}.json", "w") as f:
                json.dump(sanitize(day_data), f, separators=(",", ":"))
            available_dates.append(day_str)

        except Exception:
            continue

    available_dates.sort()
    write_json(available_dates, "available_dates.json")
    print(f"  Intraday: {len(available_dates)} days")


def main():
    print(f"Preparing frontend data: {STRATEGY}")
    process_performance()
    process_trades()
    process_equity()
    process_intraday()
    print(f"\nDone! {API_DIR}")


if __name__ == "__main__":
    main()
