"""Pre-process vanilla straddle backtest output into JSON for the frontend."""

import json
import math
import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.data_utils import load_spot, load_options_at_strike

STRATEGY = "vanilla_straddle"
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


def write_json(data, filename: str):
    path = API_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(sanitize(data), f, separators=(",", ":"))


def process_performance():
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

    print("  Performance -> JSON")


def process_trades():
    df = pd.read_excel(OUTPUT_DIR / "trades.xlsx")
    write_json(df.to_dict("records"), "trades.json")
    print(f"  Trades ({len(df)} rows) -> JSON")


def process_equity():
    df = pd.read_csv(OUTPUT_DIR / "equity_curve.csv")
    write_json(df.to_dict("records"), "equity.json")
    print(f"  Equity ({len(df)} rows) -> JSON")


def process_intraday():
    """Per-day intraday data with spot + ATM strike straddle price."""
    trades = pd.read_excel(OUTPUT_DIR / "trades.xlsx")

    # Group by date — show all trades for each day
    available_dates = []
    DAYS_DIR.mkdir(parents=True, exist_ok=True)

    for day_str, day_trades in tqdm(trades.groupby("date"), desc="  Intraday"):
        try:
            first_trade = day_trades.iloc[0]
            atm_strike = int(first_trade["atm_strike"])

            spot_df = load_spot(day_str)
            spot_df = spot_df.sort_values("datetime").reset_index(drop=True)

            opts = load_options_at_strike(day_str, atm_strike)

            if opts is not None and not opts.empty:
                merged = spot_df.merge(opts, on="datetime", how="inner")
            else:
                merged = spot_df.copy()
                merged["straddle_price"] = None
                merged["ce_ltp"] = None
                merged["pe_ltp"] = None

            merged = merged.sort_values("datetime")
            sampled = merged.iloc[::60].copy()

            ticks = []
            for _, row in sampled.iterrows():
                tick = {"time": row["datetime"].strftime("%H:%M"), "spot": round(float(row["spot"]), 2)}
                if "straddle_price" in row and pd.notna(row.get("straddle_price")):
                    tick["straddle"] = round(float(row["straddle_price"]), 2)
                ticks.append(tick)

            # Build trade entries for this day
            day_trade_list = []
            for _, t in day_trades.iterrows():
                day_trade_list.append({
                    "trade_num": int(t["trade_num"]),
                    "atm_strike": int(t["atm_strike"]),
                    "entry_ce": round(float(t["entry_ce"]), 2),
                    "entry_pe": round(float(t["entry_pe"]), 2),
                    "exit_ce": round(float(t.get("exit_ce", 0)), 2),
                    "exit_pe": round(float(t.get("exit_pe", 0)), 2),
                    "combined_premium": round(float(t["combined_premium"]), 2),
                    "exit_trigger": round(float(t["exit_trigger"]), 2),
                    "pnl": round(float(t["pnl"]), 2),
                    "exit_reason": t.get("exit_reason", "EOD"),
                    "exit_time": t.get("exit_time", "15:10"),
                })

            day_data = {
                "ticks": ticks,
                "trades": day_trade_list,
                "dte": int(first_trade.get("dte", 0)),
                "day_pnl": round(float(day_trades["pnl"].sum()), 2),
            }

            with open(DAYS_DIR / f"{day_str}.json", "w") as f:
                json.dump(sanitize(day_data), f, separators=(",", ":"))

            available_dates.append(day_str)

        except Exception as e:
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
