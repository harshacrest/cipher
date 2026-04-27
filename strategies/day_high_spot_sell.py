"""
Day High SPOT-Based OTM Sell Strategy — NautilusTrader
------------------------------------------------------
After 09:15 IST on a 3-min timeframe:
  1. Track NIFTY SPOT rolling day high.
  2. When a NEW spot day high is formed, monitor for a 5% pullback on SPOT.
  3. If SPOT falls 5% from that day high AND closes a 3-min bar below it → SHORT
     OTM 1 CE + OTM 1 PE (dynamic rolling strikes based on spot at signal time).
  4. Stop-loss: SPOT rises 5% above the day high at signal time → EXIT both legs.
  5. After exit, RESET: pick fresh OTM1 strikes, continue tracking spot day high.
  6. At 15:15 IST: close any remaining open positions.

CE and PE enter TOGETHER and exit TOGETHER. Signal is on SPOT, not on option prices.
Multiple trades per day are possible (re-entry after SL with fresh OTM1 strikes).
"""

from __future__ import annotations

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class DayHighSpotSellConfig(StrategyConfig):
    start_time: str = "09:15:00"
    exit_time: str = "15:15:00"
    bar_interval_minutes: int = 3
    pullback_pct: float = 5.0
    sl_pct_above_high: float = 5.0
    strike_step: int = 50
    lot_size: int = 1
    num_lots: int = 1
    underlying: str = "NIFTY"
    venue: str = "NSE"
    spot_instrument_id: str = "NIFTY-SPOT.NSE"


