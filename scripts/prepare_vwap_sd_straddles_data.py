"""Pre-process VWAP SD Straddles backtest output into JSON for the frontend."""

import json
import math
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

STRATEGY = "vwap_sd_straddles"
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
    p = OUTPUT_DIR / "performance.xlsx"
    if not p.exists():
        print(f"  performance.xlsx not found")
        return
    xls = pd.ExcelFile(p)
    for sheet, fname in [
        ("Summary", "metrics.json"),
        ("Monthly", "monthly.json"),
        ("Yearly", "yearly.json"),
        ("DayOfWeek", "dow.json"),
    ]:
        if sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet)
            write_json(df.to_dict("records"), API_DIR / fname)
        else:
            write_json([], API_DIR / fname)
    write_json([], API_DIR / "dte.json")


def process_trades() -> None:
    p = OUTPUT_DIR / "trades.xlsx"
    if not p.exists():
        return
    df = pd.read_excel(p)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    for col in df.columns:
        if df[col].dtype == "float64":
            df[col] = df[col].round(2)
    write_json(df.to_dict("records"), API_DIR / "trades.json")
    print(f"  trades: {len(df)} rows")


def process_equity() -> None:
    p = OUTPUT_DIR / "equity_curve.csv"
    if not p.exists():
        return
    df = pd.read_csv(p)
    write_json(df.to_dict("records"), API_DIR / "equity.json")
    print(f"  equity: {len(df)} rows")


def process_exit_reasons() -> None:
    p = OUTPUT_DIR / "trades.xlsx"
    if not p.exists():
        return
    df = pd.read_excel(p)
    if "exit_reason" not in df.columns:
        return
    br = (
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
    write_json(br.to_dict("records"), API_DIR / "exit_reasons.json")
    print(f"  exit_reasons: {len(br)} categories")


def main() -> None:
    API_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Preparing frontend data for {STRATEGY}...")
    process_performance()
    process_trades()
    process_equity()
    process_exit_reasons()
    print(f"Done. Output: {API_DIR}")


if __name__ == "__main__":
    main()
