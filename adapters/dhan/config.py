"""DhanHQ adapter configuration."""

from __future__ import annotations

import os

from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.live.config import LiveDataClientConfig, LiveExecClientConfig


class DhanDataClientConfig(LiveDataClientConfig, frozen=True):
    """Configuration for the DhanHQ live data client."""
    access_token: str = ""
    client_id: str = ""
    ws_reconnect_delay: float = 5.0
    instrument_filters: dict | None = None  # e.g. {"underlying": "NIFTY", "max_expiries": 2}

    def get_access_token(self) -> str:
        return self.access_token or os.environ.get("DHAN_ACCESS_TOKEN", "")

    def get_client_id(self) -> str:
        return self.client_id or os.environ.get("DHAN_CLIENT_ID", "")


class DhanExecClientConfig(LiveExecClientConfig, frozen=True):
    """Configuration for the DhanHQ live execution client."""
    access_token: str = ""
    client_id: str = ""
    product_type: str = "INTRA"
    fill_poll_interval_ms: int = 200

    def get_access_token(self) -> str:
        return self.access_token or os.environ.get("DHAN_ACCESS_TOKEN", "")

    def get_client_id(self) -> str:
        return self.client_id or os.environ.get("DHAN_CLIENT_ID", "")
