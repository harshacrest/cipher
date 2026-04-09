"""DhanHQ client factories for NautilusTrader TradingNode."""

from __future__ import annotations

import asyncio

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.live.factories import LiveDataClientFactory, LiveExecClientFactory

from adapters.dhan.config import DhanDataClientConfig, DhanExecClientConfig
from adapters.dhan.data import DhanDataClient
from adapters.dhan.execution import DhanExecutionClient
from adapters.dhan.providers import DhanInstrumentProvider

# Shared provider instance — both data and exec clients use the same one
_shared_provider: DhanInstrumentProvider | None = None


def get_shared_provider(filters: dict | None = None) -> DhanInstrumentProvider:
    """Get or create the shared instrument provider."""
    global _shared_provider
    if _shared_provider is None:
        _shared_provider = DhanInstrumentProvider(filters=filters)
    return _shared_provider


class DhanLiveDataClientFactory(LiveDataClientFactory):

    @staticmethod
    def create(
        loop: asyncio.AbstractEventLoop,
        name: str,
        config: DhanDataClientConfig,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
    ) -> DhanDataClient:
        provider = get_shared_provider(config.instrument_filters)
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

    @staticmethod
    def create(
        loop: asyncio.AbstractEventLoop,
        name: str,
        config: DhanExecClientConfig,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
    ) -> DhanExecutionClient:
        provider = get_shared_provider()  # Reuse same instance from data factory
        return DhanExecutionClient(
            loop=loop,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=provider,
            config=config,
            name=name,
        )
