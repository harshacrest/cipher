"""
VWAP SD Straddles Strategy — V2 (1SD band)
------------------------------------------
Same aggregate 15-straddle construction as v1. Key differences:

Entry (short the aggregate straddle):
- Minute bar close sClose crosses under VAL (1 SD below VWAP) — fresh crossdown
- Time is between 09:21 and 15:00 IST
- No open position
- No prev-day or other filters

Exit (close all 30 legs simultaneously):
1. Stop Loss: sClose > VAL + sl_points_above_val    [default 500 pts]
2. Forced:    time >= 15:12 IST

There is NO profit target — winners ride to forced exit.
"""

from __future__ import annotations

import math

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


STATE_IDLE = "IDLE"
STATE_PENDING_ENTRY = "PENDING_ENTRY"
STATE_ACTIVE = "ACTIVE"
STATE_PENDING_EXIT = "PENDING_EXIT"
STATE_TERMINAL = "TERMINAL"


class VWAPSDStraddlesV2Config(StrategyConfig):
    # Time windows (IST)
    session_start_time: str = "09:15:00"
    entry_window_start: str = "09:21:00"
    entry_window_end: str = "15:00:00"
    forced_exit_time: str = "15:12:00"
    eod_time: str = "15:25:00"

    # Structure
    strike_step: int = 50
    num_strikes_each_side: int = 7
    lot_size: int = 1
    num_lots: int = 1

    # Signal parameters
    num_sd: float = 1.0                    # multiplier for VAL/VAH
    sl_points_above_val: float = 500.0     # SL = VAL + this many points (absolute)

    # Strike shift: roll strikes when |spot-entry_spot| > atm_straddle/spot_band_x
    spot_band_x: float = 1.5

    # Identifiers
    underlying: str = "NIFTY"
    venue: str = "NSE"
    spot_instrument_id: str = "NIFTY-SPOT.NSE"


