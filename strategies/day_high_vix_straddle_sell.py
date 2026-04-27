"""
Day High VIX ATM Straddle Sell Strategy — NautilusTrader
--------------------------------------------------------
After 09:15 IST on a 3-min timeframe:
  1. Track India VIX rolling day high on 3-min bar closes.
  2. When VIX forms a new day high and then pulls back pullback_pct% → sell ATM NIFTY straddle.
  3. ATM strike = round(spot / strike_step) * strike_step at signal time.
  4. Stop-loss: straddle premium rises sl_pct% above entry premium → EXIT both legs.
  5. After exit, RESET: continue tracking VIX day high, re-enter on next pullback signal.
  6. At 15:15 IST: close any remaining open positions.

Signal is on VIX (fear gauge), execution is on NIFTY ATM straddle.
VIX day high = peak fear → pullback = vol crush → sell premium.
"""

from __future__ import annotations

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class DayHighVixStraddleSellConfig(StrategyConfig):
    start_time: str = "09:15:00"
    exit_time: str = "15:15:00"
    bar_interval_minutes: int = 3
    pullback_pct: float = 2.0        # VIX pullback % from day high to trigger entry
    sl_pct: float = 30.0             # SL as % above straddle entry premium
    strike_step: int = 50
    lot_size: int = 1
    num_lots: int = 1
    underlying: str = "NIFTY"
    venue: str = "NSE"
    spot_instrument_id: str = "NIFTY-SPOT.NSE"
    vix_instrument_id: str = "VIX-SPOT.NSE"


