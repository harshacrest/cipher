"""Backtest runner for Vanilla ATM Straddle strategy."""

import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.objects import Money

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.data_utils import list_trading_days
from lib.nautilus_data import VENUE, INR, load_day_data
from lib.reporting import generate_report
from strategies.vanilla_straddle import VanillaStraddle, VanillaStraddleConfig


def run_single_day(date_str: str, config: VanillaStraddleConfig) -> list[dict] | None:
    """Run vanilla straddle on one day. Returns list of trades (can be multiple)."""
    try:
        instruments, ticks = load_day_data(
            date_str,
            entry_time=config.first_entry_time,
            strike_step=config.strike_step,
            strike_range=3,
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

    strategy = VanillaStraddle(config=config)
    engine.add_strategy(strategy)

    try:
        engine.run()
        result = strategy.get_daily_result(date_str)
    finally:
        engine.dispose()

    return result


def run_backtest(strategy_name: str = "vanilla_straddle") -> pd.DataFrame:
    """Run across all trading days."""
    days = list_trading_days()
    config = VanillaStraddleConfig()
    all_trades = []

    for day in tqdm(days, desc=f"Backtesting {strategy_name}"):
        result = run_single_day(day, config)
        if result:
            all_trades.extend(result)

    if not all_trades:
        print("No trades generated.")
        return pd.DataFrame()

    trades_df = pd.DataFrame(all_trades)
    trades_df["date"] = pd.to_datetime(trades_df["date"])
    trades_df = trades_df.sort_values(["date", "trade_num"]).reset_index(drop=True)
    trades_df["cumulative_pnl"] = trades_df["pnl"].cumsum()

    return trades_df


def main():
    strategy_name = "vanilla_straddle"
    print(f"Running backtest: {strategy_name}")

    trades_df = run_backtest(strategy_name)
    if trades_df.empty:
        print("No trades to report.")
        return

    print(f"\nTotal trades: {len(trades_df)}")
    print(f"Unique days: {trades_df['date'].nunique()}")
    print(f"Total PnL: {trades_df['pnl'].sum():.2f}")

    generate_report(strategy_name, trades_df)
    print(f"\nOutput saved to: output/{strategy_name}/")


if __name__ == "__main__":
    main()
