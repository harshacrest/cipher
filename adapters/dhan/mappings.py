"""Bidirectional mapping between Dhan security IDs and NautilusTrader InstrumentIds."""

from __future__ import annotations

import pandas as pd

from nautilus_trader.model.identifiers import InstrumentId, Symbol

from adapters._common.nse import VENUE, SPOT_ID, build_option_symbol
from adapters.dhan.constants import NIFTY_SPOT_SECURITY_ID


def build_mappings_from_csv(
    df: pd.DataFrame,
    underlying: str = "NIFTY",
) -> tuple[dict[int, InstrumentId], dict[InstrumentId, int]]:
    """Build bidirectional security_id <-> InstrumentId maps from the Dhan scrip master CSV.

    Args:
        df: Filtered DataFrame from api-scrip-master-detailed.csv
        underlying: Underlying name to filter for

    Returns:
        (security_id_to_nautilus, nautilus_to_security_id) dicts
    """
    sec_to_naut: dict[int, InstrumentId] = {}
    naut_to_sec: dict[InstrumentId, int] = {}

    # Add NIFTY spot
    sec_to_naut[NIFTY_SPOT_SECURITY_ID] = SPOT_ID
    naut_to_sec[SPOT_ID] = NIFTY_SPOT_SECURITY_ID

    # Add options from CSV
    for _, row in df.iterrows():
        sec_id = int(row["SEM_SMST_SECURITY_ID"])
        strike = int(float(row["SEM_STRIKE_PRICE"]))
        opt_type = str(row["SEM_OPTION_TYPE"]).strip().upper()

        if opt_type not in ("CE", "PE"):
            continue

        # Parse expiry date to YYYYMMDD
        expiry_raw = row["SEM_EXPIRY_DATE"]
        if isinstance(expiry_raw, str):
            expiry_dt = pd.Timestamp(expiry_raw)
        else:
            expiry_dt = pd.Timestamp(expiry_raw)
        expiry_str = expiry_dt.strftime("%Y%m%d")

        sym = build_option_symbol(underlying, strike, opt_type, expiry_str)
        inst_id = InstrumentId(Symbol(sym), VENUE)

        sec_to_naut[sec_id] = inst_id
        naut_to_sec[inst_id] = sec_id

    return sec_to_naut, naut_to_sec
