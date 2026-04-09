"""Bidirectional mapping between Dhan security IDs and NautilusTrader InstrumentIds."""

from __future__ import annotations

import pandas as pd

from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue

from adapters._common.nse import VENUE, build_option_symbol


def build_mappings_from_csv(
    df: pd.DataFrame,
    underlying: str = "NIFTY",
    venue: Venue | None = None,
) -> tuple[dict[int, InstrumentId], dict[InstrumentId, int]]:
    """Build bidirectional security_id <-> InstrumentId maps from the Dhan scrip master CSV."""
    v = venue or VENUE
    sec_to_naut: dict[int, InstrumentId] = {}
    naut_to_sec: dict[InstrumentId, int] = {}

    # Add options from CSV (spot is added by the provider separately)
    for _, row in df.iterrows():
        sec_id = int(row["SECURITY_ID"])
        strike = int(float(row["STRIKE_PRICE"]))
        opt_type = str(row["OPTION_TYPE"]).strip().upper()

        if opt_type not in ("CE", "PE"):
            continue

        expiry_raw = row["SM_EXPIRY_DATE"]
        expiry_dt = pd.Timestamp(expiry_raw)
        expiry_str = expiry_dt.strftime("%Y%m%d")

        sym = build_option_symbol(underlying, strike, opt_type, expiry_str)
        inst_id = InstrumentId(Symbol(sym), v)

        sec_to_naut[sec_id] = inst_id
        naut_to_sec[inst_id] = sec_id

    return sec_to_naut, naut_to_sec
