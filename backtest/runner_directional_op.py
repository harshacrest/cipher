"""Backtest runner — Directional OP Selling (Credit Spreads)."""

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
from strategies.directional_op_sell import DirectionalOPSell, DirectionalOPSellConfig


def run_single_day_engine(date_str: str, config: DirectionalOPSellConfig) -> dict | None:
    """Run strategy on a single day using BacktestEngine."""
    try:
        instruments, ticks = load_day_data(
            date_str,
            entry_time="09:17:00",
            strike_step=config.strike_step,
            strike_range=12,  # wider range for premium-based strike selection
        )
    except Exception as e:
        print(f"  Data load failed {date_str}: {e}")
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

    strategy = DirectionalOPSell(config=config)
    engine.add_strategy(strategy)

    try:
        engine.run()
        result = strategy.get_daily_result(date_str)
    finally:
        engine.dispose()

    return result


def run_backtest(strategy_name: str = "directional_op_sell") -> pd.DataFrame:
    """Run strategy across all available trading days."""
    days = list_trading_days()
    config = DirectionalOPSellConfig()
    trades = []

    for day in tqdm(days, desc=f"Backtesting {strategy_name}"):
        result = run_single_day_engine(day, config)
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
    strategy_name = "directional_op_sell"
    print(f"Running NautilusTrader backtest: {strategy_name}")

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
