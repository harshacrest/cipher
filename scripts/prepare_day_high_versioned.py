"""
Prepare frontend JSON for v4/v5/v6 (same format as v3 prepare_day_high_data.py).
Usage: uv run python scripts/prepare_day_high_versioned.py <version_suffix>
       e.g. _v4, _v5, _v6
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


def sanitize(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj


def main():
    if len(sys.argv) < 2:
        print("Usage: prepare_day_high_versioned.py <suffix>")
        print("   e.g. _v4, _v5, _v6")
        sys.exit(1)

    suffix = sys.argv[1]
    strategy = f"day_high_otm_sell{suffix}"
    output_dir = PROJECT_ROOT / "output" / strategy
    api_dir = output_dir / "api"
    days_dir = api_dir / "days"

    def write_json(data, filename: str):
        path = api_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(sanitize(data), f, separators=(",", ":"))

    print(f"Preparing frontend data for: {strategy}")

    # Performance sheets
    xls = pd.ExcelFile(output_dir / "performance.xlsx")
    write_json(pd.read_excel(xls, "Summary").to_dict("records"), "metrics.json")
    write_json(pd.read_excel(xls, "Monthly").to_dict("records"), "monthly.json")
    write_json(pd.read_excel(xls, "Yearly").to_dict("records"), "yearly.json")
    write_json(pd.read_excel(xls, "DayOfWeek").to_dict("records"), "dow.json")
    if "ByDTE" in xls.sheet_names:
        write_json(pd.read_excel(xls, "ByDTE").to_dict("records"), "dte.json")
    else:
        write_json([], "dte.json")
    print("  Performance sheets -> JSON")

    # Trades
    trades = pd.read_excel(output_dir / "trades.xlsx")
    write_json(trades.to_dict("records"), "trades.json")
    print(f"  Trades ({len(trades)} rows) -> JSON")

    # Equity
    eq = pd.read_csv(output_dir / "equity_curve.csv")
    write_json(eq.to_dict("records"), "equity.json")
    print(f"  Equity ({len(eq)} rows) -> JSON")

    # Intraday per day
    days_dir.mkdir(parents=True, exist_ok=True)
    available_dates = []
    grouped = trades.groupby("date")

    for day_str, day_trades in tqdm(grouped, desc="  Intraday JSON"):
        try:
            spot_df = load_spot(day_str).sort_values("datetime").reset_index(drop=True)
            merged = spot_df.copy()
            merged["time_str"] = merged["datetime"].dt.strftime("%H:%M:%S")
            sampled = merged.iloc[::60].copy()

            ce_strikes, pe_strikes = set(), set()
            for _, t in day_trades.iterrows():
                s = int(t["strike"]) if pd.notna(t.get("strike")) else None
                side = t.get("side", "")
                if s:
                    (ce_strikes if side == "CE" else pe_strikes).add(s)

            ce_price_data, pe_price_data = {}, {}
            for strike in ce_strikes:
                opts = load_options_at_strike(day_str, strike)
                if opts is not None and not opts.empty:
                    opts = opts.sort_values("datetime")
                    opts["time_str"] = opts["datetime"].dt.strftime("%H:%M")
                    opts_s = opts.drop_duplicates(subset=["time_str"], keep="last")
                    ce_price_data[strike] = dict(zip(opts_s["time_str"], opts_s["ce_ltp"]))
            for strike in pe_strikes:
                opts = load_options_at_strike(day_str, strike)
                if opts is not None and not opts.empty:
                    opts = opts.sort_values("datetime")
                    opts["time_str"] = opts["datetime"].dt.strftime("%H:%M")
                    opts_s = opts.drop_duplicates(subset=["time_str"], keep="last")
                    pe_price_data[strike] = dict(zip(opts_s["time_str"], opts_s["pe_ltp"]))

            trade_entries = []
            for _, t in day_trades.iterrows():
                entry_raw = t.get("entry_time")
                exit_raw = t.get("exit_time")
                entry_hm = None
                exit_hm = None
                if pd.notna(entry_raw):
                    entry_hm = pd.Timestamp(entry_raw).strftime("%H:%M:%S")
                    entry_rows = merged[merged["time_str"] >= entry_hm].head(1)
                    sampled = pd.concat([sampled, entry_rows]).drop_duplicates(subset=["datetime"]).sort_values("datetime")
                if pd.notna(exit_raw):
                    exit_hm = pd.Timestamp(exit_raw).strftime("%H:%M:%S")
                    exit_rows = merged[merged["time_str"] >= exit_hm].head(1)
                    sampled = pd.concat([sampled, exit_rows]).drop_duplicates(subset=["datetime"]).sort_values("datetime")

                side = t.get("side", "?")
                strike = int(t["strike"]) if pd.notna(t.get("strike")) else 0
                price_map = (ce_price_data.get(strike) if side == "CE" else pe_price_data.get(strike)) or {}
                price_ticks = [{"time": k, "price": round(float(v), 2)} for k, v in sorted(price_map.items())]

                trade_entries.append({
                    "trade_num": int(t.get("trade_num", 1)),
                    "side": side,
                    "strike": strike,
                    "entry_time": entry_hm[:5] if entry_hm else None,
                    "exit_time": exit_hm[:5] if exit_hm else None,
                    "day_high": round(float(t["day_high"]), 2),
                    "pullback_level": round(float(t["pullback_level"]), 2),
                    "sl_level": round(float(t["sl_level"]), 2),
                    "exit_reason": t.get("exit_reason", "EOD"),
                    "entry_px": round(float(t["entry_px"]), 2) if pd.notna(t.get("entry_px")) else 0,
                    "exit_px": round(float(t["exit_px"]), 2) if pd.notna(t.get("exit_px")) else 0,
                    "pnl": round(float(t["pnl"]), 2),
                    "price_ticks": price_ticks,
                })

            ticks = [{"time": r["datetime"].strftime("%H:%M"), "spot": round(float(r["spot"]), 2)} for _, r in sampled.iterrows()]
            total_pnl = round(sum(t["pnl"] for t in trade_entries), 2)

            with open(days_dir / f"{day_str}.json", "w") as f:
                json.dump(sanitize({"ticks": ticks, "trades": trade_entries, "total_pnl": total_pnl}), f, separators=(",", ":"))
            available_dates.append(day_str)
        except Exception as e:
            print(f"    Skipped {day_str}: {e}")
            continue

    available_dates.sort()
    write_json(available_dates, "available_dates.json")
    print(f"  Intraday: {len(available_dates)} day files written")
    print(f"\nDone! Output in: {api_dir}")


if __name__ == "__main__":
    main()
