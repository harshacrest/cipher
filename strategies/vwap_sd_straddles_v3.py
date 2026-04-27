"""
VWAP SD Straddles V3 — NautilusTrader
--------------------------------------
Simplified variant: sells 30-leg aggregate straddle at 09:21 unconditionally.
No VWAP / SD signal — time-based entry only.

Structure (same as v1): 15 CE + 15 PE at baseStrike ± 350 (step 50).

Entry
-----
- Unconditional SHORT at 09:21 IST.
- If instruments not yet loaded or spot unknown, retry every 3 min until 15:00.

Exits (checked on every option tick):
1. Trade SL: current_sClose > entry_sClose + 500 pts  → exit, 3-min cooldown, re-enter
2. Daily SL: realized_daily + unrealized < -1500 pts  → exit, terminal (no re-entry)
3. SHIFT:   |spot - entry_spot| > atm_straddle/1.5    → exit + IMMEDIATE re-open at new ATM
4. Forced: 15:12 IST                                   → exit, terminal

Re-entry on trade-SL uses fresh baseStrike (new ATM) after cooldown.
SHIFT is a roll — same-day strike migration with no cooldown.
"""

from __future__ import annotations

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
STATE_COOLDOWN = "COOLDOWN"
STATE_TERMINAL = "TERMINAL"


class VWAPSDStraddlesV3Config(StrategyConfig):
    # Time windows (IST)
    session_start_time: str = "09:15:00"
    entry_time: str = "09:21:00"             # unconditional sell
    last_entry_time: str = "15:00:00"        # no re-entry attempts after this
    forced_exit_time: str = "15:12:00"
    eod_time: str = "15:25:00"

    # Structure
    strike_step: int = 50
    num_strikes_each_side: int = 7            # 15 strikes total (CE+PE = 30 legs)
    lot_size: int = 1
    num_lots: int = 1

    # SL thresholds (in premium points = sum of leg mids)
    trade_sl_points: float = 500.0
    daily_sl_points: float = 1500.0

    # Spot-band strike shift: spot_move > atm_straddle / spot_band_x → roll strikes
    spot_band_x: float = 1.5

    # Cooldown between trades (after trade-SL exit). SHIFT has NO cooldown.
    cooldown_minutes: float = 3.0

    # Identifiers
    underlying: str = "NIFTY"
    venue: str = "NSE"
    spot_instrument_id: str = "NIFTY-SPOT.NSE"


