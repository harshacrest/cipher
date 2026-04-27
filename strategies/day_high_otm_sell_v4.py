"""
Day High OTM Sell Strategy v4 — Real Orders with Variable Quantity
------------------------------------------------------------------
Same signal generation as v3 (close-based DH, maturity lock, cooldown after SL,
no trailing SL, SL frozen at entry-time day_high × 1.05). Identical state machine
evolution to v3.

NEW v4 BEHAVIOR:
  - ALL trades submit real orders through Nautilus (no phantom skip).
  - First `skip_first_n_trades` trades of the day use `phantom_qty` (default 1).
  - From trade #(skip_first_n_trades + 1) onwards, use `real_qty` (default 100).
  - Stored PnL in trade dict is scaled by the trade's quantity:
      gross_pnl_stored = (entry_px − exit_px) × leg.qty

Rationale: by actually submitting real orders for trades #1-3 (at minimal quantity),
the state machine (day_high, cooldown timing, strike selection) evolves identically
to v3. This eliminates the phantom-drift problem of the prior v4 implementation
(+1,340) and is equivalent to running v3 and skipping the first 3 trades' PnL.
Expected PnL ≈ v3-filtered-to-#4+ × 100 + small contribution from qty=1 trades.

Preserves v3's correct SL behavior: DH is NOT updated during in-position bars,
so sl_level stays frozen at entry-time value.
"""

from __future__ import annotations

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class DayHighOTMSellV4Config(StrategyConfig):
    start_time: str = "09:15:00"
    exit_time: str = "15:15:00"
    bar_interval_minutes: int = 3
    pullback_pct: float = 5.0
    sl_pct_above_high: float = 5.0
    cooldown_bars: int = 5
    strike_step: int = 50
    underlying: str = "NIFTY"
    venue: str = "NSE"
    spot_instrument_id: str = "NIFTY-SPOT.NSE"
    cost_per_round_trip_pts: float = 0.0

    # v4 params
    skip_first_n_trades: int = 3        # How many trades/day are "phantom-sized"
    # Nautilus options require positive integer qty (no qty=0 or fractional allowed).
    # Use qty=1 for phantom orders for state-machine tracking, but ZERO out their
    # PnL in the output (equivalent to qty=0 for P&L purposes).
    phantom_qty: int = 1
    real_qty: int = 1                   # Qty for trades from #(skip_first_n+1) onwards


class _LegState:
    def __init__(self, side: str):
        self.side = side
        self.strike: int | None = None
        self.instrument_id: InstrumentId | None = None

        self.day_high: float = 0.0
        self.signal_day_high: float = 0.0
        self.pullback_level: float = 0.0
        self.sl_level: float = 0.0
        self.bars_since_dh_update: int = 0
        self.dh_locked: bool = False

        self.bar_high: float = 0.0
        self.bar_close: float = 0.0
        self.bar_tick_count: int = 0

        self.is_entered: bool = False
        self.pending_exit: bool = False
        self.latest_px: float = 0.0

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

        # v4: tracked quantity for this trade
        self.qty: int = 0
        self.is_phantom_sized: bool = False   # True if this trade used phantom_qty

    def reset_monitoring(self):
        self.strike = None
        self.instrument_id = None
        self.day_high = 0.0
        self.signal_day_high = 0.0
        self.pullback_level = 0.0
        self.sl_level = 0.0
        self.bars_since_dh_update = 0
        self.dh_locked = False
        self.bar_high = 0.0
        self.bar_close = 0.0
        self.bar_tick_count = 0
        self.is_entered = False
        self.pending_exit = False
        self.entry_px = None
        self.exit_px = None
        self.entry_time = None
        self.exit_time = None
        self.exit_reason = None
        self.entry_strike = None
        self.qty = 0
        self.is_phantom_sized = False


