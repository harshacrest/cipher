"""Shared NSE instrument definitions for all broker adapters.

This is the single source of truth for how NIFTY instruments are represented
in NautilusTrader. Both backtest (lib/nautilus_data.py) and live adapters
must produce instruments matching these specs so the strategy works unchanged.
"""

from nautilus_trader.model.enums import AssetClass, OptionKind
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import IndexInstrument, OptionContract
from nautilus_trader.model.objects import Currency, Price, Quantity

VENUE = Venue("NSE")
INR = Currency.from_str("INR")
SPOT_ID = InstrumentId(Symbol("NIFTY-SPOT"), VENUE)

PRICE_PREC = 2
SIZE_PREC = 0
PRICE_INCREMENT = Price.from_str("0.05")
SIZE_INCREMENT = Quantity.from_int(1)
LOT_SIZE = Quantity.from_int(25)
MULTIPLIER = Quantity.from_int(25)


def make_spot_instrument() -> IndexInstrument:
    """Create the NIFTY spot index instrument."""
    return IndexInstrument(
        instrument_id=SPOT_ID,
        raw_symbol=Symbol("NIFTY-SPOT"),
        currency=INR,
        price_precision=PRICE_PREC,
        price_increment=PRICE_INCREMENT,
        size_precision=SIZE_PREC,
        size_increment=SIZE_INCREMENT,
        ts_event=0,
        ts_init=0,
    )


def build_option_symbol(underlying: str, strike: int, kind_str: str, expiry_str: str) -> str:
    """Build NautilusTrader symbol string for an option.

    Returns e.g. "NIFTY-22500-CE-20250326"
    """
    return f"{underlying}-{strike}-{kind_str}-{expiry_str}"


def make_option_instrument(
    strike: int,
    option_kind: OptionKind,
    expiry_str: str,
    activation_ns: int,
    expiration_ns: int,
) -> OptionContract:
    """Create a NIFTY option instrument.

    Args:
        strike: Strike price (e.g. 22500)
        option_kind: OptionKind.CALL or OptionKind.PUT
        expiry_str: Expiry date as YYYYMMDD string
        activation_ns: UTC nanosecond timestamp for contract activation
        expiration_ns: UTC nanosecond timestamp for contract expiration
    """
    kind_str = "CE" if option_kind == OptionKind.CALL else "PE"
    sym = build_option_symbol("NIFTY", strike, kind_str, expiry_str)
    return OptionContract(
        instrument_id=InstrumentId(Symbol(sym), VENUE),
        raw_symbol=Symbol(sym),
        asset_class=AssetClass.INDEX,
        currency=INR,
        price_precision=PRICE_PREC,
        price_increment=PRICE_INCREMENT,
        multiplier=MULTIPLIER,
        lot_size=LOT_SIZE,
        underlying="NIFTY",
        option_kind=option_kind,
        strike_price=Price.from_str(f"{strike}.00"),
        activation_ns=activation_ns,
        expiration_ns=expiration_ns,
        ts_event=0,
        ts_init=0,
    )


def make_alert_time_ns(date_str: str, time_str: str) -> int:
    """Create true-UTC nanosecond timestamp for a given IST date+time."""
    import pandas as pd
    ist_dt = pd.Timestamp(f"{date_str} {time_str}", tz="Asia/Kolkata")
    return int(ist_dt.tz_convert("UTC").value)
