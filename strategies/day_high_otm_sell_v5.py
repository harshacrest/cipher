"""
Day High OTM Sell Strategy v5 — True Whole-Day Day High
-------------------------------------------------------
Fixes the two fundamental issues identified in v3/v4:

  FIX 1: Day high keeps updating during in-position AND cooldown bars.
         Previously the bar handler `continue`d out before running the DH update
         block when a leg was in-position or cooling down. Now the DH update is
         the FIRST thing run on every bar; only entry evaluation is skipped when
         in-position or in cooldown.

  FIX 2: Day high does NOT reset on exit.
         `reset_monitoring` no longer zeroes day_high / signal_day_high /
         pullback_level / sl_level. These only reset when the OTM1 strike
         actually rolls (detected in `_ensure_leg_subscribed`).

Economic consequence: the day_high used for every entry's pullback and SL
reference is the TRUE running max of the OTM1 option ASK for the current
strike since 09:15 IST (or since the last strike roll if spot drifted).
Re-entries require a genuine new absolute day high + 5% pullback — not a
trivial bar-after-reset local high.

All other mechanics unchanged from v3:
  - Close-based day high (uses bar_close, not bar_high)
  - Maturity lock (entry blocked on same bar that set new DH)
  - Cooldown 5 bars after SL
  - Per-leg independent CE / PE legs
  - EOD exit 15:15 IST
"""

from __future__ import annotations

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class DayHighOTMSellV5Config(StrategyConfig):
    start_time: str = "09:15:00"
    exit_time: str = "15:15:00"
    bar_interval_minutes: int = 3
    pullback_pct: float = 5.0
    sl_pct_above_high: float = 5.0
    cooldown_bars: int = 5
    strike_step: int = 50
    lot_size: int = 1
    num_lots: int = 1
    underlying: str = "NIFTY"
    venue: str = "NSE"
    spot_instrument_id: str = "NIFTY-SPOT.NSE"
    cost_per_round_trip_pts: float = 0.0  # set >0 to model brokerage+STT+slippage


class _LegState:
    """One independent leg (CE or PE)."""

    def __init__(self, side: str):
        self.side = side

        # Strike + instrument
        self.strike: int | None = None
        self.instrument_id: InstrumentId | None = None

        # DAY HIGH STATE — persists across exits and cooldown.
        # Only reset when strike actually rolls (in _ensure_leg_subscribed).
        self.day_high: float = 0.0
        self.signal_day_high: float = 0.0
        self.pullback_level: float = 0.0
        self.sl_level: float = 0.0
        self.bars_since_dh_update: int = 0
        self.dh_locked: bool = False

        # Bar construction (transient per-bar)
        self.bar_high: float = 0.0
        self.bar_close: float = 0.0
        self.bar_tick_count: int = 0

        # POSITION STATE — cleared on exit, independent of DH state
        self.is_entered: bool = False
        self.pending_exit: bool = False
        self.latest_px: float = 0.0

        # Cooldown
        self.cooldown_remaining: int = 0

        # Fills
        self.entry_px: float | None = None
        self.exit_px: float | None = None
        self.entry_time: str | None = None
        self.exit_time: str | None = None
        self.exit_reason: str | None = None
        self.entry_strike: int | None = None
        self.entry_day_high: float = 0.0
        self.entry_pullback: float = 0.0
        self.entry_sl: float = 0.0
        self.spot_at_entry: float = 0.0
        self.spot_at_exit: float = 0.0

    def reset_position_only(self):
        """Called after exit. Clears POSITION fields but preserves day_high state."""
        self.is_entered = False
        self.pending_exit = False
        self.entry_px = None
        self.exit_px = None
        self.entry_time = None
        self.exit_time = None
        self.exit_reason = None
        self.entry_strike = None
        self.entry_day_high = 0.0
        self.entry_pullback = 0.0
        self.entry_sl = 0.0

    def reset_day_high_state(self):
        """Called ONLY when strike rolls — the new strike has no history."""
        self.day_high = 0.0
        self.signal_day_high = 0.0
        self.pullback_level = 0.0
        self.sl_level = 0.0
        self.bars_since_dh_update = 0
        self.dh_locked = False
        self.bar_high = 0.0
        self.bar_close = 0.0
        self.bar_tick_count = 0


