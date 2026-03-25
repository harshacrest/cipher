"""DhanHQ live market data client for NautilusTrader."""

from __future__ import annotations

import asyncio
import logging
import time

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.core.datetime import nanos_to_secs
from nautilus_trader.live.data_client import LiveMarketDataClient
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.identifiers import ClientId, InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from adapters._common.nse import VENUE, PRICE_PREC, SIZE_PREC
from adapters.dhan.config import DhanDataClientConfig
from adapters.dhan.constants import ExchangeSegment, NIFTY_SPOT_SECURITY_ID
from adapters.dhan.providers import DhanInstrumentProvider
from adapters.dhan.ws import DhanWebSocketClient

log = logging.getLogger(__name__)


class DhanDataClient(LiveMarketDataClient):
    """Live market data client for DhanHQ broker."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        instrument_provider: DhanInstrumentProvider,
        config: DhanDataClientConfig,
        name: str = "DHAN",
    ) -> None:
        super().__init__(
            loop=loop,
            client_id=ClientId(name),
            venue=VENUE,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=instrument_provider,
            config=config,
        )
        self._provider = instrument_provider
        self._config = config
        self._ws: DhanWebSocketClient | None = None

    async def _connect(self) -> None:
        """Connect to DhanHQ and load instruments."""
        # Load instruments
        await self._provider.load_all_async(self._config.instrument_filters)

        # Push instruments to engine cache
        for instrument in self._provider.list_all():
            self._handle_data(instrument)

        log.info("Pushed %d instruments to cache", len(self._provider.list_all()))

        # Create and connect WebSocket
        self._ws = DhanWebSocketClient(
            access_token=self._config.get_access_token(),
            client_id=self._config.get_client_id(),
            on_tick=self._on_ws_tick,
            reconnect_delay=self._config.ws_reconnect_delay,
        )
        await self._ws.connect()

    async def _disconnect(self) -> None:
        """Disconnect from DhanHQ."""
        if self._ws:
            await self._ws.disconnect()

    async def _subscribe_quote_ticks(self, command) -> None:
        """Subscribe to quote ticks for an instrument."""
        instrument_id: InstrumentId = command.instrument_id

        sec_id = self._provider.nautilus_to_security_id.get(instrument_id)
        if sec_id is None:
            log.error("No Dhan security ID for %s", instrument_id)
            return

        # Determine exchange segment
        if sec_id == NIFTY_SPOT_SECURITY_ID:
            segment = ExchangeSegment.IDX_I
        else:
            segment = ExchangeSegment.NSE_FNO

        log.info("Subscribing to ticks: %s (secId=%d, seg=%d)", instrument_id, sec_id, segment)
        await self._ws.subscribe([(segment, sec_id)])

    async def _unsubscribe_quote_ticks(self, command) -> None:
        """Unsubscribe from quote ticks (no-op for now, WS stays connected)."""
        log.info("Unsubscribe quote ticks: %s (keeping WS alive)", command.instrument_id)

    def _on_ws_tick(
        self,
        exchange_segment: int,
        security_id: int,
        bid: float,
        ask: float,
        bid_qty: int,
        ask_qty: int,
        ltt_epoch_s: int,
    ) -> None:
        """Callback from WebSocket — convert to QuoteTick and push to engine."""
        instrument_id = self._provider.security_id_to_nautilus.get(security_id)
        if instrument_id is None:
            return

        # Use server timestamp if available, otherwise local clock
        if ltt_epoch_s > 0:
            ts_event = int(ltt_epoch_s * 1_000_000_000)
        else:
            ts_event = self._clock.timestamp_ns()

        tick = QuoteTick(
            instrument_id=instrument_id,
            bid_price=Price(bid, precision=PRICE_PREC),
            ask_price=Price(ask, precision=PRICE_PREC),
            bid_size=Quantity(bid_qty, precision=SIZE_PREC),
            ask_size=Quantity(ask_qty, precision=SIZE_PREC),
            ts_event=ts_event,
            ts_init=self._clock.timestamp_ns(),
        )
        self._handle_data(tick)
