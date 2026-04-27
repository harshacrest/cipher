"""
Directional OP Selling — NIFTY 50 Credit Spreads
-------------------------------------------------
9/21 EMA crossover on 15-min bars drives direction.
Bullish → PE credit spread, Bearish → CE credit spread.

Sets 1/2: Morning session (non-expiry or expiry before noon).
Sets 3/4: Expiry day afternoon (after 12:00 PM).

Premium-based strike selection (premium units):
  Morning: Buy >25, Sell <120
  Afternoon (expiry): Buy closest to 50, Sell closest to 150

Exit: 55% SL on sold leg, 70% target on sold leg,
      EMA signal reversal, expiry EOD for morning trades.
"""

from __future__ import annotations

import pandas as pd
import numpy as np

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.enums import OrderSide, OptionKind
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class DirectionalOPSellConfig(StrategyConfig):
    strike_step: int = 50
    lot_size: int = 1
    num_lots: int = 1
    sl_pct: float = 55.0       # SL on sold leg (price increase %)
    target_pct: float = 70.0   # Target on sold leg (price decrease %)
    ema_fast: int = 9
    ema_slow: int = 21
    bar_minutes: int = 15
    morning_start: str = "09:17:00"
    expiry_cutoff: str = "12:00:00"
    afternoon_start: str = "12:00:00"
    expiry_eod_exit: str = "15:17:00"
    final_exit: str = "15:25:00"
    # Morning premium filters
    buy_premium_min: float = 25.0
    sell_premium_max: float = 120.0
    # Afternoon (expiry) premium targets
    buy_premium_target: float = 50.0
    sell_premium_target: float = 150.0
    underlying: str = "NIFTY"
    venue: str = "NSE"
    spot_instrument_id: str = "NIFTY-SPOT.NSE"