class DayHighSpotSell(Strategy):

    def __init__(self, config: DayHighSpotSellConfig) -> None:
        super().__init__(config)
        self.spot_id = InstrumentId.from_str(config.spot_instrument_id)
        self.start_time = config.start_time
        self.exit_time = config.exit_time
        self.bar_interval = config.bar_interval_minutes
        self.pullback_pct = config.pullback_pct
        self.sl_pct = config.sl_pct_above_high
        self.strike_step = config.strike_step
        self.lot_size = config.lot_size
        self.num_lots = config.num_lots
        self.underlying = config.underlying
        self.venue_str = config.venue

        # Bar building state
        self._bar_high: float = 0.0
        self._bar_close: float = 0.0
        self._bar_start_ns: int = 0
        self._bar_tick_count: int = 0

        # Day tracking state (persists across trades)
        self.latest_spot: float = 0.0
        self.day_high: float = 0.0
        self.signal_day_high: float = 0.0
        self.pullback_level: float = 0.0
        self.sl_level: float = 0.0

        # Current position state (reset after each exit)
        self.is_entered: bool = False
        self.ce_id: InstrumentId | None = None
        self.pe_id: InstrumentId | None = None
        self.ce_strike: int | None = None
        self.pe_strike: int | None = None
        self.expiry_str: str | None = None

        # Current trade fill tracking
        self._cur_entry_ce_px: float | None = None
        self._cur_entry_pe_px: float | None = None
        self._cur_exit_ce_px: float | None = None
        self._cur_exit_pe_px: float | None = None
        self._cur_spot_at_entry: float = 0.0
        self._cur_spot_at_exit: float = 0.0
        self._cur_entry_time: str | None = None
        self._cur_exit_time: str | None = None
        self._cur_exit_reason: str | None = None
        self._cur_day_high: float = 0.0
        self._cur_pullback_level: float = 0.0
        self._cur_sl_level: float = 0.0
        self._cur_ce_strike: int | None = None
        self._cur_pe_strike: int | None = None

        self._trades: list[dict] = []

        self._date_str: str = ""
        self._trading_started: bool = False
        self._eod_triggered: bool = False
        self._bar_interval_ns: int = self.bar_interval * 60 * 1_000_000_000
        self._pending_exit: bool = False

    def on_start(self) -> None:
        self.subscribe_quote_ticks(self.spot_id)

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

    def on_quote_tick(self, tick) -> None:
        if tick.instrument_id != self.spot_id:
            return

        self.latest_spot = float(tick.bid_price)

        if not self._trading_started:
            return

        ts_ns = tick.ts_event

        if self._bar_tick_count == 0:
            self._bar_high = self.latest_spot
            self._bar_close = self.latest_spot
            self._bar_start_ns = ts_ns
            self._bar_tick_count = 1
            return

        self._bar_high = max(self._bar_high, self.latest_spot)
        self._bar_close = self.latest_spot
        self._bar_tick_count += 1

        elapsed = ts_ns - self._bar_start_ns
        if elapsed >= self._bar_interval_ns:
            self._on_bar_close()
            self._bar_high = self.latest_spot
            self._bar_close = self.latest_spot
            self._bar_start_ns = ts_ns
            self._bar_tick_count = 1

        # Check SL on every tick if entered
        if self.is_entered and not self._pending_exit:
            if self.latest_spot >= self.sl_level:
                self._close_positions("SL")

    def _on_bar_close(self) -> None:
        bar_close = self._bar_close

        # Always track day high
        prev_high = self.day_high
        if self._bar_high > self.day_high:
            self.day_high = self._bar_high

        if self.is_entered or self._pending_exit or self._eod_triggered:
            return

        # New day high?
        if self.day_high > prev_high and prev_high > 0:
            self.signal_day_high = self.day_high
            self.pullback_level = self.day_high * (1 - self.pullback_pct / 100)
            self.sl_level = self.day_high * (1 + self.sl_pct / 100)

        # Pullback entry?
        if self.pullback_level > 0 and bar_close <= self.pullback_level:
            self._enter_position()

    def _find_otm_strikes(self, spot: float) -> tuple[int, int]:
        atm = int(round(spot / self.strike_step) * self.strike_step)
        return atm + self.strike_step, atm - self.strike_step

    def _enter_position(self) -> None:
        if self.is_entered:
            return

        spot = self.latest_spot
        if spot <= 0:
            return

        ce_strike, pe_strike = self._find_otm_strikes(spot)
        self.ce_strike = ce_strike
        self.pe_strike = pe_strike
        self._cur_ce_strike = ce_strike
        self._cur_pe_strike = pe_strike
        self._cur_spot_at_entry = spot
        self._cur_day_high = self.signal_day_high
        self._cur_pullback_level = self.pullback_level
        self._cur_sl_level = self.sl_level

        ce_sym = f"{self.underlying}-{ce_strike}-CE-{self.expiry_str}"
        pe_sym = f"{self.underlying}-{pe_strike}-PE-{self.expiry_str}"
        venue = Venue(self.venue_str)
        self.ce_id = InstrumentId(Symbol(ce_sym), venue)
        self.pe_id = InstrumentId(Symbol(pe_sym), venue)

        if self.cache.instrument(self.ce_id) is None or self.cache.instrument(self.pe_id) is None:
            return

        self.subscribe_quote_ticks(self.ce_id)
        self.subscribe_quote_ticks(self.pe_id)

        qty = Quantity.from_int(self.lot_size * self.num_lots)
        self.submit_order(self.order_factory.market(instrument_id=self.ce_id, order_side=OrderSide.SELL, quantity=qty))
        self.submit_order(self.order_factory.market(instrument_id=self.pe_id, order_side=OrderSide.SELL, quantity=qty))
        self.is_entered = True

        self._cur_entry_ce_px = None
        self._cur_entry_pe_px = None
        self._cur_exit_ce_px = None
        self._cur_exit_pe_px = None
        self._cur_exit_reason = None

        ts_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(ts_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        self._cur_entry_time = ist_dt.strftime("%H:%M:%S")

    def _close_positions(self, reason: str) -> None:
        self._pending_exit = True
        self._cur_spot_at_exit = self.latest_spot
        self._cur_exit_reason = reason

        ts_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(ts_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        self._cur_exit_time = ist_dt.strftime("%H:%M:%S")

        for pos in self.cache.positions_open(strategy_id=self.id):
            self.close_position(pos)

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
            "ce_strike": self._cur_ce_strike,
            "pe_strike": self._cur_pe_strike,
            "day_high": round(self._cur_day_high, 2),
            "pullback_level": round(self._cur_pullback_level, 2),
            "sl_level": round(self._cur_sl_level, 2),
            "entry_time": f"{self._date_str} {self._cur_entry_time}" if self._cur_entry_time else None,
            "exit_time": f"{self._date_str} {self._cur_exit_time}" if self._cur_exit_time else None,
            "exit_reason": self._cur_exit_reason or "UNKNOWN",
            "spot_at_entry": round(self._cur_spot_at_entry, 2),
            "spot_at_exit": round(self._cur_spot_at_exit, 2),
            "entry_ce": entry_ce,
            "entry_pe": entry_pe,
            "exit_ce": exit_ce,
            "exit_pe": exit_pe,
            "ce_pnl": round(ce_pnl, 2),
            "pe_pnl": round(pe_pnl, 2),
            "pnl": round(total_pnl, 2),
            "pnl_pct": round((total_pnl / entry_total) * 100, 2) if entry_total > 0 else 0,
        }
        self._trades.append(trade)

        # Reset for re-entry
        self.is_entered = False
        self._pending_exit = False
        self.ce_id = None
        self.pe_id = None
        self.pullback_level = 0.0

    def get_daily_results(self, date_str: str) -> list[dict]:
        return self._trades
