"""DhanHQ async WebSocket client for live market data.

Handles binary message parsing (Little Endian) and auto-reconnection.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
from collections.abc import Callable

import aiohttp

from adapters.dhan.constants import DHAN_WS_URL, ExchangeSegment, FeedRequestCode

log = logging.getLogger(__name__)

# Dhan v2 binary quote packet layout (after 8-byte header):
# Offset  Size  Field
# 0       4     LTP (float LE)
# 4       2     LTQ (uint16 LE)
# 6       4     LTT (uint32 LE, epoch seconds)
# 10      4     Avg price (float LE)
# 14      4     Volume (uint32 LE)
# 18      4     Total sell qty (uint32 LE)
# 22      4     Total buy qty (uint32 LE)
# 26      4     Day open (float LE)
# 30      4     Day close (float LE)
# 34      4     Day high (float LE)
# 38      4     Day low (float LE)

# Header: 2 bytes (response code uint8 + padding/length), 1 byte exchange segment, 4 bytes security ID
HEADER_SIZE = 8
QUOTE_PAYLOAD_SIZE = 42

TickCallback = Callable[[int, int, float, float, int, int, int], None]
# (exchange_segment, security_id, bid, ask, bid_qty, ask_qty, ltt_epoch_s)


class DhanWebSocketClient:
    """Async WebSocket client for DhanHQ v2 binary market feed."""

    def __init__(
        self,
        access_token: str,
        client_id: str,
        on_tick: TickCallback,
        reconnect_delay: float = 5.0,
    ) -> None:
        self._access_token = access_token
        self._client_id = client_id
        self._on_tick = on_tick
        self._reconnect_delay = reconnect_delay

        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._subscriptions: list[tuple[int, int]] = []  # (exchange_segment, security_id)
        self._running = False
        self._read_task: asyncio.Task | None = None

    @property
    def url(self) -> str:
        return (
            f"{DHAN_WS_URL}?version=2"
            f"&token={self._access_token}"
            f"&clientId={self._client_id}"
            f"&authType=2"
        )

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        print(f"[DhanWS] Connecting...", flush=True)
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(self.url, heartbeat=30)
        self._running = True
        self._read_task = asyncio.create_task(self._read_loop())
        print("[DhanWS] Connected!", flush=True)
        log.info("DhanHQ WebSocket connected")

        # Re-subscribe if reconnecting
        if self._subscriptions:
            await self._send_subscribe(self._subscriptions)

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        self._running = False
        if self._read_task:
            self._read_task.cancel()
            self._read_task = None
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        log.info("DhanHQ WebSocket disconnected")

    async def subscribe(self, instruments: list[tuple[int, int]]) -> None:
        """Subscribe to market data for given (exchange_segment, security_id) pairs."""
        new_subs = [s for s in instruments if s not in self._subscriptions]
        if not new_subs:
            return
        self._subscriptions.extend(new_subs)
        if self._ws and not self._ws.closed:
            await self._send_subscribe(new_subs)

    async def _send_subscribe(self, instruments: list[tuple[int, int]]) -> None:
        """Send subscribe messages, batching at 100 instruments per message."""
        for i in range(0, len(instruments), 100):
            batch = instruments[i:i + 100]
            msg = {
                "RequestCode": FeedRequestCode.SUBSCRIBE,
                "InstrumentCount": len(batch),
                "InstrumentList": [
                    {"ExchangeSegment": str(seg), "SecurityId": str(sid)}
                    for seg, sid in batch
                ],
            }
            print(f"[DhanWS] Subscribe: {msg}", flush=True)
            await self._ws.send_str(json.dumps(msg))
            log.debug("Subscribed to %d instruments", len(batch))

    async def _read_loop(self) -> None:
        """Read and parse binary WebSocket messages."""
        while self._running:
            try:
                msg = await self._ws.receive(timeout=45)

                if msg.type == aiohttp.WSMsgType.BINARY:
                    self._parse_binary(msg.data)
                elif msg.type == aiohttp.WSMsgType.PING:
                    await self._ws.pong(msg.data)
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    print(f"[DhanWS] WS closed/error: {msg.type}", flush=True)
                    log.warning("WebSocket closed/error: %s", msg.type)
                    break
            except asyncio.TimeoutError:
                print("[DhanWS] Read timeout!", flush=True)
                log.warning("WebSocket read timeout, reconnecting...")
                break
            except asyncio.CancelledError:
                return
            except Exception as e:
                log.error("WebSocket read error: %s", e)
                break

        if self._running:
            asyncio.create_task(self._reconnect())

    async def _reconnect(self) -> None:
        """Reconnect with delay."""
        log.info("Reconnecting in %.1fs...", self._reconnect_delay)
        await asyncio.sleep(self._reconnect_delay)
        try:
            if self._ws and not self._ws.closed:
                await self._ws.close()
            self._ws = await self._session.ws_connect(self.url, heartbeat=30)
            self._read_task = asyncio.create_task(self._read_loop())
            log.info("DhanHQ WebSocket reconnected")
            if self._subscriptions:
                await self._send_subscribe(self._subscriptions)
        except Exception as e:
            log.error("Reconnection failed: %s, retrying...", e)
            asyncio.create_task(self._reconnect())

    def _parse_binary(self, data: bytes) -> None:
        """Parse DhanHQ v2 binary market data frame.

        Dhan v2 ticker format (16 bytes):
          Byte 0: response code (2=ticker, 4=quote)
          Byte 1: packet length
          Bytes 2-3: padding
          Bytes 4-7: security_id (uint32 LE)
          Bytes 8-11: LTP (float LE)
          Bytes 12-15: LTT epoch seconds (uint32 LE)
        """
        if len(data) < 12:
            return

        security_id = struct.unpack_from("<I", data, 4)[0]
        ltp = struct.unpack_from("<f", data, 8)[0]
        ltt = struct.unpack_from("<I", data, 12)[0] if len(data) >= 16 else 0

        if ltp <= 0:
            return

        self._on_tick(0, security_id, ltp, ltp, 1, 1, ltt)