class VWAPSDStraddlesV2(Strategy):

    def __init__(self, config: VWAPSDStraddlesV2Config) -> None:
        super().__init__(config)
        self.spot_id = InstrumentId.from_str(config.spot_instrument_id)
        self.strike_step = config.strike_step
        self.n_side = config.num_strikes_each_side
        self.lot_size = config.lot_size
        self.num_lots = config.num_lots
        self.num_sd = config.num_sd
        self.sl_points = config.sl_points_above_val
        self.spot_band_x = config.spot_band_x
        self.underlying = config.underlying
        self.venue_str = config.venue
        self.expiry_str: str | None = None
        self._date_str: str = ""

        self._session_start_time = config.session_start_time
        self._entry_window_start_time = config.entry_window_start
        self._entry_window_end_time = config.entry_window_end
        self._forced_exit_time = config.forced_exit_time
        self._eod_time = config.eod_time
        self._session_start_ns: int = 0
        self._entry_window_start_ns: int = 0
        self._entry_window_end_ns: int = 0
        self._forced_exit_ns: int = 0
        self._eod_ns: int = 0

        self.latest_spot: float = 0.0

        self.base_strike: int | None = None
        self.leg_instruments: list[dict] = []
        self._leg_by_id: dict = {}

        # 1-minute bar aggregation
        self._current_minute_ns: int = 0
        self._bar_sclose: float = 0.0
        self._prev_bar_sclose: float | None = None
        self._prev_bar_lower: float | None = None
        self._minute_ns = 60_000_000_000

        # Cumulative VWAP + SD bands
        self._sum_sclose: float = 0.0
        self._sum_sclose_sq: float = 0.0
        self._bar_count: int = 0
        self.current_vwap: float = 0.0
        self.current_lower_band: float = 0.0
        self.current_upper_band: float = 0.0

        # Position state
        self._fsm: str = STATE_IDLE
        self.trade_num: int = 0
        self.completed_trades: list[dict] = []
        self.current_entry_sclose: float = 0.0
        self.current_entry_vwap: float = 0.0
        self.current_entry_val: float = 0.0
        self.current_entry_ns: int = 0
        self.current_entry_spot: float = 0.0

        self.current_legs: list[dict] = []
        self._entry_fills: int = 0
        self._exit_fills: int = 0
        self._entry_orders_submitted: int = 0

        # Strike-shift tracking
        self.current_atm_straddle: float = 0.0
        self.current_band_half: float = 0.0
        self._shift_pending_immediate_entry: bool = False

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

        def to_ns(t: str) -> int:
            return int(pd.Timestamp(f"{self._date_str} {t}", tz="Asia/Kolkata").tz_convert("UTC").value)

        self._session_start_ns = to_ns(self._session_start_time)
        self._entry_window_start_ns = to_ns(self._entry_window_start_time)
        self._entry_window_end_ns = to_ns(self._entry_window_end_time)
        self._forced_exit_ns = to_ns(self._forced_exit_time)
        self._eod_ns = to_ns(self._eod_time)

        self.clock.set_time_alert_ns("session_start", self._session_start_ns, self._on_session_start)
        self.clock.set_time_alert_ns("forced_exit", self._forced_exit_ns, self._on_forced_exit)
        self.clock.set_time_alert_ns("eod_hard", self._eod_ns, self._on_eod_hard)

    def _on_session_start(self, event) -> None:
        if self.latest_spot <= 0 or self.expiry_str is None:
            self.log.warning("Session start: no spot/expiry — cannot build legs")
            return

        self.base_strike = int(round(self.latest_spot / self.strike_step) * self.strike_step)
        self.log.info(
            f"Session start: spot={self.latest_spot:.2f}, base_strike={self.base_strike}"
        )

        venue = Venue(self.venue_str)
        for offset in range(-self.n_side, self.n_side + 1):
            strike = self.base_strike + offset * self.strike_step
            for side in ("CE", "PE"):
                sym = f"{self.underlying}-{strike}-{side}-{self.expiry_str}"
                inst_id = InstrumentId(Symbol(sym), venue)
                if self.cache.instrument(inst_id) is None:
                    continue
                leg = {
                    "strike": strike,
                    "side": side,
                    "instrument_id": inst_id,
                    "latest_mid": None,
                    "latest_bid": None,
                    "latest_ask": None,
                }
                self.leg_instruments.append(leg)
                self._leg_by_id[inst_id] = leg
                self.subscribe_quote_ticks(inst_id)

    def on_quote_tick(self, tick) -> None:
        inst_id = tick.instrument_id

        if inst_id == self.spot_id:
            self.latest_spot = float(tick.bid_price)
            if self._fsm == STATE_ACTIVE and self.current_band_half > 0:
                move = abs(self.latest_spot - self.current_entry_spot)
                if move > self.current_band_half:
                    self.log.info(
                        f"SHIFT: spot_move={move:.2f} > band_half={self.current_band_half:.2f}"
                    )
                    self._shift_pending_immediate_entry = True
                    self._exit_all("SHIFT")
            return

        leg = self._leg_by_id.get(inst_id)
        if leg is None:
            return
        bid = float(tick.bid_price)
        ask = float(tick.ask_price)
        leg["latest_mid"] = (bid + ask) / 2.0
        leg["latest_bid"] = bid
        leg["latest_ask"] = ask

        tick_ns = tick.ts_event
        tick_minute_ns = tick_ns - (tick_ns % self._minute_ns)

        if self._current_minute_ns == 0:
            self._current_minute_ns = tick_minute_ns
        elif tick_minute_ns != self._current_minute_ns:
            self._close_bar(self._current_minute_ns)
            self._current_minute_ns = tick_minute_ns

    def _close_bar(self, bar_minute_ns: int) -> None:
        total = 0.0
        n_valid = 0
        for leg in self.leg_instruments:
            m = leg["latest_mid"]
            if m is not None:
                total += m
                n_valid += 1

        if n_valid < 10:
            return

        sclose = total
        self._bar_sclose = sclose

        self._sum_sclose += sclose
        self._sum_sclose_sq += sclose * sclose
        self._bar_count += 1

        self.current_vwap = self._sum_sclose / self._bar_count
        if self._bar_count >= 2:
            mean = self.current_vwap
            var = (self._sum_sclose_sq / self._bar_count) - (mean * mean)
            stdev = math.sqrt(max(var, 0.0))
            self.current_lower_band = mean - self.num_sd * stdev
            self.current_upper_band = mean + self.num_sd * stdev
        else:
            self.current_lower_band = sclose
            self.current_upper_band = sclose

        # ---- Exit check: SL at VAL + sl_points ----
        if self._fsm == STATE_ACTIVE:
            sl_level = self.current_lower_band + self.sl_points
            if sclose > sl_level:
                self.log.info(
                    f"Exit SL: sclose={sclose:.2f} > sl_lvl={sl_level:.2f} "
                    f"(val={self.current_lower_band:.2f}, entry={self.current_entry_sclose:.2f})"
                )
                self._exit_all("SL")
                self._prev_bar_sclose = sclose
                self._prev_bar_lower = self.current_lower_band
                return

        # ---- Entry check: fresh crossdown of VAL (1SD band) ----
        if self._fsm == STATE_IDLE:
            in_window = (bar_minute_ns >= self._entry_window_start_ns) and (bar_minute_ns < self._entry_window_end_ns)

            crossed_under_val = (
                self._prev_bar_sclose is not None
                and self._prev_bar_lower is not None
                and self._prev_bar_sclose >= self._prev_bar_lower
                and sclose < self.current_lower_band
            )

            if in_window and crossed_under_val:
                self._enter_short(sclose)

        self._prev_bar_sclose = sclose
        self._prev_bar_lower = self.current_lower_band

    def _enter_short(self, sclose: float) -> None:
        if not self.leg_instruments:
            return

        self.trade_num += 1
        self.current_entry_sclose = sclose
        self.current_entry_vwap = self.current_vwap
        self.current_entry_val = self.current_lower_band
        self.current_entry_ns = self.clock.timestamp_ns()
        self.current_entry_spot = self.latest_spot

        self.current_legs = []
        for leg in self.leg_instruments:
            self.current_legs.append({
                "strike": leg["strike"],
                "side": leg["side"],
                "instrument_id": leg["instrument_id"],
                "entry_px": None,
                "exit_px": None,
            })
        self._entry_fills = 0
        self._exit_fills = 0
        self._entry_orders_submitted = len(self.current_legs)

        qty = Quantity.from_int(self.lot_size * self.num_lots)
        for leg in self.current_legs:
            order = self.order_factory.market(
                instrument_id=leg["instrument_id"],
                order_side=OrderSide.SELL,
                quantity=qty,
            )
            self.submit_order(order)

        self._fsm = STATE_PENDING_ENTRY
        self.log.info(
            f"ENTRY #{self.trade_num}: SHORT {len(self.current_legs)} legs at "
            f"sclose={sclose:.2f}, val={self.current_lower_band:.2f}, "
            f"sl={self.current_lower_band + self.sl_points:.2f}"
        )

    def _exit_all(self, reason: str) -> None:
        if self._fsm != STATE_ACTIVE:
            return
        self._current_exit_reason = reason
        self._fsm = STATE_PENDING_EXIT

        open_positions = list(self.cache.positions_open(strategy_id=self.id))
        if not open_positions:
            self._finalize_trade()
            return
        for pos in open_positions:
            self.close_position(pos)

    def _finalize_trade(self) -> None:
        contracts = self.lot_size * self.num_lots
        trade_pnl_points = 0.0
        trade_pnl_premium = 0.0
        for leg in self.current_legs:
            if leg["entry_px"] is not None and leg["exit_px"] is not None:
                pts = leg["entry_px"] - leg["exit_px"]
                trade_pnl_points += pts
                trade_pnl_premium += pts * contracts

        entry_ist = pd.Timestamp(self.current_entry_ns, unit="ns", tz="UTC").tz_convert("Asia/Kolkata")
        exit_ist = pd.Timestamp(self.clock.timestamp_ns(), unit="ns", tz="UTC").tz_convert("Asia/Kolkata")

        trade_record = {
            "date": self._date_str,
            "trade_num": self.trade_num,
            "entry_time": entry_ist.strftime("%H:%M:%S"),
            "exit_time": exit_ist.strftime("%H:%M:%S"),
            "exit_reason": getattr(self, "_current_exit_reason", "UNKNOWN"),
            "base_strike": self.base_strike,
            "spot_at_entry": round(self.current_entry_spot, 2),
            "spot_at_exit": round(self.latest_spot, 2),
            "entry_sclose": round(self.current_entry_sclose, 2),
            "exit_sclose": round(self._bar_sclose, 2),
            "entry_vwap": round(self.current_entry_vwap, 2),
            "exit_vwap": round(self.current_vwap, 2),
            "entry_val": round(self.current_entry_val, 2),
            "exit_val": round(self.current_lower_band, 2),
            "num_legs": len(self.current_legs),
            "pnl_points": round(trade_pnl_points, 2),
            "pnl_premium": round(trade_pnl_premium, 2),
            "pnl": round(trade_pnl_points, 2),
        }
        self.completed_trades.append(trade_record)

        self.current_legs = []
        self.current_atm_straddle = 0.0
        self.current_band_half = 0.0
        self._fsm = STATE_IDLE

        # Handle SHIFT: roll strikes to new ATM and re-open immediately
        if self._shift_pending_immediate_entry:
            self._shift_pending_immediate_entry = False
            now_ns = self.clock.timestamp_ns()
            if now_ns < self._entry_window_end_ns and self.latest_spot > 0:
                self._roll_legs_to_new_atm()
                self._reset_vwap_state()
                self._open_short_direct()

    def _on_forced_exit(self, event) -> None:
        if self._fsm == STATE_ACTIVE:
            self._exit_all("FORCED")

    def _on_eod_hard(self, event) -> None:
        if self._fsm == STATE_ACTIVE:
            self._exit_all("EOD_HARD")
        elif self._fsm not in (STATE_PENDING_EXIT,):
            self._fsm = STATE_TERMINAL

    def on_order_filled(self, event: OrderFilled) -> None:
        px = float(event.last_px)
        is_sell = event.order_side == OrderSide.SELL
        inst_id = event.instrument_id

        matching = None
        for leg in self.current_legs:
            if leg["instrument_id"] != inst_id:
                continue
            if is_sell and leg["entry_px"] is None:
                matching = leg
                break
            if (not is_sell) and leg["entry_px"] is not None and leg["exit_px"] is None:
                matching = leg
                break

        if matching is None:
            return

        if is_sell:
            matching["entry_px"] = px
            self._entry_fills += 1
            if self._fsm == STATE_PENDING_ENTRY and self._entry_fills >= self._entry_orders_submitted:
                self._fsm = STATE_ACTIVE
                # Capture ATM straddle → band size for SHIFT detection
                atm_ce = next(
                    (l["entry_px"] for l in self.current_legs
                     if l["strike"] == self.base_strike and l["side"] == "CE"),
                    None,
                )
                atm_pe = next(
                    (l["entry_px"] for l in self.current_legs
                     if l["strike"] == self.base_strike and l["side"] == "PE"),
                    None,
                )
                if atm_ce is not None and atm_pe is not None:
                    self.current_atm_straddle = atm_ce + atm_pe
                    self.current_band_half = self.current_atm_straddle / self.spot_band_x
                self.current_entry_spot = self.latest_spot
        else:
            matching["exit_px"] = px
            self._exit_fills += 1
            if self._fsm == STATE_PENDING_EXIT and self._exit_fills >= self._entry_fills:
                self._finalize_trade()

    def get_all_trades(self, date_str: str) -> list[dict]:
        return list(self.completed_trades)

    # ---------------------------------------------------------------
    # Strike-shift helpers (SHIFT support)
    # ---------------------------------------------------------------

    def _roll_legs_to_new_atm(self) -> None:
        """Rebuild leg set around current ATM. Existing subscriptions are left alone
        (Nautilus keeps routing ticks, but _leg_by_id is reset so only new legs
        contribute to sClose)."""
        new_base = int(round(self.latest_spot / self.strike_step) * self.strike_step)
        self.base_strike = new_base

        self.leg_instruments = []
        self._leg_by_id = {}
        venue = Venue(self.venue_str)
        for offset in range(-self.n_side, self.n_side + 1):
            strike = new_base + offset * self.strike_step
            for side in ("CE", "PE"):
                sym = f"{self.underlying}-{strike}-{side}-{self.expiry_str}"
                inst_id = InstrumentId(Symbol(sym), venue)
                if self.cache.instrument(inst_id) is None:
                    continue
                leg = {
                    "strike": strike,
                    "side": side,
                    "instrument_id": inst_id,
                    "latest_mid": None,
                    "latest_bid": None,
                    "latest_ask": None,
                }
                self.leg_instruments.append(leg)
                self._leg_by_id[inst_id] = leg
                self.subscribe_quote_ticks(inst_id)

    def _reset_vwap_state(self) -> None:
        self._sum_sclose = 0.0
        self._sum_sclose_sq = 0.0
        self._bar_count = 0
        self.current_vwap = 0.0
        self.current_lower_band = 0.0
        self.current_upper_band = 0.0
        self._prev_bar_sclose = None
        self._prev_bar_lower = None
        self._current_minute_ns = 0
        self._bar_sclose = 0.0

    def _open_short_direct(self) -> None:
        """Open 30-leg short at the current leg set without waiting for VAL crossdown.
        Used after SHIFT to maintain the position at new strikes."""
        if not self.leg_instruments or len(self.leg_instruments) < 14:
            return

        self.trade_num += 1
        self.current_entry_sclose = 0.0
        self.current_entry_vwap = self.current_vwap
        self.current_entry_val = self.current_lower_band
        self.current_entry_ns = self.clock.timestamp_ns()
        self.current_entry_spot = self.latest_spot

        self.current_legs = [
            {
                "strike": leg["strike"],
                "side": leg["side"],
                "instrument_id": leg["instrument_id"],
                "entry_px": None,
                "exit_px": None,
            }
            for leg in self.leg_instruments
        ]
        self._entry_fills = 0
        self._exit_fills = 0
        self._entry_orders_submitted = len(self.current_legs)

        qty = Quantity.from_int(self.lot_size * self.num_lots)
        for leg in self.current_legs:
            order = self.order_factory.market(
                instrument_id=leg["instrument_id"],
                order_side=OrderSide.SELL,
                quantity=qty,
            )
            self.submit_order(order)

        self._fsm = STATE_PENDING_ENTRY
        self.log.info(
            f"SHIFT-ENTRY #{self.trade_num}: SHORT {len(self.current_legs)} legs at "
            f"new base_strike={self.base_strike}, spot={self.latest_spot:.2f}"
        )
