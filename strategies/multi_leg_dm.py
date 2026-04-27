"""
MultiLegDM Strategy — NautilusTrader
-------------------------------------
At each entry, sells 6 short strangles simultaneously (12 legs total, all ATM/OTM
— never ITM at entry):

  Strangle 1: ATM CE + ATM PE
  Strangle 2: OTM_1 CE + OTM_1 PE  (ATM ± 50)
  Strangle 3: OTM_2 CE + OTM_2 PE  (ATM ± 100)
  Strangle 4: OTM_3 CE + OTM_3 PE  (ATM ± 150)
  Strangle 5: OTM_4 CE + OTM_4 PE  (ATM ± 200)
  Strangle 6: OTM_5 CE + OTM_5 PE  (ATM ± 250)

Quantity per leg: lot_size * num_lots_per_strangle (default 1 * 1).

Entry window
------------
First entry at 09:21 IST (clock alert). After every exit, the FSM enters a
3-minute COOLDOWN and may re-enter with fresh strikes (new ATM) until 14:05.
EOD flatten at 14:51.

Exit triggers (evaluated on every relevant tick)
------------------------------------------------
1. Daily SL  — realized + unrealized for the day <= daily_sl_threshold_premium
              (default -1500 pts) -> exit all, day goes TERMINAL.
2. Trade SL  — unrealized < trade_sl_premium (default -500 pts) -> exit all,
              cooldown, may re-enter.
3. Spot band — |spot - spot_at_entry| > atm_straddle_at_entry / spot_band_x,
              where spot_band_x is DTE-aware:
                spot_band_x_far_dte  = 3.0 for DTE >= 2  (tighter band)
                spot_band_x_near_dte = 2.0 for DTE <= 1  (wider band)
              -> exit all, cooldown, may re-enter.
4. EOD       — clock alert at 14:51 IST -> force-flatten, terminalize.

Re-entry budget gate
--------------------
Before each entry, remaining headroom = daily_pnl - daily_sl. If headroom is
below min_reenter_budget_premium (0.48 pts), the day terminalizes — prevents
entries that can't even fit one full SL within the daily cap.

DTE source
----------
DTE is the canonical TRADING-day count derived from the trading-dates table
(data/NSE/trading_dates.csv) — NOT a calendar diff. Calendar DTE would inflate
Friday/Monday cycles by the weekend (Friday-before-Thu-expiry is 6 calendar
days but only 4 trading days). All reporting (intraday JSONs, MTM analysis,
frontend tabs) reads the same column for consistency.

PnL accounting
--------------
- Realized at exit:    pnl_points = entry_px - exit_px per leg.
- Unrealized intraday: baseline is mid (bid+ask)/2 at first tick AFTER the
                       entry fill, NOT the SELL fill_px (which would count
                       the entry half-spread as instant unrealized loss).
                       Realized PnL at exit still captures the round-trip
                       spread cost.
- Daily PnL accumulates across re-entries (fed to daily SL + budget gate).

State machine
-------------
IDLE -> PENDING_ENTRY -> ACTIVE -> PENDING_EXIT -> COOLDOWN -> (PENDING_ENTRY | TERMINAL)
                                              \\-> TERMINAL  (DAILY_SL / EOD / no-budget / past 14:05)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


# ──────────────────────────────────────────────────────────────────────────
# Trading-day DTE source — loaded once at module import, reused across all
# per-day BacktestEngine runs. This is the CANONICAL DTE used by both the
# strategy's band-divisor selection and downstream reporting.
#
# Source: NSE/trading_dates.csv has a `DTE` column = trading-day count to
# nearest expiry (Exp1). NIFTY weeklies range 0..5. Calendar diff would
# inflate Friday/Monday cycles by the weekend (e.g. Friday-before-Thu-expiry
# is 6 calendar days but only 4 trading days), which would mis-route those
# days into the wrong band-divisor branch.
# ──────────────────────────────────────────────────────────────────────────
_TRADING_DATES_CSV = Path("/Users/harsha/Desktop/Research/DATA/NSE/trading_dates.csv")


def _load_dte_lookup() -> dict[str, int]:
    """{trade_date_str (YYYY-MM-DD): trading_day_dte}. Empty dict if file missing."""
    if not _TRADING_DATES_CSV.exists():
        return {}
    df = pd.read_csv(_TRADING_DATES_CSV, usecols=["t_date", "DTE"])
    df = df.dropna(subset=["DTE"])
    df["t_date"] = pd.to_datetime(df["t_date"]).dt.strftime("%Y-%m-%d")
    df["DTE"] = df["DTE"].astype(int)
    return dict(zip(df["t_date"], df["DTE"]))


_DTE_LOOKUP: dict[str, int] = _load_dte_lookup()


# State machine
STATE_IDLE = "IDLE"                # before first entry
STATE_PENDING_ENTRY = "PENDING"    # orders submitted, waiting for fills
STATE_ACTIVE = "ACTIVE"            # all legs filled, monitoring exits
STATE_PENDING_EXIT = "EXITING"     # exit orders submitted, waiting for fills
STATE_COOLDOWN = "COOLDOWN"        # between trades
STATE_TERMINAL = "TERMINAL"        # no more entries for the day


class MultiLegDMConfig(StrategyConfig):
    entry_time: str = "09:21:00"
    last_entry_time: str = "14:05:00"
    exit_time: str = "14:51:00"
    strike_step: int = 50
    lot_size: int = 1
    num_lots_per_strangle: int = 1
    num_strangles: int = 6                 # ATM + OTM_1..5
    fixed_margin: float = 1_000_000.0
    daily_sl_threshold_premium: float = -1500.0    # hard daily loss cap in premium units
    trade_sl_premium: float = -500.0               # per-trade loss SL in premium units
    min_reenter_budget_premium: float = 0.48       # block re-entry if remaining headroom below this
    # Spot-band divisor — band_half = ATM_straddle / divisor.
    # Higher divisor → tighter band → exits sooner on spot drift.
    # We use a tighter band on far-DTE (more theta to protect, less gamma)
    # and a wider band on 0/1 DTE (gamma is large, expect more spot whippiness).
    spot_band_x_far_dte: float = 3.0   # used when DTE >= 2
    spot_band_x_near_dte: float = 2.0  # used when DTE <= 1
    cooldown_minutes: float = 3.0
    underlying: str = "NIFTY"
    venue: str = "NSE"
    spot_instrument_id: str = "NIFTY-SPOT.NSE"


class MultiLegDM(Strategy):

    def __init__(self, config: MultiLegDMConfig) -> None:
        super().__init__(config)
        self.spot_id = InstrumentId.from_str(config.spot_instrument_id)
        self.entry_time = config.entry_time
        self.last_entry_time = config.last_entry_time
        self.exit_time = config.exit_time
        self.strike_step = config.strike_step
        self.lot_size = config.lot_size
        self.num_lots = config.num_lots_per_strangle
        self.num_strangles = config.num_strangles
        self.fixed_margin = config.fixed_margin
        self.daily_sl_premium = config.daily_sl_threshold_premium
        self.trade_sl_premium = config.trade_sl_premium
        self.min_reenter_premium = config.min_reenter_budget_premium
        self.spot_band_x_far_dte = config.spot_band_x_far_dte
        self.spot_band_x_near_dte = config.spot_band_x_near_dte
        self.cooldown_ns = int(config.cooldown_minutes * 60 * 1_000_000_000)
        self.underlying = config.underlying
        self.venue_str = config.venue

        # Per-day state
        self.daily_pnl_premium: float = 0.0
        self.completed_trades: list[dict] = []
        self.expiry_str: str | None = None
        self._date_str: str = ""
        self._dte: int | None = None      # trading days to expiry — sourced from data/NSE/trading_dates.csv
        self._last_entry_ns: int = 0
        self._eod_exit_ns: int = 0

        # Per-trade state — reset each entry
        self._fsm: str = STATE_IDLE
        self.trade_num: int = 0
        self.current_legs: list[dict] = []
        # Each leg: {strike, side, instrument_id, entry_px, exit_px, entry_time, exit_time, active, pnl_points, pnl_premium}

        self.current_spot_entry: float = 0.0
        self.current_spot_exit: float = 0.0
        self.current_atm_straddle: float = 0.0
        self.current_band_half: float = 0.0
        self.current_entry_ns: int = 0
        self.current_exit_ns: int = 0
        self.current_exit_reason: str = ""
        self.last_exit_ns: int = 0

        # Latest prices
        self.latest_spot: float = 0.0
        self.latest_option_asks: dict[str, float] = {}  # inst_id_str -> ask
        self.latest_option_bids: dict[str, float] = {}  # inst_id_str -> bid (for mid-mark unrealized)

        # Fill counters
        self._entry_fills: int = 0
        self._exit_fills: int = 0
        self._entry_orders_submitted: int = 0

    # -----------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------

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

        # Determine trading date from clock
        clock_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(clock_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        self._date_str = ist_dt.strftime("%Y-%m-%d")

        # Lookup trading-day DTE from data/NSE/trading_dates.csv. This is the
        # canonical source used by both this strategy and downstream reporting.
        # Falls back to None if the date isn't in the CSV (rare; ~35 NaN rows
        # in early data) — _active_spot_band_x() then defaults to far-DTE divisor.
        self._dte = _DTE_LOOKUP.get(self._date_str)
        if self._dte is not None:
            self.log.info(
                f"DTE={self._dte} (trading days), band_x="
                f"{self._active_spot_band_x():.2f} "
                f"(near<=1: {self.spot_band_x_near_dte}, far>=2: {self.spot_band_x_far_dte})"
            )
        else:
            self.log.warning(
                f"DTE not found for {self._date_str} in trading_dates.csv — "
                f"defaulting to far-DTE band_x={self.spot_band_x_far_dte}"
            )

        # Schedule first entry + EOD exit
        first_entry_ist = pd.Timestamp(f"{self._date_str} {self.entry_time}", tz="Asia/Kolkata")
        last_entry_ist = pd.Timestamp(f"{self._date_str} {self.last_entry_time}", tz="Asia/Kolkata")
        eod_ist = pd.Timestamp(f"{self._date_str} {self.exit_time}", tz="Asia/Kolkata")

        self._last_entry_ns = int(last_entry_ist.tz_convert("UTC").value)
        self._eod_exit_ns = int(eod_ist.tz_convert("UTC").value)

        first_entry_ns = int(first_entry_ist.tz_convert("UTC").value)
        self.clock.set_time_alert_ns("first_entry", first_entry_ns, self._on_first_entry)
        self.clock.set_time_alert_ns("eod_exit", self._eod_exit_ns, self._on_eod_exit)

    # -----------------------------------------------------------------
    # Entry
    # -----------------------------------------------------------------

    def _on_first_entry(self, event) -> None:
        if self._fsm == STATE_IDLE:
            self._try_enter()

    def _try_enter(self) -> None:
        """Attempt a new entry. Sets state to PENDING_ENTRY on success."""
        if self._fsm in (STATE_TERMINAL, STATE_PENDING_ENTRY, STATE_PENDING_EXIT, STATE_ACTIVE):
            return
        if self.latest_spot <= 0 or self.expiry_str is None:
            return

        now_ns = self.clock.timestamp_ns()
        if now_ns > self._last_entry_ns:
            self._fsm = STATE_TERMINAL
            return

        # Check remaining budget
        remaining_budget = self.daily_pnl_premium - self.daily_sl_premium
        if remaining_budget <= self.min_reenter_premium:
            self.log.info(f"Re-entry blocked: remaining budget {remaining_budget:.0f} <= {self.min_reenter_premium:.0f}")
            self._fsm = STATE_TERMINAL
            return

        # Compute ATM from current spot
        atm = int(round(self.latest_spot / self.strike_step) * self.strike_step)

        # Build 12 legs
        venue = Venue(self.venue_str)
        legs: list[dict] = []
        atm_ce_id = None
        atm_pe_id = None
        for i in range(self.num_strangles):
            offset = i * self.strike_step
            ce_strike = atm + offset
            pe_strike = atm - offset
            ce_sym = f"{self.underlying}-{ce_strike}-CE-{self.expiry_str}"
            pe_sym = f"{self.underlying}-{pe_strike}-PE-{self.expiry_str}"
            ce_id = InstrumentId(Symbol(ce_sym), venue)
            pe_id = InstrumentId(Symbol(pe_sym), venue)

            if i == 0:
                atm_ce_id = ce_id
                atm_pe_id = pe_id

            ce_ok = self.cache.instrument(ce_id) is not None
            pe_ok = self.cache.instrument(pe_id) is not None
            if not ce_ok or not pe_ok:
                if i == 0:
                    # ATM missing → retry in 3 min
                    self._schedule_retry(now_ns)
                    return
                continue  # skip this OTM strangle

            legs.append({
                "strike": ce_strike, "side": "CE", "instrument_id": ce_id,
                "entry_px": None, "exit_px": None,
                "entry_mid": None,  # snapshot of MID at entry, used for unrealized PnL baseline
                "entry_time": None, "exit_time": None,
                "active": False, "pnl_points": 0.0, "pnl_premium": 0.0,
            })
            legs.append({
                "strike": pe_strike, "side": "PE", "instrument_id": pe_id,
                "entry_px": None, "exit_px": None,
                "entry_mid": None,
                "entry_time": None, "exit_time": None,
                "active": False, "pnl_points": 0.0, "pnl_premium": 0.0,
            })

        if not legs:
            self._schedule_retry(now_ns)
            return

        self.trade_num += 1
        self.current_legs = legs
        self.current_spot_entry = self.latest_spot
        self.current_entry_ns = now_ns
        self._entry_fills = 0
        self._exit_fills = 0
        self._entry_orders_submitted = len(legs)

        # Subscribe to option ticks
        for leg in legs:
            self.subscribe_quote_ticks(leg["instrument_id"])

        # Submit all 12 SELL orders
        qty = Quantity.from_int(self.lot_size * self.num_lots)
        for leg in legs:
            order = self.order_factory.market(
                instrument_id=leg["instrument_id"],
                order_side=OrderSide.SELL,
                quantity=qty,
            )
            self.submit_order(order)

        self._fsm = STATE_PENDING_ENTRY
        self.log.info(
            f"ENTRY#{self.trade_num}: ATM={atm}, {len(legs)} legs submitted, spot={self.latest_spot:.2f}"
        )

    def _schedule_retry(self, now_ns: int) -> None:
        retry_ns = now_ns + self.cooldown_ns
        if retry_ns > self._last_entry_ns:
            self._fsm = STATE_TERMINAL
            return
        self._fsm = STATE_COOLDOWN
        self.last_exit_ns = now_ns
        self.clock.set_time_alert_ns(f"retry_{now_ns}", retry_ns, self._on_retry_time)

    def _on_retry_time(self, event) -> None:
        if self._fsm == STATE_COOLDOWN:
            self._try_enter()

    # -----------------------------------------------------------------
    # Tick handlers
    # -----------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        inst_id = tick.instrument_id

        if inst_id == self.spot_id:
            self.latest_spot = float(tick.bid_price)
            if self._fsm == STATE_ACTIVE:
                self._check_spot_band()
                self._check_daily_sl()
            return

        # Option tick — update latest bid/ask
        ask = float(tick.ask_price)
        bid = float(tick.bid_price)
        inst_str = str(inst_id)
        self.latest_option_asks[inst_str] = ask
        self.latest_option_bids[inst_str] = bid

        # Lazy snapshot of entry_mid — first quote tick after entry fill
        for leg in self.current_legs:
            if leg["instrument_id"] == inst_id and leg["active"] and leg["entry_mid"] is None:
                leg["entry_mid"] = (bid + ask) / 2.0
                break

        if self._fsm == STATE_ACTIVE:
            self._check_trade_sl()
            if self._fsm == STATE_ACTIVE:
                self._check_daily_sl()

    def _check_trade_sl(self) -> None:
        unrealized = self._compute_unrealized_pnl_premium()
        if unrealized < self.trade_sl_premium:
            self.log.info(
                f"TRADE_SL exit: unrealized={unrealized:.2f} < {self.trade_sl_premium:.2f}"
            )
            self._exit_all("TRADE_SL")

    def _check_spot_band(self) -> None:
        if self.current_band_half <= 0:
            return
        move = abs(self.latest_spot - self.current_spot_entry)
        if move > self.current_band_half:
            self.log.info(
                f"SPOT_BAND exit: move={move:.2f} > half={self.current_band_half:.2f}"
            )
            self._exit_all("SPOT_BAND")

    def _check_daily_sl(self) -> None:
        unrealized = self._compute_unrealized_pnl_premium()
        total = self.daily_pnl_premium + unrealized
        if total < self.daily_sl_premium:
            self._exit_all("DAILY_SL")

    def _compute_unrealized_pnl_premium(self) -> float:
        """Mark to current MID using ENTRY_MID as baseline (not fill_px).

        Rationale: our SELL market orders fill at the bid. Using fill_px as
        baseline would count the entry half-spread as an immediate unrealized
        loss, which is not a real adverse move — it's just spread crossing.
        We snapshot mid at entry-fill time and measure drift in mid vs mid.
        Realized PnL at exit still captures the full round-trip spread cost.
        """
        if self._fsm != STATE_ACTIVE:
            return 0.0
        total = 0.0
        contracts = self.lot_size * self.num_lots
        for leg in self.current_legs:
            if not leg["active"] or leg["entry_mid"] is None:
                continue
            inst_str = str(leg["instrument_id"])
            bid = self.latest_option_bids.get(inst_str)
            ask = self.latest_option_asks.get(inst_str)
            if bid is None or ask is None:
                continue
            current_mid = (bid + ask) / 2.0
            # Short position unrealized = entry_mid - current_mid, per contract
            total += (leg["entry_mid"] - current_mid) * contracts
        return total

    # -----------------------------------------------------------------
    # Exit
    # -----------------------------------------------------------------

    def _on_eod_exit(self, event) -> None:
        """Force-exit at EOD. Do NOT set TERMINAL here — let _finalize_trade
        transition after exit fills are processed. If no active trade, go terminal."""
        if self._fsm == STATE_ACTIVE:
            self._exit_all("EOD")
        elif self._fsm != STATE_PENDING_EXIT:
            # Not trading — safe to terminalize
            self._fsm = STATE_TERMINAL

    def _exit_all(self, reason: str) -> None:
        if self._fsm != STATE_ACTIVE:
            return
        self.current_exit_reason = reason
        self.current_spot_exit = self.latest_spot
        self.current_exit_ns = self.clock.timestamp_ns()
        self._fsm = STATE_PENDING_EXIT

        # Close all open positions for this strategy
        open_positions = list(self.cache.positions_open(strategy_id=self.id))
        if not open_positions:
            # Nothing to close — finalize immediately
            self._finalize_trade()
            return
        for pos in open_positions:
            self.close_position(pos)

    def _finalize_trade(self) -> None:
        """Called when all exit fills are recorded OR no positions exist."""
        # Compute per-leg PnL in premium units
        contracts = self.lot_size * self.num_lots
        trade_pnl_premium = 0.0
        trade_pnl_points = 0.0
        for leg in self.current_legs:
            if leg["entry_px"] is not None and leg["exit_px"] is not None:
                pts = leg["entry_px"] - leg["exit_px"]
                leg["pnl_points"] = round(pts, 4)
                leg["pnl_premium"] = round(pts * contracts, 2)
                trade_pnl_points += pts
                trade_pnl_premium += pts * contracts

        self.daily_pnl_premium += trade_pnl_premium

        # Record trade
        entry_ist = pd.Timestamp(self.current_entry_ns, unit="ns", tz="UTC").tz_convert("Asia/Kolkata")
        exit_ist = pd.Timestamp(self.current_exit_ns, unit="ns", tz="UTC").tz_convert("Asia/Kolkata")

        trade_record = {
            "date": self._date_str,
            "trade_num": self.trade_num,
            "entry_time": entry_ist.strftime("%H:%M:%S"),
            "exit_time": exit_ist.strftime("%H:%M:%S"),
            "exit_reason": self.current_exit_reason,
            "spot_at_entry": round(self.current_spot_entry, 2),
            "spot_at_exit": round(self.current_spot_exit, 2),
            "spot_move": round(self.current_spot_exit - self.current_spot_entry, 2),
            "atm_strike": int(round(self.current_spot_entry / self.strike_step) * self.strike_step),
            "atm_straddle": round(self.current_atm_straddle, 2),
            "band_half": round(self.current_band_half, 2),
            "num_legs": len(self.current_legs),
            "pnl_points": round(trade_pnl_points, 2),
            "pnl_premium": round(trade_pnl_premium, 2),
            "cumulative_daily_pnl_premium": round(self.daily_pnl_premium, 2),
            "legs": [
                {
                    "strike": leg["strike"],
                    "side": leg["side"],
                    "entry_px": leg["entry_px"],
                    "exit_px": leg["exit_px"],
                    "pnl_points": leg["pnl_points"],
                    "pnl_premium": leg["pnl_premium"],
                }
                for leg in self.current_legs
            ],
        }
        self.completed_trades.append(trade_record)

        # Decide next state
        if self.current_exit_reason in ("DAILY_SL", "EOD"):
            self._fsm = STATE_TERMINAL
            return

        # Cooldown + possibly re-enter
        self.last_exit_ns = self.current_exit_ns
        cooldown_end = self.last_exit_ns + self.cooldown_ns

        if cooldown_end > self._last_entry_ns:
            # Cooldown end is past last entry deadline — no re-entry
            self._fsm = STATE_TERMINAL
            return

        # Check budget
        remaining_budget = self.daily_pnl_premium - self.daily_sl_premium
        if remaining_budget <= self.min_reenter_premium:
            self._fsm = STATE_TERMINAL
            return

        # Reset per-trade state (but keep daily_pnl_premium + completed_trades)
        self.current_legs = []
        self.current_atm_straddle = 0.0
        self.current_band_half = 0.0
        self.current_spot_entry = 0.0

        self._fsm = STATE_COOLDOWN
        self.clock.set_time_alert_ns(f"cooldown_{cooldown_end}", cooldown_end, self._on_retry_time)

    # -----------------------------------------------------------------
    # Order fills
    # -----------------------------------------------------------------

    def on_order_filled(self, event: OrderFilled) -> None:
        px = float(event.last_px)
        is_sell = event.order_side == OrderSide.SELL
        inst_id = event.instrument_id

        # Find matching leg
        matching_leg = None
        for leg in self.current_legs:
            if leg["instrument_id"] == inst_id and (
                (is_sell and leg["entry_px"] is None) or
                (not is_sell and leg["entry_px"] is not None and leg["exit_px"] is None)
            ):
                matching_leg = leg
                break

        if matching_leg is None:
            return

        if is_sell:
            # Entry fill. entry_mid is snapshotted LAZILY in on_quote_tick because
            # on_order_filled fires BEFORE on_quote_tick updates latest_option_bids/asks.
            matching_leg["entry_px"] = px
            matching_leg["entry_mid"] = None  # filled by on_quote_tick's next tick for this instrument
            matching_leg["active"] = True
            matching_leg["entry_time"] = self._now_hms()
            self._entry_fills += 1

            if self._fsm == STATE_PENDING_ENTRY and self._entry_fills >= self._entry_orders_submitted:
                self._on_all_entries_filled()
        else:
            # Exit fill (buy-to-close)
            matching_leg["exit_px"] = px
            matching_leg["active"] = False
            matching_leg["exit_time"] = self._now_hms()
            self._exit_fills += 1

            if self._fsm == STATE_PENDING_EXIT and self._exit_fills >= self._entry_fills:
                self._finalize_trade()

    def _on_all_entries_filled(self) -> None:
        # Compute ATM straddle premium from ATM CE + ATM PE entry fills
        atm_ce_px = None
        atm_pe_px = None
        # ATM legs are the first two (i=0 in _try_enter)
        for leg in self.current_legs[:2]:
            if leg["side"] == "CE":
                atm_ce_px = leg["entry_px"]
            elif leg["side"] == "PE":
                atm_pe_px = leg["entry_px"]

        active_band_x = self._active_spot_band_x()
        if atm_ce_px is not None and atm_pe_px is not None:
            self.current_atm_straddle = atm_ce_px + atm_pe_px
            self.current_band_half = self.current_atm_straddle / active_band_x
        else:
            # ATM legs missing — fall back to combining all entries (shouldn't happen)
            total_entry = sum(
                leg["entry_px"] for leg in self.current_legs if leg["entry_px"] is not None
            )
            self.current_atm_straddle = total_entry / max(len(self.current_legs) / 2, 1)
            self.current_band_half = self.current_atm_straddle / active_band_x

        self._fsm = STATE_ACTIVE
        self.log.info(
            f"ACTIVE#{self.trade_num}: atm_straddle={self.current_atm_straddle:.2f}, "
            f"band_half={self.current_band_half:.2f}, spot_entry={self.current_spot_entry:.2f}"
        )

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _active_spot_band_x(self) -> float:
        """Pick the spot-band divisor based on calendar DTE.

        DTE <= 1 (today/tomorrow expiry) → near-DTE divisor (default 2.0, wider band)
        DTE >= 2                          → far-DTE divisor  (default 3.0, tighter band)
        Unknown DTE                       → far-DTE divisor (safer/tighter default)
        """
        if self._dte is not None and self._dte <= 1:
            return self.spot_band_x_near_dte
        return self.spot_band_x_far_dte

    def _now_hms(self) -> str:
        ts_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(ts_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        return ist_dt.strftime("%H:%M:%S")

    def get_all_trades(self, date_str: str) -> list[dict]:
        """Return all completed trades for this day. Called by runner after engine.run()."""
        return list(self.completed_trades)
