"""
Vanilla ATM Straddle Sell Strategy — NautilusTrader
---------------------------------------------------
Rule A (Initial Entry):
  After 9:21 on 3-min intervals (9:21, 9:24, ...).
  Condition: |ATM CE price - ATM PE price| < 20.
  Action: Sell 1 ATM CE + 1 ATM PE (current week expiry).

Rule B (Re-Entry after spot exit):
  If already exited today due to spot move, re-enter new ATM straddle
  if spot moves > original_combined_premium / 2 from last entry spot.

Exit:
  DTE <= 1: spot moves from last entry spot > combined_premium / 2.
  DTE > 1:  spot moves from last entry spot > combined_premium / 3.

Universal Exit:
  3:10 PM close all.
  Day loss >= 50 pts close all (loss limit).
"""

from __future__ import annotations

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class VanillaStraddleConfig(StrategyConfig):
    first_entry_time: str = "09:21:00"
    final_exit_time: str = "15:10:00"
    entry_interval_min: int = 3
    skew_threshold: float = 20.0   # |CE - PE| < this to enter
    strike_step: int = 50
    lot_size: int = 1
    num_lots: int = 1
    day_loss_limit: float = 50.0   # max cumulative day loss in points
    underlying: str = "NIFTY"
    venue: str = "NSE"
    spot_instrument_id: str = "NIFTY-SPOT.NSE"


