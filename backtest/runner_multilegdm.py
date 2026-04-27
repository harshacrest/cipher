"""MultiLegDM backtest runner — per-day NautilusTrader BacktestEngine runs.

Strategy sells 6 strangles (ATM + OTM_1..5) simultaneously per trade, with
multiple re-entry cycles per day.
"""

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


def run_single_day_engine(date_str: str, config: MultiLegDMConfig) -> list[dict]:
    """Run strategy on a single day; returns list of trades (can be 0..N)."""
    try:
        instruments, ticks = load_day_data(
            date_str,
            entry_time=config.entry_time,
            strike_step=config.strike_step,
            strike_range=8,  # ATM + 5 OTMs + 3 buffer strikes for spot drift
            resample="30s",  # ~30x faster than native 1s ticks
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
        starting_balances=[Money(100_000_000, INR)],  # 10 Cr (headroom for 96 lots)
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
    strategy_name: str = "multi_leg_dm",
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """Run strategy across trading days, aggregate all trades.

    Args:
        start_date: "YYYY-MM-DD" inclusive filter (default: all days)
        end_date: "YYYY-MM-DD" inclusive filter (default: all days)
    """
    days = list_trading_days()
    if start_date:
        days = [d for d in days if d >= start_date]
    if end_date:
        days = [d for d in days if d <= end_date]
    config = MultiLegDMConfig()
    all_trades: list[dict] = []

    for day in tqdm(days, desc=f"Backtesting {strategy_name}"):
        trades = run_single_day_engine(day, config)
        all_trades.extend(trades)

    if not all_trades:
        print("No trades generated.")
        return pd.DataFrame()

    # Flatten into DataFrame (exclude nested legs list for xlsx compatibility)
    rows = []
    legs_rows = []  # parallel structure for leg-level detail sheet
    for t in all_trades:
        row = {k: v for k, v in t.items() if k != "legs"}
        # reporting.py expects a "pnl" column in premium units
        row["pnl"] = t.get("pnl_points", 0.0)
        row["pnl_pct"] = 0.0  # not meaningful here; keep column present
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

    # Save leg-level detail as a separate file
    if legs_rows:
        legs_df = pd.DataFrame(legs_rows)
        out_dir = Path(__file__).parent.parent / "output" / strategy_name
        out_dir.mkdir(parents=True, exist_ok=True)
        legs_df.to_csv(out_dir / "legs.csv", index=False)

    return trades_df


def main():
    import os
    strategy_name = "multi_leg_dm"
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

    # Exit reason breakdown
    print("\nExit reason breakdown:")
    print(trades_df["exit_reason"].value_counts().to_string())

    generate_report(strategy_name, trades_df)
    print(f"\nOutput saved to: output/{strategy_name}/")


if __name__ == "__main__":
    main()
