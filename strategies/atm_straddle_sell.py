"""
ATM Straddle Sell Strategy — NautilusTrader
-------------------------------------------
At 09:21 IST: find ATM strike (nearest to spot), sell CE + PE.
At 15:00 IST: buy back CE + PE at the SAME strike.

This Strategy subclass works identically in backtest and live.
"""

from __future__ import annotations

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class ATMStraddleSellConfig(StrategyConfig):
    entry_time: str = "09:21:00"
    exit_time: str = "15:00:00"
    strike_step: int = 50
    lot_size: int = 25
    num_lots: int = 1
    spot_instrument_id: str = "NIFTY-SPOT.NSE"


class ATMStraddleSell(Strategy):

    def __init__(self, config: ATMStraddleSellConfig) -> None:
        super().__init__(config)
        self.spot_id = InstrumentId.from_str(config.spot_instrument_id)
        self.entry_time = config.entry_time
        self.exit_time = config.exit_time
        self.strike_step = config.strike_step
        self.lot_size = config.lot_size
        self.num_lots = config.num_lots

        # State — reset each day
        self.latest_spot: float = 0.0
        self.atm_strike: int | None = None
        self.ce_id: InstrumentId | None = None
        self.pe_id: InstrumentId | None = None
        self.expiry_str: str | None = None

        # Fill tracking for result extraction
        self.entry_ce_px: float | None = None
        self.entry_pe_px: float | None = None
        self.exit_ce_px: float | None = None
        self.exit_pe_px: float | None = None
        self.spot_at_entry: float = 0.0
        self.spot_at_exit: float = 0.0

    def on_start(self) -> None:
        # Subscribe to spot for ATM detection
        self.subscribe_quote_ticks(self.spot_id)

        # Discover expiry from loaded option instruments
        for inst in self.cache.instruments(venue=Venue("NSE")):
            sym = str(inst.id.symbol)
            if sym.startswith("NIFTY-") and sym != "NIFTY-SPOT":
                parts = sym.split("-")
                if len(parts) == 4:
                    self.expiry_str = parts[3]
                    break

        # Determine trading date from clock (first data timestamp)
        clock_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(clock_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        date_str = ist_dt.strftime("%Y-%m-%d")

        # Set entry/exit alerts
        entry_ist = pd.Timestamp(f"{date_str} {self.entry_time}", tz="Asia/Kolkata")
        exit_ist = pd.Timestamp(f"{date_str} {self.exit_time}", tz="Asia/Kolkata")

        entry_ns = int(entry_ist.tz_convert("UTC").value)
        exit_ns = int(exit_ist.tz_convert("UTC").value)

        self.clock.set_time_alert_ns("entry", entry_ns, self._on_entry)
        self.clock.set_time_alert_ns("exit", exit_ns, self._on_exit)

    def on_quote_tick(self, tick) -> None:
        if tick.instrument_id == self.spot_id:
            self.latest_spot = float(tick.bid_price)

    def _find_atm_strike(self, spot: float) -> int:
        return int(round(spot / self.strike_step) * self.strike_step)

    def _resolve_option_ids(self, strike: int) -> None:
        ce_sym = f"NIFTY-{strike}-CE-{self.expiry_str}"
        pe_sym = f"NIFTY-{strike}-PE-{self.expiry_str}"
        self.ce_id = InstrumentId(Symbol(ce_sym), Venue("NSE"))
        self.pe_id = InstrumentId(Symbol(pe_sym), Venue("NSE"))

    def _on_entry(self, event) -> None:
        if self.latest_spot <= 0:
            self.log.warning("No spot price at entry time, skipping")
            return

        self.atm_strike = self._find_atm_strike(self.latest_spot)
        self._resolve_option_ids(self.atm_strike)
        self.spot_at_entry = self.latest_spot

        # Verify instruments exist
        if self.cache.instrument(self.ce_id) is None:
            self.log.warning(f"CE instrument {self.ce_id} not found, skipping")
            return
        if self.cache.instrument(self.pe_id) is None:
            self.log.warning(f"PE instrument {self.pe_id} not found, skipping")
            return

        # Subscribe to option ticks (needed for matching engine)
        self.subscribe_quote_ticks(self.ce_id)
        self.subscribe_quote_ticks(self.pe_id)

        qty = Quantity.from_int(self.lot_size * self.num_lots)

        ce_order = self.order_factory.market(
            instrument_id=self.ce_id,
            order_side=OrderSide.SELL,
            quantity=qty,
        )
        pe_order = self.order_factory.market(
            instrument_id=self.pe_id,
            order_side=OrderSide.SELL,
            quantity=qty,
        )

        self.submit_order(ce_order)
        self.submit_order(pe_order)

    def _on_exit(self, event) -> None:
        self.spot_at_exit = self.latest_spot
        for pos in self.cache.positions_open(strategy_id=self.id):
            self.close_position(pos)

    def on_order_filled(self, event: OrderFilled) -> None:
        px = float(event.last_px)
        is_sell = event.order_side == OrderSide.SELL

        if event.instrument_id == self.ce_id:
            if is_sell:
                self.entry_ce_px = px
            else:
                self.exit_ce_px = px
        elif event.instrument_id == self.pe_id:
            if is_sell:
                self.entry_pe_px = px
            else:
                self.exit_pe_px = px

    def get_daily_result(self, date_str: str) -> dict | None:
        """Extract trade result after engine.run(). Called by runner."""
        if any(v is None for v in [
            self.entry_ce_px, self.entry_pe_px, self.exit_ce_px, self.exit_pe_px
        ]):
            return None

        entry_straddle = self.entry_ce_px + self.entry_pe_px
        exit_straddle = self.exit_ce_px + self.exit_pe_px
        pnl = entry_straddle - exit_straddle

        return {
            "date": date_str,
            "atm_strike": self.atm_strike,
            "entry_time": f"{date_str} {self.entry_time}",
            "exit_time": f"{date_str} {self.exit_time}",
            "spot_at_entry": self.spot_at_entry,
            "spot_at_exit": self.spot_at_exit,
            "spot_move": self.spot_at_exit - self.spot_at_entry,
            "spot_move_pct": (self.spot_at_exit - self.spot_at_entry) / self.spot_at_entry * 100
            if self.spot_at_entry > 0 else 0,
            "entry_ce": self.entry_ce_px,
            "entry_pe": self.entry_pe_px,
            "exit_ce": self.exit_ce_px,
            "exit_pe": self.exit_pe_px,
            "entry_straddle": entry_straddle,
            "exit_straddle": exit_straddle,
            "pnl": pnl,
            "pnl_pct": (pnl / entry_straddle) * 100 if entry_straddle > 0 else 0,
        }
