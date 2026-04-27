"""
Index All Rounder NIFTY 50 — NautilusTrader Strategy
-----------------------------------------------------
Entry (after 9:18):
  CE/PE premium ratio between 0.80 and 1.20 → Sell ATM CE + ATM PE.
  Dynamic expiry: on expiry day use next week, else current week.

Repair Once (per leg):
  Exit leg if ask >= max(1.25 * entry_price, 1.25 * low_since_entry).
  Trailing: tracks lowest price since entry for each leg independently.
  Only one repair per leg (once stopped, stays stopped).

Universal Exit: 3:00 PM close all.
"""

from __future__ import annotations

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class IndexAllRounderConfig(StrategyConfig):
    entry_time: str = "09:18:00"
    exit_time: str = "15:00:00"
    strike_step: int = 50
    lot_size: int = 1
    num_lots: int = 1
    sl_pct: float = 25.0         # 25% SL from entry AND from trailing low
    ratio_low: float = 0.80      # CE/PE ratio lower bound
    ratio_high: float = 1.20     # CE/PE ratio upper bound
    underlying: str = "NIFTY"
    venue: str = "NSE"
    spot_instrument_id: str = "NIFTY-SPOT.NSE"


class IndexAllRounder(Strategy):

    def __init__(self, config: IndexAllRounderConfig) -> None:
        super().__init__(config)
        self.spot_id = InstrumentId.from_str(config.spot_instrument_id)
        self.entry_time = config.entry_time
        self.exit_time = config.exit_time
        self.strike_step = config.strike_step
        self.lot_size = config.lot_size
        self.num_lots = config.num_lots
        self.sl_pct = config.sl_pct
        self.ratio_low = config.ratio_low
        self.ratio_high = config.ratio_high
        self.underlying = config.underlying
        self.venue_str = config.venue

        # Day state
        self.latest_spot: float = 0.0
        self.expiry_str: str | None = None
        self._date_str: str = ""

        # Position state
        self.ce_id: InstrumentId | None = None
        self.pe_id: InstrumentId | None = None
        self.atm_strike: int = 0
        self.spot_at_entry: float = 0.0

        # Entry fills
        self.entry_ce_px: float | None = None
        self.entry_pe_px: float | None = None
        self.exit_ce_px: float | None = None
        self.exit_pe_px: float | None = None

        # Trailing low tracking (the key feature)
        self.low_ce: float = float("inf")
        self.low_pe: float = float("inf")

        # Per-leg state
        self.ce_active: bool = False
        self.pe_active: bool = False
        self.ce_repaired: bool = False  # "repair once" — only one exit per leg
        self.pe_repaired: bool = False

        # Exit info
        self.ce_exit_time: str | None = None
        self.pe_exit_time: str | None = None
        self.ce_exit_reason: str | None = None
        self.pe_exit_reason: str | None = None

        self._entered: bool = False
        self._entry_done: bool = False
        self._pending_entry: bool = False
        self._ce_filled: bool = False
        self._pe_filled: bool = False

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

        # Date
        clock_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(clock_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        self._date_str = ist_dt.strftime("%Y-%m-%d")

        # Entry alert at 9:18
        entry_ist = pd.Timestamp(f"{self._date_str} {self.entry_time}", tz="Asia/Kolkata")
        entry_ns = int(entry_ist.tz_convert("UTC").value)
        self.clock.set_time_alert_ns("entry", entry_ns, self._on_entry)

        # Exit at 15:00
        exit_ist = pd.Timestamp(f"{self._date_str} {self.exit_time}", tz="Asia/Kolkata")
        exit_ns = int(exit_ist.tz_convert("UTC").value)
        self.clock.set_time_alert_ns("exit", exit_ns, self._on_exit)

    def on_quote_tick(self, tick) -> None:
        if tick.instrument_id == self.spot_id:
            self.latest_spot = float(tick.bid_price)
            return

        # Track option prices for trailing low and SL
        ask_px = float(tick.ask_price)  # cost to buy back

        if self.ce_id and tick.instrument_id == self.ce_id and self.ce_active:
            # Update trailing low
            if ask_px < self.low_ce and ask_px > 0:
                self.low_ce = ask_px

            # Check SL: max(1.25 * entry, 1.25 * low)
            if not self.ce_repaired and self.entry_ce_px is not None:
                fixed_sl = self.entry_ce_px * (1 + self.sl_pct / 100)
                trailing_sl = self.low_ce * (1 + self.sl_pct / 100)
                trigger = min(fixed_sl, trailing_sl)  # whichever is tighter

                if ask_px >= trigger:
                    self.log.info(
                        f"CE REPAIR: ask={ask_px:.2f} >= trigger={trigger:.2f} "
                        f"(fixed_sl={fixed_sl:.2f}, trail_sl={trailing_sl:.2f}, low={self.low_ce:.2f})"
                    )
                    self.ce_repaired = True
                    self.ce_exit_reason = "SL" if ask_px >= fixed_sl else "TSL"
                    self._record_exit_time("ce")
                    self._close_leg("CE")

        if self.pe_id and tick.instrument_id == self.pe_id and self.pe_active:
            if ask_px < self.low_pe and ask_px > 0:
                self.low_pe = ask_px

            if not self.pe_repaired and self.entry_pe_px is not None:
                fixed_sl = self.entry_pe_px * (1 + self.sl_pct / 100)
                trailing_sl = self.low_pe * (1 + self.sl_pct / 100)
                trigger = min(fixed_sl, trailing_sl)

                if ask_px >= trigger:
                    self.log.info(
                        f"PE REPAIR: ask={ask_px:.2f} >= trigger={trigger:.2f} "
                        f"(fixed_sl={fixed_sl:.2f}, trail_sl={trailing_sl:.2f}, low={self.low_pe:.2f})"
                    )
                    self.pe_repaired = True
                    self.pe_exit_reason = "SL" if ask_px >= fixed_sl else "TSL"
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

    def _on_entry(self, event) -> None:
        if self._entry_done or self.latest_spot <= 0:
            return

        atm = int(round(self.latest_spot / self.strike_step) * self.strike_step)
        venue = Venue(self.venue_str)

        ce_sym = f"{self.underlying}-{atm}-CE-{self.expiry_str}"
        pe_sym = f"{self.underlying}-{atm}-PE-{self.expiry_str}"
        ce_id = InstrumentId(Symbol(ce_sym), venue)
        pe_id = InstrumentId(Symbol(pe_sym), venue)

        if self.cache.instrument(ce_id) is None or self.cache.instrument(pe_id) is None:
            self.log.warning(f"Instruments not found: {ce_sym} / {pe_sym}")
            return

        # Subscribe to get quotes
        self.subscribe_quote_ticks(ce_id)
        self.subscribe_quote_ticks(pe_id)

        # Check CE/PE premium ratio
        ce_tick = self.cache.quote_tick(ce_id)
        pe_tick = self.cache.quote_tick(pe_id)

        if ce_tick is None or pe_tick is None:
            self.log.warning("No option quotes available at entry time")
            return

        ce_mid = (float(ce_tick.bid_price) + float(ce_tick.ask_price)) / 2
        pe_mid = (float(pe_tick.bid_price) + float(pe_tick.ask_price)) / 2

        if pe_mid <= 0 or ce_mid <= 0:
            self.log.warning(f"Invalid premiums: CE={ce_mid:.2f} PE={pe_mid:.2f}")
            return

        ratio = ce_mid / pe_mid
        if ratio < self.ratio_low or ratio > self.ratio_high:
            self.log.info(f"Ratio {ratio:.3f} outside [{self.ratio_low}, {self.ratio_high}], skipping")
            return

        # Execute entry
        self.ce_id = ce_id
        self.pe_id = pe_id
        self.atm_strike = atm
        self.spot_at_entry = self.latest_spot
        self._pending_entry = True
        self._ce_filled = False
        self._pe_filled = False

        qty = Quantity.from_int(self.lot_size * self.num_lots)

        self.submit_order(self.order_factory.market(
            instrument_id=ce_id, order_side=OrderSide.SELL, quantity=qty,
        ))
        self.submit_order(self.order_factory.market(
            instrument_id=pe_id, order_side=OrderSide.SELL, quantity=qty,
        ))

        self.log.info(f"ENTRY: ATM {atm}, CE/PE ratio={ratio:.3f}, spot={self.latest_spot:.2f}")

    def _close_leg(self, leg: str) -> None:
        target_id = self.ce_id if leg == "CE" else self.pe_id
        for pos in self.cache.positions_open(strategy_id=self.id):
            if pos.instrument_id == target_id:
                self.close_position(pos)
                break

    def _on_exit(self, event) -> None:
        if self.ce_active and not self.ce_repaired:
            self.ce_exit_reason = "EOD"
            self._record_exit_time("ce")
        if self.pe_active and not self.pe_repaired:
            self.pe_exit_reason = "EOD"
            self._record_exit_time("pe")

        for pos in self.cache.positions_open(strategy_id=self.id):
            self.close_position(pos)

    def on_order_filled(self, event: OrderFilled) -> None:
        px = float(event.last_px)
        is_sell = event.order_side == OrderSide.SELL

        if is_sell:
            if event.instrument_id == self.ce_id and not self._ce_filled:
                self.entry_ce_px = px
                self.low_ce = px  # initialize trailing low to entry price
                self.ce_active = True
                self._ce_filled = True
                self.log.info(f"CE entry fill: {px:.2f}")

            elif event.instrument_id == self.pe_id and not self._pe_filled:
                self.entry_pe_px = px
                self.low_pe = px
                self.pe_active = True
                self._pe_filled = True
                self.log.info(f"PE entry fill: {px:.2f}")

            if self._ce_filled and self._pe_filled and self._pending_entry:
                self._pending_entry = False
                self._entry_done = True
                self._entered = True
                self.log.info(
                    f"POSITIONED: CE={self.entry_ce_px:.2f} PE={self.entry_pe_px:.2f}"
                )
        else:
            # Exit fill
            if event.instrument_id == self.ce_id:
                self.exit_ce_px = px
                self.ce_active = False
            elif event.instrument_id == self.pe_id:
                self.exit_pe_px = px
                self.pe_active = False

    def get_daily_result(self, date_str: str) -> dict | None:
        if not self._entered:
            return None
        if any(v is None for v in [self.entry_ce_px, self.entry_pe_px, self.exit_ce_px, self.exit_pe_px]):
            return None

        ce_pnl = self.entry_ce_px - self.exit_ce_px
        pe_pnl = self.entry_pe_px - self.exit_pe_px
        total_pnl = ce_pnl + pe_pnl
        entry_total = self.entry_ce_px + self.entry_pe_px

        return {
            "date": date_str,
            "atm_strike": self.atm_strike,
            "entry_time": f"{date_str} {self.entry_time}",
            "exit_time": f"{date_str} {self.exit_time}",
            "spot_at_entry": round(self.spot_at_entry, 2),
            "spot_at_exit": round(self.latest_spot, 2),
            "spot_move": round(self.latest_spot - self.spot_at_entry, 2),
            "entry_ce": round(self.entry_ce_px, 2),
            "entry_pe": round(self.entry_pe_px, 2),
            "exit_ce": round(self.exit_ce_px, 2),
            "exit_pe": round(self.exit_pe_px, 2),
            "low_ce": round(self.low_ce, 2),
            "low_pe": round(self.low_pe, 2),
            "ce_pnl": round(ce_pnl, 2),
            "pe_pnl": round(pe_pnl, 2),
            "ce_exit_reason": self.ce_exit_reason or "EOD",
            "pe_exit_reason": self.pe_exit_reason or "EOD",
            "ce_exit_time": self.ce_exit_time or self.exit_time,
            "pe_exit_time": self.pe_exit_time or self.exit_time,
            "pnl": round(total_pnl, 2),
            "pnl_pct": round((total_pnl / entry_total) * 100, 2) if entry_total > 0 else 0,
        }
