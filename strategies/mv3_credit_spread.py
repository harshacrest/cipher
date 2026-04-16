"""
MV3 Version 33 — Credit Spread Strategy (NautilusTrader)
---------------------------------------------------------
Two independent credit spreads entered after opening range breakdown.

Set 1 (PE Credit Spread):
  Sell ATM+2 PE + Buy far OTM PE (premium <= 10)
  Entry: 5-min close of ATM+2 PE crosses below its 9:15-9:19 low, after 9:25

Set 2 (CE Credit Spread):
  Sell ATM-2 CE + Buy far OTM CE (premium <= 10)
  Entry: 5-min close of ATM-2 CE crosses below its 9:15-9:19 low, after 9:25

Exits per set (monitored on bought/hedge leg):
  - 1-min close >= midpoint of hedge leg's 9:15-9:19 range
  - Trailing SL: activates +20pts, trails every 5pts, 2pt stop
  - PnL <= -2000 (SL) or PnL >= +6000 (target)  [in rupees]
  - Universal exit 15:00

Repairs are DISABLED (per spec).
"""

from __future__ import annotations

import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy

_IST_OFFSET_NS = (5 * 3600 + 30 * 60) * 1_000_000_000
_MARKET_OPEN_MIN = 9 * 60 + 15  # 9:15 AM in minutes since midnight


