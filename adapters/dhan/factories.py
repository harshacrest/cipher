"""DhanHQ client factories for NautilusTrader TradingNode."""

from __future__ import annotations

import asyncio
from functools import lru_cache

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.live.factories import LiveDataClientFactory, LiveExecClientFactory

from adapters.dhan.config import DhanDataClientConfig, DhanExecClientConfig
from adapters.dhan.data import DhanDataClient
from adapters.dhan.execution import DhanExecutionClient
from adapters.dhan.providers import DhanInstrumentProvider


@lru_cache(maxsize=1)
def get_cached_dhan_instrument_provider(
    filters: tuple | None = None,
) -> DhanInstrumentProvider:
    """Get or create a shared DhanInstrumentProvider instance."""
    filter_dict = dict(filters) if filters else None
    return DhanInstrumentProvider(filters=filter_dict)


class DhanLiveDataClientFactory(LiveDataClientFactory):
    """Factory for creating DhanHQ live data clients."""

    @staticmethod
    def create(
        loop: asyncio.AbstractEventLoop,
        name: str,
        config: DhanDataClientConfig,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
    ) -> DhanDataClient:
        filters = tuple(sorted(config.instrument_filters.items())) if config.instrument_filters else None
        provider = get_cached_dhan_instrument_provider(filters)
        return DhanDataClient(
            loop=loop,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=provider,
            config=config,
            name=name,
        )


class DhanLiveExecClientFactory(LiveExecClientFactory):
    """Factory for creating DhanHQ live execution clients."""

    @staticmethod
    def create(
        loop: asyncio.AbstractEventLoop,
        name: str,
        config: DhanExecClientConfig,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
    ) -> DhanExecutionClient:
        provider = get_cached_dhan_instrument_provider()
        return DhanExecutionClient(
            loop=loop,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=provider,
            config=config,
            name=name,
        )