class VWAPSDStraddlesV3(Strategy):

    def __init__(self, config: VWAPSDStraddlesV3Config) -> None:
        super().__init__(config)
        self.spot_id = InstrumentId.from_str(config.spot_instrument_id)
        self.strike_step = config.strike_step
        self.n_side = config.num_strikes_each_side
        self.lot_size = config.lot_size
        self.num_lots = config.num_lots
        self.trade_sl = config.trade_sl_points
        self.daily_sl = config.daily_sl_points
        self.spot_band_x = config.spot_band_x
        self.cooldown_ns = int(config.cooldown_minutes * 60 * 1_000_000_000)
        self.underlying = config.underlying
        self.venue_str = config.venue

        self.expiry_str: str | None = None
        self._date_str: str = ""

        # Time boundaries
        self._entry_time = config.entry_time
        self._last_entry_time = config.last_entry_time
        self._forced_exit_time = config.forced_exit_time
        self._eod_time = config.eod_time
        self._first_entry_ns: int = 0
        self._last_entry_ns: int = 0
        self._forced_exit_ns: int = 0
        self._eod_ns: int = 0

        # Latest prices
        self.latest_spot: float = 0.0

        # Per-trade leg tracking (rebuilt at each entry)
        self.leg_instruments: list[dict] = []        # {strike, side, instrument_id, latest_mid, latest_bid, latest_ask}
        self._leg_by_id: dict = {}                   # inst_id -> leg dict

        # Per-trade state
        self._fsm: str = STATE_IDLE
        self.trade_num: int = 0
        self.completed_trades: list[dict] = []
        self.base_strike: int | None = None
        self.current_entry_sclose: float = 0.0
        self.current_entry_ns: int = 0
        self.current_entry_spot: float = 0.0
        self.current_atm_straddle: float = 0.0       # ATM CE + ATM PE at entry (for shift band)
        self.current_band_half: float = 0.0          # atm_straddle / spot_band_x
        self.current_legs: list[dict] = []           # {strike, side, instrument_id, entry_px, exit_px}
        self._entry_fills: int = 0
        self._exit_fills: int = 0
        self._entry_orders_submitted: int = 0
        self._current_exit_reason: str = ""

        # Day-level accumulator
        self.daily_pnl_points: float = 0.0           # realized across all trades today

        # Last exit timestamp (for cooldown scheduling)
        self.last_exit_ns: int = 0

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------

    def on_start(self) -> None:
        self.subscribe_quote_ticks(self.spot_id)

        # Discover expiry from any loaded option instrument
        for inst in self.cache.instruments(venue=Venue(self.venue_str)):
            sym = str(inst.id.symbol)
            if sym.startswith(f"{self.underlying}-") and sym != f"{self.underlying}-SPOT":
                parts = sym.split("-")
                if len(parts) == 4:
                    self.expiry_str = parts[3]
                    break

        # Trading date from clock
        clock_ns = self.clock.timestamp_ns()
        ist_dt = pd.Timestamp(clock_ns, unit="ns", tz="UTC").tz_convert("Asia/Kolkata")
        self._date_str = ist_dt.strftime("%Y-%m-%d")

        def to_ns(t: str) -> int:
            return int(pd.Timestamp(f"{self._date_str} {t}", tz="Asia/Kolkata").tz_convert("UTC").value)

        self._first_entry_ns = to_ns(self._entry_time)
        self._last_entry_ns = to_ns(self._last_entry_time)
        self._forced_exit_ns = to_ns(self._forced_exit_time)
        self._eod_ns = to_ns(self._eod_time)

        self.clock.set_time_alert_ns("first_entry", self._first_entry_ns, self._on_first_entry)
        self.clock.set_time_alert_ns("forced_exit", self._forced_exit_ns, self._on_forced_exit)
        self.clock.set_time_alert_ns("eod_hard", self._eod_ns, self._on_eod_hard)

    # ---------------------------------------------------------------
    # Entry
    # ---------------------------------------------------------------

    def _on_first_entry(self, event) -> None:
        if self._fsm == STATE_IDLE:
            self._try_enter()

    def _on_retry_time(self, event) -> None:
        if self._fsm == STATE_COOLDOWN:
            self._try_enter()

    def _try_enter(self) -> None:
        """Attempt an unconditional SHORT entry. Sells 30 legs around current ATM."""
        if self._fsm in (STATE_TERMINAL, STATE_PENDING_ENTRY, STATE_PENDING_EXIT, STATE_ACTIVE):
            return
        if self.latest_spot <= 0 or self.expiry_str is None:
            return

        now_ns = self.clock.timestamp_ns()
        if now_ns > self._last_entry_ns:
            self._fsm = STATE_TERMINAL
            return

        # Daily SL budget check (no point re-entering if already breached)
        if self.daily_pnl_points <= -self.daily_sl:
            self._fsm = STATE_TERMINAL
            return

        # Fresh baseStrike each entry (re-entry uses current ATM, not first-of-day)
        self.base_strike = int(round(self.latest_spot / self.strike_step) * self.strike_step)
        venue = Venue(self.venue_str)

        # Build legs — 15 CE + 15 PE, ATM ± n_side * step
        self.leg_instruments = []
        self._leg_by_id = {}
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

        if len(self.leg_instruments) < 10:
            # Not enough strikes loaded — retry after cooldown
            self._schedule_retry(now_ns)
            return

        self.trade_num += 1
        self.current_entry_ns = now_ns
        self.current_entry_spot = self.latest_spot
        # Entry sClose snapshot will come from next option tick (lazy) — for now use placeholder
        self.current_entry_sclose = 0.0

        # Snapshot legs for this trade
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
            f"ENTRY #{self.trade_num}: SHORT {len(self.current_legs)} legs at "
            f"base_strike={self.base_strike}, spot={self.latest_spot:.2f}"
        )

    def _schedule_retry(self, now_ns: int) -> None:
        retry_ns = now_ns + self.cooldown_ns
        if retry_ns > self._last_entry_ns:
            self._fsm = STATE_TERMINAL
            return
        self._fsm = STATE_COOLDOWN
        self.last_exit_ns = now_ns
        self.clock.set_time_alert_ns(f"retry_{now_ns}", retry_ns, self._on_retry_time)

    # ---------------------------------------------------------------
    # Tick handler: track leg mids, check exit SLs
    # ---------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        inst_id = tick.instrument_id

        if inst_id == self.spot_id:
            self.latest_spot = float(tick.bid_price)
            # Strike-shift check: spot move beyond band → roll to new ATM
            if self._fsm == STATE_ACTIVE and self.current_band_half > 0:
                move = abs(self.latest_spot - self.current_entry_spot)
                if move > self.current_band_half:
                    self.log.info(
                        f"SHIFT: spot_move={move:.2f} > band_half={self.current_band_half:.2f} "
                        f"(straddle={self.current_atm_straddle:.2f})"
                    )
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

        # When active, check SLs
        if self._fsm == STATE_ACTIVE:
            sclose = self._compute_sclose()
            if sclose is None:
                return

            # Lazy capture of entry_sclose on first post-fill tick
            if self.current_entry_sclose <= 0.0:
                self.current_entry_sclose = sclose

            # --- Trade SL ---
            if sclose > self.current_entry_sclose + self.trade_sl:
                self.log.info(
                    f"Trade SL: sclose={sclose:.2f} > entry_sclose+{self.trade_sl:.0f}={self.current_entry_sclose + self.trade_sl:.2f}"
                )
                self._exit_all("TRADE_SL")
                return

            # --- Daily SL (realized + unrealized from entry_sclose) ---
            # Unrealized = entry_sclose - current_sclose (we're short the aggregate)
            unrealized = self.current_entry_sclose - sclose
            total_day = self.daily_pnl_points + unrealized
            if total_day <= -self.daily_sl:
                self.log.info(
                    f"Daily SL: day_total={total_day:.2f} <= -{self.daily_sl:.0f}"
                )
                self._exit_all("DAILY_SL")
                return

    def _compute_sclose(self) -> float | None:
        """Sum of all current leg mids. Returns None unless ALL legs have a mid —
        otherwise sclose grows as more legs' first ticks arrive, producing a
        false 'premium rising' signal that fires trade SL on the first few ticks."""
        total = 0.0
        n = 0
        for leg in self.leg_instruments:
            m = leg["latest_mid"]
            if m is None:
                return None
            total += m
            n += 1
        return total if n > 0 else None

    # ---------------------------------------------------------------
    # Exit
    # ---------------------------------------------------------------

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

        self.daily_pnl_points += trade_pnl_points

        entry_ist = pd.Timestamp(self.current_entry_ns, unit="ns", tz="UTC").tz_convert("Asia/Kolkata")
        exit_ist = pd.Timestamp(self.clock.timestamp_ns(), unit="ns", tz="UTC").tz_convert("Asia/Kolkata")

        exit_sclose = self._compute_sclose() or 0.0

        trade_record = {
            "date": self._date_str,
            "trade_num": self.trade_num,
            "entry_time": entry_ist.strftime("%H:%M:%S"),
            "exit_time": exit_ist.strftime("%H:%M:%S"),
            "exit_reason": self._current_exit_reason,
            "base_strike": self.base_strike,
            "spot_at_entry": round(self.current_entry_spot, 2),
            "spot_at_exit": round(self.latest_spot, 2),
            "entry_sclose": round(self.current_entry_sclose, 2),
            "exit_sclose": round(exit_sclose, 2),
            "atm_straddle": round(self.current_atm_straddle, 2),
            "band_half": round(self.current_band_half, 2),
            "num_legs": len(self.current_legs),
            "pnl_points": round(trade_pnl_points, 2),
            "pnl_premium": round(trade_pnl_premium, 2),
            "pnl": round(trade_pnl_points, 2),           # reporting expects "pnl"
            "daily_pnl_points": round(self.daily_pnl_points, 2),
        }
        self.completed_trades.append(trade_record)

        # Decide next state
        if self._current_exit_reason in ("DAILY_SL", "FORCED", "EOD_HARD"):
            self._fsm = STATE_TERMINAL
            return

        # Clear per-trade state but keep day-level accumulator
        self.current_legs = []
        self.current_entry_sclose = 0.0
        self.current_atm_straddle = 0.0
        self.current_band_half = 0.0
        self.base_strike = None

        now_ns = self.clock.timestamp_ns()
        self.last_exit_ns = now_ns

        # Daily SL check (can't re-enter if budget blown)
        if self.daily_pnl_points <= -self.daily_sl:
            self._fsm = STATE_TERMINAL
            return

        # SHIFT = immediate re-enter at new ATM (no cooldown)
        if self._current_exit_reason == "SHIFT":
            if now_ns > self._last_entry_ns:
                self._fsm = STATE_TERMINAL
                return
            self._fsm = STATE_IDLE
            self._try_enter()
            return

        # TRADE_SL → cooldown → possibly re-enter
        retry_ns = now_ns + self.cooldown_ns
        if retry_ns > self._last_entry_ns:
            self._fsm = STATE_TERMINAL
            return
        self._fsm = STATE_COOLDOWN
        self.clock.set_time_alert_ns(f"cooldown_{retry_ns}", retry_ns, self._on_retry_time)

    # ---------------------------------------------------------------
    # Time alerts
    # ---------------------------------------------------------------

    def _on_forced_exit(self, event) -> None:
        if self._fsm == STATE_ACTIVE:
            self._exit_all("FORCED")
        elif self._fsm not in (STATE_PENDING_EXIT,):
            self._fsm = STATE_TERMINAL

    def _on_eod_hard(self, event) -> None:
        if self._fsm == STATE_ACTIVE:
            self._exit_all("EOD_HARD")
        elif self._fsm not in (STATE_PENDING_EXIT,):
            self._fsm = STATE_TERMINAL

    # ---------------------------------------------------------------
    # Fill tracking
    # ---------------------------------------------------------------

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
                # Snapshot ATM straddle from the ATM CE + ATM PE entry fills (band sizing)
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
        else:
            matching["exit_px"] = px
            self._exit_fills += 1
            if self._fsm == STATE_PENDING_EXIT and self._exit_fills >= self._entry_fills:
                self._finalize_trade()

    # ---------------------------------------------------------------
    # Public hooks for runner
    # ---------------------------------------------------------------

    def get_all_trades(self, date_str: str) -> list[dict]:
        return list(self.completed_trades)