class VanillaStraddle(Strategy):

    def __init__(self, config: VanillaStraddleConfig) -> None:
        super().__init__(config)
        self.spot_id = InstrumentId.from_str(config.spot_instrument_id)
        self.first_entry_time = config.first_entry_time
        self.final_exit_time = config.final_exit_time
        self.entry_interval_min = config.entry_interval_min
        self.skew_threshold = config.skew_threshold
        self.strike_step = config.strike_step
        self.lot_size = config.lot_size
        self.num_lots = config.num_lots
        self.day_loss_limit = config.day_loss_limit
        self.underlying = config.underlying
        self.venue_str = config.venue

        # Day state
        self.latest_spot: float = 0.0
        self.expiry_str: str | None = None
        self.dte: int = 0
        self._date_str: str = ""

        # Current position state
        self.is_positioned: bool = False
        self.ce_id: InstrumentId | None = None
        self.pe_id: InstrumentId | None = None
        self.ce_strike: int = 0
        self.pe_strike: int = 0
        self.entry_spot: float = 0.0
        self.entry_ce_px: float = 0.0
        self.entry_pe_px: float = 0.0
        self.combined_premium: float = 0.0
        self.exit_trigger: float = 0.0  # spot move threshold
        self._ce_filled: bool = False
        self._pe_filled: bool = False

        # Re-entry state
        self.original_combined_premium: float = 0.0  # from FIRST entry of the day
        self.has_exited_today: bool = False
        self.re_entry_allowed: bool = True

        # Day P&L tracking
        self.day_pnl: float = 0.0
        self.day_stopped: bool = False  # hit day loss limit

        # Trade log for results
        self._trades: list[dict] = []
        self._current_trade: dict | None = None

        # Pending fills
        self._pending_entry: bool = False
        self._pending_exit: bool = False

        # Entry scan state
        self._initial_entry_done: bool = False
        self._entry_scan_active: bool = True

    def on_start(self) -> None:
        self.subscribe_quote_ticks(self.spot_id)

        # Discover expiry and compute DTE
        for inst in self.cache.instruments(venue=Venue(self.venue_str)):
            sym = str(inst.id.symbol)
            if sym.startswith(f"{self.underlying}-") and sym != f"{self.underlying}-SPOT":
                parts = sym.split("-")
                if len(parts) == 4:
                    self.expiry_str = parts[3]
                    break

        # Date and DTE
        clock_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(clock_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        self._date_str = ist_dt.strftime("%Y-%m-%d")

        if self.expiry_str:
            expiry_date = pd.Timestamp(
                f"{self.expiry_str[:4]}-{self.expiry_str[4:6]}-{self.expiry_str[6:8]}"
            ).date()
            trading_date = ist_dt.date()
            self.dte = (expiry_date - trading_date).days
            self.log.info(f"DTE={self.dte}, expiry={self.expiry_str}")

        # Schedule entry scan alerts every 3 min from 09:21 to 15:07
        h, m, s = 9, 21, 0
        alert_idx = 0
        while h < 15 or (h == 15 and m <= 7):
            t_str = f"{h:02d}:{m:02d}:{s:02d}"
            ist = pd.Timestamp(f"{self._date_str} {t_str}", tz="Asia/Kolkata")
            ns = int(ist.tz_convert("UTC").value)
            self.clock.set_time_alert_ns(f"scan_{alert_idx}", ns, self._on_scan_tick)
            alert_idx += 1
            m += self.entry_interval_min
            if m >= 60:
                h += 1
                m -= 60

        # Universal exit at 15:10
        exit_ist = pd.Timestamp(f"{self._date_str} {self.final_exit_time}", tz="Asia/Kolkata")
        exit_ns = int(exit_ist.tz_convert("UTC").value)
        self.clock.set_time_alert_ns("final_exit", exit_ns, self._on_final_exit)

    def on_quote_tick(self, tick) -> None:
        if tick.instrument_id == self.spot_id:
            self.latest_spot = float(tick.bid_price)

            # Check spot-based exit if positioned
            if self.is_positioned and not self._pending_exit and self.exit_trigger > 0:
                spot_move = abs(self.latest_spot - self.entry_spot)
                if spot_move > self.exit_trigger:
                    self.log.info(
                        f"Spot exit: move={spot_move:.2f} > trigger={self.exit_trigger:.2f}"
                    )
                    self._exit_position("SPOT_MOVE")

            # Check re-entry condition if exited
            if (
                self.has_exited_today
                and not self.is_positioned
                and self.re_entry_allowed
                and not self.day_stopped
                and not self._pending_entry
                and self.original_combined_premium > 0
            ):
                spot_move = abs(self.latest_spot - self.entry_spot)
                re_entry_trigger = self.original_combined_premium / 2
                if spot_move > re_entry_trigger:
                    self.log.info(
                        f"Re-entry trigger: move={spot_move:.2f} > {re_entry_trigger:.2f}"
                    )
                    self._attempt_entry()

            return

        # Track option prices (for mid-price skew check on entry)
        # Not used for SL — exit is purely spot-based

    def _on_scan_tick(self, event) -> None:
        """Called every 3 min. Attempts initial entry if not yet positioned."""
        if self._initial_entry_done or self.is_positioned or self.day_stopped:
            return
        if self._pending_entry or self._pending_exit:
            return
        self._attempt_entry()

    def _attempt_entry(self) -> None:
        """Try to enter ATM straddle. Checks skew condition for initial entry."""
        if self.latest_spot <= 0 or self.day_stopped:
            return

        atm_strike = int(round(self.latest_spot / self.strike_step) * self.strike_step)
        venue = Venue(self.venue_str)

        ce_sym = f"{self.underlying}-{atm_strike}-CE-{self.expiry_str}"
        pe_sym = f"{self.underlying}-{atm_strike}-PE-{self.expiry_str}"
        ce_id = InstrumentId(Symbol(ce_sym), venue)
        pe_id = InstrumentId(Symbol(pe_sym), venue)

        # Verify instruments exist
        if self.cache.instrument(ce_id) is None or self.cache.instrument(pe_id) is None:
            return

        # Subscribe if not already
        self.subscribe_quote_ticks(ce_id)
        self.subscribe_quote_ticks(pe_id)

        # Get latest quotes for skew check (initial entry only)
        if not self._initial_entry_done:
            ce_tick = self.cache.quote_tick(ce_id)
            pe_tick = self.cache.quote_tick(pe_id)

            if ce_tick is None or pe_tick is None:
                return

            ce_mid = (float(ce_tick.bid_price) + float(ce_tick.ask_price)) / 2
            pe_mid = (float(pe_tick.bid_price) + float(pe_tick.ask_price)) / 2

            skew = abs(ce_mid - pe_mid)
            if skew >= self.skew_threshold:
                self.log.info(f"Skew too high: {skew:.2f} >= {self.skew_threshold}, skip")
                return

        # Execute entry
        self.ce_id = ce_id
        self.pe_id = pe_id
        self.ce_strike = atm_strike
        self.pe_strike = atm_strike
        self.entry_spot = self.latest_spot
        self._ce_filled = False
        self._pe_filled = False
        self._pending_entry = True

        qty = Quantity.from_int(self.lot_size * self.num_lots)

        ce_order = self.order_factory.market(
            instrument_id=self.ce_id, order_side=OrderSide.SELL, quantity=qty,
        )
        pe_order = self.order_factory.market(
            instrument_id=self.pe_id, order_side=OrderSide.SELL, quantity=qty,
        )

        self.submit_order(ce_order)
        self.submit_order(pe_order)

        self.log.info(f"ENTRY orders submitted: ATM {atm_strike} at spot={self.latest_spot:.2f}")

    def _exit_position(self, reason: str) -> None:
        """Close all open positions."""
        if self._pending_exit:
            return
        self._pending_exit = True

        self.log.info(f"EXIT: reason={reason}")

        for pos in self.cache.positions_open(strategy_id=self.id):
            self.close_position(pos)

    def _on_final_exit(self, event) -> None:
        """3:10 PM — close everything."""
        if self.is_positioned:
            self._exit_position("EOD")
        self.re_entry_allowed = False

    def on_order_filled(self, event: OrderFilled) -> None:
        px = float(event.last_px)
        is_sell = event.order_side == OrderSide.SELL

        if is_sell:
            # Entry fill
            if event.instrument_id == self.ce_id and not self._ce_filled:
                self.entry_ce_px = px
                self._ce_filled = True
                self.log.info(f"CE entry fill: {px:.2f}")
            elif event.instrument_id == self.pe_id and not self._pe_filled:
                self.entry_pe_px = px
                self._pe_filled = True
                self.log.info(f"PE entry fill: {px:.2f}")

            # Both legs filled — position is live
            if self._ce_filled and self._pe_filled and self._pending_entry:
                self._pending_entry = False
                self.is_positioned = True
                self.combined_premium = self.entry_ce_px + self.entry_pe_px

                if not self._initial_entry_done:
                    self.original_combined_premium = self.combined_premium
                    self._initial_entry_done = True

                # Compute exit trigger
                if self.dte <= 1:
                    self.exit_trigger = self.combined_premium / 2
                else:
                    self.exit_trigger = self.combined_premium / 3

                self._current_trade = {
                    "entry_spot": self.entry_spot,
                    "ce_strike": self.ce_strike,
                    "pe_strike": self.pe_strike,
                    "entry_ce": self.entry_ce_px,
                    "entry_pe": self.entry_pe_px,
                    "combined_premium": self.combined_premium,
                    "exit_trigger": self.exit_trigger,
                }

                self.log.info(
                    f"POSITIONED: CE={self.entry_ce_px:.2f} PE={self.entry_pe_px:.2f} "
                    f"combined={self.combined_premium:.2f} trigger={self.exit_trigger:.2f}"
                )
        else:
            # Exit fill (BUY to close)
            if event.instrument_id == self.ce_id:
                exit_ce = px
                ce_pnl = self.entry_ce_px - exit_ce
                if self._current_trade:
                    self._current_trade["exit_ce"] = exit_ce
                    self._current_trade["ce_pnl"] = round(ce_pnl, 2)

            elif event.instrument_id == self.pe_id:
                exit_pe = px
                pe_pnl = self.entry_pe_px - exit_pe
                if self._current_trade:
                    self._current_trade["exit_pe"] = exit_pe
                    self._current_trade["pe_pnl"] = round(pe_pnl, 2)

            # Check if fully exited
            open_positions = list(self.cache.positions_open(strategy_id=self.id))
            if len(open_positions) == 0 and self._pending_exit:
                self._pending_exit = False
                self.is_positioned = False

                if self._current_trade and "exit_ce" in self._current_trade and "exit_pe" in self._current_trade:
                    trade_pnl = self._current_trade["ce_pnl"] + self._current_trade["pe_pnl"]
                    self._current_trade["pnl"] = round(trade_pnl, 2)
                    self._current_trade["exit_spot"] = self.latest_spot
                    self._current_trade["exit_time"] = self._get_ist_time_str()
                    self._trades.append(self._current_trade)
                    self._current_trade = None

                    self.day_pnl += trade_pnl
                    self.has_exited_today = True

                    self.log.info(f"Trade closed: pnl={trade_pnl:.2f}, day_pnl={self.day_pnl:.2f}")

                    # Check day loss limit
                    if self.day_pnl <= -self.day_loss_limit:
                        self.log.info(f"DAY LOSS LIMIT: {self.day_pnl:.2f} <= -{self.day_loss_limit}")
                        self.day_stopped = True
                        self.re_entry_allowed = False

    def _get_ist_time_str(self) -> str:
        ts_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(ts_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        return ist_dt.strftime("%H:%M:%S")

    def get_daily_result(self, date_str: str) -> list[dict] | None:
        """Return list of trades for the day (multiple entries possible)."""
        if not self._trades:
            return None

        results = []
        for i, t in enumerate(self._trades):
            results.append({
                "date": date_str,
                "trade_num": i + 1,
                "dte": self.dte,
                "atm_strike": t["ce_strike"],
                "entry_spot": round(t["entry_spot"], 2),
                "exit_spot": round(t.get("exit_spot", 0), 2),
                "entry_ce": round(t["entry_ce"], 2),
                "entry_pe": round(t["entry_pe"], 2),
                "exit_ce": round(t.get("exit_ce", 0), 2),
                "exit_pe": round(t.get("exit_pe", 0), 2),
                "combined_premium": round(t["combined_premium"], 2),
                "exit_trigger": round(t["exit_trigger"], 2),
                "ce_pnl": t.get("ce_pnl", 0),
                "pe_pnl": t.get("pe_pnl", 0),
                "pnl": t.get("pnl", 0),
                "exit_time": t.get("exit_time", self.final_exit_time),
                "exit_reason": "DAY_LOSS" if self.day_stopped and i == len(self._trades) - 1
                    else "SPOT_MOVE" if t.get("exit_spot", 0) != 0 and t.get("exit_time", "") != self.final_exit_time
                    else "EOD",
                "day_pnl": round(self.day_pnl, 2),
            })

        return results
