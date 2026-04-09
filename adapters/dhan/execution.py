"""DhanHQ live execution client for NautilusTrader."""

from __future__ import annotations

import asyncio
import logging

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.execution.reports import (
    FillReport,
    OrderStatusReport,
    PositionStatusReport,
)
from nautilus_trader.live.execution_client import LiveExecutionClient
from nautilus_trader.model.enums import (
    AccountType,
    OmsType,
    OrderSide,
    OrderStatus,
    OrderType,
)
from nautilus_trader.model.identifiers import (
    AccountId,
    ClientId,
    InstrumentId,
    TradeId,
    Venue,
    VenueOrderId,
)
from nautilus_trader.model.events import AccountState
from nautilus_trader.model.objects import Currency, Money, Price, Quantity, AccountBalance, MarginBalance

from adapters._common.nse import INR, VENUE
from adapters.dhan.config import DhanExecClientConfig
from adapters.dhan.constants import ExchangeSegment, NIFTY_SPOT_SECURITY_ID
from adapters.dhan.providers import DhanInstrumentProvider

log = logging.getLogger(__name__)


class DhanExecutionClient(LiveExecutionClient):
    """Live execution client for DhanHQ broker."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        instrument_provider: DhanInstrumentProvider,
        config: DhanExecClientConfig,
        name: str = "DHAN",
    ) -> None:
        super().__init__(
            loop=loop,
            client_id=ClientId(name),
            venue=Venue("MCX") if "MCX" in config.order_exchange_segment else VENUE,
            oms_type=OmsType.HEDGING,
            account_type=AccountType.MARGIN,
            base_currency=INR,
            instrument_provider=instrument_provider,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=config,
        )
        self._provider = instrument_provider
        self._config = config
        self._dhan = None  # dhanhq.DhanHQ instance, initialized on connect

    async def _connect(self) -> None:
        """Connect to DhanHQ execution API."""
        try:
            from dhanhq import dhanhq as DhanHQ
        except ImportError:
            raise ImportError("dhanhq package required: pip install dhanhq")

        self._dhan = DhanHQ(
            client_id=self._config.get_client_id(),
            access_token=self._config.get_access_token(),
        )

        # Set account_id and generate initial AccountState
        account_id = AccountId(f"DHAN-{self._config.get_client_id()}")
        self._set_account_id(account_id)
        self.generate_account_state(
            balances=[
                AccountBalance(
                    total=Money(1_000_000, INR),
                    locked=Money(0, INR),
                    free=Money(1_000_000, INR),
                ),
            ],
            margins=[],
            reported=True,
            ts_event=self._clock.timestamp_ns(),
        )
        log.info("DhanHQ execution client connected (client_id=%s, account=%s)", self._config.get_client_id(), account_id)

    async def _disconnect(self) -> None:
        """Disconnect from DhanHQ."""
        self._dhan = None
        log.info("DhanHQ execution client disconnected")

    # --- Order submission ---

    async def _submit_order(self, command) -> None:
        """Submit a market order to DhanHQ."""
        order = command.order
        instrument_id = order.instrument_id

        # Generate submitted event
        self.generate_order_submitted(
            strategy_id=order.strategy_id,
            instrument_id=instrument_id,
            client_order_id=order.client_order_id,
            ts_event=self._clock.timestamp_ns(),
        )

        sec_id = self._provider.nautilus_to_security_id.get(instrument_id)
        print(f"[ExecClient] Submit order: {instrument_id} -> secId={sec_id}, mappings={len(self._provider.nautilus_to_security_id)}", flush=True)
        if sec_id is None:
            print(f"[ExecClient] FAILED: No secId for {instrument_id}. Available: {list(self._provider.nautilus_to_security_id.keys())[:5]}", flush=True)
            log.error("No Dhan security ID for %s", instrument_id)
            self.generate_order_rejected(
                strategy_id=order.strategy_id,
                instrument_id=instrument_id,
                client_order_id=order.client_order_id,
                reason=f"Unknown instrument: {instrument_id}",
                ts_event=self._clock.timestamp_ns(),
            )
            return

        # Map order side
        transaction_type = "SELL" if order.side == OrderSide.SELL else "BUY"

        try:
            response = self._dhan.place_order(
                security_id=str(sec_id),
                exchange_segment=self._config.order_exchange_segment,
                transaction_type=transaction_type,
                quantity=int(order.quantity),
                order_type="MARKET",
                product_type=self._config.product_type,
                price=0,
            )
        except Exception as e:
            print(f"[ExecClient] Order placement exception: {e}", flush=True)
            log.error("Order placement failed: %s", e)
            self.generate_order_rejected(
                strategy_id=order.strategy_id,
                instrument_id=instrument_id,
                client_order_id=order.client_order_id,
                reason=str(e),
                ts_event=self._clock.timestamp_ns(),
            )
            return

        if response.get("status") != "success":
            reason = response.get("remarks", str(response))
            log.error("Order rejected by Dhan: %s", reason)
            self.generate_order_rejected(
                strategy_id=order.strategy_id,
                instrument_id=instrument_id,
                client_order_id=order.client_order_id,
                reason=reason,
                ts_event=self._clock.timestamp_ns(),
            )
            return

        order_id = str(response["data"]["orderId"])
        venue_order_id = VenueOrderId(order_id)

        self.generate_order_accepted(
            strategy_id=order.strategy_id,
            instrument_id=instrument_id,
            client_order_id=order.client_order_id,
            venue_order_id=venue_order_id,
            ts_event=self._clock.timestamp_ns(),
        )

        log.info("Order accepted: %s -> Dhan orderId=%s", order.client_order_id, order_id)

        # Start polling for fill (market orders fill quickly)
        asyncio.create_task(
            self._poll_for_fill(order, venue_order_id)
        )

    async def _poll_for_fill(self, order, venue_order_id: VenueOrderId) -> None:
        """Poll Dhan API for order fill status."""
        interval = self._config.fill_poll_interval_ms / 1000.0
        max_attempts = 50  # 10 seconds max

        for _ in range(max_attempts):
            await asyncio.sleep(interval)
            try:
                resp = self._dhan.get_order_by_id(str(venue_order_id.value))
                if resp.get("status") != "success":
                    continue

                order_data = resp["data"]
                dhan_status = order_data.get("orderStatus", "")

                if dhan_status == "TRADED":
                    fill_price = float(order_data.get("price", 0) or order_data.get("tradedPrice", 0))
                    fill_qty = int(order_data.get("tradedQuantity", order_data.get("quantity", 0)))
                    trade_id = str(order_data.get("exchangeOrderId", venue_order_id.value))

                    self.generate_order_filled(
                        strategy_id=order.strategy_id,
                        instrument_id=order.instrument_id,
                        client_order_id=order.client_order_id,
                        venue_order_id=venue_order_id,
                        venue_position_id=None,
                        trade_id=TradeId(trade_id),
                        order_side=order.side,
                        order_type=OrderType.MARKET,
                        last_qty=Quantity(fill_qty, precision=0),
                        last_px=Price(fill_price, precision=2),
                        currency=INR,
                        commission=Money(0, INR),
                        ts_event=self._clock.timestamp_ns(),
                    )
                    log.info(
                        "Order filled: %s @ %.2f x %d",
                        order.client_order_id, fill_price, fill_qty,
                    )
                    return

                elif dhan_status == "REJECTED":
                    reason = order_data.get("rejectedReason", "Unknown rejection")
                    self.generate_order_rejected(
                        strategy_id=order.strategy_id,
                        instrument_id=order.instrument_id,
                        client_order_id=order.client_order_id,
                        reason=reason,
                        ts_event=self._clock.timestamp_ns(),
                    )
                    log.warning("Order rejected: %s — %s", order.client_order_id, reason)
                    return

                elif dhan_status == "CANCELLED":
                    log.warning("Order cancelled: %s", order.client_order_id)
                    return

            except Exception as e:
                log.warning("Fill poll error: %s", e)

        log.error("Fill poll timeout for %s after %d attempts", order.client_order_id, max_attempts)

    # --- Order cancellation ---

    async def _cancel_order(self, command) -> None:
        """Cancel an order on DhanHQ."""
        venue_order_id = command.venue_order_id
        try:
            self._dhan.cancel_order(str(venue_order_id.value))
            log.info("Cancelled order: %s", venue_order_id)
        except Exception as e:
            log.error("Cancel failed for %s: %s", venue_order_id, e)

    async def _cancel_all_orders(self, command) -> None:
        """Cancel all open orders."""
        for order in self.cache.orders_open(venue=VENUE):
            if order.venue_order_id:
                try:
                    self._dhan.cancel_order(str(order.venue_order_id.value))
                except Exception as e:
                    log.warning("Cancel failed for %s: %s", order.venue_order_id, e)

    # --- Reconciliation reports ---

    async def generate_order_status_report(self, command) -> OrderStatusReport | None:
        return None

    async def generate_order_status_reports(self, command) -> list[OrderStatusReport]:
        return []

    async def generate_fill_reports(self, command) -> list[FillReport]:
        return []

    async def generate_position_status_reports(self, command) -> list[PositionStatusReport]:
        return []

    async def generate_mass_status(self, lookback_mins: int | None = None):
        return None