class DirectionalOPSell(Strategy):

    def __init__(self, config: DirectionalOPSellConfig) -> None:
        super().__init__(config)
        self.cfg = config
        self.spot_id = InstrumentId.from_str(config.spot_instrument_id)

        # EMA state
        self._bar_close_prices: list[float] = []
        self._current_bar_start_ns: int = 0
        self._current_bar_open: float = 0.0
        self._current_bar_high: float = 0.0
        self._current_bar_low: float = float("inf")
        self._current_bar_close: float = 0.0
        self._bar_interval_ns = config.bar_minutes * 60 * 1_000_000_000
        self._ema_fast_val: float | None = None
        self._ema_slow_val: float | None = None
        self._prev_ema_fast: float | None = None
        self._prev_ema_slow: float | None = None
        self._ema_fast_mult = 2.0 / (config.ema_fast + 1)
        self._ema_slow_mult = 2.0 / (config.ema_slow + 1)
        self._bars_count = 0

        # Spot
        self.latest_spot: float = 0.0

        # Option premiums cache: {instrument_id_str: last_ask_price}
        self._option_premiums: dict[str, float] = {}

        # Expiry
        self.expiry_str: str | None = None
        self._date_str: str = ""
        self._is_expiry_day: bool = False

        # Position state
        self._active_set: int | None = None  # 1,2,3,4
        self._buy_leg_id: InstrumentId | None = None
        self._sell_leg_id: InstrumentId | None = None
        self._entry_sell_px: float | None = None
        self._entry_buy_px: float | None = None
        self._exit_sell_px: float | None = None
        self._exit_buy_px: float | None = None
        self._sell_sl: float = 0.0
        self._sell_target: float = 0.0
        self._direction: str | None = None  # "bullish" or "bearish"

        # Tracking
        self._latest_sell_px: float = 0.0
        self._entered: bool = False
        self._exited: bool = False
        self._exit_reason: str | None = None
        self._entry_time_str: str | None = None
        self._exit_time_str: str | None = None
        self.spot_at_entry: float = 0.0
        self.spot_at_exit: float = 0.0

        # Pending repair: waiting for buy fill before placing sell
        self._pending_sell: bool = False

        # For morning set: check for expiry EOD exit
        self._morning_set: bool = False

        # Alert flags
        self._final_exit_set: bool = False

    def on_start(self) -> None:
        self.subscribe_quote_ticks(self.spot_id)

        # Discover expiry from loaded option instruments
        venue = Venue(self.cfg.venue)
        for inst in self.cache.instruments(venue=venue):
            sym = str(inst.id.symbol)
            if sym.startswith(f"{self.cfg.underlying}-") and sym != f"{self.cfg.underlying}-SPOT":
                parts = sym.split("-")
                if len(parts) == 4:
                    self.expiry_str = parts[3]
                    break

        # Determine trading date
        clock_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(clock_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        self._date_str = ist_dt.strftime("%Y-%m-%d")

        # Check if today is expiry day
        if self.expiry_str:
            expiry_date = f"{self.expiry_str[:4]}-{self.expiry_str[4:6]}-{self.expiry_str[6:8]}"
            self._is_expiry_day = (self._date_str == expiry_date)

        # Subscribe to all option instruments for premium scanning
        for inst in self.cache.instruments(venue=venue):
            sym = str(inst.id.symbol)
            if sym.startswith(f"{self.cfg.underlying}-") and sym != f"{self.cfg.underlying}-SPOT":
                self.subscribe_quote_ticks(inst.id)

        # Set final exit alert
        exit_ist = pd.Timestamp(f"{self._date_str} {self.cfg.final_exit}", tz="Asia/Kolkata")
        exit_ns = int(exit_ist.tz_convert("UTC").value)
        self.clock.set_time_alert_ns("final_exit", exit_ns, self._on_final_exit)
        self._final_exit_set = True

        # Set expiry EOD exit for morning trades
        if self._is_expiry_day:
            eod_ist = pd.Timestamp(f"{self._date_str} {self.cfg.expiry_eod_exit}", tz="Asia/Kolkata")
            eod_ns = int(eod_ist.tz_convert("UTC").value)
            self.clock.set_time_alert_ns("expiry_eod", eod_ns, self._on_expiry_eod_exit)

        # Init bar tracking from market open
        open_ist = pd.Timestamp(f"{self._date_str} 09:15:00", tz="Asia/Kolkata")
        self._current_bar_start_ns = int(open_ist.tz_convert("UTC").value)

    def on_quote_tick(self, tick) -> None:
        ts_ns = tick.ts_event

        if tick.instrument_id == self.spot_id:
            px = float(tick.bid_price)
            self.latest_spot = px
            self._update_bar(px, ts_ns)
            return

        # Track option premiums
        ask_px = float(tick.ask_price)
        self._option_premiums[str(tick.instrument_id)] = ask_px

        # Monitor sold leg for SL/target
        if self._sell_leg_id and tick.instrument_id == self._sell_leg_id and self._entered and not self._exited:
            self._latest_sell_px = ask_px
            if self._entry_sell_px and self._entry_sell_px > 0:
                # 55% SL: sold price increased by 55%
                if ask_px >= self._sell_sl > 0:
                    self._exit_position("SL")
                # 70% Target: sold price decreased by 70%
                elif ask_px <= self._sell_target and self._sell_target > 0:
                    self._exit_position("TARGET")

    def _update_bar(self, price: float, ts_ns: int) -> None:
        """Aggregate spot ticks into 15-min bars and update EMAs."""
        if self._current_bar_start_ns == 0:
            return

        # Check if we crossed into a new bar
        while ts_ns >= self._current_bar_start_ns + self._bar_interval_ns:
            # Close current bar
            if self._current_bar_close > 0:
                self._on_bar_close(self._current_bar_close)

            # Start new bar
            self._current_bar_start_ns += self._bar_interval_ns
            self._current_bar_open = 0.0
            self._current_bar_high = 0.0
            self._current_bar_low = float("inf")
            self._current_bar_close = 0.0

        # Update current bar
        if self._current_bar_open == 0.0:
            self._current_bar_open = price
        self._current_bar_high = max(self._current_bar_high, price)
        self._current_bar_low = min(self._current_bar_low, price)
        self._current_bar_close = price

    def _on_bar_close(self, close_price: float) -> None:
        """Called when a 15-min bar completes. Update EMAs and check signals."""
        self._bars_count += 1

        # Update EMAs
        if self._ema_fast_val is None:
            self._ema_fast_val = close_price
            self._ema_slow_val = close_price
        else:
            self._prev_ema_fast = self._ema_fast_val
            self._prev_ema_slow = self._ema_slow_val
            self._ema_fast_val = (close_price - self._ema_fast_val) * self._ema_fast_mult + self._ema_fast_val
            self._ema_slow_val = (close_price - self._ema_slow_val) * self._ema_slow_mult + self._ema_slow_val

        # Check for signal reversal exit
        if self._entered and not self._exited and self._prev_ema_fast is not None:
            if self._direction == "bullish":
                # Bearish cross: fast crosses below slow
                if self._prev_ema_fast >= self._prev_ema_slow and self._ema_fast_val < self._ema_slow_val:
                    self._exit_position("REVERSAL")
            elif self._direction == "bearish":
                # Bullish cross: fast crosses above slow
                if self._prev_ema_fast <= self._prev_ema_slow and self._ema_fast_val > self._ema_slow_val:
                    self._exit_position("REVERSAL")

        # Check for entry
        if not self._entered and not self._exited and self._bars_count >= self.cfg.ema_slow:
            self._check_entry()

    def _get_ist_time(self) -> str:
        ts_ns = self.clock.timestamp_ns()
        utc_dt = pd.Timestamp(ts_ns, unit="ns", tz="UTC")
        ist_dt = utc_dt.tz_convert("Asia/Kolkata")
        return ist_dt.strftime("%H:%M:%S")

    def _check_entry(self) -> None:
        """Check if entry conditions are met for any set."""
        if self._ema_fast_val is None or self._ema_slow_val is None:
            return

        current_time = self._get_ist_time()

        # Must be after 09:17
        if current_time < self.cfg.morning_start:
            return

        bullish = self._ema_fast_val > self._ema_slow_val
        bearish = self._ema_fast_val < self._ema_slow_val

        if not bullish and not bearish:
            return

        # Determine which set applies
        if self._is_expiry_day and current_time >= self.cfg.afternoon_start:
            # Sets 3/4: Expiry afternoon
            if bullish:
                self._enter_spread("bullish", 3, afternoon=True)
            else:
                self._enter_spread("bearish", 4, afternoon=True)
        elif not self._is_expiry_day or current_time < self.cfg.expiry_cutoff:
            # Sets 1/2: Morning session
            if bullish:
                self._enter_spread("bullish", 1, afternoon=False)
            else:
                self._enter_spread("bearish", 2, afternoon=False)

    def _find_strike_by_premium(
        self, option_type: str, condition: str, value: float
    ) -> InstrumentId | None:
        """Find an option strike matching premium criteria.

        condition: "gt" (greater than), "lt" (less than), "closest" (closest to)
        """
        venue = Venue(self.cfg.venue)
        candidates = []

        for inst in self.cache.instruments(venue=venue):
            sym = str(inst.id.symbol)
            if not sym.startswith(f"{self.cfg.underlying}-") or sym == f"{self.cfg.underlying}-SPOT":
                continue
            parts = sym.split("-")
            if len(parts) != 4:
                continue
            if parts[2] != option_type:
                continue
            if parts[3] != self.expiry_str:
                continue

            premium = self._option_premiums.get(str(inst.id))
            if premium is None or premium <= 0:
                continue

            candidates.append((inst.id, int(parts[1]), premium))

        if not candidates:
            return None

        if condition == "gt":
            # Find cheapest option with premium > value (furthest OTM with premium > min)
            valid = [(iid, s, p) for iid, s, p in candidates if p > value]
            if not valid:
                return None
            # For buy leg: want cheapest (furthest OTM)
            valid.sort(key=lambda x: x[2])
            return valid[0][0]

        elif condition == "lt":
            # Find most expensive option with premium < value (closest to ATM with premium < max)
            valid = [(iid, s, p) for iid, s, p in candidates if p < value]
            if not valid:
                return None
            # For sell leg: want most expensive (closest to ATM)
            valid.sort(key=lambda x: x[2], reverse=True)
            return valid[0][0]

        elif condition == "closest":
            # Find option with premium closest to target value
            candidates.sort(key=lambda x: abs(x[2] - value))
            return candidates[0][0]

        return None

    def _enter_spread(self, direction: str, set_num: int, afternoon: bool) -> None:
        """Enter a credit spread."""
        if self.latest_spot <= 0:
            return

        option_type = "PE" if direction == "bullish" else "CE"

        if afternoon:
            # Expiry afternoon: closest to target premiums
            buy_id = self._find_strike_by_premium(option_type, "closest", self.cfg.buy_premium_target)
            sell_id = self._find_strike_by_premium(option_type, "closest", self.cfg.sell_premium_target)
        else:
            # Morning: buy > 25, sell < 120 (premium units)
            buy_id = self._find_strike_by_premium(option_type, "gt", self.cfg.buy_premium_min)
            sell_id = self._find_strike_by_premium(option_type, "lt", self.cfg.sell_premium_max)

        if buy_id is None or sell_id is None:
            self.log.warning(f"Could not find suitable strikes for {direction} spread (set {set_num})")
            return

        if buy_id == sell_id:
            self.log.warning(f"Buy and sell resolved to same instrument, skipping")
            return

        self._buy_leg_id = buy_id
        self._sell_leg_id = sell_id
        self._direction = direction
        self._active_set = set_num
        self._morning_set = not afternoon
        self.spot_at_entry = self.latest_spot
        self._entry_time_str = self._get_ist_time()

        qty = Quantity.from_int(self.cfg.lot_size * self.cfg.num_lots)

        # Place buy order first, then sell on fill (repair once pattern)
        buy_order = self.order_factory.market(
            instrument_id=buy_id,
            order_side=OrderSide.BUY,
            quantity=qty,
        )
        self._pending_sell = True
        self._entered = True
        self.submit_order(buy_order)

        self.log.info(
            f"ENTRY Set {set_num} ({direction}): Buy {buy_id.symbol} | Sell {sell_id.symbol} | Spot={self.latest_spot:.2f}"
        )

    def _exit_position(self, reason: str) -> None:
        """Close both legs."""
        if self._exited:
            return
        self._exited = True
        self._exit_reason = reason
        self._exit_time_str = self._get_ist_time()
        self.spot_at_exit = self.latest_spot

        for pos in self.cache.positions_open(strategy_id=self.id):
            self.close_position(pos)

        self.log.info(f"EXIT ({reason}): Set {self._active_set}")

    def _on_expiry_eod_exit(self, event) -> None:
        """Close morning trades (Set 1/2) at 3:17 PM on expiry day."""
        if self._entered and not self._exited and self._morning_set:
            self._exit_position("EXPIRY_EOD")

    def _on_final_exit(self, event) -> None:
        """Final exit at 3:25 PM."""
        if self._entered and not self._exited:
            self._exit_position("EOD")

    def on_order_filled(self, event: OrderFilled) -> None:
        px = float(event.last_px)
        is_buy = event.order_side == OrderSide.BUY

        if event.instrument_id == self._buy_leg_id:
            if is_buy:
                self._entry_buy_px = px
                self.log.info(f"Buy leg filled at {px:.2f}")
                # Repair once: place sell leg
                if self._pending_sell and self._sell_leg_id:
                    self._pending_sell = False
                    qty = Quantity.from_int(self.cfg.lot_size * self.cfg.num_lots)
                    sell_order = self.order_factory.market(
                        instrument_id=self._sell_leg_id,
                        order_side=OrderSide.SELL,
                        quantity=qty,
                    )
                    self.submit_order(sell_order)
            else:
                self._exit_buy_px = px

        elif event.instrument_id == self._sell_leg_id:
            if not is_buy:
                # Sell leg entry fill
                self._entry_sell_px = px
                self._sell_sl = round(px * (1 + self.cfg.sl_pct / 100), 2)
                self._sell_target = round(px * (1 - self.cfg.target_pct / 100), 2)
                self.log.info(f"Sell leg filled at {px:.2f}, SL={self._sell_sl:.2f}, Target={self._sell_target:.2f}")
            else:
                # Sell leg exit fill (buying back)
                self._exit_sell_px = px

    def get_daily_result(self, date_str: str) -> dict | None:
        """Extract trade result after engine run."""
        if not self._entered:
            return None

        # May not have all fills if strategy couldn't find strikes
        entry_sell = self._entry_sell_px or 0
        entry_buy = self._entry_buy_px or 0
        exit_sell = self._exit_sell_px or 0
        exit_buy = self._exit_buy_px or 0

        if entry_sell == 0 and entry_buy == 0:
            return None

        # Credit spread PnL: (sell premium - buy premium) at entry vs exit
        # Sell leg: profit = entry - exit (sold high, buy back low)
        # Buy leg: profit = exit - entry (bought low, sell high) — but this is hedge
        sell_pnl = entry_sell - exit_sell
        buy_pnl = exit_buy - entry_buy
        total_pnl = sell_pnl + buy_pnl

        buy_strike = None
        sell_strike = None
        if self._buy_leg_id:
            parts = str(self._buy_leg_id.symbol).split("-")
            if len(parts) >= 2:
                buy_strike = int(parts[1])
        if self._sell_leg_id:
            parts = str(self._sell_leg_id.symbol).split("-")
            if len(parts) >= 2:
                sell_strike = int(parts[1])

        return {
            "date": date_str,
            "set": self._active_set,
            "direction": self._direction,
            "is_expiry": self._is_expiry_day,
            "buy_strike": buy_strike,
            "sell_strike": sell_strike,
            "buy_leg": str(self._buy_leg_id.symbol) if self._buy_leg_id else None,
            "sell_leg": str(self._sell_leg_id.symbol) if self._sell_leg_id else None,
            "spot_at_entry": round(self.spot_at_entry, 2),
            "spot_at_exit": round(self.spot_at_exit, 2),
            "entry_buy_px": round(entry_buy, 2),
            "entry_sell_px": round(entry_sell, 2),
            "exit_buy_px": round(exit_buy, 2),
            "exit_sell_px": round(exit_sell, 2),
            "sell_pnl": round(sell_pnl, 2),
            "buy_pnl": round(buy_pnl, 2),
            "pnl": round(total_pnl, 2),
            "exit_reason": self._exit_reason or "EOD",
            "entry_time": f"{date_str} {self._entry_time_str}" if self._entry_time_str else None,
            "exit_time": f"{date_str} {self._exit_time_str}" if self._exit_time_str else None,
            "ema_fast": round(self._ema_fast_val, 2) if self._ema_fast_val else None,
            "ema_slow": round(self._ema_slow_val, 2) if self._ema_slow_val else None,
        }
