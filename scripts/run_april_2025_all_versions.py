"""Run April 2025 backtest on all 5 versions (v3, v4, v5, v6, v7) and compare."""

import sys
import time
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.objects import Money

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.data_utils import list_trading_days
from lib.nautilus_data import VENUE, INR, load_day_data
from lib.reporting import generate_report

# Import all strategies
from strategies.day_high_otm_sell import DayHighOTMSell, DayHighOTMSellConfig
from strategies.day_high_otm_sell_v4 import DayHighOTMSellV4, DayHighOTMSellV4Config
from strategies.day_high_otm_sell_v5 import DayHighOTMSellV5, DayHighOTMSellV5Config
from strategies.day_high_otm_sell_v6 import DayHighOTMSellV6, DayHighOTMSellV6Config
from strategies.day_high_otm_sell_v7 import DayHighOTMSellV7, DayHighOTMSellV7Config


def run_one_day(date_str, strategy_cls, config):
    try:
        instruments, ticks = load_day_data(
            date_str,
            entry_time=config.start_time,
            strike_step=config.strike_step,
            strike_range=5,
        )
    except Exception as e:
        print(f"  Data load failed {date_str}: {e}")
        return []

    if not ticks or len(instruments) < 2:
        return []

    engine = BacktestEngine(config=BacktestEngineConfig(
        logging=LoggingConfig(log_level="ERROR"),
    ))
    engine.add_venue(
        venue=VENUE,
        oms_type=OmsType.HEDGING,
        account_type=AccountType.MARGIN,
        starting_balances=[Money(10_000_000, INR)],
    )
    for inst in instruments:
        engine.add_instrument(inst)
    engine.add_data(ticks, sort=True)

    strategy = strategy_cls(config=config)
    engine.add_strategy(strategy)

    try:
        engine.run()
        results = strategy.get_daily_results(date_str)
    finally:
        engine.dispose()

    return results


def run_strategy(version, strategy_cls, config, days):
    all_trades = []
    for day in tqdm(days, desc=f"  {version}"):
        day_trades = run_one_day(day, strategy_cls, config)
        all_trades.extend(day_trades)

    if not all_trades:
        return pd.DataFrame()

    trades_df = pd.DataFrame(all_trades)
    trades_df["date"] = pd.to_datetime(trades_df["date"])
    trades_df = trades_df.sort_values(["date", "trade_num"]).reset_index(drop=True)
    trades_df["cumulative_pnl"] = trades_df["pnl"].cumsum()
    return trades_df


def main():
    # Filter to April 2025 only
    all_days = list_trading_days()
    april_days = [d for d in all_days if d.startswith("2025-04")]
    print(f"April 2025 trading days: {len(april_days)}")
    print(f"Date range: {april_days[0]} to {april_days[-1]}\n")

    runs = [
        ("v3", "day_high_otm_sell", DayHighOTMSell, DayHighOTMSellConfig()),
        ("v4", "day_high_otm_sell_v4", DayHighOTMSellV4, DayHighOTMSellV4Config(phantom_qty=1, real_qty=1)),
        ("v5", "day_high_otm_sell_v5", DayHighOTMSellV5, DayHighOTMSellV5Config()),
        ("v6", "day_high_otm_sell_v6", DayHighOTMSellV6, DayHighOTMSellV6Config()),
        ("v7", "day_high_otm_sell_v7", DayHighOTMSellV7, DayHighOTMSellV7Config()),
    ]

    summary = []
    for version, strat_name, cls, cfg in runs:
        print(f"\n=== Running {version} on April 2025 ===")
        t0 = time.time()
        df = run_strategy(version, cls, cfg, april_days)
        elapsed = time.time() - t0

        if df.empty:
            print(f"  {version}: no trades")
            summary.append({"version": version, "trades": 0, "pnl": 0.0, "elapsed_sec": elapsed})
            continue

        # Save output
        out_dir = PROJECT_ROOT / "output" / strat_name
        out_dir.mkdir(parents=True, exist_ok=True)
        # Save trades + equity CSV directly
        df.to_excel(out_dir / "trades.xlsx", index=False)
        df[["date", "pnl", "cumulative_pnl"]].to_csv(out_dir / "equity_curve.csv", index=False)

        # For v4 specifically, also track how many phantom trades were zeroed
        extra = ""
        if "is_phantom_sized" in df.columns:
            n_phantom = df["is_phantom_sized"].sum()
            extra = f" | {n_phantom} phantom zeroed"

        print(f"  {version}: {len(df)} trades, PnL={df['pnl'].sum():.2f}, elapsed={elapsed:.0f}s{extra}")
        summary.append({
            "version": version,
            "trades": len(df),
            "pnl": round(df["pnl"].sum(), 2),
            "wins": int((df["pnl"] > 0).sum()),
            "losses": int((df["pnl"] < 0).sum()),
            "win_rate_pct": round((df["pnl"] > 0).mean() * 100, 1),
            "elapsed_sec": round(elapsed, 0),
        })

    print("\n\n" + "=" * 70)
    print("APRIL 2025 — ALL VERSIONS SUMMARY")
    print("=" * 70)
    for s in summary:
        print(s)

    # Save summary as CSV
    pd.DataFrame(summary).to_csv("output/april_2025_all_versions_summary.csv", index=False)


if __name__ == "__main__":
    main()
