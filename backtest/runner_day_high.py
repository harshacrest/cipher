"""Backtest runner — Day High OTM Sell strategy, per-day NautilusTrader BacktestEngine runs."""

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
from strategies.day_high_otm_sell import DayHighOTMSell, DayHighOTMSellConfig


def run_single_day_engine(date_str: str, config: DayHighOTMSellConfig) -> list[dict]:
    """Run strategy on a single day. Returns list of trades (possibly multiple per day)."""
    try:
        instruments, ticks = load_day_data(
            date_str,
            entry_time=config.start_time,
            strike_step=config.strike_step,
            strike_range=5,  # wider range: re-entries can hit different strikes
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

    strategy = DayHighOTMSell(config=config)
    engine.add_strategy(strategy)

    try:
        engine.run()
        results = strategy.get_daily_results(date_str)
    finally:
        engine.dispose()

    return results


def run_backtest(strategy_name: str = "day_high_otm_sell", last_n: int = 0) -> pd.DataFrame:
    """Run strategy across trading days. last_n=0 means all days."""
    days = list_trading_days()
    if last_n > 0:
        days = days[-last_n:]
    config = DayHighOTMSellConfig()
    all_trades = []

    for day in tqdm(days, desc=f"Backtesting {strategy_name}"):
        day_trades = run_single_day_engine(day, config)
        all_trades.extend(day_trades)

    if not all_trades:
        print("No trades generated.")
        return pd.DataFrame()

    trades_df = pd.DataFrame(all_trades)
    trades_df["date"] = pd.to_datetime(trades_df["date"])
    trades_df = trades_df.sort_values(["date", "trade_num"]).reset_index(drop=True)
    trades_df["cumulative_pnl"] = trades_df["pnl"].cumsum()

    return trades_df


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--last-n", type=int, default=0, help="Run only last N trading days (0=all)")
    args = parser.parse_args()

    strategy_name = "day_high_otm_sell"
    print(f"Running NautilusTrader backtest: {strategy_name}")
    if args.last_n > 0:
        print(f"  (last {args.last_n} trading days only)")

    trades_df = run_backtest(strategy_name, last_n=args.last_n)
    if trades_df.empty:
        print("No trades to report.")
        return
    print(f"\nTotal trades: {len(trades_df)}")
    print(f"Total PnL: {trades_df['pnl'].sum():.2f}")

    generate_report(strategy_name, trades_df)
    print(f"\nOutput saved to: output/{strategy_name}/")


if __name__ == "__main__":
    main()