def _ts_to_ist_min(ts_ns: int) -> int:
    """UTC nanoseconds -> IST minutes since midnight."""
    return ((ts_ns + _IST_OFFSET_NS) // 60_000_000_000) % (24 * 60)


class MV3CreditSpreadConfig(StrategyConfig):
    # Pre-computed strikes (set by runner per day)
    sold_pe_strike: int = 0
    sold_ce_strike: int = 0
    hedge_pe_strike: int = 0
    hedge_ce_strike: int = 0

    # Pre-computed opening ranges (9:15-9:19 ltp)
    sold_pe_range_low: float = 0.0
    sold_ce_range_low: float = 0.0
    hedge_pe_range_high: float = 0.0
    hedge_pe_range_low: float = 0.0
    hedge_ce_range_high: float = 0.0
    hedge_ce_range_low: float = 0.0

    # Which sets are tradeable today
    pe_set_active: bool = True
    ce_set_active: bool = True

    # Timing
    exit_time: str = "15:00:00"

    # Risk / trailing
    lot_size: int = 75
    num_lots: int = 1
    trailing_activation_pts: float = 20.0
    trailing_step_pts: float = 5.0
    trailing_distance_pts: float = 2.0
    sl_rupees: float = 2000.0
    target_rupees: float = 6000.0

    # General
    strike_step: int = 50
    underlying: str = "NIFTY"
    venue: str = "NSE"
    spot_instrument_id: str = "NIFTY-SPOT.NSE"
    expiry_str: str = ""


class _SetState:
    """Tracks one credit spread set (PE or CE)."""

    def __init__(self, side: str) -> None:
        self.side = side  # "PE" or "CE"

        # Instrument IDs (set on_start)
        self.sold_id: InstrumentId | None = None
        self.hedge_id: InstrumentId | None = None

        # Opening range data
        self.sold_range_low: float = 0.0
        self.hedge_range_mid: float = 0.0

        # 5-min bar tracking for sold leg (entry signal)
        self.bar_5m_idx: int = -1
        self.bar_5m_close: float = 0.0

        # 1-min bar tracking for hedge leg (exit target)
        self.bar_1m_idx: int = -1
        self.bar_1m_close: float = 0.0

        # Position state
        self.entered: bool = False
        self.exited: bool = False
        self.sold_filled: bool = False
        self.hedge_filled: bool = False

        # Fill prices
        self.sold_entry_px: float = 0.0
        self.sold_exit_px: float = 0.0
        self.hedge_entry_px: float = 0.0
        self.hedge_exit_px: float = 0.0

        # Latest prices
        self.hedge_latest_bid: float = 0.0

        # Trailing SL state
        self.trailing_active: bool = False
        self.trailing_max_profit: float = 0.0
        self.trailing_stop_px: float = 0.0

        # Result metadata
        self.entry_time_str: str = ""
        self.exit_time_str: str = ""
        self.exit_reason: str = ""
        self.spot_at_entry: float = 0.0
        self.spot_at_exit: float = 0.0
        self.sold_strike: int = 0
        self.hedge_strike: int = 0


class MV3CreditSpread(Strategy):

    def __init__(self, config: MV3CreditSpreadConfig) -> None:
        super().__init__(config)
        self.spot_id = InstrumentId.from_str(config.spot_instrument_id)
        self.cfg = config

        self.latest_spot: float = 0.0
        self._date_str: str = ""
        self._eod_triggered: bool = False

        # Initialize set states
        self._pe_set: _SetState | None = None
        self._ce_set: _SetState | None = None

        if config.pe_set_active and config.sold_pe_strike > 0 and config.hedge_pe_strike > 0:
            s = _SetState("PE")
            s.sold_range_low = config.sold_pe_range_low
            s.hedge_range_mid = (config.hedge_pe_range_high + config.hedge_pe_range_low) / 2
            s.sold_strike = config.sold_pe_strike
            s.hedge_strike = config.hedge_pe_strike
            self._pe_set = s

        if config.ce_set_active and config.sold_ce_strike > 0 and config.hedge_ce_strike > 0:
            s = _SetState("CE")
            s.sold_range_low = config.sold_ce_range_low
            s.hedge_range_mid = (config.hedge_ce_range_high + config.hedge_ce_range_low) / 2
            s.sold_strike = config.sold_ce_strike
            s.hedge_strike = config.hedge_ce_strike
            self._ce_set = s

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.subscribe_quote_ticks(self.spot_id)

        # Determine trading date
        clock_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(clock_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        self._date_str = ist_dt.strftime("%Y-%m-%d")

        venue = Venue(self.cfg.venue)

        # Setup PE set instruments
        if self._pe_set:
            self._pe_set.sold_id = InstrumentId(
                Symbol(f"{self.cfg.underlying}-{self.cfg.sold_pe_strike}-PE-{self.cfg.expiry_str}"),
                venue,
            )
            self._pe_set.hedge_id = InstrumentId(
                Symbol(f"{self.cfg.underlying}-{self.cfg.hedge_pe_strike}-PE-{self.cfg.expiry_str}"),
                venue,
            )
            if not (
                self.cache.instrument(self._pe_set.sold_id)
                and self.cache.instrument(self._pe_set.hedge_id)
            ):
                self.log.warning("PE set instruments not available, disabling")
                self._pe_set = None
            else:
                self.subscribe_quote_ticks(self._pe_set.sold_id)
                self.subscribe_quote_ticks(self._pe_set.hedge_id)

        # Setup CE set instruments
        if self._ce_set:
            self._ce_set.sold_id = InstrumentId(
                Symbol(f"{self.cfg.underlying}-{self.cfg.sold_ce_strike}-CE-{self.cfg.expiry_str}"),
                venue,
            )
            self._ce_set.hedge_id = InstrumentId(
                Symbol(f"{self.cfg.underlying}-{self.cfg.hedge_ce_strike}-CE-{self.cfg.expiry_str}"),
                venue,
            )
            if not (
                self.cache.instrument(self._ce_set.sold_id)
                and self.cache.instrument(self._ce_set.hedge_id)
            ):
                self.log.warning("CE set instruments not available, disabling")
                self._ce_set = None
            else:
                self.subscribe_quote_ticks(self._ce_set.sold_id)
                self.subscribe_quote_ticks(self._ce_set.hedge_id)

        # Set EOD exit alert
        exit_ist = pd.Timestamp(f"{self._date_str} {self.cfg.exit_time}", tz="Asia/Kolkata")
        self.clock.set_time_alert_ns("eod_exit", int(exit_ist.tz_convert("UTC").value), self._on_eod_exit)

    # ------------------------------------------------------------------
    # Tick processing
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick) -> None:
        ts_ns = tick.ts_event

        if tick.instrument_id == self.spot_id:
            self.latest_spot = float(tick.bid_price)
            return

        for s in (self._pe_set, self._ce_set):
            if s is None:
                continue

            # Sold leg tick -> 5-min bar for entry signal
            if tick.instrument_id == s.sold_id:
                self._update_5m_bar(s, ts_ns, float(tick.ask_price))
                break

            # Hedge leg tick -> 1-min bar + exit checks
            if tick.instrument_id == s.hedge_id:
                bid_px = float(tick.bid_price)
                s.hedge_latest_bid = bid_px

                if s.entered and not s.exited:
                    self._update_1m_bar(s, ts_ns, bid_px)
                    self._check_tick_exits(s, ts_ns, bid_px)
                break

    # ------------------------------------------------------------------
    # 5-min bar entry logic
    # ------------------------------------------------------------------

    def _update_5m_bar(self, s: _SetState, ts_ns: int, price: float) -> None:
        if s.entered or s.exited:
            return

        ist_min = _ts_to_ist_min(ts_ns)
        bar_idx = (ist_min - _MARKET_OPEN_MIN) // 5

        if bar_idx != s.bar_5m_idx:
            # Previous bar just closed; bar_5m_close holds its close price
            if s.bar_5m_idx >= 2 and not s.entered:
                # bar_idx >= 2 means bar closed at or after 9:25
                self._check_entry(s, ts_ns)
            s.bar_5m_idx = bar_idx

        s.bar_5m_close = price

    def _check_entry(self, s: _SetState, ts_ns: int) -> None:
        if s.entered or s.exited or s.sold_range_low <= 0:
            return

        # First 5-min bar close below opening range low -> entry
        if s.bar_5m_close < s.sold_range_low:
            self._enter_set(s, ts_ns)

    # ------------------------------------------------------------------
    # Entry execution
    # ------------------------------------------------------------------

    def _enter_set(self, s: _SetState, ts_ns: int) -> None:
        if s.entered:
            return

        s.entered = True
        s.spot_at_entry = self.latest_spot

        utc_dt = pd.Timestamp(ts_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        s.entry_time_str = ist_dt.strftime("%H:%M:%S")

        qty = Quantity.from_int(self.cfg.lot_size * self.cfg.num_lots)

        # Sell the sold leg (open short)
        sell_order = self.order_factory.market(
            instrument_id=s.sold_id,
            order_side=OrderSide.SELL,
            quantity=qty,
        )
        self.submit_order(sell_order)

        # Buy the hedge leg (open long)
        buy_order = self.order_factory.market(
            instrument_id=s.hedge_id,
            order_side=OrderSide.BUY,
            quantity=qty,
        )
        self.submit_order(buy_order)

        self.log.info(
            f"ENTRY {s.side} SET: sell {s.sold_strike} buy {s.hedge_strike} "
            f"spot={self.latest_spot:.2f} time={s.entry_time_str}"
        )

    # ------------------------------------------------------------------
    # 1-min bar exit target
    # ------------------------------------------------------------------

    def _update_1m_bar(self, s: _SetState, ts_ns: int, price: float) -> None:
        ist_min = _ts_to_ist_min(ts_ns)

        if ist_min != s.bar_1m_idx:
            if s.bar_1m_idx >= 0 and s.entered and not s.exited:
                # Previous 1-min bar closed
                if s.hedge_range_mid > 0 and s.bar_1m_close >= s.hedge_range_mid:
                    self._exit_set(s, "TARGET_1M", ts_ns)
                    return
            s.bar_1m_idx = ist_min

        s.bar_1m_close = price

    # ------------------------------------------------------------------
    # Tick-level exit checks (trailing SL, PnL SL/target)
    # ------------------------------------------------------------------

    def _check_tick_exits(self, s: _SetState, ts_ns: int, hedge_bid: float) -> None:
        if not s.entered or s.exited or s.hedge_entry_px <= 0:
            return

        qty = self.cfg.lot_size * self.cfg.num_lots
        profit_pts = hedge_bid - s.hedge_entry_px
        pnl_rupees = profit_pts * qty

        # PnL-based SL
        if pnl_rupees <= -self.cfg.sl_rupees:
            self._exit_set(s, "SL_PNL", ts_ns)
            return

        # PnL-based target
        if pnl_rupees >= self.cfg.target_rupees:
            self._exit_set(s, "TARGET_PNL", ts_ns)
            return

        # Trailing SL
        act = self.cfg.trailing_activation_pts
        step = self.cfg.trailing_step_pts
        dist = self.cfg.trailing_distance_pts

        if not s.trailing_active:
            if profit_pts >= act:
                s.trailing_active = True
                s.trailing_max_profit = profit_pts
                s.trailing_stop_px = s.hedge_entry_px + act - dist
        else:
            if profit_pts > s.trailing_max_profit:
                s.trailing_max_profit = profit_pts
                steps = int((s.trailing_max_profit - act) / step)
                step_level = act + steps * step
                s.trailing_stop_px = s.hedge_entry_px + step_level - dist

            if hedge_bid <= s.trailing_stop_px:
                self._exit_set(s, "TRAILING_SL", ts_ns)

    # ------------------------------------------------------------------
    # Exit execution
    # ------------------------------------------------------------------

    def _exit_set(self, s: _SetState, reason: str, ts_ns: int) -> None:
        if s.exited:
            return

        s.exited = True
        s.exit_reason = reason
        s.spot_at_exit = self.latest_spot

        utc_dt = pd.Timestamp(ts_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        s.exit_time_str = ist_dt.strftime("%H:%M:%S")

        for pos in self.cache.positions_open(strategy_id=self.id):
            if pos.instrument_id in (s.sold_id, s.hedge_id):
                self.close_position(pos)

        self.log.info(f"EXIT {s.side} SET ({reason}): time={s.exit_time_str}")

    def _on_eod_exit(self, event) -> None:
        self._eod_triggered = True
        ts_ns = self.clock.timestamp_ns()
        for s in (self._pe_set, self._ce_set):
            if s is not None and s.entered and not s.exited:
                self._exit_set(s, "EOD", ts_ns)

    # ------------------------------------------------------------------
    # Fill tracking
    # ------------------------------------------------------------------

    def on_order_filled(self, event: OrderFilled) -> None:
        px = float(event.last_px)
        is_sell = event.order_side == OrderSide.SELL

        for s in (self._pe_set, self._ce_set):
            if s is None:
                continue

            if event.instrument_id == s.sold_id:
                if is_sell:  # entry fill (sell to open)
                    s.sold_entry_px = px
                    s.sold_filled = True
                else:  # exit fill (buy to close)
                    s.sold_exit_px = px
                return

            if event.instrument_id == s.hedge_id:
                if not is_sell:  # entry fill (buy to open)
                    s.hedge_entry_px = px
                    s.hedge_filled = True
                else:  # exit fill (sell to close)
                    s.hedge_exit_px = px
                return

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def get_daily_results(self, date_str: str) -> list[dict]:
        results = []
        qty = self.cfg.lot_size * self.cfg.num_lots

        for s in (self._pe_set, self._ce_set):
            if s is None or not s.entered:
                continue
            if s.sold_entry_px <= 0 and s.hedge_entry_px <= 0:
                continue

            sold_pnl = s.sold_entry_px - s.sold_exit_px  # short: entry - exit
            hedge_pnl = s.hedge_exit_px - s.hedge_entry_px  # long: exit - entry
            net_pnl = sold_pnl + hedge_pnl

            results.append({
                "date": date_str,
                "set": s.side,
                "sold_strike": s.sold_strike,
                "hedge_strike": s.hedge_strike,
                "entry_time": f"{date_str} {s.entry_time_str}",
                "exit_time": f"{date_str} {s.exit_time_str}" if s.exit_time_str else f"{date_str} {self.cfg.exit_time}",
                "exit_reason": s.exit_reason or "EOD",
                "spot_at_entry": round(s.spot_at_entry, 2),
                "spot_at_exit": round(s.spot_at_exit, 2),
                "sold_entry_px": round(s.sold_entry_px, 2),
                "sold_exit_px": round(s.sold_exit_px, 2),
                "hedge_entry_px": round(s.hedge_entry_px, 2),
                "hedge_exit_px": round(s.hedge_exit_px, 2),
                "sold_pnl": round(sold_pnl, 2),
                "hedge_pnl": round(hedge_pnl, 2),
                "pnl": round(net_pnl, 2),
                "pnl_rupees": round(net_pnl * qty, 2),
            })

        return results