class DayHighOTMSellV4(Strategy):

    def __init__(self, config: DayHighOTMSellV4Config) -> None:
        super().__init__(config)
        self.spot_id = InstrumentId.from_str(config.spot_instrument_id)
        self.start_time = config.start_time
        self.exit_time = config.exit_time
        self.bar_interval = config.bar_interval_minutes
        self.pullback_pct = config.pullback_pct
        self.sl_pct = config.sl_pct_above_high
        self.cooldown_bars = config.cooldown_bars
        self.strike_step = config.strike_step
        self.underlying = config.underlying
        self.venue_str = config.venue
        self.cost_per_rt = config.cost_per_round_trip_pts

        self.skip_first_n = config.skip_first_n_trades
        self.phantom_qty = config.phantom_qty
        self.real_qty = config.real_qty

        self.latest_spot: float = 0.0
        self.expiry_str: str | None = None

        self.ce = _LegState("CE")
        self.pe = _LegState("PE")

        self._trades: list[dict] = []
        # Global signal counter — covers both legs combined, persists within the day
        self._signal_count: int = 0

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
        current_strike = self._get_otm_strike(leg.side)
        if leg.strike == current_strike and leg.instrument_id is not None:
            return True
        new_id = self._resolve_instrument(current_strike, leg.side)
        if self.cache.instrument(new_id) is None:
            return False
        leg.strike = current_strike
        leg.instrument_id = new_id
        leg.day_high = 0.0
        leg.signal_day_high = 0.0
        leg.pullback_level = 0.0
        leg.bars_since_dh_update = 0
        leg.dh_locked = False
        leg.bar_tick_count = 0
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

                # SL check — uses frozen sl_level (v3 semantics, no widening)
                if leg.is_entered and not leg.pending_exit:
                    if leg.sl_level > 0 and px >= leg.sl_level:
                        self._close_leg(leg, "SL")
                break

    def _on_3min_bar_close(self) -> None:
        if self._eod_triggered:
            return

        for leg in (self.ce, self.pe):
            # v3 semantics: skip DH update during position/cooldown (prevents SL widening)
            if leg.is_entered or leg.pending_exit:
                leg.bar_high = 0.0
                leg.bar_close = 0.0
                leg.bar_tick_count = 0
                continue

            if leg.cooldown_remaining > 0:
                leg.cooldown_remaining -= 1
                leg.bar_high = 0.0
                leg.bar_close = 0.0
                leg.bar_tick_count = 0
                continue

            if not self._ensure_leg_subscribed(leg):
                leg.bar_tick_count = 0
                continue

            if leg.bar_tick_count == 0:
                continue

            bar_close = leg.bar_close

            # DH from bar close (v3 behavior)
            if bar_close > leg.day_high:
                leg.day_high = bar_close
                leg.bars_since_dh_update = 0
                leg.dh_locked = False

                leg.signal_day_high = leg.day_high
                leg.pullback_level = leg.day_high * (1 - self.pullback_pct / 100)
                leg.sl_level = leg.day_high * (1 + self.sl_pct / 100)
            else:
                leg.bars_since_dh_update += 1
                if not leg.dh_locked and leg.bars_since_dh_update >= 1 and leg.signal_day_high > 0:
                    leg.dh_locked = True

            # Entry on fresh cross-down below pullback, after DH is locked
            if leg.dh_locked and leg.pullback_level > 0 and bar_close <= leg.pullback_level:
                self._enter_leg(leg)

            leg.bar_high = 0.0
            leg.bar_close = 0.0
            leg.bar_tick_count = 0

    def _enter_leg(self, leg: _LegState) -> None:
        if leg.is_entered or leg.instrument_id is None:
            return
        if self.cache.instrument(leg.instrument_id) is None:
            return

        # Increment signal counter (for logging only — not used for qty decision)
        self._signal_count += 1

        # v3-semantics fix: decide phantom vs real by COMPLETION count
        # (matches v3's trade_num = len(_trades) + 1 at finalize time)
        # First N completed trades of the day get phantom_qty; after that real_qty.
        is_phantom_sized = len(self._trades) < self.skip_first_n
        qty_value = self.phantom_qty if is_phantom_sized else self.real_qty

        # Always submit a real order (goes through Nautilus matching engine)
        qty = Quantity.from_int(qty_value)
        order = self.order_factory.market(
            instrument_id=leg.instrument_id,
            order_side=OrderSide.SELL,
            quantity=qty,
        )
        self.submit_order(order)

        leg.is_entered = True
        leg.qty = qty_value
        leg.is_phantom_sized = is_phantom_sized
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

        # Always real close (submit market BUY via close_position)
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
        per_unit_pnl = entry_px - exit_px
        # Scale PnL by quantity. Phantom-sized trades contribute ZERO to P&L
        # (simulating qty=0 semantics since Nautilus doesn't accept qty=0 orders).
        if leg.is_phantom_sized:
            gross_pnl = 0.0
        else:
            gross_pnl = per_unit_pnl * leg.qty
        net_pnl = gross_pnl - (0.0 if leg.is_phantom_sized else self.cost_per_rt)

        trade = {
            "date": self._date_str,
            "trade_num": len(self._trades) + 1,
            "signal_num": self._signal_count,
            "side": leg.side,
            "strike": leg.entry_strike,
            "qty": leg.qty,
            "is_phantom_sized": leg.is_phantom_sized,
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
            "per_unit_pnl": round(per_unit_pnl, 2),
            "gross_pnl": round(gross_pnl, 2),
            "cost": self.cost_per_rt,
            "pnl": round(net_pnl, 2),
            "pnl_pct": round((per_unit_pnl / entry_px) * 100, 2) if entry_px > 0 else 0,
        }
        self._trades.append(trade)

        was_sl = leg.exit_reason == "SL"
        cooldown = self.cooldown_bars if was_sl else 0
        leg.reset_monitoring()
        leg.cooldown_remaining = cooldown

    def get_daily_results(self, date_str: str) -> list[dict]:
        return self._trades