class DayHighVixStraddleSell(Strategy):

    def __init__(self, config: DayHighVixStraddleSellConfig) -> None:
        super().__init__(config)
        self.spot_id = InstrumentId.from_str(config.spot_instrument_id)
        self.vix_id = InstrumentId.from_str(config.vix_instrument_id)
        self.start_time = config.start_time
        self.exit_time = config.exit_time
        self.bar_interval = config.bar_interval_minutes
        self.pullback_pct = config.pullback_pct
        self.sl_pct = config.sl_pct
        self.strike_step = config.strike_step
        self.lot_size = config.lot_size
        self.num_lots = config.num_lots
        self.underlying = config.underlying
        self.venue_str = config.venue

        # VIX bar building state
        self._vix_bar_high: float = 0.0
        self._vix_bar_close: float = 0.0
        self._vix_bar_start_ns: int = 0
        self._vix_bar_tick_count: int = 0

        # VIX day tracking
        self.latest_vix: float = 0.0
        self.vix_day_high: float = 0.0
        self.signal_vix_high: float = 0.0
        self.vix_pullback_level: float = 0.0

        # Spot tracking
        self.latest_spot: float = 0.0

        # Position state
        self.is_entered: bool = False
        self.ce_id: InstrumentId | None = None
        self.pe_id: InstrumentId | None = None
        self.ce_strike: int | None = None
        self.pe_strike: int | None = None
        self.expiry_str: str | None = None

        # SL on straddle premium
        self.straddle_sl: float = 0.0
        self._latest_ce_px: float = 0.0
        self._latest_pe_px: float = 0.0
        self.ce_active: bool = False
        self.pe_active: bool = False

        # Fill tracking
        self._cur_entry_ce_px: float | None = None
        self._cur_entry_pe_px: float | None = None
        self._cur_exit_ce_px: float | None = None
        self._cur_exit_pe_px: float | None = None
        self._cur_spot_at_entry: float = 0.0
        self._cur_spot_at_exit: float = 0.0
        self._cur_vix_at_entry: float = 0.0
        self._cur_vix_at_exit: float = 0.0
        self._cur_entry_time: str | None = None
        self._cur_exit_time: str | None = None
        self._cur_exit_reason: str | None = None
        self._cur_vix_day_high: float = 0.0
        self._cur_vix_pullback: float = 0.0
        self._cur_ce_strike: int | None = None
        self._cur_pe_strike: int | None = None

        self._trades: list[dict] = []

        self._date_str: str = ""
        self._trading_started: bool = False
        self._eod_triggered: bool = False
        self._bar_interval_ns: int = self.bar_interval * 60 * 1_000_000_000
        self._pending_exit: bool = False
        self._exit_fills_needed: int = 0

    def on_start(self) -> None:
        self.subscribe_quote_ticks(self.spot_id)
        self.subscribe_quote_ticks(self.vix_id)

        # Discover expiry
        for inst in self.cache.instruments(venue=Venue(self.venue_str)):
            sym = str(inst.id.symbol)
            if sym.startswith(f"{self.underlying}-") and sym != f"{self.underlying}-SPOT":
                parts = sym.split("-")
                if len(parts) == 4:
                    self.expiry_str = parts[3]
                    break

        clock_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(clock_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        self._date_str = ist_dt.strftime("%Y-%m-%d")

        start_ist = pd.Timestamp(f"{self._date_str} {self.start_time}", tz="Asia/Kolkata")
        exit_ist = pd.Timestamp(f"{self._date_str} {self.exit_time}", tz="Asia/Kolkata")

        self.clock.set_time_alert_ns("trading_start", int(start_ist.tz_convert("UTC").value), self._on_trading_start)
        self.clock.set_time_alert_ns("exit", int(exit_ist.tz_convert("UTC").value), self._on_exit)

    def _on_trading_start(self, event) -> None:
        self._trading_started = True
        self.log.info("Trading session started — monitoring VIX day high for ATM straddle entry")

    def on_quote_tick(self, tick) -> None:
        # Spot tick — just track price
        if tick.instrument_id == self.spot_id:
            self.latest_spot = float(tick.bid_price)
            return

        # VIX tick — drive bar building and entry logic
        if tick.instrument_id == self.vix_id:
            self.latest_vix = float(tick.bid_price)

            if not self._trading_started:
                return

            ts_ns = tick.ts_event

            if self._vix_bar_tick_count == 0:
                self._vix_bar_high = self.latest_vix
                self._vix_bar_close = self.latest_vix
                self._vix_bar_start_ns = ts_ns
                self._vix_bar_tick_count = 1
                return

            self._vix_bar_high = max(self._vix_bar_high, self.latest_vix)
            self._vix_bar_close = self.latest_vix
            self._vix_bar_tick_count += 1

            elapsed = ts_ns - self._vix_bar_start_ns
            if elapsed >= self._bar_interval_ns:
                self._on_vix_bar_close()
                self._vix_bar_high = self.latest_vix
                self._vix_bar_close = self.latest_vix
                self._vix_bar_start_ns = ts_ns
                self._vix_bar_tick_count = 1

            return

        # Option tick — monitor SL on straddle premium
        if self.is_entered and not self._pending_exit:
            px = float(tick.ask_price)
            if self.ce_id and tick.instrument_id == self.ce_id:
                self._latest_ce_px = px
            elif self.pe_id and tick.instrument_id == self.pe_id:
                self._latest_pe_px = px

            # Check straddle SL
            if self._latest_ce_px > 0 and self._latest_pe_px > 0:
                current_straddle = self._latest_ce_px + self._latest_pe_px
                if self.straddle_sl > 0 and current_straddle >= self.straddle_sl:
                    self.log.info(
                        f"Straddle SL triggered: {current_straddle:.2f} >= {self.straddle_sl:.2f}"
                    )
                    self._close_positions("SL")

    def _on_vix_bar_close(self) -> None:
        """Called when a 3-min VIX bar completes."""
        if self._eod_triggered or self.is_entered or self._pending_exit:
            return

        vix_bar_close = self._vix_bar_close
        prev_high = self.vix_day_high

        # Update VIX day high from bar high
        if self._vix_bar_high > self.vix_day_high:
            self.vix_day_high = self._vix_bar_high

        # New VIX day high formed?
        if self.vix_day_high > prev_high and prev_high > 0:
            self.signal_vix_high = self.vix_day_high
            self.vix_pullback_level = self.vix_day_high * (1 - self.pullback_pct / 100)
            self.log.info(
                f"VIX new day high={self.vix_day_high:.4f}, "
                f"pullback level={self.vix_pullback_level:.4f}"
            )

        # Check VIX pullback entry
        if self.vix_pullback_level > 0 and vix_bar_close <= self.vix_pullback_level:
            self.log.info(
                f"VIX PULLBACK ENTRY: bar_close={vix_bar_close:.4f} <= "
                f"pullback={self.vix_pullback_level:.4f} (vix_high={self.signal_vix_high:.4f})"
            )
            self._enter_position()

    def _enter_position(self) -> None:
        if self.is_entered or self.latest_spot <= 0:
            return

        # ATM strike
        atm_strike = int(round(self.latest_spot / self.strike_step) * self.strike_step)
        self.ce_strike = atm_strike
        self.pe_strike = atm_strike
        self._cur_ce_strike = atm_strike
        self._cur_pe_strike = atm_strike
        self._cur_spot_at_entry = self.latest_spot
        self._cur_vix_at_entry = self.latest_vix
        self._cur_vix_day_high = self.signal_vix_high
        self._cur_vix_pullback = self.vix_pullback_level

        venue = Venue(self.venue_str)
        ce_sym = f"{self.underlying}-{atm_strike}-CE-{self.expiry_str}"
        pe_sym = f"{self.underlying}-{atm_strike}-PE-{self.expiry_str}"
        self.ce_id = InstrumentId(Symbol(ce_sym), venue)
        self.pe_id = InstrumentId(Symbol(pe_sym), venue)

        if self.cache.instrument(self.ce_id) is None or self.cache.instrument(self.pe_id) is None:
            self.log.warning(f"ATM instruments not found: {ce_sym} / {pe_sym}")
            return

        self.subscribe_quote_ticks(self.ce_id)
        self.subscribe_quote_ticks(self.pe_id)

        qty = Quantity.from_int(self.lot_size * self.num_lots)
        self.submit_order(self.order_factory.market(
            instrument_id=self.ce_id, order_side=OrderSide.SELL, quantity=qty,
        ))
        self.submit_order(self.order_factory.market(
            instrument_id=self.pe_id, order_side=OrderSide.SELL, quantity=qty,
        ))
        self.is_entered = True

        self._cur_entry_ce_px = None
        self._cur_entry_pe_px = None
        self._cur_exit_ce_px = None
        self._cur_exit_pe_px = None
        self._cur_exit_reason = None
        self._latest_ce_px = 0.0
        self._latest_pe_px = 0.0

        ts_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(ts_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        self._cur_entry_time = ist_dt.strftime("%H:%M:%S")

        self.log.info(
            f"ENTERED ATM straddle {atm_strike} at spot={self.latest_spot:.2f}, "
            f"vix={self.latest_vix:.4f}, time={self._cur_entry_time}"
        )

    def _close_positions(self, reason: str) -> None:
        self._pending_exit = True
        self._cur_spot_at_exit = self.latest_spot
        self._cur_vix_at_exit = self.latest_vix
        self._cur_exit_reason = reason

        ts_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(ts_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        self._cur_exit_time = ist_dt.strftime("%H:%M:%S")

        self._exit_fills_needed = 0
        for pos in self.cache.positions_open(strategy_id=self.id):
            self.close_position(pos)
            self._exit_fills_needed += 1

    def _on_exit(self, event) -> None:
        self._eod_triggered = True
        if self.is_entered and not self._pending_exit:
            self._close_positions("EOD")

    def on_order_filled(self, event: OrderFilled) -> None:
        px = float(event.last_px)
        is_sell = event.order_side == OrderSide.SELL

        if event.instrument_id == self.ce_id:
            if is_sell:
                self._cur_entry_ce_px = px
            else:
                self._cur_exit_ce_px = px
        elif event.instrument_id == self.pe_id:
            if is_sell:
                self._cur_entry_pe_px = px
            else:
                self._cur_exit_pe_px = px

        # Set SL after both entry fills
        if is_sell and self._cur_entry_ce_px is not None and self._cur_entry_pe_px is not None:
            entry_straddle = self._cur_entry_ce_px + self._cur_entry_pe_px
            self.straddle_sl = round(entry_straddle * (1 + self.sl_pct / 100), 2)
            self.log.info(
                f"Straddle entry={entry_straddle:.2f}, SL at {self.straddle_sl:.2f}"
            )

        # Check if exit is complete
        if self._pending_exit:
            if self._cur_exit_ce_px is not None and self._cur_exit_pe_px is not None:
                self._finalize_trade()

    def _finalize_trade(self) -> None:
        entry_ce = self._cur_entry_ce_px or 0.0
        entry_pe = self._cur_entry_pe_px or 0.0
        exit_ce = self._cur_exit_ce_px or 0.0
        exit_pe = self._cur_exit_pe_px or 0.0

        ce_pnl = entry_ce - exit_ce
        pe_pnl = entry_pe - exit_pe
        total_pnl = ce_pnl + pe_pnl
        entry_total = entry_ce + entry_pe

        trade = {
            "date": self._date_str,
            "trade_num": len(self._trades) + 1,
            "atm_strike": self._cur_ce_strike,
            "vix_day_high": round(self._cur_vix_day_high, 4),
            "vix_pullback_level": round(self._cur_vix_pullback, 4),
            "vix_at_entry": round(self._cur_vix_at_entry, 4),
            "vix_at_exit": round(self._cur_vix_at_exit, 4),
            "entry_time": f"{self._date_str} {self._cur_entry_time}" if self._cur_entry_time else None,
            "exit_time": f"{self._date_str} {self._cur_exit_time}" if self._cur_exit_time else None,
            "exit_reason": self._cur_exit_reason or "UNKNOWN",
            "spot_at_entry": round(self._cur_spot_at_entry, 2),
            "spot_at_exit": round(self._cur_spot_at_exit, 2),
            "entry_ce": entry_ce,
            "entry_pe": entry_pe,
            "exit_ce": exit_ce,
            "exit_pe": exit_pe,
            "straddle_entry": round(entry_total, 2),
            "straddle_exit": round(exit_ce + exit_pe, 2),
            "straddle_sl": self.straddle_sl,
            "ce_pnl": round(ce_pnl, 2),
            "pe_pnl": round(pe_pnl, 2),
            "pnl": round(total_pnl, 2),
            "pnl_pct": round((total_pnl / entry_total) * 100, 2) if entry_total > 0 else 0,
        }
        self._trades.append(trade)
        self.log.info(
            f"Trade #{trade['trade_num']} ATM {self._cur_ce_strike} finalized: "
            f"PnL={total_pnl:.2f} ({self._cur_exit_reason})"
        )

        # Reset for re-entry
        self.is_entered = False
        self._pending_exit = False
        self.ce_id = None
        self.pe_id = None
        self.straddle_sl = 0.0
        self._latest_ce_px = 0.0
        self._latest_pe_px = 0.0
        self.vix_pullback_level = 0.0

    def get_daily_results(self, date_str: str) -> list[dict]:
        """Extract ALL trade results for the day. Called by runner."""
        return self._trades