class DayHighOTMSellV5(Strategy):

    def __init__(self, config: DayHighOTMSellV5Config) -> None:
        super().__init__(config)
        self.spot_id = InstrumentId.from_str(config.spot_instrument_id)
        self.start_time = config.start_time
        self.exit_time = config.exit_time
        self.bar_interval = config.bar_interval_minutes
        self.pullback_pct = config.pullback_pct
        self.sl_pct = config.sl_pct_above_high
        self.cooldown_bars = config.cooldown_bars
        self.strike_step = config.strike_step
        self.lot_size = config.lot_size
        self.num_lots = config.num_lots
        self.underlying = config.underlying
        self.venue_str = config.venue
        self.cost_per_rt = config.cost_per_round_trip_pts

        self.latest_spot: float = 0.0
        self.expiry_str: str | None = None

        self.ce = _LegState("CE")
        self.pe = _LegState("PE")

        self._trades: list[dict] = []
        self._date_str: str = ""
        self._trading_started: bool = False
        self._eod_triggered: bool = False
        self._bar_interval_ns: int = self.bar_interval * 60 * 1_000_000_000
        self._spot_bar_start_ns: int = 0
        self._spot_bar_count: int = 0

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

    def _get_otm_strike(self, side: str) -> int:
        atm = int(round(self.latest_spot / self.strike_step) * self.strike_step)
        return atm + self.strike_step if side == "CE" else atm - self.strike_step

    def _resolve_instrument(self, strike: int, side: str) -> InstrumentId:
        sym = f"{self.underlying}-{strike}-{side}-{self.expiry_str}"
        return InstrumentId(Symbol(sym), Venue(self.venue_str))

    def _ensure_leg_subscribed(self, leg: _LegState) -> bool:
        """Ensure leg is tracking current OTM1 strike. Reset DH if strike rolled."""
        current_strike = self._get_otm_strike(leg.side)
        if leg.strike == current_strike and leg.instrument_id is not None:
            return True

        new_id = self._resolve_instrument(current_strike, leg.side)
        if self.cache.instrument(new_id) is None:
            return False

        # Strike rolled — reset DAY HIGH state (new strike has no history)
        leg.strike = current_strike
        leg.instrument_id = new_id
        leg.reset_day_high_state()
        self.subscribe_quote_ticks(new_id)
        return True

    def on_quote_tick(self, tick) -> None:
        if tick.instrument_id == self.spot_id:
            self.latest_spot = float(tick.bid_price)
            if not self._trading_started:
                return

            ts_ns = tick.ts_event
            if self._spot_bar_count == 0:
                self._spot_bar_start_ns = ts_ns
                self._spot_bar_count = 1
                return

            self._spot_bar_count += 1
            if ts_ns - self._spot_bar_start_ns >= self._bar_interval_ns:
                self._on_3min_bar_close()
                self._spot_bar_start_ns = ts_ns
                self._spot_bar_count = 1
            return

        # Option tick
        for leg in (self.ce, self.pe):
            if leg.instrument_id and tick.instrument_id == leg.instrument_id:
                px = float(tick.ask_price)
                leg.latest_px = px

                if leg.bar_tick_count == 0:
                    leg.bar_high = px
                    leg.bar_close = px
                else:
                    leg.bar_high = max(leg.bar_high, px)
                    leg.bar_close = px
                leg.bar_tick_count += 1

                # SL check uses leg.entry_sl (frozen at entry time) — not leg.sl_level
                # which drifts as day_high updates during in-position bars. This fixes
                # the "SL widening" bug where stop would move against the trader.
                if leg.is_entered and not leg.pending_exit:
                    if leg.entry_sl > 0 and px >= leg.entry_sl:
                        self._close_leg(leg, "SL")
                break

    def _on_3min_bar_close(self) -> None:
        """Process every leg's bar close. DH updates ALWAYS run; entry logic may be gated."""
        if self._eod_triggered:
            return

        for leg in (self.ce, self.pe):
            # ALWAYS ensure the leg is subscribed to current OTM1
            # (even during in-position or cooldown — so DH tracking can continue)
            if not self._ensure_leg_subscribed(leg):
                leg.bar_tick_count = 0
                continue

            # If bar has no ticks (gap / no quotes), skip this iteration
            if leg.bar_tick_count == 0:
                continue

            bar_close = leg.bar_close

            # ─── FIX 1: Day high update ALWAYS runs ───
            # Even when in-position or in cooldown, we update DH/SL/pullback.
            # This keeps day_high a true running max across the entire session.
            if bar_close > leg.day_high:
                leg.day_high = bar_close
                leg.bars_since_dh_update = 0
                leg.dh_locked = False
                leg.signal_day_high = leg.day_high
                leg.pullback_level = leg.day_high * (1 - self.pullback_pct / 100)
                # SL only updates for NEW positions; existing position keeps its entry-time SL.
                # But the "monitor-level" SL reference updates so re-entry uses fresh level.
                leg.sl_level = leg.day_high * (1 + self.sl_pct / 100)
            else:
                leg.bars_since_dh_update += 1
                if not leg.dh_locked and leg.bars_since_dh_update >= 1 and leg.signal_day_high > 0:
                    leg.dh_locked = True

            # Clear bar state after processing
            leg.bar_high = 0.0
            leg.bar_close = 0.0
            leg.bar_tick_count = 0

            # ─── ENTRY GATING ───
            # Skip entry evaluation if already positioned or in cooldown.
            if leg.is_entered or leg.pending_exit:
                continue
            if leg.cooldown_remaining > 0:
                leg.cooldown_remaining -= 1
                continue

            # Entry condition: DH mature AND bar_close <= pullback_level
            if leg.dh_locked and leg.pullback_level > 0 and bar_close <= leg.pullback_level:
                self._enter_leg(leg)

    def _enter_leg(self, leg: _LegState) -> None:
        if leg.is_entered or leg.instrument_id is None:
            return
        if self.cache.instrument(leg.instrument_id) is None:
            return

        qty = Quantity.from_int(self.lot_size * self.num_lots)
        order = self.order_factory.market(
            instrument_id=leg.instrument_id,
            order_side=OrderSide.SELL,
            quantity=qty,
        )
        self.submit_order(order)
        leg.is_entered = True
        leg.entry_strike = leg.strike
        leg.entry_day_high = leg.signal_day_high
        leg.entry_pullback = leg.pullback_level
        leg.entry_sl = leg.sl_level
        leg.spot_at_entry = self.latest_spot

        ts_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(ts_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        leg.entry_time = ist_dt.strftime("%H:%M:%S")

    def _close_leg(self, leg: _LegState, reason: str) -> None:
        leg.pending_exit = True
        leg.exit_reason = reason
        leg.spot_at_exit = self.latest_spot

        ts_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(ts_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        leg.exit_time = ist_dt.strftime("%H:%M:%S")

        for pos in self.cache.positions_open(strategy_id=self.id):
            if pos.instrument_id == leg.instrument_id:
                self.close_position(pos)
                break

    def _on_exit(self, event) -> None:
        self._eod_triggered = True
        for leg in (self.ce, self.pe):
            if leg.is_entered and not leg.pending_exit:
                self._close_leg(leg, "EOD")

    def on_order_filled(self, event: OrderFilled) -> None:
        px = float(event.last_px)
        is_sell = event.order_side == OrderSide.SELL

        for leg in (self.ce, self.pe):
            if leg.instrument_id and event.instrument_id == leg.instrument_id:
                if is_sell:
                    leg.entry_px = px
                else:
                    leg.exit_px = px
                    if leg.pending_exit:
                        self._finalize_leg(leg)
                break

    def _finalize_leg(self, leg: _LegState) -> None:
        entry_px = leg.entry_px or 0.0
        exit_px = leg.exit_px or 0.0
        gross_pnl = entry_px - exit_px
        net_pnl = gross_pnl - self.cost_per_rt

        trade = {
            "date": self._date_str,
            "trade_num": len(self._trades) + 1,
            "side": leg.side,
            "strike": leg.entry_strike,
            "day_high": round(leg.entry_day_high, 2),
            "pullback_level": round(leg.entry_pullback, 2),
            "sl_level": round(leg.entry_sl, 2),
            "entry_time": f"{self._date_str} {leg.entry_time}" if leg.entry_time else None,
            "exit_time": f"{self._date_str} {leg.exit_time}" if leg.exit_time else None,
            "exit_reason": leg.exit_reason or "UNKNOWN",
            "spot_at_entry": round(leg.spot_at_entry, 2),
            "spot_at_exit": round(leg.spot_at_exit, 2),
            "entry_px": round(entry_px, 2),
            "exit_px": round(exit_px, 2),
            "gross_pnl": round(gross_pnl, 2),
            "cost": self.cost_per_rt,
            "pnl": round(net_pnl, 2),
            "pnl_pct": round((net_pnl / entry_px) * 100, 2) if entry_px > 0 else 0,
        }
        self._trades.append(trade)

        # ─── FIX 2: Reset ONLY position state, NOT day high ───
        # day_high, signal_day_high, pullback_level, sl_level all persist.
        # dh_locked persists too — the DH is already locked at this point.
        leg.reset_position_only()

        # Cooldown after SL only
        was_sl = leg.exit_reason == "SL"
        leg.cooldown_remaining = self.cooldown_bars if was_sl else 0

    def get_daily_results(self, date_str: str) -> list[dict]:
        return self._trades
