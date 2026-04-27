"""Backtest runner — Day High OTM Sell v7 (v6 base + max_trades_per_day=3)."""

import argparse
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
from strategies.day_high_otm_sell_v7 import DayHighOTMSellV7, DayHighOTMSellV7Config


def run_single_day_engine(date_str: str, config: DayHighOTMSellV7Config) -> list[dict]:
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

    strategy = DayHighOTMSellV7(config=config)
    engine.add_strategy(strategy)

    try:
        engine.run()
        results = strategy.get_daily_results(date_str)
    finally:
        engine.dispose()

    return results


def run_backtest(last_n: int = 0, max_trades: int = 3, cost: float = 0.0) -> pd.DataFrame:
    days = list_trading_days()
    if last_n > 0:
        days = days[-last_n:]
    config = DayHighOTMSellV7Config(
        max_trades_per_day=max_trades,
        cost_per_round_trip_pts=cost,
    )
    all_trades = []

    for day in tqdm(days, desc=f"Backtesting day_high_otm_sell_v7"):
        day_trades = run_single_day_engine(day, config)
        all_trades.extend(day_trades)

    if not all_trades:
        return pd.DataFrame()

    trades_df = pd.DataFrame(all_trades)
    trades_df["date"] = pd.to_datetime(trades_df["date"])
    trades_df = trades_df.sort_values(["date", "trade_num"]).reset_index(drop=True)
    trades_df["cumulative_pnl"] = trades_df["pnl"].cumsum()
    return trades_df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--last-n", type=int, default=0, help="Run only last N trading days (0=all)")
    parser.add_argument("--max-trades", type=int, default=3, help="Max entries per day (default 3)")
    parser.add_argument("--cost", type=float, default=0.0, help="Cost per round trip (pts)")
    args = parser.parse_args()

    strategy_name = "day_high_otm_sell_v7"
    print(f"Running NautilusTrader backtest: {strategy_name}")
    print(f"  Max trades/day: {args.max_trades}")
    print(f"  Cost per round trip: {args.cost} pts")
    if args.last_n > 0:
        print(f"  (last {args.last_n} days only)")

    trades_df = run_backtest(args.last_n, args.max_trades, args.cost)
    if trades_df.empty:
        print("No trades.")
        return

    print(f"\nTotal trades: {len(trades_df)}")
    print(f"Total gross PnL: {trades_df['gross_pnl'].sum():.2f}")
    print(f"Total net PnL: {trades_df['pnl'].sum():.2f}")
    print(f"Win rate: {(trades_df['pnl'] > 0).mean() * 100:.1f}%")

    generate_report(strategy_name, trades_df)
    print(f"\nOutput saved to: output/{strategy_name}/")


if __name__ == "__main__":
    main()
