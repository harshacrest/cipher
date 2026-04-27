"""Backtest runner for Index All Rounder strategy with dynamic expiry."""

import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.objects import Money

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.data_utils import list_trading_days, is_expiry_day
from lib.nautilus_data import VENUE, INR, load_day_data
from lib.reporting import generate_report
from strategies.index_allrounder import IndexAllRounder, IndexAllRounderConfig


def run_single_day(date_str: str, config: IndexAllRounderConfig) -> dict | None:
    """Run strategy on one day with dynamic expiry selection."""
    # Dynamic expiry: on expiry day use next week (index=1), else current week (index=0)
    expiry_idx = 1 if is_expiry_day(date_str) else 0

    try:
        instruments, ticks = load_day_data(
            date_str,
            entry_time=config.entry_time,
            strike_step=config.strike_step,
            strike_range=2,
            expiry_index=expiry_idx,
        )
    except Exception as e:
        return None

    if not ticks or len(instruments) < 2:
        return None

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

    strategy = IndexAllRounder(config=config)
    engine.add_strategy(strategy)

    try:
        engine.run()
        result = strategy.get_daily_result(date_str)
    finally:
        engine.dispose()

    return result


def run_backtest(strategy_name: str = "index_allrounder") -> pd.DataFrame:
    days = list_trading_days()
    config = IndexAllRounderConfig()
    trades = []

    for day in tqdm(days, desc=f"Backtesting {strategy_name}"):
        result = run_single_day(day, config)
        if result is not None:
            trades.append(result)

    if not trades:
        print("No trades generated.")
        return pd.DataFrame()

    trades_df = pd.DataFrame(trades)
    trades_df["date"] = pd.to_datetime(trades_df["date"])
    trades_df = trades_df.sort_values("date").reset_index(drop=True)
    trades_df["cumulative_pnl"] = trades_df["pnl"].cumsum()

    return trades_df


def main():
    strategy_name = "index_allrounder"
    print(f"Running backtest: {strategy_name}")

    trades_df = run_backtest(strategy_name)
    if trades_df.empty:
        print("No trades to report.")
        return

    print(f"\nTotal trades: {len(trades_df)}")
    print(f"Total PnL: {trades_df['pnl'].sum():.2f}")

    generate_report(strategy_name, trades_df)
    print(f"\nOutput saved to: output/{strategy_name}/")


if __name__ == "__main__":
    main()
