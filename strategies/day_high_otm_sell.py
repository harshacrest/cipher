"""
Day High OTM Sell Strategy v3 — NautilusTrader
-----------------------------------------------
After 09:15 IST on a 3-min timeframe, CE and PE are tracked INDEPENDENTLY:

For each leg (CE / PE):
  1. Determine current OTM1 strike based on spot (rolling dynamic).
  2. Track that option's day high using BAR CLOSE (not bar high — avoids wick noise).
  3. When a new day high forms, LOCK IT — entry only allowed from the NEXT bar onwards.
  4. On a subsequent bar, if bar_close crosses below pullback_level → SHORT.
  5. Stop-loss: 5% above the day_high at signal time (original logic — preserves theta runway).
  6. NO trailing SL — the edge IS holding to EOD for full theta decay.
  7. Cooldown: after SL exit, skip cooldown_bars bars before allowing re-entry.
  8. At 15:15 IST: close any remaining open legs.

v3 keeps: close-based DH, maturity lock, cooldown after SL.
v3 reverts: SL back to day_high-anchored (not entry-anchored), no trailing SL.
"""

from __future__ import annotations

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class DayHighOTMSellConfig(StrategyConfig):
    start_time: str = "09:15:00"
    exit_time: str = "15:15:00"
    bar_interval_minutes: int = 3
    pullback_pct: float = 5.0
    sl_pct_above_high: float = 5.0       # SL as % above DAY HIGH (original)
    cooldown_bars: int = 5                # bars to skip after SL exit (5 bars = 15 min)
    strike_step: int = 50
    lot_size: int = 1
    num_lots: int = 1
    underlying: str = "NIFTY"
    venue: str = "NSE"
    spot_instrument_id: str = "NIFTY-SPOT.NSE"


class _LegState:
    """Tracks one independent leg (CE or PE)."""

    def __init__(self, side: str):
        self.side = side

        # Monitoring state
        self.strike: int | None = None
        self.instrument_id: InstrumentId | None = None
        self.day_high: float = 0.0
        self.signal_day_high: float = 0.0
        self.pullback_level: float = 0.0
        self.sl_level: float = 0.0

        # Day high maturity
        self.bars_since_dh_update: int = 0
        self.dh_locked: bool = False

        # Bar building
        self.bar_high: float = 0.0
        self.bar_close: float = 0.0
        self.bar_tick_count: int = 0

        # Position state
        self.is_entered: bool = False
        self.pending_exit: bool = False
        self.latest_px: float = 0.0

        # Cooldown
        self.cooldown_remaining: int = 0

        # Fill tracking
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


class DayHighOTMSell(Strategy):

    def __init__(self, config: DayHighOTMSellConfig) -> None:
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

                # SL check (no trailing — just static SL)
                if leg.is_entered and not leg.pending_exit:
                    if leg.sl_level > 0 and px >= leg.sl_level:
                        self._close_leg(leg, "SL")
                break

    def _on_3min_bar_close(self) -> None:
        if self._eod_triggered:
            return

        for leg in (self.ce, self.pe):
            if leg.is_entered or leg.pending_exit:
                leg.bar_high = 0.0
                leg.bar_close = 0.0
                leg.bar_tick_count = 0
                continue

            # Cooldown after SL
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

            # FIX 1: Day high from BAR CLOSE (not bar_high)
            if bar_close > leg.day_high:
                leg.day_high = bar_close
                leg.bars_since_dh_update = 0
                leg.dh_locked = False

                leg.signal_day_high = leg.day_high
                leg.pullback_level = leg.day_high * (1 - self.pullback_pct / 100)
                # SL anchored to day high (original logic — preserves theta runway)
                leg.sl_level = leg.day_high * (1 + self.sl_pct / 100)
            else:
                leg.bars_since_dh_update += 1

                # FIX 2: Lock day high after 1 bar of no update
                if not leg.dh_locked and leg.bars_since_dh_update >= 1 and leg.signal_day_high > 0:
                    leg.dh_locked = True

            # FIX 3: Only allow entry on FRESH crossover below pullback, AFTER DH is locked
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
        pnl = entry_px - exit_px

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
            "pnl": round(pnl, 2),
            "pnl_pct": round((pnl / entry_px) * 100, 2) if entry_px > 0 else 0,
        }
        self._trades.append(trade)

        was_sl = leg.exit_reason == "SL"
        cooldown = self.cooldown_bars if was_sl else 0

        leg.reset_monitoring()
        leg.cooldown_remaining = cooldown

    def get_daily_results(self, date_str: str) -> list[dict]:
        return self._trades
