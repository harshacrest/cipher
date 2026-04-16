"""Convert parquet market data to NautilusTrader instruments and QuoteTicks."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import AssetClass, OptionKind
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import IndexInstrument, OptionContract
from nautilus_trader.model.objects import Currency, Price, Quantity

from lib.data_utils import DATA_ROOT, get_nearest_expiry_file
VENUE = Venue("NSE")
INR = Currency.from_str("INR")
SPOT_ID = InstrumentId(Symbol("NIFTY-SPOT"), VENUE)

_IST_OFFSET_MS = (5 * 3600 + 30 * 60) * 1000
_PRICE_PREC = 2
_SIZE_PREC = 0


def _ist_to_utc_ns(dt_series: pd.Series) -> np.ndarray:
    """Convert IST-labeled-as-UTC datetime series to true UTC nanoseconds."""
    ms_epoch = dt_series.astype("int64")
    true_utc_ms = ms_epoch - _IST_OFFSET_MS
    return (true_utc_ms * 1_000_000).values.astype(np.uint64)


def make_alert_time_ns(date_str: str, time_str: str) -> int:
    """Create true-UTC nanosecond timestamp for a given IST date+time."""
    ist_dt = pd.Timestamp(f"{date_str} {time_str}", tz="Asia/Kolkata")
    return int(ist_dt.tz_convert("UTC").value)


def make_spot_instrument() -> IndexInstrument:
    return IndexInstrument(
        instrument_id=SPOT_ID,
        raw_symbol=Symbol("NIFTY-SPOT"),
        currency=INR,
        price_precision=_PRICE_PREC,
        price_increment=Price.from_str("0.05"),
        size_precision=_SIZE_PREC,
        size_increment=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )


def make_option_instrument(
    strike: int,
    option_kind: OptionKind,
    expiry_str: str,
    activation_ns: int,
    expiration_ns: int,
) -> OptionContract:
    kind_str = "CE" if option_kind == OptionKind.CALL else "PE"
    sym = f"NIFTY-{strike}-{kind_str}-{expiry_str}"
    return OptionContract(
        instrument_id=InstrumentId(Symbol(sym), VENUE),
        raw_symbol=Symbol(sym),
        asset_class=AssetClass.INDEX,
        currency=INR,
        price_precision=_PRICE_PREC,
        price_increment=Price.from_str("0.05"),
        multiplier=Quantity.from_int(25),
        lot_size=Quantity.from_int(25),
        underlying="NIFTY",
        option_kind=option_kind,
        strike_price=Price.from_str(f"{strike}.00"),
        activation_ns=activation_ns,
        expiration_ns=expiration_ns,
        ts_event=0,
        ts_init=0,
    )


def _get_approximate_spot_at_entry(date_str: str, entry_time: str = "09:21:00") -> float | None:
    """Quick read of spot at entry time for ATM strike pre-filtering."""
    path = DATA_ROOT / date_str / "Index" / "Cleaned_Spot.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path, columns=["datetime", "ltp"])
    df["time_str"] = df["datetime"].dt.strftime("%H:%M:%S")
    mask = df["time_str"] >= entry_time
    if not mask.any():
        return None
    return float(df.loc[mask].iloc[0]["ltp"])


def _build_ticks_batch(
    instrument_id: InstrumentId,
    bid_prices: np.ndarray,
    ask_prices: np.ndarray,
    bid_sizes: np.ndarray,
    ask_sizes: np.ndarray,
    ts_ns: np.ndarray,
) -> list[QuoteTick]:
    """Use Nautilus batch API for fast tick creation from arrays."""
    bid_raw = np.round(bid_prices, _PRICE_PREC).astype(np.float64)
    ask_raw = np.round(ask_prices, _PRICE_PREC).astype(np.float64)
    bid_sz_raw = bid_sizes.astype(np.float64)
    ask_sz_raw = ask_sizes.astype(np.float64)
    ts = ts_ns.astype(np.uint64)

    return QuoteTick.from_raw_arrays_to_list(
        instrument_id=instrument_id,
        price_prec=_PRICE_PREC,
        size_prec=_SIZE_PREC,
        bid_prices_raw=bid_raw,
        ask_prices_raw=ask_raw,
        bid_sizes_raw=bid_sz_raw,
        ask_sizes_raw=ask_sz_raw,
        ts_events=ts,
        ts_inits=ts,
    )


def load_spot_ticks(date_str: str) -> tuple[IndexInstrument, list[QuoteTick]]:
    """Load spot data as IndexInstrument + QuoteTicks (batch API)."""
    path = DATA_ROOT / date_str / "Index" / "Cleaned_Spot.parquet"
    df = pd.read_parquet(path, columns=["datetime", "ltp"])
    df = df.sort_values("datetime").reset_index(drop=True)
    df = df.drop_duplicates(subset=["datetime"], keep="first")

    # Filter valid
    df = df[df["ltp"] > 0].dropna(subset=["ltp"]).reset_index(drop=True)

    ts_arr = _ist_to_utc_ns(df["datetime"])
    prices = df["ltp"].values.astype(np.float64)
    ones = np.ones(len(df), dtype=np.uint64)

    instrument = make_spot_instrument()
    ticks = _build_ticks_batch(SPOT_ID, prices, prices, ones, ones, ts_arr)

    return instrument, ticks


def load_option_ticks(
    date_str: str,
    atm_estimate: float | None = None,
    strike_step: int = 50,
    strike_range: int = 2,
) -> tuple[list[OptionContract], list[QuoteTick]]:
    """Load option ticks for nearest expiry using batch API. Filters near ATM."""
    path = get_nearest_expiry_file(date_str)
    if path is None:
        return [], []

    expiry_str = path.stem.split("_")[1]
    expiry_date = f"{expiry_str[:4]}-{expiry_str[4:6]}-{expiry_str[6:8]}"
    expiration_ns = make_alert_time_ns(expiry_date, "15:30:00")
    activation_ns = make_alert_time_ns(date_str, "09:15:00")

    df = pd.read_parquet(path, columns=[
        "datetime", "option_type", "strike_price", "ltp", "buy_price", "sell_price",
        "buy_qty", "sell_qty",
    ])

    # Decode option_type bytes
    if df["option_type"].dtype == object:
        df["option_type"] = df["option_type"].apply(
            lambda x: x.decode() if isinstance(x, bytes) else x
        )

    # Filter to strikes near ATM
    if atm_estimate is not None and atm_estimate > 0:
        atm_strike = int(round(atm_estimate / strike_step) * strike_step)
        low = atm_strike - strike_range * strike_step
        high = atm_strike + strike_range * strike_step
        df = df[(df["strike_price"] >= low) & (df["strike_price"] <= high)]

    if df.empty:
        return [], []

    df = df.sort_values("datetime").reset_index(drop=True)
    df = df.drop_duplicates(subset=["datetime", "strike_price", "option_type"], keep="first")
    df = df.reset_index(drop=True)

    # Fix bid/ask: use ltp as fallback, ensure ask >= bid
    bid = df["buy_price"].values.astype(np.float64)
    ask = df["sell_price"].values.astype(np.float64)
    ltp = df["ltp"].values.astype(np.float64)

    bad_bid = (bid <= 0) | np.isnan(bid)
    bad_ask = (ask <= 0) | np.isnan(ask)
    bid[bad_bid] = ltp[bad_bid]
    ask[bad_ask] = ltp[bad_ask]

    # Ensure ask >= bid
    swapped = ask < bid
    bid[swapped], ask[swapped] = ask[swapped].copy(), bid[swapped].copy()

    # Filter rows where both are still invalid
    valid = (bid > 0) & (ask > 0) & ~np.isnan(bid) & ~np.isnan(ask)
    df = df[valid].reset_index(drop=True)
    bid = bid[valid]
    ask = ask[valid]

    bid_qty = np.maximum(df["buy_qty"].values.astype(np.uint64), 1)
    ask_qty = np.maximum(df["sell_qty"].values.astype(np.uint64), 1)
    ts_arr = _ist_to_utc_ns(df["datetime"])

    # Create instruments and batch ticks per instrument
    instruments: dict[str, OptionContract] = {}
    all_ticks: list[QuoteTick] = []

    for (strike, opt_type), group in df.groupby(["strike_price", "option_type"]):
        kind = OptionKind.CALL if opt_type == "CE" else OptionKind.PUT
        inst = make_option_instrument(int(strike), kind, expiry_str, activation_ns, expiration_ns)
        instruments[str(inst.id)] = inst

        mask = group.index.values
        ticks = _build_ticks_batch(
            inst.id, bid[mask], ask[mask], bid_qty[mask], ask_qty[mask], ts_arr[mask],
        )
        all_ticks.extend(ticks)

    return list(instruments.values()), all_ticks


def load_options_for_strikes(
    date_str: str,
    strikes: list[tuple[int, str]],
) -> tuple[list[OptionContract], list[QuoteTick]]:
    """Load option ticks for specific (strike, option_type) pairs only."""
    path = get_nearest_expiry_file(date_str)
    if path is None:
        return [], []

    expiry_str = path.stem.split("_")[1]
    expiry_date = f"{expiry_str[:4]}-{expiry_str[4:6]}-{expiry_str[6:8]}"
    expiration_ns = make_alert_time_ns(expiry_date, "15:30:00")
    activation_ns = make_alert_time_ns(date_str, "09:15:00")

    df = pd.read_parquet(path, columns=[
        "datetime", "option_type", "strike_price", "ltp", "buy_price", "sell_price",
        "buy_qty", "sell_qty",
    ])

    if df["option_type"].dtype == object:
        df["option_type"] = df["option_type"].apply(
            lambda x: x.decode() if isinstance(x, bytes) else x
        )

    # Filter to only requested (strike, type) pairs
    mask = pd.Series(False, index=df.index)
    for strike, opt_type in strikes:
        mask = mask | ((df["strike_price"] == strike) & (df["option_type"] == opt_type))
    df = df[mask]

    if df.empty:
        return [], []

    df = df.sort_values("datetime").reset_index(drop=True)
    df = df.drop_duplicates(subset=["datetime", "strike_price", "option_type"], keep="first")
    df = df.reset_index(drop=True)

    bid = df["buy_price"].values.astype(np.float64)
    ask = df["sell_price"].values.astype(np.float64)
    ltp = df["ltp"].values.astype(np.float64)

    bad_bid = (bid <= 0) | np.isnan(bid)
    bad_ask = (ask <= 0) | np.isnan(ask)
    bid[bad_bid] = ltp[bad_bid]
    ask[bad_ask] = ltp[bad_ask]

    swapped = ask < bid
    bid[swapped], ask[swapped] = ask[swapped].copy(), bid[swapped].copy()

    valid = (bid > 0) & (ask > 0) & ~np.isnan(bid) & ~np.isnan(ask)
    df = df[valid].reset_index(drop=True)
    bid = bid[valid]
    ask = ask[valid]

    bid_qty = np.maximum(df["buy_qty"].values.astype(np.uint64), 1)
    ask_qty = np.maximum(df["sell_qty"].values.astype(np.uint64), 1)
    ts_arr = _ist_to_utc_ns(df["datetime"])

    instruments: dict[str, OptionContract] = {}
    all_ticks: list[QuoteTick] = []

    for (strike, opt_type), group in df.groupby(["strike_price", "option_type"]):
        kind = OptionKind.CALL if opt_type == "CE" else OptionKind.PUT
        inst = make_option_instrument(int(strike), kind, expiry_str, activation_ns, expiration_ns)
        instruments[str(inst.id)] = inst

        idx = group.index.values
        ticks = _build_ticks_batch(
            inst.id, bid[idx], ask[idx], bid_qty[idx], ask_qty[idx], ts_arr[idx],
        )
        all_ticks.extend(ticks)

    return list(instruments.values()), all_ticks


def load_day_data(
    date_str: str,
    entry_time: str = "09:21:00",
    strike_step: int = 50,
    strike_range: int = 2,
) -> tuple[list, list[QuoteTick]]:
    """Load instruments and ticks for a trading day. Filters options near ATM."""
    atm_estimate = _get_approximate_spot_at_entry(date_str, entry_time)

    spot_inst, spot_ticks = load_spot_ticks(date_str)
    opt_insts, opt_ticks = load_option_ticks(
        date_str, atm_estimate=atm_estimate,
        strike_step=strike_step, strike_range=strike_range,
    )

    return [spot_inst] + opt_insts, spot_ticks + opt_ticks
