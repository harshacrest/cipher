"""VWAP SD Straddles backtest runner — per-day NautilusTrader runs with cross-day state.

Strategy aggregates 15 straddles (30 legs) and trades mean-reversion signals
against cumulative VWAP +/- SD bands. Cross-day state: previous day's last
lower band value is passed as `prev_day_lower_band` to next day's strategy.
"""

import os
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
from strategies.vwap_sd_straddles import VWAPSDStraddles, VWAPSDStraddlesConfig


def run_single_day_engine(
    date_str: str,
    prev_day_lower_band: float | None,
    base_config_kwargs: dict,
) -> tuple[list[dict], float | None]:
    """Run strategy on a single day; returns (trades, last_lower_band_of_day)."""
    try:
        # Wider strike_range for 15 strikes ATM ± 7 (needs 8 buffer in load)
        instruments, ticks = load_day_data(
            date_str,
            entry_time=base_config_kwargs.get("session_start_time", "09:15:00"),
            strike_step=base_config_kwargs.get("strike_step", 50),
            strike_range=9,  # ATM ± 7 strikes + 2 buffer
            resample="30s",  # ~30x faster than native 1s ticks
        )
    except Exception as e:
        print(f"  Data load failed {date_str}: {e}")
        return [], None

    if not ticks or len(instruments) < 2:
        return [], None

    engine = BacktestEngine(config=BacktestEngineConfig(
        logging=LoggingConfig(log_level="ERROR"),
    ))
    engine.add_venue(
        venue=VENUE,
        oms_type=OmsType.HEDGING,
        account_type=AccountType.MARGIN,
        starting_balances=[Money(100_000_000, INR)],
    )
    for inst in instruments:
        engine.add_instrument(inst)
    engine.add_data(ticks, sort=True)

    config = VWAPSDStraddlesConfig(
        **base_config_kwargs,
        prev_day_lower_band=prev_day_lower_band,
    )
    strategy = VWAPSDStraddles(config=config)
    engine.add_strategy(strategy)

    try:
        engine.run()
        trades = strategy.get_all_trades(date_str)
        last_lower = strategy.get_last_lower_band()
    finally:
        engine.dispose()

    return trades, last_lower


def run_backtest(
    strategy_name: str = "vwap_sd_straddles",
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    days = list_trading_days()
    if start_date:
        days = [d for d in days if d >= start_date]
    if end_date:
        days = [d for d in days if d <= end_date]

    base_config_kwargs = {
        "session_start_time": "09:15:00",
        "entry_window_start": "09:21:00",
        "entry_window_end": "15:00:00",
        "forced_exit_time": "15:12:00",
        "eod_time": "15:25:00",
        "strike_step": 50,
        "num_strikes_each_side": 7,
        "lot_size": 1,
        "num_lots": 1,
        "num_sd": 1.0,
        "sl_points_above_vwap": 500.0,
    }

    all_trades: list[dict] = []
    prev_day_lower: float | None = None

    for day in tqdm(days, desc=f"Backtesting {strategy_name}"):
        trades, last_lower = run_single_day_engine(day, prev_day_lower, base_config_kwargs)
        all_trades.extend(trades)
        # Update prev_day_lower for next day (only if this day produced a valid value)
        if last_lower is not None:
            prev_day_lower = last_lower

    if not all_trades:
        print("No trades generated.")
        return pd.DataFrame()

    trades_df = pd.DataFrame(all_trades)
    trades_df["date"] = pd.to_datetime(trades_df["date"])
    trades_df = trades_df.sort_values(["date", "trade_num"]).reset_index(drop=True)
    trades_df["cumulative_pnl"] = trades_df["pnl"].cumsum()
    return trades_df


def main():
    strategy_name = "vwap_sd_straddles"
    start = os.environ.get("BACKTEST_START")
    end = os.environ.get("BACKTEST_END")
    print(f"Running NautilusTrader backtest: {strategy_name}")
    if start or end:
        print(f"  Date range: {start or 'all'} to {end or 'all'}")

    trades_df = run_backtest(strategy_name, start_date=start, end_date=end)
    if trades_df.empty:
        print("No trades to report.")
        return

    n_days = trades_df["date"].dt.date.nunique()
    print(f"\nTotal trades: {len(trades_df)} across {n_days} days")
    print(f"Trades per day avg: {len(trades_df) / n_days:.2f}")
    print(f"Total PnL (premium): {trades_df['pnl'].sum():.2f}")

    print("\nExit reason breakdown:")
    print(trades_df["exit_reason"].value_counts().to_string())

    generate_report(strategy_name, trades_df)
    print(f"\nOutput saved to: output/{strategy_name}/")


if __name__ == "__main__":
    main()
