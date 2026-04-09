"""
Pre-process day_high_otm_sell backtest output into JSON files for the frontend.
Each trade is a SINGLE LEG (CE or PE). Intraday data includes option price series per trade.
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

STRATEGY = "day_high_otm_sell"
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
    print("  Performance sheets -> JSON")


def process_trades():
    df = pd.read_excel(OUTPUT_DIR / "trades.xlsx")
    write_json(df.to_dict("records"), "trades.json")
    print(f"  Trades ({len(df)} rows) -> JSON")


def process_equity():
    df = pd.read_csv(OUTPUT_DIR / "equity_curve.csv")
    write_json(df.to_dict("records"), "equity.json")
    print(f"  Equity curve ({len(df)} rows) -> JSON")


def process_intraday():
    """Generate per-day intraday JSON with spot + option price series per trade."""
    trades = pd.read_excel(OUTPUT_DIR / "trades.xlsx")

    available_dates = []
    DAYS_DIR.mkdir(parents=True, exist_ok=True)

    grouped = trades.groupby("date")

    for day_str, day_trades in tqdm(grouped, desc="  Intraday JSON"):
        try:
            spot_df = load_spot(day_str)
            spot_df = spot_df.sort_values("datetime").reset_index(drop=True)

            merged = spot_df.copy()
            merged["time_str"] = merged["datetime"].dt.strftime("%H:%M:%S")

            # Downsample spot to ~1 per minute
            sampled = merged.iloc[::60].copy()

            # Collect unique strikes per side for option price loading
            ce_strikes = set()
            pe_strikes = set()
            for _, trade in day_trades.iterrows():
                strike = int(trade["strike"]) if pd.notna(trade.get("strike")) else None
                side = trade.get("side", "")
                if strike:
                    if side == "CE":
                        ce_strikes.add(strike)
                    elif side == "PE":
                        pe_strikes.add(strike)

            # Load option price data for all traded CE strikes
            ce_price_data = {}  # strike -> {time_str: price}
            for strike in ce_strikes:
                opts = load_options_at_strike(day_str, strike)
                if opts is not None and not opts.empty:
                    opts = opts.sort_values("datetime")
                    opts["time_str"] = opts["datetime"].dt.strftime("%H:%M")
                    # Downsample to 1-min
                    opts_sampled = opts.drop_duplicates(subset=["time_str"], keep="last")
                    ce_price_data[strike] = dict(zip(opts_sampled["time_str"], opts_sampled["ce_ltp"]))

            # Load option price data for all traded PE strikes
            pe_price_data = {}
            for strike in pe_strikes:
                opts = load_options_at_strike(day_str, strike)
                if opts is not None and not opts.empty:
                    opts = opts.sort_values("datetime")
                    opts["time_str"] = opts["datetime"].dt.strftime("%H:%M")
                    opts_sampled = opts.drop_duplicates(subset=["time_str"], keep="last")
                    pe_price_data[strike] = dict(zip(opts_sampled["time_str"], opts_sampled["pe_ltp"]))

            # Build per-leg trade entries with price series
            trade_entries = []
            for _, trade in day_trades.iterrows():
                entry_time_raw = trade.get("entry_time")
                exit_time_raw = trade.get("exit_time")
                entry_hm = None
                exit_hm = None

                if pd.notna(entry_time_raw):
                    entry_ts = pd.Timestamp(entry_time_raw)
                    entry_hm = entry_ts.strftime("%H:%M:%S")
                    entry_rows = merged[merged["time_str"] >= entry_hm].head(1)
                    sampled = pd.concat([sampled, entry_rows]).drop_duplicates(
                        subset=["datetime"]
                    ).sort_values("datetime")

                if pd.notna(exit_time_raw):
                    exit_ts = pd.Timestamp(exit_time_raw)
                    exit_hm = exit_ts.strftime("%H:%M:%S")
                    exit_rows = merged[merged["time_str"] >= exit_hm].head(1)
                    sampled = pd.concat([sampled, exit_rows]).drop_duplicates(
                        subset=["datetime"]
                    ).sort_values("datetime")

                side = trade.get("side", "?")
                strike = int(trade["strike"]) if pd.notna(trade.get("strike")) else 0

                # Get price series for this trade's strike
                if side == "CE" and strike in ce_price_data:
                    price_map = ce_price_data[strike]
                elif side == "PE" and strike in pe_price_data:
                    price_map = pe_price_data[strike]
                else:
                    price_map = {}

                # Build price ticks for this trade
                price_ticks = []
                for t_str, px in sorted(price_map.items()):
                    price_ticks.append({
                        "time": t_str,
                        "price": round(float(px), 2),
                    })

                trade_entries.append({
                    "trade_num": int(trade.get("trade_num", 1)),
                    "side": side,
                    "strike": strike,
                    "entry_time": entry_hm[:5] if entry_hm else None,
                    "exit_time": exit_hm[:5] if exit_hm else None,
                    "day_high": round(float(trade["day_high"]), 2),
                    "pullback_level": round(float(trade["pullback_level"]), 2),
                    "sl_level": round(float(trade["sl_level"]), 2),
                    "exit_reason": trade.get("exit_reason", "EOD"),
                    "entry_px": round(float(trade["entry_px"]), 2) if pd.notna(trade.get("entry_px")) else 0,
                    "exit_px": round(float(trade["exit_px"]), 2) if pd.notna(trade.get("exit_px")) else 0,
                    "pnl": round(float(trade["pnl"]), 2),
                    "price_ticks": price_ticks,
                })

            # Build spot ticks
            ticks = []
            for _, row in sampled.iterrows():
                ticks.append({
                    "time": row["datetime"].strftime("%H:%M"),
                    "spot": round(float(row["spot"]), 2),
                })

            total_pnl = round(sum(t["pnl"] for t in trade_entries), 2)

            day_data = {
                "ticks": ticks,
                "trades": trade_entries,
                "total_pnl": total_pnl,
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
