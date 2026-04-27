"""
OTM1 Strangle Sell Strategy — NautilusTrader
---------------------------------------------
At 09:21 IST: find ATM strike, then sell OTM1 CE (ATM + step) and OTM1 PE (ATM - step).
Each leg has an independent stop-loss (SL% above entry price for that leg).
If one leg is stopped out, the other continues independently.
At 15:00 IST: close any remaining open positions.

CE and PE have DIFFERENT strikes (OTM 1 on each side).
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
    lot_size: int = 1
    num_lots: int = 1
    sl_pct: float = 30.0  # SL as % above entry premium for each leg
    underlying: str = "NIFTY"
    venue: str = "NSE"
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
        self.sl_pct = config.sl_pct
        self.underlying = config.underlying
        self.venue_str = config.venue

        # State — reset each day
        self.latest_spot: float = 0.0
        self.ce_strike: int | None = None
        self.pe_strike: int | None = None
        self.ce_id: InstrumentId | None = None
        self.pe_id: InstrumentId | None = None
        self.expiry_str: str | None = None

        # Fill tracking
        self.entry_ce_px: float | None = None
        self.entry_pe_px: float | None = None
        self.exit_ce_px: float | None = None
        self.exit_pe_px: float | None = None
        self.spot_at_entry: float = 0.0
        self.spot_at_exit: float = 0.0

        # Per-leg SL tracking
        self.ce_sl: float = 0.0  # SL price for CE leg
        self.pe_sl: float = 0.0  # SL price for PE leg
        self.ce_stopped: bool = False
        self.pe_stopped: bool = False
        self.ce_active: bool = False
        self.pe_active: bool = False

        # Exit tracking
        self.ce_exit_time: str | None = None
        self.pe_exit_time: str | None = None
        self.ce_exit_reason: str | None = None
        self.pe_exit_reason: str | None = None

        # Latest option prices for SL monitoring
        self._latest_ce_px: float = 0.0
        self._latest_pe_px: float = 0.0

        self._date_str: str = ""
        self._entered: bool = False

    def on_start(self) -> None:
        self.subscribe_quote_ticks(self.spot_id)

        # Discover expiry from loaded option instruments
        for inst in self.cache.instruments(venue=Venue(self.venue_str)):
            sym = str(inst.id.symbol)
            if sym.startswith(f"{self.underlying}-") and sym != f"{self.underlying}-SPOT":
                parts = sym.split("-")
                if len(parts) == 4:
                    self.expiry_str = parts[3]
                    break

        # Determine trading date from clock
        clock_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(clock_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        self._date_str = ist_dt.strftime("%Y-%m-%d")

        # Set entry/exit alerts
        entry_ist = pd.Timestamp(f"{self._date_str} {self.entry_time}", tz="Asia/Kolkata")
        exit_ist = pd.Timestamp(f"{self._date_str} {self.exit_time}", tz="Asia/Kolkata")

        entry_ns = int(entry_ist.tz_convert("UTC").value)
        exit_ns = int(exit_ist.tz_convert("UTC").value)

        self.clock.set_time_alert_ns("entry", entry_ns, self._on_entry)
        self.clock.set_time_alert_ns("exit", exit_ns, self._on_exit)

    def on_quote_tick(self, tick) -> None:
        if tick.instrument_id == self.spot_id:
            self.latest_spot = float(tick.bid_price)
            return

        # Monitor option prices for SL
        px = float(tick.ask_price)  # ask = cost to buy back short

        if self.ce_id and tick.instrument_id == self.ce_id:
            self._latest_ce_px = px
            if self.ce_active and not self.ce_stopped and self.ce_sl > 0:
                if px >= self.ce_sl:
                    self.log.info(
                        f"CE SL triggered: price={px:.2f} >= sl={self.ce_sl:.2f}"
                    )
                    self.ce_stopped = True
                    self.ce_exit_reason = "SL"
                    self._record_exit_time("ce")
                    self._close_leg("CE")

        if self.pe_id and tick.instrument_id == self.pe_id:
            self._latest_pe_px = px
            if self.pe_active and not self.pe_stopped and self.pe_sl > 0:
                if px >= self.pe_sl:
                    self.log.info(
                        f"PE SL triggered: price={px:.2f} >= sl={self.pe_sl:.2f}"
                    )
                    self.pe_stopped = True
                    self.pe_exit_reason = "SL"
                    self._record_exit_time("pe")
                    self._close_leg("PE")

    def _record_exit_time(self, leg: str) -> None:
        ts_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(ts_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        t = ist_dt.strftime("%H:%M:%S")
        if leg == "ce":
            self.ce_exit_time = t
        else:
            self.pe_exit_time = t

    def _find_otm_strikes(self, spot: float) -> tuple[int, int]:
        """OTM1 CE = ATM + step, OTM1 PE = ATM - step."""
        atm = int(round(spot / self.strike_step) * self.strike_step)
        ce_strike = atm + self.strike_step
        pe_strike = atm - self.strike_step
        return ce_strike, pe_strike

    def _on_entry(self, event) -> None:
        if self.latest_spot <= 0:
            self.log.warning("No spot price at entry time, skipping")
            return

        ce_strike, pe_strike = self._find_otm_strikes(self.latest_spot)
        self.ce_strike = ce_strike
        self.pe_strike = pe_strike
        self.spot_at_entry = self.latest_spot

        # Resolve instrument IDs
        venue = Venue(self.venue_str)
        ce_sym = f"{self.underlying}-{ce_strike}-CE-{self.expiry_str}"
        pe_sym = f"{self.underlying}-{pe_strike}-PE-{self.expiry_str}"
        self.ce_id = InstrumentId(Symbol(ce_sym), venue)
        self.pe_id = InstrumentId(Symbol(pe_sym), venue)

        # Verify instruments exist
        if self.cache.instrument(self.ce_id) is None:
            self.log.warning(f"CE instrument {self.ce_id} not found, skipping")
            return
        if self.cache.instrument(self.pe_id) is None:
            self.log.warning(f"PE instrument {self.pe_id} not found, skipping")
            return

        # Subscribe to option ticks for SL monitoring
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
        self._entered = True

        self.log.info(
            f"ENTRY: CE {ce_strike} + PE {pe_strike} at spot={self.latest_spot:.2f}"
        )

    def _close_leg(self, leg: str) -> None:
        """Close a specific leg's position."""
        target_id = self.ce_id if leg == "CE" else self.pe_id
        for pos in self.cache.positions_open(strategy_id=self.id):
            if pos.instrument_id == target_id:
                self.close_position(pos)
                break

    def _on_exit(self, event) -> None:
        self.spot_at_exit = self.latest_spot

        # Close any remaining open legs
        if self.ce_active and not self.ce_stopped:
            self.ce_exit_reason = "EOD"
            self._record_exit_time("ce")

        if self.pe_active and not self.pe_stopped:
            self.pe_exit_reason = "EOD"
            self._record_exit_time("pe")

        for pos in self.cache.positions_open(strategy_id=self.id):
            self.close_position(pos)

    def on_order_filled(self, event: OrderFilled) -> None:
        px = float(event.last_px)
        is_sell = event.order_side == OrderSide.SELL

        if event.instrument_id == self.ce_id:
            if is_sell:
                self.entry_ce_px = px
                self.ce_sl = round(px * (1 + self.sl_pct / 100), 2)
                self.ce_active = True
                self.log.info(f"CE filled at {px:.2f}, SL at {self.ce_sl:.2f}")
            else:
                self.exit_ce_px = px
                self.ce_active = False
        elif event.instrument_id == self.pe_id:
            if is_sell:
                self.entry_pe_px = px
                self.pe_sl = round(px * (1 + self.sl_pct / 100), 2)
                self.pe_active = True
                self.log.info(f"PE filled at {px:.2f}, SL at {self.pe_sl:.2f}")
            else:
                self.exit_pe_px = px
                self.pe_active = False

    def get_daily_result(self, date_str: str) -> dict | None:
        """Extract trade result after engine.run(). Called by runner."""
        if not self._entered:
            return None
        if any(v is None for v in [
            self.entry_ce_px, self.entry_pe_px, self.exit_ce_px, self.exit_pe_px
        ]):
            return None

        ce_pnl = self.entry_ce_px - self.exit_ce_px
        pe_pnl = self.entry_pe_px - self.exit_pe_px
        total_pnl = ce_pnl + pe_pnl

        entry_total = self.entry_ce_px + self.entry_pe_px

        return {
            "date": date_str,
            "ce_strike": self.ce_strike,
            "pe_strike": self.pe_strike,
            "entry_time": f"{date_str} {self.entry_time}",
            "exit_time": f"{date_str} {self.exit_time}",
            "spot_at_entry": round(self.spot_at_entry, 2),
            "spot_at_exit": round(self.spot_at_exit, 2),
            "spot_move": round(self.spot_at_exit - self.spot_at_entry, 2),
            "spot_move_pct": round(
                (self.spot_at_exit - self.spot_at_entry) / self.spot_at_entry * 100, 2
            ) if self.spot_at_entry > 0 else 0,
            "entry_ce": self.entry_ce_px,
            "entry_pe": self.entry_pe_px,
            "exit_ce": self.exit_ce_px,
            "exit_pe": self.exit_pe_px,
            "ce_sl": self.ce_sl,
            "pe_sl": self.pe_sl,
            "ce_pnl": round(ce_pnl, 2),
            "pe_pnl": round(pe_pnl, 2),
            "ce_exit_reason": self.ce_exit_reason or "EOD",
            "pe_exit_reason": self.pe_exit_reason or "EOD",
            "ce_exit_time": f"{date_str} {self.ce_exit_time}" if self.ce_exit_time else f"{date_str} {self.exit_time}",
            "pe_exit_time": f"{date_str} {self.pe_exit_time}" if self.pe_exit_time else f"{date_str} {self.exit_time}",
            "pnl": round(total_pnl, 2),
            "pnl_pct": round((total_pnl / entry_total) * 100, 2) if entry_total > 0 else 0,
        }
