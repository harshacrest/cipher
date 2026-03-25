"""DhanHQ instrument provider — loads instrument master CSV and builds NautilusTrader instruments."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from nautilus_trader.common.providers import InstrumentProvider
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.model.enums import OptionKind
from nautilus_trader.model.identifiers import InstrumentId

from adapters._common.nse import (
    SPOT_ID,
    make_alert_time_ns,
    make_option_instrument,
    make_spot_instrument,
)
from adapters.dhan.constants import DHAN_SCRIP_MASTER_URL, NIFTY_SPOT_SECURITY_ID
from adapters.dhan.mappings import build_mappings_from_csv

log = logging.getLogger(__name__)

CACHE_DIR = Path.home() / ".cache" / "cipher"


class DhanInstrumentProvider(InstrumentProvider):
    """Loads NIFTY instruments from DhanHQ scrip master CSV."""

    def __init__(
        self,
        config: InstrumentProviderConfig | None = None,
        filters: dict | None = None,
    ) -> None:
        super().__init__(config=config)
        self._filters = filters or {}
        self.security_id_to_nautilus: dict[int, InstrumentId] = {}
        self.nautilus_to_security_id: dict[InstrumentId, int] = {}

    async def load_all_async(self, filters: dict | None = None) -> None:
        """Load all NIFTY instruments from Dhan's scrip master."""
        effective_filters = filters or self._filters
        underlying = effective_filters.get("underlying", "NIFTY")
        max_expiries = effective_filters.get("max_expiries", 2)

        df = self._load_scrip_master()
        df = self._filter_options(df, underlying, max_expiries)

        # Build mappings
        sec_to_naut, naut_to_sec = build_mappings_from_csv(df, underlying)
        self.security_id_to_nautilus = sec_to_naut
        self.nautilus_to_security_id = naut_to_sec

        # Create and cache NautilusTrader instrument objects
        # Spot
        spot = make_spot_instrument()
        self.add(spot)

        # Options
        for _, row in df.iterrows():
            try:
                strike = int(float(row["SEM_STRIKE_PRICE"]))
                opt_type = str(row["SEM_OPTION_TYPE"]).strip().upper()
                if opt_type not in ("CE", "PE"):
                    continue

                expiry_raw = row["SEM_EXPIRY_DATE"]
                expiry_dt = pd.Timestamp(expiry_raw)
                expiry_str = expiry_dt.strftime("%Y%m%d")
                expiry_date_str = expiry_dt.strftime("%Y-%m-%d")

                # Use trading day as activation (9:15 IST), expiry day 15:30 IST as expiration
                activation_ns = make_alert_time_ns(expiry_date_str, "09:15:00")
                expiration_ns = make_alert_time_ns(expiry_date_str, "15:30:00")

                kind = OptionKind.CALL if opt_type == "CE" else OptionKind.PUT
                inst = make_option_instrument(strike, kind, expiry_str, activation_ns, expiration_ns)
                self.add(inst)
            except Exception as e:
                log.warning("Failed to create instrument from row: %s — %s", row.to_dict(), e)

        log.info(
            "DhanInstrumentProvider loaded %d instruments (%d options + spot)",
            len(self._instruments), len(self._instruments) - 1,
        )

    def _load_scrip_master(self) -> pd.DataFrame:
        """Load scrip master CSV, using daily cache."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        cache_path = CACHE_DIR / f"dhan_scrip_master_{today}.csv"

        if cache_path.exists():
            log.info("Loading cached scrip master: %s", cache_path)
            return pd.read_csv(cache_path)

        log.info("Downloading scrip master from %s", DHAN_SCRIP_MASTER_URL)
        df = pd.read_csv(DHAN_SCRIP_MASTER_URL)
        df.to_csv(cache_path, index=False)
        return df

    def _filter_options(self, df: pd.DataFrame, underlying: str, max_expiries: int) -> pd.DataFrame:
        """Filter to NIFTY OPTIDX on NSE with nearest expiries."""
        mask = (
            (df["SEM_EXM_EXCH_ID"] == "NSE")
            & (df["SEM_INSTRUMENT_NAME"] == "OPTIDX")
            & (df["SEM_CUSTOM_SYMBOL"].str.contains(underlying, case=False, na=False))
        )
        filtered = df[mask].copy()

        if filtered.empty:
            return filtered

        # Parse expiry dates and keep nearest N expiries
        filtered["_expiry_dt"] = pd.to_datetime(filtered["SEM_EXPIRY_DATE"], errors="coerce")
        filtered = filtered.dropna(subset=["_expiry_dt"])

        today = pd.Timestamp.now().normalize()
        filtered = filtered[filtered["_expiry_dt"] >= today]

        # Get the nearest max_expiries unique expiry dates
        unique_expiries = sorted(filtered["_expiry_dt"].unique())[:max_expiries]
        filtered = filtered[filtered["_expiry_dt"].isin(unique_expiries)]

        log.info(
            "Filtered to %d option instruments across %d expiries",
            len(filtered), len(unique_expiries),
        )
        return filtered.drop(columns=["_expiry_dt"])
