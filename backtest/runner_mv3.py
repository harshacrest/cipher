"""Backtest runner for MV3 V33 Credit Spread strategy."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.objects import Money

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.data_utils import DATA_ROOT, list_trading_days, get_nearest_expiry_file
from lib.nautilus_data import VENUE, INR, load_spot_ticks, load_options_for_strikes
from lib.reporting import generate_report
from strategies.mv3_credit_spread import MV3CreditSpread, MV3CreditSpreadConfig


# ---------------------------------------------------------------------------
# Pre-computation helpers
# ---------------------------------------------------------------------------

def _find_hedge_strike(
    opts_df: pd.DataFrame,
    opt_type: str,
    max_premium: float,
    sold_strike: int,
    below: bool,
) -> int | None:
    """Find closest-to-ATM strike with avg premium <= max_premium near 9:25."""
    base_mask = (
        (opts_df["option_type"] == opt_type)
        & (opts_df["ltp"] > 0)
        & (opts_df["ltp"] <= max_premium)
    )
    if below:
        base_mask = base_mask & (opts_df["strike_price"] < sold_strike)
    else:
        base_mask = base_mask & (opts_df["strike_price"] > sold_strike)

    # Try narrow window first, then widen
    for t_start, t_end in [("09:25:00", "09:26:00"), ("09:20:00", "09:35:00")]:
        time_mask = (opts_df["time_str"] >= t_start) & (opts_df["time_str"] < t_end)
        subset = opts_df[base_mask & time_mask]
        if subset.empty:
            continue

        avg_premium = subset.groupby("strike_price")["ltp"].mean()
        valid = avg_premium[avg_premium <= max_premium]
        if valid.empty:
            continue

        # Closest to ATM: highest strike for PE (below), lowest for CE (above)
        return int(valid.index.max() if below else valid.index.min())

    return None


def _get_opening_range(range_df: pd.DataFrame, strike: int, opt_type: str) -> dict | None:
    """Get 9:15-9:19 high/low for a specific strike+type."""
    subset = range_df[
        (range_df["strike_price"] == strike) & (range_df["option_type"] == opt_type)
    ]
    ltp = subset["ltp"].dropna()
    ltp = ltp[ltp > 0]
    if ltp.empty:
        return None
    return {"high": float(ltp.max()), "low": float(ltp.min())}


def find_mv3_params(
    date_str: str,
    strike_step: int = 50,
    hedge_max_premium: float = 10.0,
) -> dict | None:
    """Pre-compute strikes, hedge legs, and opening ranges from raw parquet data."""
    spot_path = DATA_ROOT / date_str / "Index" / "Cleaned_Spot.parquet"
    if not spot_path.exists():
        return None

    spot_df = pd.read_parquet(spot_path, columns=["datetime", "ltp"])
    spot_df["time_str"] = spot_df["datetime"].dt.strftime("%H:%M:%S")
    rows = spot_df[spot_df["time_str"] >= "09:15:00"]
    if rows.empty:
        return None
    spot_val = float(rows.iloc[0]["ltp"])

    atm = int(round(spot_val / strike_step) * strike_step)
    sold_pe_strike = atm + 2 * strike_step   # ATM+2 (higher strike PE = slightly ITM)
    sold_ce_strike = atm - 2 * strike_step   # ATM-2 (lower strike CE = slightly ITM)

    opts_path = get_nearest_expiry_file(date_str)
    if opts_path is None:
        return None
    expiry_str = opts_path.stem.split("_")[1]

    opts_df = pd.read_parquet(opts_path, columns=[
        "datetime", "option_type", "strike_price", "ltp",
    ])
    if opts_df["option_type"].dtype == object:
        opts_df["option_type"] = opts_df["option_type"].apply(
            lambda x: x.decode() if isinstance(x, bytes) else x
        )
    opts_df["time_str"] = opts_df["datetime"].dt.strftime("%H:%M:%S")

    # Find hedge strikes
    hedge_pe = _find_hedge_strike(opts_df, "PE", hedge_max_premium, sold_pe_strike, below=True)
    hedge_ce = _find_hedge_strike(opts_df, "CE", hedge_max_premium, sold_ce_strike, below=False)

    if hedge_pe is None and hedge_ce is None:
        return None

    # Opening ranges (9:15-9:19)
    range_df = opts_df[
        (opts_df["time_str"] >= "09:15:00") & (opts_df["time_str"] < "09:20:00")
    ]

    sold_pe_range = _get_opening_range(range_df, sold_pe_strike, "PE")
    sold_ce_range = _get_opening_range(range_df, sold_ce_strike, "CE")
    hedge_pe_range = _get_opening_range(range_df, hedge_pe, "PE") if hedge_pe else None
    hedge_ce_range = _get_opening_range(range_df, hedge_ce, "CE") if hedge_ce else None

    pe_ok = hedge_pe is not None and sold_pe_range is not None and hedge_pe_range is not None
    ce_ok = hedge_ce is not None and sold_ce_range is not None and hedge_ce_range is not None

    if not pe_ok and not ce_ok:
        return None

    return {
        "expiry_str": expiry_str,
        "sold_pe_strike": sold_pe_strike,
        "sold_ce_strike": sold_ce_strike,
        "hedge_pe_strike": hedge_pe or 0,
        "hedge_ce_strike": hedge_ce or 0,
        "sold_pe_range": sold_pe_range,
        "sold_ce_range": sold_ce_range,
        "hedge_pe_range": hedge_pe_range,
        "hedge_ce_range": hedge_ce_range,
        "pe_set_active": pe_ok,
        "ce_set_active": ce_ok,
    }


# ---------------------------------------------------------------------------
# Single-day engine
# ---------------------------------------------------------------------------

def run_single_day(date_str: str, strike_step: int = 50, hedge_max_premium: float = 10.0) -> list[dict]:
    """Run MV3 on a single day. Returns list of trade dicts (0-2 per day)."""
    params = find_mv3_params(date_str, strike_step, hedge_max_premium)
    if params is None:
        return []

    # Build list of strikes to load
    strikes_to_load: list[tuple[int, str]] = []
    if params["pe_set_active"]:
        strikes_to_load.append((params["sold_pe_strike"], "PE"))
        strikes_to_load.append((params["hedge_pe_strike"], "PE"))
    if params["ce_set_active"]:
        strikes_to_load.append((params["sold_ce_strike"], "CE"))
        strikes_to_load.append((params["hedge_ce_strike"], "CE"))

    if not strikes_to_load:
        return []

    # Load data
    try:
        spot_inst, spot_ticks = load_spot_ticks(date_str)
        opt_insts, opt_ticks = load_options_for_strikes(date_str, strikes_to_load)
    except Exception as e:
        print(f"  Data load failed {date_str}: {e}")
        return []

    if not opt_ticks:
        return []

    instruments = [spot_inst] + opt_insts
    all_ticks = spot_ticks + opt_ticks

    # Build config
    cfg = MV3CreditSpreadConfig(
        sold_pe_strike=params["sold_pe_strike"],
        sold_ce_strike=params["sold_ce_strike"],
        hedge_pe_strike=params["hedge_pe_strike"],
        hedge_ce_strike=params["hedge_ce_strike"],
        sold_pe_range_low=params["sold_pe_range"]["low"] if params["sold_pe_range"] else 0.0,
        sold_ce_range_low=params["sold_ce_range"]["low"] if params["sold_ce_range"] else 0.0,
        hedge_pe_range_high=params["hedge_pe_range"]["high"] if params["hedge_pe_range"] else 0.0,
        hedge_pe_range_low=params["hedge_pe_range"]["low"] if params["hedge_pe_range"] else 0.0,
        hedge_ce_range_high=params["hedge_ce_range"]["high"] if params["hedge_ce_range"] else 0.0,
        hedge_ce_range_low=params["hedge_ce_range"]["low"] if params["hedge_ce_range"] else 0.0,
        pe_set_active=params["pe_set_active"],
        ce_set_active=params["ce_set_active"],
        expiry_str=params["expiry_str"],
    )

    # Run engine
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
    engine.add_data(all_ticks, sort=True)

    strategy = MV3CreditSpread(config=cfg)
    engine.add_strategy(strategy)

    try:
        engine.run()
        results = strategy.get_daily_results(date_str)
    finally:
        engine.dispose()

    return results


# ---------------------------------------------------------------------------
# Full backtest
# ---------------------------------------------------------------------------

def run_backtest(strategy_name: str = "mv3_credit_spread") -> pd.DataFrame:
    days = list_trading_days()
    trades: list[dict] = []

    for day in tqdm(days, desc=f"Backtesting {strategy_name}"):
        day_trades = run_single_day(day)
        trades.extend(day_trades)

    if not trades:
        print("No trades generated.")
        return pd.DataFrame()

    df = pd.DataFrame(trades)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["cumulative_pnl"] = df["pnl"].cumsum()
    return df


def main():
    strategy_name = "mv3_credit_spread"
    print(f"Running MV3 V33 Credit Spread backtest")

    trades_df = run_backtest(strategy_name)
    if trades_df.empty:
        print("No trades to report.")
        return

    print(f"\nTotal trades: {len(trades_df)}")
    print(f"Total PnL (premium): {trades_df['pnl'].sum():.2f}")

    # Per-set breakdown
    for side in trades_df["set"].unique():
        subset = trades_df[trades_df["set"] == side]
        print(f"\n  {side} Set: {len(subset)} trades, PnL={subset['pnl'].sum():.2f} pts")

    generate_report(strategy_name, trades_df)
    print(f"\nOutput saved to: output/{strategy_name}/")


if __name__ == "__main__":
    main()
