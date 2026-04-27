"""
Pre-process MultiLegDM backtest output into JSON for the frontend.
Reads xlsx/csv outputs and writes JSON to output/multi_leg_dm/api/.

Unlike per-day strategies, MultiLegDM has multiple trades per day. Equity curve
plots trade-by-trade cumulative PnL.
"""

import json
import math
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

STRATEGY = "multi_leg_dm"
OUTPUT_DIR = PROJECT_ROOT / "output" / STRATEGY
API_DIR = OUTPUT_DIR / "api"


def sanitize(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(x) for x in obj]
    return obj


def write_json(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(sanitize(data), f)


def process_performance() -> None:
    perf_path = OUTPUT_DIR / "performance.xlsx"
    if not perf_path.exists():
        print(f"  performance.xlsx not found at {perf_path}")
        return
    xls = pd.ExcelFile(perf_path)

    # Summary metrics -> metrics.json
    if "Summary" in xls.sheet_names:
        df = pd.read_excel(xls, "Summary")
        write_json(df.to_dict("records"), API_DIR / "metrics.json")

    if "Monthly" in xls.sheet_names:
        df = pd.read_excel(xls, "Monthly")
        write_json(df.to_dict("records"), API_DIR / "monthly.json")
    else:
        write_json([], API_DIR / "monthly.json")

    if "Yearly" in xls.sheet_names:
        df = pd.read_excel(xls, "Yearly")
        write_json(df.to_dict("records"), API_DIR / "yearly.json")
    else:
        write_json([], API_DIR / "yearly.json")

    if "DayOfWeek" in xls.sheet_names:
        df = pd.read_excel(xls, "DayOfWeek")
        write_json(df.to_dict("records"), API_DIR / "dow.json")
    else:
        write_json([], API_DIR / "dow.json")


def process_trades() -> None:
    trades_path = OUTPUT_DIR / "trades.xlsx"
    if not trades_path.exists():
        print(f"  trades.xlsx not found at {trades_path}")
        return

    df = pd.read_excel(trades_path)
    # Format date
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    # Round numeric columns
    for col in df.columns:
        if df[col].dtype == "float64":
            df[col] = df[col].round(2)

    write_json(df.to_dict("records"), API_DIR / "trades.json")
    print(f"  trades: {len(df)} rows")


def process_equity() -> None:
    eq_path = OUTPUT_DIR / "equity_curve.csv"
    if not eq_path.exists():
        print(f"  equity_curve.csv not found at {eq_path}")
        return

    df = pd.read_csv(eq_path)
    # For MultiLegDM, add trade_num if present in trades.xlsx
    trades_path = OUTPUT_DIR / "trades.xlsx"
    if trades_path.exists() and "trade_num" not in df.columns:
        trades_df = pd.read_excel(trades_path)
        if "trade_num" in trades_df.columns:
            df["trade_num"] = trades_df["trade_num"].values[: len(df)]

    write_json(df.to_dict("records"), API_DIR / "equity.json")
    print(f"  equity: {len(df)} rows")


def process_exit_reasons() -> None:
    """Summarize exit reason breakdown from trades.xlsx."""
    trades_path = OUTPUT_DIR / "trades.xlsx"
    if not trades_path.exists():
        return
    df = pd.read_excel(trades_path)
    if "exit_reason" not in df.columns:
        return

    breakdown = (
        df.groupby("exit_reason")
        .agg(
            count=("pnl_premium", "count"),
            total_pnl_premium=("pnl_premium", "sum"),
            avg_pnl_premium=("pnl_premium", "mean"),
            win_rate=("pnl_premium", lambda x: (x > 0).sum() / len(x) * 100),
        )
        .round(2)
        .reset_index()
    )
    write_json(breakdown.to_dict("records"), API_DIR / "exit_reasons.json")
    print(f"  exit_reasons: {len(breakdown)} categories")


def main() -> None:
    print(f"Preparing frontend data for {STRATEGY}...")
    API_DIR.mkdir(parents=True, exist_ok=True)
    process_performance()
    process_trades()
    process_equity()
    process_exit_reasons()
    # Empty dte.json (strategy doesn't segment by DTE yet)
    write_json([], API_DIR / "dte.json")
    print(f"Done. Output: {API_DIR}")


if __name__ == "__main__":
    main()
