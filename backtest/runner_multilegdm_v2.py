"""MultiLegDM v2 — tighter SL profile.

Same strategy class as v1 (`strategies/multi_leg_dm.MultiLegDM`), but with
tighter risk caps:

  trade_sl_premium       :  -155 pts  (v1: -500)
  daily_sl_threshold     :  -550 pts  (v1: -1500)

All other params (entry/exit times, strike step, num_strangles, lot/qty,
DTE-aware band divisors, cooldown, budget gate) are unchanged.

Output goes to output/multi_leg_dm_v2/ to keep v1 results untouched.
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
from strategies.multi_leg_dm import MultiLegDM, MultiLegDMConfig


STRATEGY_NAME = "multi_leg_dm_v2"


def make_v2_config() -> MultiLegDMConfig:
    """v2 config with tighter SL caps. Everything else inherits v1 defaults."""
    return MultiLegDMConfig(
        trade_sl_premium=-155.0,
        daily_sl_threshold_premium=-550.0,
    )


def run_single_day_engine(date_str: str, config: MultiLegDMConfig) -> list[dict]:
    try:
        instruments, ticks = load_day_data(
            date_str,
            entry_time=config.entry_time,
            strike_step=config.strike_step,
            strike_range=8,
            resample="30s",
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
        starting_balances=[Money(100_000_000, INR)],
    )

    for inst in instruments:
        engine.add_instrument(inst)

    engine.add_data(ticks, sort=True)

    strategy = MultiLegDM(config=config)
    engine.add_strategy(strategy)

    try:
        engine.run()
        trades = strategy.get_all_trades(date_str)
    finally:
        engine.dispose()

    return trades


def run_backtest(
    strategy_name: str = STRATEGY_NAME,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    days = list_trading_days()
    if start_date:
        days = [d for d in days if d >= start_date]
    if end_date:
        days = [d for d in days if d <= end_date]

    config = make_v2_config()
    print(
        f"v2 config: trade_sl={config.trade_sl_premium}, "
        f"daily_sl={config.daily_sl_threshold_premium}, "
        f"band_far={config.spot_band_x_far_dte}, band_near={config.spot_band_x_near_dte}"
    )

    all_trades: list[dict] = []
    for day in tqdm(days, desc=f"Backtesting {strategy_name}"):
        trades = run_single_day_engine(day, config)
        all_trades.extend(trades)

    if not all_trades:
        print("No trades generated.")
        return pd.DataFrame()

    rows = []
    legs_rows = []
    for t in all_trades:
        row = {k: v for k, v in t.items() if k != "legs"}
        row["pnl"] = t.get("pnl_points", 0.0)
        row["pnl_pct"] = 0.0
        rows.append(row)
        for leg_idx, leg in enumerate(t.get("legs", [])):
            legs_rows.append({
                "date": t["date"],
                "trade_num": t["trade_num"],
                "leg_idx": leg_idx,
                **leg,
            })

    trades_df = pd.DataFrame(rows)
    trades_df["date"] = pd.to_datetime(trades_df["date"])
    trades_df = trades_df.sort_values(["date", "trade_num"]).reset_index(drop=True)
    trades_df["cumulative_pnl"] = trades_df["pnl"].cumsum()

    if legs_rows:
        legs_df = pd.DataFrame(legs_rows)
        out_dir = Path(__file__).parent.parent / "output" / strategy_name
        out_dir.mkdir(parents=True, exist_ok=True)
        legs_df.to_csv(out_dir / "legs.csv", index=False)

    return trades_df


def main():
    start = os.environ.get("BACKTEST_START")
    end = os.environ.get("BACKTEST_END")
    print(f"Running NautilusTrader backtest: {STRATEGY_NAME}")
    if start or end:
        print(f"  Date range: {start or 'all'} to {end or 'all'}")

    trades_df = run_backtest(STRATEGY_NAME, start_date=start, end_date=end)
    if trades_df.empty:
        print("No trades to report.")
        return

    n_days = trades_df["date"].dt.date.nunique()
    print(f"\nTotal trades: {len(trades_df)} across {n_days} days")
    print(f"Trades per day avg: {len(trades_df) / n_days:.2f}")
    print(f"Total PnL (premium): {trades_df['pnl'].sum():.2f}")

    print("\nExit reason breakdown:")
    print(trades_df["exit_reason"].value_counts().to_string())

    generate_report(STRATEGY_NAME, trades_df)
    print(f"\nOutput saved to: output/{STRATEGY_NAME}/")


if __name__ == "__main__":
    main()
