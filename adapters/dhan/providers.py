"""DhanHQ instrument provider — loads instrument master CSV and builds NautilusTrader instruments."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from nautilus_trader.common.providers import InstrumentProvider
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.model.enums import OptionKind
from nautilus_trader.model.identifiers import InstrumentId, Symbol

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
        self.spot_security_id: int = self._filters.get("spot_security_id", NIFTY_SPOT_SECURITY_ID)

    async def load_all_async(self, filters: dict | None = None) -> None:
        """Load instruments from Dhan's scrip master."""
        effective_filters = filters or self._filters
        underlying = effective_filters.get("underlying", "NIFTY")
        max_expiries = effective_filters.get("max_expiries", 2)
        exchange = effective_filters.get("exchange", "NSE")
        lot_size = effective_filters.get("lot_size", 25)
        multiplier = effective_filters.get("multiplier", 25)
        price_inc = effective_filters.get("price_increment", "0.05")
        self.spot_security_id = effective_filters.get("spot_security_id", NIFTY_SPOT_SECURITY_ID)

        from nautilus_trader.model.enums import AssetClass
        from nautilus_trader.model.identifiers import Venue as V
        venue = V(exchange)
        asset_class = AssetClass.COMMODITY if exchange == "MCX" else AssetClass.INDEX

        df = self._load_scrip_master()
        df = self._filter_options(df, underlying, max_expiries)

        # Build mappings
        sec_to_naut, naut_to_sec = build_mappings_from_csv(df, underlying, venue=venue)
        # Add spot mapping
        spot_sym = f"{underlying}-SPOT"
        spot_id = InstrumentId(Symbol(spot_sym), venue)
        sec_to_naut[self.spot_security_id] = spot_id
        naut_to_sec[spot_id] = self.spot_security_id
        self.security_id_to_nautilus = sec_to_naut
        self.nautilus_to_security_id = naut_to_sec

        # Create spot instrument
        spot = make_spot_instrument(underlying=underlying, venue=venue, price_increment=price_inc)
        self.add(spot)

        # Create option instruments
        for _, row in df.iterrows():
            try:
                strike = int(float(row["STRIKE_PRICE"]))
                opt_type = str(row["OPTION_TYPE"]).strip().upper()
                if opt_type not in ("CE", "PE"):
                    continue

                expiry_raw = row["SM_EXPIRY_DATE"]
                expiry_dt = pd.Timestamp(expiry_raw)
                expiry_str = expiry_dt.strftime("%Y%m%d")
                expiry_date_str = expiry_dt.strftime("%Y-%m-%d")

                activation_ns = make_alert_time_ns(expiry_date_str, "09:15:00")
                expiration_ns = make_alert_time_ns(expiry_date_str, "15:30:00")

                kind = OptionKind.CALL if opt_type == "CE" else OptionKind.PUT
                inst = make_option_instrument(
                    strike, kind, expiry_str, activation_ns, expiration_ns,
                    underlying=underlying, venue=venue, asset_class=asset_class,
                    lot_size=lot_size, multiplier=multiplier, price_increment=price_inc,
                )
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
            return pd.read_csv(cache_path, low_memory=False)

        log.info("Downloading scrip master from %s", DHAN_SCRIP_MASTER_URL)
        df = pd.read_csv(DHAN_SCRIP_MASTER_URL, low_memory=False)
        df.to_csv(cache_path, index=False)
        return df

    def _filter_options(self, df: pd.DataFrame, underlying: str, max_expiries: int) -> pd.DataFrame:
        """Filter options for the given underlying across NSE and MCX."""
        exchange = self._filters.get("exchange", "NSE")
        instrument_type = "OPTIDX" if exchange == "NSE" else "OPTFUT"
        mask = (
            (df["EXCH_ID"] == exchange)
            & (df["INSTRUMENT"] == instrument_type)
            & (df["SYMBOL_NAME"] == underlying)
        )
        filtered = df[mask].copy()

        if filtered.empty:
            return filtered

        # Parse expiry dates and keep nearest N expiries
        filtered["_expiry_dt"] = pd.to_datetime(filtered["SM_EXPIRY_DATE"], errors="coerce")
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
