"use client";

import { useState } from "react";

type DocStrategy =
  | "atm"
  | "vanilla"
  | "day-high-otm"
  | "day-high-otm-v4"
  | "day-high-otm-v5"
  | "day-high-otm-v6"
  | "day-high-otm-v7"
  | "day-high-spot"
  | "day-high-vix"
  | "allrounder"
  | "directional-op"
  | "mv3"
  | "multilegdm";

interface DocMeta {
  id: DocStrategy;
  label: string;
  file: string;
}

const STRATS: DocMeta[] = [
  { id: "atm",              label: "OTM1 Strangle Sell",          file: "strategies/atm_straddle_sell.py" },
  { id: "vanilla",          label: "Vanilla ATM Straddle",        file: "strategies/vanilla_straddle.py" },
  { id: "day-high-otm",     label: "Day High OTM Sell (v3)",      file: "strategies/day_high_otm_sell.py" },
  { id: "day-high-otm-v4",  label: "Day High OTM Sell (v4)",      file: "strategies/day_high_otm_sell_v4.py" },
  { id: "day-high-otm-v5",  label: "Day High OTM Sell (v5)",      file: "strategies/day_high_otm_sell_v5.py" },
  { id: "day-high-otm-v6",  label: "Day High OTM Sell (v6)",      file: "strategies/day_high_otm_sell_v6.py" },
  { id: "day-high-otm-v7",  label: "Day High OTM Sell (v7)",      file: "strategies/day_high_otm_sell_v7.py" },
  { id: "day-high-spot",    label: "Day High Spot Sell",          file: "strategies/day_high_spot_sell.py" },
  { id: "day-high-vix",     label: "Day High VIX Straddle",       file: "strategies/day_high_vix_straddle_sell.py" },
  { id: "allrounder",       label: "Index All Rounder",           file: "strategies/index_allrounder.py" },
  { id: "directional-op",   label: "Directional Credit Spread",   file: "strategies/directional_op_sell.py" },
  { id: "mv3",              label: "MV3 v33 Credit Spread",       file: "strategies/mv3_credit_spread.py" },
  { id: "multilegdm",       label: "MultiLeg DM (6-Strangle Stack)", file: "strategies/multi_leg_dm.py" },
];

// ─── Shared doc primitives ────────────────────────────────────

function H1({ children }: { children: React.ReactNode }) {
  return <h2 className="text-xl font-semibold text-zinc-100 mt-2 mb-4">{children}</h2>;
}

function H2({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400 mt-6 mb-3 border-b border-zinc-800 pb-1">
      {children}
    </h3>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-zinc-300 leading-relaxed mb-3">{children}</p>;
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="font-mono text-[12px] bg-zinc-800/80 text-amber-300 px-1.5 py-0.5 rounded">
      {children}
    </code>
  );
}

function Box({ title, children, tone = "neutral" }: { title?: string; children: React.ReactNode; tone?: "neutral" | "warn" | "ok" | "info" }) {
  const ring = {
    neutral: "border-zinc-700/60 bg-zinc-800/30",
    warn: "border-amber-700/50 bg-amber-950/20",
    ok: "border-emerald-800/40 bg-emerald-950/15",
    info: "border-blue-800/40 bg-blue-950/15",
  }[tone];
  return (
    <div className={`rounded-lg border ${ring} px-4 py-3 mb-3`}>
      {title && (
        <div className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">
          {title}
        </div>
      )}
      <div className="text-sm text-zinc-300">{children}</div>
    </div>
  );
}

function Rule({ num, title, children }: { num: string; title: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 mb-3">
      <div className="shrink-0 font-mono font-bold text-xs text-zinc-500 pt-0.5 w-8">{num}</div>
      <div className="flex-1">
        <div className="text-sm font-semibold text-zinc-200 mb-0.5">{title}</div>
        <div className="text-sm text-zinc-400 leading-relaxed">{children}</div>
      </div>
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 text-sm py-1 border-b border-zinc-800/70 last:border-0">
      <div className="text-zinc-500 w-48 shrink-0 font-mono text-xs">{k}</div>
      <div className="text-zinc-200 font-mono text-xs">{v}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <H2>{title}</H2>
      {children}
    </section>
  );
}

function SourceRef({ file }: { file: string }) {
  return (
    <div className="inline-flex items-center gap-1.5 text-[10px] font-mono text-zinc-500 bg-zinc-900/60 border border-zinc-800 rounded px-2 py-0.5">
      <span>source:</span>
      <Code>{file}</Code>
    </div>
  );
}

// ─── DOC 1: OTM1 Strangle Sell ────────────────────────────────

function DocATM() {
  return (
    <article>
      <H1>OTM1 Strangle Sell</H1>
      <P>
        A fixed-time, fixed-strike, premium-collection strategy. At 09:21 IST, the strategy sells one OTM 1 CE
        and one OTM 1 PE on the current weekly expiry, holds each leg independently with a 30% stop-loss above
        entry premium, and closes any survivors at 15:00 IST.
      </P>
      <SourceRef file="strategies/atm_straddle_sell.py" />

      <Section title="Position Construction">
        <Rule num="1" title="Strikes are set at signal time">
          ATM = <Code>round(spot / 50) × 50</Code>. OTM1 CE = ATM + 50, OTM1 PE = ATM − 50. Both legs
          reference the same current weekly expiry (auto-detected from the instrument cache at
          <Code>on_start</Code>).
        </Rule>
        <Rule num="2" title="Quantity is fixed">
          <Code>lot_size × num_lots</Code> = 65 × 1 = 65 units per leg. No position sizing, no scaling,
          no vol-adjusted quantities.
        </Rule>
        <Rule num="3" title="Expiry mapping is static per run">
          The strategy picks the first non-SPOT instrument it sees; the Nautilus dataloader is expected
          to supply only the nearest-expiry contracts for the trading day.
        </Rule>
      </Section>

      <Section title="Entry">
        <Rule num="E1" title="Unconditional time trigger — 09:21 IST">
          A one-shot clock alert fires at 09:21:00 IST. There is no price filter, no volatility filter,
          no skew filter. If <Code>latest_spot &gt; 0</Code> and both OTM1 instruments resolve in cache,
          the strategy submits two simultaneous MARKET SELL orders (CE and PE).
        </Rule>
        <Rule num="E2" title="Fill price determines SL — not theoretical premium">
          The SL is locked in <Code>on_order_filled</Code> using the actual fill price:
          <Code>sl = fill_px × 1.30</Code>. If CE fills at 72.40 with 30% SL, the CE SL sits at 94.12 regardless
          of what the quote was at the time the order was sent.
        </Rule>
      </Section>

      <Section title="Stop-Loss">
        <Rule num="SL1" title="Per-leg independent SL">
          CE and PE each have their own <Code>sl</Code> level. The strategy does NOT use combined-premium SL.
          Stopping out the CE leg does not touch the PE leg and vice versa.
        </Rule>
        <Rule num="SL2" title="SL fires on ASK tick, not bar close">
          On every option quote tick, <Code>px = tick.ask_price</Code> is compared to the leg&apos;s SL. First
          tick that meets <Code>px &gt;= sl</Code> triggers an immediate MARKET BUY to close that leg. ASK is
          used because that is the price you pay to buy back a short.
        </Rule>
        <Rule num="SL3" title="Once stopped, a leg is not re-entered">
          The stopped flag (<Code>ce_stopped</Code> / <Code>pe_stopped</Code>) prevents further entries on that leg
          for the rest of the day. No re-entry logic exists.
        </Rule>
      </Section>

      <Section title="Profit Taking / Exits">
        <Rule num="X1" title="No profit target">
          There is no target price, no trailing stop, no breakeven move, no vol-based exit.
        </Rule>
        <Rule num="X2" title="EOD close at 15:00 IST">
          A second clock alert at 15:00:00 IST closes any open leg with a MARKET BUY. The leg&apos;s
          <Code>exit_reason</Code> is stamped <Code>&quot;EOD&quot;</Code> (as opposed to <Code>&quot;SL&quot;</Code>).
        </Rule>
      </Section>

      <Section title="Re-entry">
        <Box tone="warn" title="Not supported">
          This is a one-shot-per-day strategy. Once a leg is stopped, it stays stopped. There is no
          cooldown, no new-strike re-entry, no martingale behavior.
        </Box>
      </Section>

      <Section title="PnL Accounting">
        <Rule num="P1" title="Per leg">
          <Code>ce_pnl = entry_ce_px − exit_ce_px</Code>, same formula for PE.
        </Rule>
        <Rule num="P2" title="Daily total">
          <Code>pnl = ce_pnl + pe_pnl</Code>. Point PnL only — no currency conversion, no costs/fees baked in
          at the strategy level.
        </Rule>
      </Section>

      <Section title="Parameters">
        <Box>
          <KV k="entry_time" v="09:21:00 IST" />
          <KV k="exit_time" v="15:00:00 IST" />
          <KV k="strike_step" v="50" />
          <KV k="lot_size × num_lots" v="65 × 1" />
          <KV k="sl_pct" v="30.0 %" />
          <KV k="underlying / venue" v="NIFTY / NSE" />
        </Box>
      </Section>

      <Section title="Operational Characteristics">
        <Rule num="O1" title="One trade per day">
          At most one structure per day; at most 2 point-in-time positions (CE and PE). No intraday scaling.
        </Rule>
        <Rule num="O2" title="Risk is asymmetric">
          Max gain per leg ≈ entry premium. Max loss per leg ≈ 30% of entry premium (plus slippage).
          Risk-reward is capped short of expiry due to the EOD cutoff.
        </Rule>
        <Rule num="O3" title="Sensitivity">
          Profitability depends on NIFTY remaining within (entry_spot ± combined_premium) for the trading
          session. Volatility spikes will typically hit the SL on one leg (the one in the money) while the
          other decays.
        </Rule>
      </Section>
    </article>
  );
}

// ─── DOC 2: Vanilla Straddle ────────────────────────────────────

function DocVanilla() {
  return (
    <article>
      <H1>Vanilla ATM Straddle</H1>
      <P>
        A spot-move driven ATM straddle that uses combined premium as its own volatility metric for both
        entry conditioning and exit triggering. The initial entry is gated by a CE/PE skew filter; exits and
        re-entries are driven by absolute spot displacement from the last entry price.
      </P>
      <SourceRef file="strategies/vanilla_straddle.py" />

      <Section title="Position Construction">
        <Rule num="1" title="Strikes at signal time, ATM on both sides">
          ATM = <Code>round(spot / 50) × 50</Code>. CE and PE use the same ATM strike. Current weekly expiry
          is auto-detected from the instrument cache.
        </Rule>
        <Rule num="2" title="DTE is computed once at session start">
          Expiry date is parsed from the contract symbol and compared to the trading date to produce an
          integer DTE. This DTE gates the exit-trigger multiplier (see Exit rules).
        </Rule>
        <Rule num="3" title="Fixed quantity per leg">
          <Code>65 × 1</Code> units per leg.
        </Rule>
      </Section>

      <Section title="Entry — Initial (Rule A)">
        <Rule num="EA1" title="Scan every 3 minutes from 09:21 to 15:07">
          The strategy schedules clock alerts every <Code>entry_interval_min=3</Code> minutes. At each tick,
          if no position is open and <Code>_initial_entry_done</Code> is false, an entry is attempted.
        </Rule>
        <Rule num="EA2" title="Skew gate (initial entry only)">
          Entry requires <Code>|ce_mid − pe_mid| &lt; skew_threshold (20)</Code> where mids are from the latest
          cached quotes. If skew is at or above 20, the scan skips this slot and tries again in 3 minutes.
        </Rule>
        <Rule num="EA3" title="Market orders, both legs simultaneously">
          Two MARKET SELL orders (CE and PE) are submitted together. Entry fill prices set the trade&apos;s
          <Code>combined_premium</Code>.
        </Rule>
      </Section>

      <Section title="Entry — Re-Entry (Rule B)">
        <Rule num="EB1" title="Only allowed after a spot-move exit">
          <Code>has_exited_today</Code> must be true, day-loss limit must not be hit, and re-entry must still
          be allowed (i.e. before 15:10 final-exit).
        </Rule>
        <Rule num="EB2" title="Trigger = half the ORIGINAL combined premium">
          <Code>|latest_spot − entry_spot| &gt; original_combined_premium / 2</Code>. The reference is the FIRST
          entry&apos;s premium, not the most recent entry&apos;s premium. This anchors re-entry sensitivity to the
          day&apos;s opening vol regime.
        </Rule>
        <Rule num="EB3" title="Re-entry skips the skew check">
          Only the initial entry is gated by <Code>skew_threshold</Code>. Subsequent re-entries go straight
          to market-order submission.
        </Rule>
      </Section>

      <Section title="Stop-Loss / Exit Triggers">
        <Rule num="X1" title="Spot-move exit (the primary risk rule)">
          On every spot tick, <Code>|latest_spot − entry_spot|</Code> is compared against
          <Code>exit_trigger</Code>. If exceeded, MARKET BUY close both legs (exit_reason = SPOT_MOVE).
        </Rule>
        <Rule num="X2" title="DTE-dependent exit multiplier">
          <Code>DTE ≤ 1</Code>: <Code>exit_trigger = combined_premium / 2</Code> — tighter on expiry day.<br />
          <Code>DTE &gt; 1</Code>: <Code>exit_trigger = combined_premium / 3</Code> — looser with more time
          to decay. Intuition: near expiry gamma dominates, so you need to cut faster.
        </Rule>
        <Rule num="X3" title="Day loss cut-off">
          Once <Code>day_pnl ≤ −day_loss_limit (−50 pts)</Code>, <Code>day_stopped = true</Code> and
          <Code>re_entry_allowed = false</Code>. No more trades that day regardless of signal.
        </Rule>
        <Rule num="X4" title="Universal EOD exit at 15:10 IST">
          Any open position is force-closed at 15:10. Re-entry is disabled after this clock alert fires.
        </Rule>
      </Section>

      <Section title="Profit Taking">
        <Box tone="warn" title="No explicit target">
          There is no fixed premium target. The strategy collects theta until spot moves by the
          exit trigger, at which point it exits and may re-enter after a further half-premium move.
        </Box>
      </Section>

      <Section title="PnL Accounting">
        <Rule num="P1" title="Per trade, per leg">
          <Code>ce_pnl = entry_ce − exit_ce</Code>; <Code>pe_pnl = entry_pe − exit_pe</Code>;
          <Code>pnl = ce_pnl + pe_pnl</Code>.
        </Rule>
        <Rule num="P2" title="Day total">
          <Code>day_pnl</Code> accumulates across all trades that day; this is the value checked against the
          day-loss limit.
        </Rule>
      </Section>

      <Section title="Parameters">
        <Box>
          <KV k="first_entry_time / final_exit_time" v="09:21 / 15:10 IST" />
          <KV k="entry_interval_min" v="3 (scan cadence)" />
          <KV k="skew_threshold" v="20.0 pts (initial entry only)" />
          <KV k="day_loss_limit" v="50.0 pts" />
          <KV k="exit multiplier (DTE ≤ 1)" v="premium / 2" />
          <KV k="exit multiplier (DTE > 1)" v="premium / 3" />
          <KV k="re-entry trigger" v="original_combined_premium / 2" />
        </Box>
      </Section>
    </article>
  );
}

// ─── DOC 3: Day High OTM Sell (v3) ──────────────────────────────

function DocDayHighOTM() {
  return (
    <article>
      <H1>Day High OTM Sell (v3)</H1>
      <P>
        The base intraday option-selling strategy in this family. The trader watches the just-out-of-the-money
        Call (one step above the index) and the just-out-of-the-money Put (one step below the index) as
        two completely independent positions. Each option is observed for the highest price it reaches
        during the day. When that option pulls back five percent off its own peak and stays there at the
        end of a three-minute bar, the strategy sells it short, expecting time decay and mean reversion to
        deliver profit by the close. If price spikes back five percent above the peak instead, the strategy
        cuts the loss. Re-entries are allowed throughout the day after each exit, with a fifteen-minute
        cooling-off window after any stop-loss.
      </P>

      <Section title="Position Construction">
        <Rule num="1" title="Two fully independent legs">
          The Call side and the Put side are tracked and traded as separate strategies that happen to share
          the same code. Either leg can be in a live position while the other is still scanning for entry.
          Their day-high references, pullback levels, stop-loss levels and cooldown timers are completely
          decoupled.
        </Rule>
        <Rule num="2" title="One step out-of-the-money strikes, recomputed every bar">
          Before evaluating each leg every three minutes, the strategy looks at the current index level,
          rounds it to the nearest fifty-point strike, and picks the next strike up (for the Call) or down
          (for the Put). If the index has drifted enough that this changes the strike, the leg switches
          its watch to the new strike — and erases all of the tracking it built on the old one. The new
          strike starts with no day high.
        </Rule>
        <Rule num="3" title="Each leg builds its own three-minute bars">
          The strategy treats each option&apos;s tick stream like a chart of its own. A new bar starts and
          ends on the same boundary as the index&apos;s three-minute clock, but the open, high and close are
          built from the option&apos;s own quoted prices. The price used is always the offered (ask) side,
          which is the conservative choice: it makes day highs slightly higher and stop-losses slightly
          easier to trigger.
        </Rule>
      </Section>

      <Section title="Day High Tracking">
        <Rule num="DH1" title="Closing prices only — no wick chasing">
          The day-high reference for each leg is updated only by where each three-minute bar closes,
          never by an intra-bar spike. This deliberately ignores wicks and one-tick anomalies. Only a
          settled close above the previous high becomes the new high.
        </Rule>
        <Rule num="DH2" title="Maturity lock — never enter on the same bar that printed the high">
          When a fresh high is set, the strategy refuses to use it as a reference until at least one
          subsequent bar has failed to break above it. This forces a one-bar wait so that the high is
          confirmed and the entry decision is made against a stable, established level rather than a
          newly-printed peak that the very next tick might exceed.
        </Rule>
        <Rule num="DH3" title="The day high is local, not session-wide">
          After any exit, the day-high reference for that leg is wiped. The next tracking session
          rebuilds it from the very next bar onward. This is a deliberate design choice that gives the
          strategy a fresh chance after every loss instead of holding it to the original session peak.
        </Rule>
      </Section>

      <Section title="Entry Conditions">
        <Rule num="E1" title="Pullback below the locked level">
          Entry fires when a three-minute bar closes at or below five percent under the locked day high.
          That is, the option must be priced at ninety-five percent of its own day-high level (or lower)
          at the close of a bar.
        </Rule>
        <Rule num="E2" title="Maturity lock must already be active">
          Even if the price falls below the pullback threshold, no entry happens unless the day high has
          aged at least one bar without being broken. This rules out entering on the same bar that printed
          the new high.
        </Rule>
        <Rule num="E3" title="Cooldown gate (after a stop-loss)">
          If the leg recently exited on a stop-loss, the strategy ignores entry signals until five more
          bars (fifteen minutes) have passed. After the cooldown, normal evaluation resumes — including
          new strike selection and fresh day-high tracking.
        </Rule>
        <Rule num="E4" title="Order routing">
          When all conditions align on a bar close, the strategy submits a market sell for one unit of
          that strike. The fill happens on the next available tick, so the recorded entry price reflects
          true market-on-next behaviour, not the bar-close price itself.
        </Rule>
      </Section>

      <Section title="Stop-Loss">
        <Rule num="SL1" title="Anchored to the day high at signal time">
          The stop-loss for each trade is set at five percent above the day high that triggered the signal.
          If the option ever ticks up to or above this level after entry, the leg is closed.
        </Rule>
        <Rule num="SL2" title="Frozen for the life of the trade">
          Once the trade is on, the stop-loss does not move. New highs forming inside an active position
          are ignored for stop-loss purposes — a critical correctness property that keeps the trade&apos;s
          risk capped at what was understood at entry.
        </Rule>
        <Rule num="SL3" title="No trailing, no profit target">
          There is no logic to lock in partial gains. The trade either gets stopped out or runs all the
          way to the end of the trading day. This is intentional: the source of profit is option time
          decay, which compounds slowly across the session, and trailing exits cut that runway short.
        </Rule>
      </Section>

      <Section title="End-of-Day Exit">
        Any open positions are flat-closed at 15:15 IST via market buy. This is the harvesting moment
        for trades that have survived: by the time the close arrives, theta has worked all day on a
        short option that was sold at a relative peak, and the closing price is typically much lower
        than the entry. Closes after EOD do not trigger a cooldown.
      </Section>

      <Section title="Re-Entry Rules">
        <Rule num="R1" title="After a stop-loss — fifteen-minute cooling-off">
          The leg waits five three-minute bars before scanning for new entries. Both legs are independent;
          a stop on the Call side does not pause the Put side.
        </Rule>
        <Rule num="R2" title="After cooldown — fresh strike, fresh tracking">
          When monitoring resumes, the strategy looks at where the index is now and selects the new
          one-step-out-of-the-money strike. If the index drifted during the position and cooldown, this
          will be a different strike from the one just traded. Day-high tracking begins from zero on the
          very next bar.
        </Rule>
        <Rule num="R3" title="Many trades per day are possible">
          Because each exit cleans the slate and each leg trades independently, busy days can produce
          five to ten total trades across both legs. There is no daily trade cap.
        </Rule>
      </Section>

      <Section title="Quirks Worth Knowing">
        <Rule num="Q1" title="Asymmetric payoff structure">
          Stop-loss exits almost always lose (the option had already moved against the short by the
          time the stop fired). End-of-day exits win the great majority of the time. The strategy is
          profitable because the average winning trade is more than twice the average losing trade.
        </Rule>
        <Rule num="Q2" title="Sequence matters">
          The first one or two trades of the day on each leg are statistically the worst — they tend to
          be early-session noise that spikes a stop. Trades that fire later in the day, after the option
          has already shown its hand, are far more likely to survive to the close. Other versions in this
          family attempt to exploit this pattern.
        </Rule>
        <Rule num="Q3" title="Conservative pricing assumptions throughout">
          Day-high tracking and stop-loss checking both use the offer side of the quote, not the mid or
          the bid. This makes the highs slightly higher and the stops slightly easier to hit, both of
          which underestimate what a careful trader would actually achieve in live markets.
        </Rule>
      </Section>

      <Section title="Parameters at a Glance">
        <Box>
          <KV k="Trading hours" v="09:15 to 15:15 IST" />
          <KV k="Bar interval" v="3 minutes" />
          <KV k="Pullback threshold for entry" v="5% below day high" />
          <KV k="Stop-loss threshold" v="5% above day high" />
          <KV k="Cooldown after stop-loss" v="5 bars (15 minutes)" />
          <KV k="Strike step (NIFTY)" v="50 points" />
          <KV k="Quantity per trade" v="1 unit" />
        </Box>
      </Section>
    </article>
  );
}

// ─── DOC 4: Day High OTM v4 ──────────────────────────────────

function DocDayHighOTMv4() {
  return (
    <article>
      <H1>Day High OTM Sell (v4) — Skip the First Three Completions</H1>
      <P>
        v4 keeps every signal, every entry, every exit, every cooldown of v3 exactly as they were. The
        only behavioural change is that the first three completed round-trips of the day are placed at
        the smallest possible quantity, and their profit and loss is excluded from the recorded results.
        From the fourth completed trade of the day onwards, normal sizing applies and the trade is
        counted in the books. The intent is to skip the early-session trades that historically lose
        money while preserving the strategy&apos;s natural rhythm — re-entries, cooldowns and strike
        rotations all unfold in the same way they would have under v3.
      </P>

      <Section title="Position Construction">
        Same as v3 — two independent legs (one Call, one Put), each watching the strike one step
        out-of-the-money on the current weekly expiry. The Call goes one strike above the index, the
        Put goes one strike below. Strikes are recomputed every bar based on the current index level
        and re-rolled if the index has drifted.
      </Section>

      <Section title="Day High Tracking">
        Identical to v3. Each leg builds its own three-minute bars from the option&apos;s offered price,
        records the highest closing price of the day, and locks that level in only after one subsequent
        bar fails to break it. The day high resets on every exit and on every strike change.
      </Section>

      <Section title="Entry Conditions">
        Same trigger as v3: a three-minute bar must close at or below five percent under the locked day
        high, with the maturity lock already active and no cooldown in force. Entries always send a real
        market order to the exchange so that fills, timing and downstream state evolve realistically.
      </Section>

      <Section title="Stop-Loss">
        Stop-loss is set at five percent above the day high at signal time and frozen for the life of
        the trade — exactly as in v3. The active position is closed by a market buy if the option price
        ever reaches the stop level intraday.
      </Section>

      <Section title="End-of-Day Exit">
        Any open trade is flat-closed at 15:15 IST. No cooldown after the EOD exit because the session
        is ending.
      </Section>

      <Section title="Re-Entry Rules">
        The same fifteen-minute cooling-off window applies after a stop-loss; trades after the close
        of cooldown reset to fresh strike, fresh day high, and resume scanning. Both legs operate
        independently — a stop on one side does not pause the other.
      </Section>

      <Section title="Quantity Sizing — the v4 difference">
        <Rule num="Q1" title="Counter based on completed trades, not signals">
          The strategy keeps a running count of trades that have already finished for the day. While
          fewer than three trades have completed, the next entry is sized at one unit — the smallest
          allowed quantity. Once three trades have completed, the next entry uses the normal trading
          quantity (also set to one in this configuration but conceptually scalable).
        </Rule>
        <Rule num="Q2" title="Phantom-sized trades produce zero recorded P&amp;L">
          For trades sized at the phantom quantity, the recorded profit-and-loss in the strategy&apos;s
          report is forced to zero. Real fills still occur at the exchange, but their tiny size has
          negligible economic impact — and the report treats them as if they hadn&apos;t happened. From
          the fourth completed trade onwards, P&amp;L is recorded as it normally would be.
        </Rule>
        <Rule num="Q3" title="Why this gives v3&apos;s state machine but v3-minus-first-three&apos;s P&amp;L">
          Because real orders are still submitted (just at a tiny size), every aspect of the
          strategy&apos;s timing — fills, cooldowns, strike rotations, the day-high reset cadence — unfolds
          identically to v3. The only thing that&apos;s different is what shows up in the results: the
          early trades&apos; profit and loss is suppressed.
        </Rule>
      </Section>

      <Section title="Why &apos;Completion&apos; not &apos;Entry&apos;">
        <Box tone="info">
          A subtle but important detail: the counter advances when a trade closes, not when it opens.
          If both the Call and the Put leg open early in the day and both stay open into the afternoon,
          the day&apos;s next entry is still considered an early trade (because no trade has completed yet).
          This matches the way the original v3 backtest counted trades and ensures v4&apos;s skip is
          equivalent to filtering v3&apos;s trade history to the fourth and later completion of each day.
        </Box>
      </Section>

      <Section title="Quirks Worth Knowing">
        <Rule num="Q4" title="Concurrent positions can shift which trade gets &apos;skipped&apos;">
          Because the Call and Put legs run simultaneously, the day&apos;s &quot;trades 1-3&quot; depend on which
          legs happen to finish first. A leg that opens early but holds to the close can end up being
          recorded as a later trade — possibly one that does count in the P&amp;L. This is by design:
          the rule is about completion order, not about entry order.
        </Rule>
        <Rule num="Q5" title="No transaction-cost adjustments are applied">
          The strategy does not subtract brokerage, exchange fees or slippage. Real-world deployment
          should account for these separately — costs can be passed in via configuration.
        </Rule>
      </Section>

      <Section title="Parameters at a Glance">
        <Box>
          <KV k="Trading hours" v="09:15 to 15:15 IST" />
          <KV k="Bar interval" v="3 minutes" />
          <KV k="Pullback threshold for entry" v="5% below day high" />
          <KV k="Stop-loss threshold" v="5% above day high" />
          <KV k="Cooldown after stop-loss" v="5 bars (15 minutes)" />
          <KV k="Strike step (NIFTY)" v="50 points" />
          <KV k="Trades skipped per day" v="3 (the first three completions)" />
          <KV k="Phantom-sized quantity" v="1 unit (P&L recorded as zero)" />
          <KV k="Real-sized quantity" v="1 unit (P&L recorded normally)" />
        </Box>
      </Section>
    </article>
  );
}

// ─── DOC 5: Day High OTM v5 — True Whole-Day DH ──────────────

function DocDayHighOTMv5() {
  return (
    <article>
      <H1>Day High OTM Sell (v5) — True Whole-Day Day High</H1>
      <P>
        v5 is the same family of strategy as v3 — it watches one-step-out-of-the-money options for a
        five-percent pullback off the day&apos;s peak and sells short — but it changes how that peak is
        tracked. In v3, the peak reference was wiped after every exit, giving the strategy a fresh start
        each time. In v5, the peak persists across exits and continues updating even while a position is
        live or while the cooldown is running. The result is that re-entries always reference the real
        session peak, not a fresh local maximum that just happened to form after a stop-loss.
      </P>

      <Section title="Position Construction">
        Same as v3 — independent Call and Put legs, each tracking the strike one step out-of-the-money.
        Strikes are recomputed every bar based on the current index level and rolled if the index has
        drifted. When a strike rolls (the underlying option being watched changes), the day-high tracking
        for that leg starts over with the new option.
      </Section>

      <Section title="Day High Tracking — the v5 difference">
        <Rule num="DH1" title="The day high keeps updating, always">
          On every three-minute bar close, the day high is checked against the new closing price — even
          if the leg is in a live trade or in a cooling-off window. This means the strategy always knows
          where the real session peak is, including any new highs that printed during a position.
        </Rule>
        <Rule num="DH2" title="The day high survives exits">
          After a stop-loss or end-of-day close, the day-high reference is NOT erased. It carries over
          intact, along with the pullback level and the stop-loss level that go with it. Only a switch
          to a different strike (when the index drifts far enough that the one-step-out-of-the-money
          strike changes) resets these references.
        </Rule>
        <Rule num="DH3" title="Implication for re-entries">
          Because the day high persists, each new entry must clear a real five-percent pullback from
          the genuine session peak — not from a fresh-local-max that v3 would have built up after a
          reset. Signals are stricter; there are fewer of them; each one is more selective.
        </Rule>
      </Section>

      <Section title="Entry Conditions">
        Same trigger as v3: a three-minute bar must close at or below five percent under the locked
        day high, with the maturity lock active and no cooldown running. With the day high persisting
        across exits, the pullback threshold for the next entry is higher (because it&apos;s referenced to
        the real session peak), so re-entries fire less often than under v3.
      </Section>

      <Section title="Stop-Loss">
        <Rule num="SL1" title="Five percent above the day high at entry time">
          The stop-loss is set when the trade enters and never moves for the life of the trade. New highs
          forming during the position update the strategy&apos;s tracking variables, but the live trade&apos;s
          stop-loss is frozen at what it was when the order went in. This freeze is critical and is
          enforced explicitly so that the stop never widens against the trader.
        </Rule>
        <Rule num="SL2" title="Triggered on every option tick">
          As soon as the option ticks at or above the stop-loss level, the strategy market-buys to
          close. The next-tick fill behaviour applies — small slippage in real markets.
        </Rule>
      </Section>

      <Section title="End-of-Day Exit">
        Any open trade is flat-closed at 15:15 IST. Both legs close concurrently if both are open.
      </Section>

      <Section title="Re-Entry Rules">
        <Rule num="R1" title="Fifteen-minute cooling-off after a stop-loss">
          The same five-bar wait as v3 applies after every stop-loss exit. End-of-day exits do not
          trigger a cooldown.
        </Rule>
        <Rule num="R2" title="Fresh entry, but same day high">
          When the cooldown ends, the strategy resumes scanning. If the strike has rolled because of
          index drift, day-high tracking starts over for the new strike. If the strike is still the
          same, the strategy continues watching the same persistent peak — and the next entry must clear
          a fresh five-percent pullback from it.
        </Rule>
        <Rule num="R3" title="No fresh-cross-down requirement">
          v5 will fire an entry on the very first eligible bar where the close is at or below the
          pullback level — even if the price was already below that level when the cooldown ended. It
          does not require the price to first recover above the level and then cross back down. This
          edge case is specifically tightened in v6.
        </Rule>
      </Section>

      <Section title="What This Version Tries to Fix">
        <Box tone="info">
          Under v3, after a stop-loss the day high gets reset to zero and the very next bar trivially
          becomes a &quot;new day high&quot;. The pullback reference for the very next entry is therefore a
          fresh local maximum rather than the real session peak. v5 corrects that: the reference is
          always the genuine intraday peak. The hope was that fewer, stricter signals would raise per-trade
          quality. In practice this change made the strategy substantially less profitable — v3&apos;s
          &quot;reset and try again&quot; behaviour turns out to be a feature, not a bug.
        </Box>
      </Section>

      <Section title="Parameters at a Glance">
        <Box>
          <KV k="Trading hours" v="09:15 to 15:15 IST" />
          <KV k="Bar interval" v="3 minutes" />
          <KV k="Pullback threshold for entry" v="5% below the persistent day high" />
          <KV k="Stop-loss threshold" v="5% above the day high (frozen at entry)" />
          <KV k="Cooldown after stop-loss" v="5 bars (15 minutes)" />
          <KV k="Strike step (NIFTY)" v="50 points" />
          <KV k="Quantity per trade" v="1 unit" />
        </Box>
      </Section>
    </article>
  );
}

// ─── DOC 6: Day High OTM v6 — Fresh-Cross Guard ──────────────

function DocDayHighOTMv6() {
  return (
    <article>
      <H1>Day High OTM Sell (v6) — Whole-Day DH plus Fresh-Cross Guard</H1>
      <P>
        v6 is v5 with one extra rule: after any exit, the strategy refuses to re-enter until the option
        price has first risen back above the pullback threshold and then crossed down through it again.
        This forces every re-entry to be a genuine cross-down event rather than a passive re-engagement
        with a level the price was already below. The guard is the only behavioural change from v5.
      </P>

      <Section title="Position Construction">
        Same as v5 — independent Call and Put legs, each tracking the strike one step
        out-of-the-money. Strikes are recomputed every bar based on the current index level and rolled
        if the index has drifted.
      </Section>

      <Section title="Day High Tracking">
        Same as v5 — the day high is a true running maximum across the whole session. It updates on
        every bar close (including bars where a position is live or the cooldown is running) and
        survives exits. Only a strike roll resets it.
      </Section>

      <Section title="Entry Conditions">
        <Rule num="E1" title="Pullback below the locked level">
          A three-minute bar must close at or below five percent under the day high, and the maturity
          lock must already be active. Same as v3 / v5.
        </Rule>
        <Rule num="E2" title="No active cooldown">
          The leg must not be inside the fifteen-minute window after a recent stop-loss.
        </Rule>
        <Rule num="E3" title="Fresh-cross armed (the v6 addition)">
          After any exit, a re-entry is gated. The strategy waits for a bar to close strictly above the
          pullback threshold before allowing the next pullback signal to fire. Only then can the next
          bar-close at or below the threshold count as a genuine entry.
        </Rule>
      </Section>

      <Section title="Stop-Loss">
        Same as v5 — set at five percent above the day high at entry time and frozen for the life of
        the trade. Triggered on the first option tick that meets or exceeds the stop level.
      </Section>

      <Section title="End-of-Day Exit">
        Any open trade is flat-closed at 15:15 IST.
      </Section>

      <Section title="Re-Entry Rules">
        <Rule num="R1" title="Fifteen-minute cooling-off after a stop-loss">
          Same five-bar wait as v3 / v5. End-of-day exits do not trigger a cooldown but they DO arm the
          fresh-cross guard, so even if a session ends with the option below pullback, no entry would
          fire (which is moot — the session is over anyway).
        </Rule>
        <Rule num="R2" title="Fresh-cross requirement">
          Every re-entry — whether after a stop-loss or after end-of-day — requires a bar that closes
          ABOVE the pullback level to re-arm the strategy. A subsequent bar that closes at or below
          the threshold is the genuine entry signal.
        </Rule>
        <Rule num="R3" title="Strike roll cancels the guard">
          When the underlying strike changes (index drifted enough), all tracking — including the
          fresh-cross guard — resets. The new strike has no prior cross to worry about, so the guard
          starts disarmed.
        </Rule>
      </Section>

      <Section title="Concrete Example of the v6 Guard">
        <Box tone="info">
          Suppose a stop-loss fired at 10:15 IST when the option printed 55, taking the day high to 55
          and the pullback level to 52.25. The fifteen-minute cooldown ends at 10:30, and during that
          window the option drifted down to 51 — never recovering back above 52.25.
          <br /><br />
          Under v5, the very next bar close at 10:30 (option still at 51) would trigger an immediate
          re-entry, despite no genuine pullback signal having occurred.
          <br /><br />
          Under v6, the entry is blocked at 10:30. The strategy waits. At 10:33 the option recovers to
          52.5 — above the threshold — and re-arms the guard. At 10:36 it pulls back to 52, below the
          threshold. THIS bar fires the entry, and it is a real cross-down event.
        </Box>
      </Section>

      <Section title="Quirks Worth Knowing">
        <Rule num="Q1" title="The fresh-cross fix can prevent helpful re-entries">
          On days where the option grinds steadily downward without any rebound, v6 may sit out
          opportunities that v5 would have taken. In return, it avoids entering into trends that are
          still pressing lower. Whether this is net positive depends on the regime.
        </Rule>
        <Rule num="Q2" title="The stop-loss is still frozen at entry">
          As of the latest correctness fix, the stop-loss reference is captured at entry and never
          drifts during the trade — a subtle bug present in earlier iterations. The trade&apos;s risk is
          fixed at what was understood at entry.
        </Rule>
      </Section>

      <Section title="Parameters at a Glance">
        <Box>
          <KV k="Trading hours" v="09:15 to 15:15 IST" />
          <KV k="Bar interval" v="3 minutes" />
          <KV k="Pullback threshold for entry" v="5% below the persistent day high" />
          <KV k="Stop-loss threshold" v="5% above the day high (frozen at entry)" />
          <KV k="Cooldown after stop-loss" v="5 bars (15 minutes)" />
          <KV k="Fresh-cross guard" v="Required after every exit" />
          <KV k="Strike step (NIFTY)" v="50 points" />
          <KV k="Quantity per trade" v="1 unit" />
        </Box>
      </Section>
    </article>
  );
}

// ─── DOC 7: Day High OTM v7 — Hard Cap on Trades Per Day ──────

function DocDayHighOTMv7() {
  return (
    <article>
      <H1>Day High OTM Sell (v7) — Three Trades a Day, Then Stop</H1>
      <P>
        v7 takes v6 and adds a hard limit: at most three trades per day, total, across both legs combined.
        Once three positions have entered for the day, the strategy will not open any new positions —
        even if the signal conditions are met and the cooldowns are clear. Existing open positions
        continue to be monitored normally. The intent is to test whether limiting exposure to early
        trades — which under the v6 framework are typically the cleanest signals — can be a viable
        sizing discipline on its own.
      </P>

      <Section title="Position Construction">
        Same as v6 — independent Call and Put legs, each tracking the strike one step
        out-of-the-money. Strikes are recomputed every bar based on the current index level and rolled
        if the index drifts. The day-cap counts entries across BOTH legs together — a Call entry and a
        Put entry both decrement the remaining trade budget.
      </Section>

      <Section title="Day High Tracking">
        Same as v5 / v6 — the day high is a true running maximum, updates on every bar close (including
        bars where a position is live or the cooldown is running), and survives exits. Only a strike
        roll resets it.
      </Section>

      <Section title="Entry Conditions">
        <Rule num="E1" title="Pullback below the locked level">
          Same as v6 — a three-minute bar must close at or below five percent under the day high, with
          the maturity lock already active.
        </Rule>
        <Rule num="E2" title="No active cooldown">
          The leg must not be inside the fifteen-minute window after a recent stop-loss.
        </Rule>
        <Rule num="E3" title="Fresh-cross armed">
          Same as v6 — every re-entry requires a bar to close above the pullback level before another
          bar-close at or below it can fire an entry.
        </Rule>
        <Rule num="E4" title="Daily entry budget not yet exhausted (the v7 rule)">
          The strategy keeps a running count of how many entries have been submitted today across both
          legs. If this count has reached the cap (three by default), no new entries fire — for either
          leg — for the rest of the session.
        </Rule>
      </Section>

      <Section title="Stop-Loss">
        Same as v5 / v6 — set at five percent above the day high at entry time and frozen. Triggered
        intraday on the first option tick that hits or exceeds the stop. Existing positions continue to
        be monitored normally even after the daily entry cap has been hit; the cap only blocks new
        entries.
      </Section>

      <Section title="End-of-Day Exit">
        Any open trade is flat-closed at 15:15 IST. Open positions are not affected by the daily entry
        cap — they always run to either a stop-loss or the end of the day.
      </Section>

      <Section title="Re-Entry Rules">
        <Rule num="R1" title="Standard cooldown applies — until cap is hit">
          The fifteen-minute cooling-off after a stop-loss applies as in v6, but only matters as long
          as new entries are still permitted. Once the daily cap is exhausted, the cooldown is moot —
          no further entries are allowed regardless.
        </Rule>
        <Rule num="R2" title="Fresh-cross requirement applies — until cap is hit">
          Same as the cooldown — meaningful only while the daily entry budget has slots remaining.
        </Rule>
        <Rule num="R3" title="Strike rolls do NOT reset the daily cap">
          The cap counts every entry submitted today, regardless of which strike or leg. If the index
          drifts enough that the Call switches strike mid-day, the count is unaffected.
        </Rule>
      </Section>

      <Section title="Daily Entry Cap — the v7 rule">
        <Rule num="C1" title="Counter advances on entry, not on exit">
          Unlike v4 (which counts completed trades), v7 counts trades when they OPEN. The third entry
          of the day exhausts the budget, even if all three are still open simultaneously and none have
          finalized yet.
        </Rule>
        <Rule num="C2" title="Combined across both legs">
          A Call entry and a Put entry each consume one slot. A typical exhaustion path is one Call
          entry + one Put entry + one re-entry of either leg.
        </Rule>
        <Rule num="C3" title="Once exhausted, no entries — period">
          Even if a great signal forms in the afternoon, after three trades are done the strategy will
          not act on it. This is the deliberate trade-off.
        </Rule>
      </Section>

      <Section title="Quirks Worth Knowing">
        <Rule num="Q1" title="Lighter days produce fewer trades than the cap">
          On many days, the fresh-cross guard combined with the cooldown filter produces only one or
          two entries naturally — the cap of three is a ceiling, not a target.
        </Rule>
        <Rule num="Q2" title="Performance trade-off is real">
          By cutting exposure to the later trades of the day, v7 also gives up the trades that under
          v3 / v4 historically had the highest win rates (those that came after the early-session
          stop-out noise). Whether the simplification is worth it depends on what the trader values
          most: certainty of activity vs maximisation of edge.
        </Rule>
      </Section>

      <Section title="Parameters at a Glance">
        <Box>
          <KV k="Trading hours" v="09:15 to 15:15 IST" />
          <KV k="Bar interval" v="3 minutes" />
          <KV k="Pullback threshold for entry" v="5% below the persistent day high" />
          <KV k="Stop-loss threshold" v="5% above the day high (frozen at entry)" />
          <KV k="Cooldown after stop-loss" v="5 bars (15 minutes)" />
          <KV k="Fresh-cross guard" v="Required after every exit" />
          <KV k="Maximum entries per day" v="3 (across both legs combined)" />
          <KV k="Strike step (NIFTY)" v="50 points" />
          <KV k="Quantity per trade" v="1 unit" />
        </Box>
      </Section>
    </article>
  );
}

// ─── DOC 5: Day High Spot Sell ─────────────────────────────────

function DocDayHighSpot() {
  return (
    <article>
      <H1>Day High Spot Sell</H1>
      <P>
        Same broad architecture as Day High OTM but the signal is on NIFTY SPOT, not on option price.
        When spot forms a new rolling day high and then closes a 3-min bar 5% below it, the strategy sells
        BOTH OTM1 CE and OTM1 PE TOGETHER on a single signal. SL is 5% above the spot day high. Exits are
        coupled — the whole pair closes on any SL hit or at EOD.
      </P>
      <SourceRef file="strategies/day_high_spot_sell.py" />

      <Section title="Position Construction">
        <Rule num="1" title="Signal on spot, execution on two options">
          One spot-day-high → one simultaneous CE + PE sell pair. The pair is treated as a unit for
          entry and exit — there is no per-leg SL.
        </Rule>
        <Rule num="2" title="Dynamic OTM1 strikes at signal time">
          <Code>ce_strike = ATM + 50</Code>, <Code>pe_strike = ATM − 50</Code>, where ATM uses the spot
          at the moment the bar closes below the pullback level.
        </Rule>
      </Section>

      <Section title="Day High Tracking (on spot)">
        <Rule num="DH1" title="Uses bar_high, not bar_close">
          <Code>if self._bar_high &gt; self.day_high: self.day_high = self._bar_high</Code>. This makes the
          tracker more sensitive to intra-bar wicks than the OTM-price variant (which uses close). Less
          lag, but more susceptible to single-tick spikes.
        </Rule>
        <Rule num="DH2" title="Running max, resets only after an exit">
          Day high is a running maximum from 09:15 until an exit finalizes. After exit, the pullback
          level is reset (<Code>pullback_level = 0</Code>) so a NEW day high must form before the next
          entry can fire — but <Code>day_high</Code> itself persists.
        </Rule>
      </Section>

      <Section title="Entry">
        <Rule num="E1" title="Two conditions, both on a 3-min bar close">
          (a) A new spot day high has formed since the last entry (via the <Code>day_high &gt; prev_high
          &amp;&amp; prev_high &gt; 0</Code> gate), which populates a fresh pullback/SL level. <br />
          (b) The current bar&apos;s close is at or below <Code>pullback_level = day_high × 0.95</Code>.
        </Rule>
        <Rule num="E2" title="Simultaneous market orders">
          Both legs are submitted as MARKET SELL at the bar-close moment; Nautilus fills at the next
          tick. Both fills must complete before the position is considered live.
        </Rule>
      </Section>

      <Section title="Stop-Loss (spot-based)">
        <Rule num="SL1" title="On every SPOT tick, not option tick">
          <Code>if self.latest_spot &gt;= self.sl_level: _close_positions(&quot;SL&quot;)</Code>. SL level is
          locked in at signal time as <Code>day_high × 1.05</Code>.
        </Rule>
        <Rule num="SL2" title="Closes BOTH legs together">
          When SL fires, both CE and PE positions are closed via MARKET BUY. No per-leg granularity.
        </Rule>
      </Section>

      <Section title="Re-Entry">
        <Rule num="R1" title="Needs a new day high AFTER exit">
          <Code>_finalize_trade</Code> resets <Code>pullback_level = 0</Code> but keeps
          <Code>day_high</Code>. Because the entry condition requires <Code>day_high &gt; prev_high</Code>
          to rebuild the pullback level, the next trade only fires on a fresh day-high break — no
          cooldown timer, no bar counter.
        </Rule>
        <Rule num="R2" title="Fresh OTM1 strikes on each re-entry">
          New ATM is computed from current spot at the new signal. If spot has drifted, the strikes are
          different from the previous trade.
        </Rule>
      </Section>

      <Section title="Profit Taking">
        <Box tone="info">
          No target. Both legs are held until spot-SL fires or until 15:15 EOD.
        </Box>
      </Section>

      <Section title="Parameters">
        <Box>
          <KV k="start_time / exit_time" v="09:15 / 15:15 IST" />
          <KV k="bar_interval_minutes" v="3" />
          <KV k="pullback_pct" v="5.0 % (spot below day high)" />
          <KV k="sl_pct_above_high" v="5.0 % (spot above day high)" />
          <KV k="strike_step" v="50" />
          <KV k="lot_size × num_lots" v="25 × 1" />
        </Box>
      </Section>
    </article>
  );
}

// ─── DOC 6: Day High VIX Straddle ───────────────────────────────

function DocDayHighVix() {
  return (
    <article>
      <H1>Day High VIX Straddle</H1>
      <P>
        Cross-asset signal: entries are timed by India VIX (the volatility index), but executions are on
        NIFTY options. When VIX forms a new rolling day high on 3-min bars and then closes 2% below it,
        the strategy shorts one ATM NIFTY straddle. The stop is a 30% rise in combined straddle premium
        from entry. Re-entries are allowed on fresh VIX pullback signals throughout the day.
      </P>
      <SourceRef file="strategies/day_high_vix_straddle_sell.py" />

      <Section title="Why VIX as the signal">
        <Box tone="info">
          VIX day-high represents peak fear on the session. A measurable pullback in VIX signals the
          start of a volatility crush — the classic condition under which option premiums mean-revert
          lower. Executing on NIFTY ATM (rather than on VIX itself — no direct VIX options in India)
          captures this through the straddle&apos;s vega exposure.
        </Box>
      </Section>

      <Section title="Position Construction">
        <Rule num="1" title="Two asset streams">
          The strategy subscribes to BOTH <Code>NIFTY-SPOT</Code> and <Code>VIX-SPOT</Code>. The Nautilus
          loader must supply a VIX instrument and VIX tick stream for this strategy to run.
        </Rule>
        <Rule num="2" title="ATM NIFTY straddle, not ATM VIX">
          At signal time, <Code>atm = round(nifty_spot / 50) × 50</Code>. CE and PE are both at this same
          ATM on current weekly expiry.
        </Rule>
      </Section>

      <Section title="VIX Day High Tracking">
        <Rule num="V1" title="Uses bar_high">
          VIX bars are built from VIX ticks on 3-min intervals. Day high updates on
          <Code>vix_bar_high</Code> (intra-bar peak), not on close — more reactive to VIX spikes.
        </Rule>
        <Rule num="V2" title="Pullback level set on each new high">
          When <Code>vix_day_high &gt; prev_high &amp;&amp; prev_high &gt; 0</Code>:
          <Code>vix_pullback_level = vix_day_high × 0.98</Code> (2% below). The 2% threshold is gentler
          than the 5% used for spot/option-price variants because VIX itself is a noisier time series.
        </Rule>
      </Section>

      <Section title="Entry">
        <Rule num="E1" title="VIX bar-close pullback">
          On a 3-min VIX bar close, if <Code>vix_bar_close &lt;= vix_pullback_level</Code>, fire.
        </Rule>
        <Rule num="E2" title="Simultaneous CE+PE market sell on NIFTY ATM">
          Both legs submitted as MARKET SELL together. Combined entry premium is used to set SL.
        </Rule>
        <Rule num="E3" title="No entry while positioned or in EOD state">
          <Code>if self.is_entered or self._pending_exit or self._eod_triggered: return</Code>. One
          position at a time.
        </Rule>
      </Section>

      <Section title="Stop-Loss (on NIFTY straddle premium)">
        <Rule num="SL1" title="30% above entry combined premium">
          After both entry fills, <Code>straddle_sl = (entry_ce + entry_pe) × 1.30</Code>. This is NOT
          per-leg — a single threshold on the sum.
        </Rule>
        <Rule num="SL2" title="Checked on every option tick">
          On each CE or PE ASK tick, the strategy recomputes <Code>current_straddle = latest_ce + latest_pe</Code>
          (using the most recently seen price for each). If this sum crosses <Code>straddle_sl</Code>,
          both legs are closed via MARKET BUY.
        </Rule>
      </Section>

      <Section title="Re-Entry">
        <Rule num="R1" title="Via a new VIX pullback signal">
          After an exit, <Code>_finalize_trade</Code> resets <Code>vix_pullback_level = 0</Code>. A new
          VIX day high must form and then pull back 2% before the next entry can fire. The VIX
          <Code>day_high</Code> itself is not reset, so the condition is genuinely &quot;above the prior
          session peak&quot;.
        </Rule>
        <Rule num="R2" title="No cooldown timer">
          Pure event-driven re-entry. If VIX prints a new high and pulls back within seconds of the
          previous exit, the strategy will re-enter.
        </Rule>
      </Section>

      <Section title="Profit Taking">
        <Box tone="info">No target, no trailing. EOD at 15:15 IST.</Box>
      </Section>

      <Section title="Parameters">
        <Box>
          <KV k="start_time / exit_time" v="09:15 / 15:15 IST" />
          <KV k="bar_interval_minutes" v="3" />
          <KV k="pullback_pct (on VIX)" v="2.0 %" />
          <KV k="sl_pct (on straddle premium)" v="30.0 %" />
          <KV k="strike_step" v="50 (NIFTY)" />
          <KV k="lot_size × num_lots" v="25 × 1" />
        </Box>
      </Section>
    </article>
  );
}

// ─── DOCs for not-detail-read strategies: concise summaries ─────

function DocAllRounder() {
  return (
    <article>
      <H1>Index All Rounder</H1>
      <P>
        A multi-setup intraday strategy combining morning breakout and ORB (Opening Range Breakout)
        patterns across credit-spread structures. The detailed rule set is documented in the source file.
      </P>
      <SourceRef file="strategies/index_allrounder.py" />
      <Box tone="info">
        This strategy page currently reads directly from the source. Full rule documentation will be
        expanded to the same depth as the primary strategies once its backtest has been finalised.
      </Box>
    </article>
  );
}

function DocDirectionalOp() {
  return (
    <article>
      <H1>Directional Credit Spread</H1>
      <P>
        Directional option-selling strategy driven by 9 / 21 EMA crossover on 15-min NIFTY bars. Bull
        crossover → PE credit spread; bear crossover → CE credit spread. Strikes are filtered by
        morning / afternoon premium bands. Exits on 55% SL or 70% target on the sold leg, or on EMA
        reversal.
      </P>
      <SourceRef file="strategies/directional_op_sell.py" />
      <Section title="Signal">
        <Rule num="S1" title="9/21 EMA crossover on 15-min bars">
          Bull cross (fast above slow) → short PE spread. Bear cross (fast below slow) → short CE spread.
        </Rule>
      </Section>
      <Section title="Strike Selection">
        <Rule num="K1" title="Time-of-day premium filter">
          Morning entries use one premium band; afternoon / near-expiry entries use a different band to
          account for theta compression.
        </Rule>
      </Section>
      <Section title="Exits">
        <Rule num="X1" title="55% SL on sold leg">Stops out if sold leg premium rises 55% above entry.</Rule>
        <Rule num="X2" title="70% target on sold leg">Profit target on decay of sold leg.</Rule>
        <Rule num="X3" title="EMA reversal exit">Exit if the 9/21 cross reverses intraday.</Rule>
      </Section>
    </article>
  );
}

function DocMV3() {
  return (
    <article>
      <H1>MV3 v33 Credit Spread</H1>
      <P>
        Dual-independent ORB credit spread system. After 09:25, two independent signals (Set 1 PE and Set 2
        CE) trigger when a 5-min close of ATM±2 breaks its 09:15–09:19 low. Trailing SL arms at +20 pts,
        then trails every 5 pts with a 2 pt stop. PnL bands at -26.67 / +80 (premium units). EOD flat at 15:00.
      </P>
      <SourceRef file="strategies/mv3_credit_spread.py" />
      <Section title="Signal">
        <Rule num="S1" title="Opening-range break on 5-min bars">
          ORB reference = 09:15 to 09:19 low of the ATM±2 leg. After 09:25, any 5-min close below this
          reference triggers entry of the corresponding credit spread (Set 1 PE side, Set 2 CE side).
        </Rule>
      </Section>
      <Section title="Trailing Stop">
        <Rule num="T1" title="Armed at +20 pts">Trailing logic activates only after unrealized PnL ≥ +20 pts.</Rule>
        <Rule num="T2" title="Step-and-lock">Trails every 5 pt improvement, locking a 2 pt stop behind.</Rule>
      </Section>
      <Section title="Hard PnL Bands">
        <Rule num="B1" title="-26.67 hard stop (premium)">Any single structure breaching this threshold is force-closed.</Rule>
        <Rule num="B2" title="+80 hard target (premium)">Lock in gains at this level.</Rule>
      </Section>
      <Section title="EOD">
        <Rule num="E1" title="15:00 IST universal close">Any open spread is closed at 3 PM.</Rule>
      </Section>
    </article>
  );
}

// ─── DOC: MultiLeg DM ────────────────────────────────────────────

function DocMultiLegDM() {
  return (
    <article>
      <H1>MultiLeg DM — 6-Strangle Premium Stack</H1>
      <P>
        At each entry the strategy sells <strong>six short strangles simultaneously</strong> — the ATM
        straddle plus five OTM strangles, stepping by 50 points each. That&apos;s 12 short legs per
        trade (6 CE + 6 PE). Position is exited as a unit on a tight set of risk triggers, and the
        strategy can re-enter throughout the day with fresh strikes after a 3-minute cooldown.
      </P>
      <SourceRef file="strategies/multi_leg_dm.py" />

      <Section title="Position Construction">
        <Rule num="1" title="Compute ATM at signal time">
          <Code>ATM = round(spot / 50) × 50</Code>. Each entry rebuilds strikes from the live spot — there is
          no day-locked anchor.
        </Rule>
        <Rule num="2" title="Build 6 strangles, stepping outward by 50">
          For <Code>i ∈ [0..5]</Code>, sell <Code>CE = ATM + 50·i</Code> and <Code>PE = ATM − 50·i</Code>.
          So strangle #1 is the ATM straddle, then OTM 1, 2, 3, 4, 5. <strong>Zero ITM legs at entry</strong>.
        </Rule>
        <Rule num="3" title="Quantity per leg is fixed">
          <Code>lot_size × num_lots_per_strangle</Code> = 1 × 1 = 1 contract per leg, 12 legs total.
          Configurable but unscaled — no vol-adjusted sizing.
        </Rule>
        <Rule num="4" title="Same expiry across all 12 legs">
          The expiry string is parsed once in <Code>on_start</Code> from any cached option symbol
          (<Code>NIFTY-{`{strike}`}-{`{CE|PE}`}-{`{YYYYMMDD}`}</Code>); the data loader is responsible for
          supplying the nearest-expiry contracts for the trading day.
        </Rule>
      </Section>

      <Section title="Entry">
        <Rule num="E1" title="First entry at 09:21 IST (clock alert)">
          A one-shot alert fires at <Code>entry_time</Code>. If state is <Code>IDLE</Code>, it calls
          <Code>_try_enter()</Code> which submits 12 simultaneous MARKET SELLs.
        </Rule>
        <Rule num="E2" title="Re-entry up to 14:05 IST">
          After every exit, the FSM transitions to <Code>COOLDOWN</Code> and schedules a retry alert at
          <Code>now + cooldown_minutes</Code> (default 3 min). On retry, fresh strikes are picked from
          current spot. If the cooldown end is past <Code>last_entry_time</Code> (14:05), state goes
          <Code>TERMINAL</Code> instead.
        </Rule>
        <Rule num="E3" title="Budget gate">
          Before each entry, remaining headroom = <Code>daily_pnl − daily_sl</Code>. If headroom ≤
          <Code>min_reenter_budget_premium</Code> (0.48), the day terminalizes — preventing entries that
          can&apos;t even fit one full SL within the daily cap.
        </Rule>
        <Rule num="E4" title="Missing-strike handling">
          If the ATM CE/PE pair isn&apos;t resolvable in the cache, the entry retries after the cooldown.
          Missing OTM strikes are simply skipped (the trade enters with however many strangles are
          available, but at least the ATM one).
        </Rule>
      </Section>

      <Section title="Exit Triggers (priority order)">
        <Rule num="X1" title="Daily SL — hard cap">
          On every spot AND option tick: <Code>total = daily_pnl + unrealized</Code>. If
          <Code>total &lt; daily_sl_threshold_premium</Code> (default −1500 pts), the trade is exited and the
          day goes <Code>TERMINAL</Code> — no further re-entries.
        </Rule>
        <Rule num="X2" title="Trade SL — per-trade cap">
          On every option tick: <Code>unrealized &lt; trade_sl_premium</Code> (default −500 pts) → exit. After
          a trade-SL exit, the strategy enters cooldown and may re-enter (subject to E3 + time gate).
        </Rule>
        <Rule num="X3" title="Spot band — DTE-aware">
          On every spot tick: <Code>|spot − spot_at_entry| &gt; band_half</Code>, where
          <Code>band_half = ATM_straddle_at_entry / spot_band_x</Code>. The divisor is DTE-aware:
          <Code>spot_band_x_far_dte = 3.0</Code> for DTE ≥ 2 (tighter band — exit on smaller drift);
          <Code>spot_band_x_near_dte = 2.0</Code> for DTE ≤ 1 (wider band — give 0/1 DTE gamma some
          breathing room).
        </Rule>
        <Rule num="X4" title="EOD flatten at 14:51 IST">
          A clock alert at <Code>exit_time</Code> force-closes any open position and (if not already in
          <Code>PENDING_EXIT</Code>) terminalizes the day.
        </Rule>
      </Section>

      <Section title="DTE Source — Critical">
        <Box tone="warn" title="Trading-day DTE, not calendar-day">
          DTE is read from <Code>data/NSE/trading_dates.csv</Code> (column <Code>DTE</Code>) — the
          canonical TRADING-day count to nearest expiry (Exp1). NIFTY weeklies see DTE in the range 0–5.
          Calendar-day DTE would inflate this (Friday-before-Thursday-expiry would be 6 calendar days
          but is only 4 trading days). All reporting (intraday JSONs, MTM analysis, frontend tabs) uses
          this trading-day DTE.
        </Box>
      </Section>

      <Section title="State Machine">
        <Box>
          <KV k="IDLE" v="Pre-first-entry; only the 09:21 alert can advance" />
          <KV k="PENDING_ENTRY" v="12 SELLs submitted, awaiting fills" />
          <KV k="ACTIVE" v="All entries filled — exit triggers armed" />
          <KV k="PENDING_EXIT" v="Close orders submitted, awaiting fills" />
          <KV k="COOLDOWN" v="Between trades; retry timer set" />
          <KV k="TERMINAL" v="No more entries today (DAILY_SL, EOD, budget exhausted, or past 14:05)" />
        </Box>
      </Section>

      <Section title="PnL Accounting">
        <Rule num="P1" title="Realized — at exit">
          Per leg: <Code>pnl_points = entry_px − exit_px</Code>. Per trade:
          <Code>Σ leg pnl_points</Code>, multiplied by contracts for premium units.
        </Rule>
        <Rule num="P2" title="Unrealized — mid vs entry-mid (not fill_px)">
          To avoid the SELL fill-at-bid showing as instant unrealized loss, the baseline is a snapshot
          of <Code>(bid + ask) / 2</Code> taken at the first tick AFTER entry fill. Unrealized =
          <Code>Σ (entry_mid − current_mid) × contracts</Code>. Realized PnL at exit still captures the
          full round-trip spread cost.
        </Rule>
        <Rule num="P3" title="Daily PnL accumulates across re-entries">
          <Code>daily_pnl_premium</Code> persists across the COOLDOWN→ACTIVE cycle and feeds both the
          daily SL check and the budget gate.
        </Rule>
      </Section>

      <Section title="Parameters (defaults)">
        <Box>
          <KV k="entry_time" v="09:21:00 IST" />
          <KV k="last_entry_time" v="14:05:00 IST" />
          <KV k="exit_time (EOD)" v="14:51:00 IST" />
          <KV k="strike_step" v="50" />
          <KV k="num_strangles" v="6 (ATM + OTM 1..5)" />
          <KV k="lot_size × num_lots_per_strangle" v="1 × 1 (12 leg-contracts/trade)" />
          <KV k="daily_sl_threshold_premium" v="−1500 pts" />
          <KV k="trade_sl_premium" v="−500 pts" />
          <KV k="min_reenter_budget_premium" v="0.48 pts" />
          <KV k="spot_band_x_far_dte (DTE ≥ 2)" v="3.0  →  band_half = straddle / 3" />
          <KV k="spot_band_x_near_dte (DTE ≤ 1)" v="2.0  →  band_half = straddle / 2" />
          <KV k="cooldown_minutes" v="3.0" />
          <KV k="underlying / venue" v="NIFTY / NSE" />
          <KV k="spot_instrument_id" v="NIFTY-SPOT.NSE" />
        </Box>
      </Section>

      <Section title="Backtest Performance (full history, 30s ticks, DTE-aware bands)">
        <Box tone="ok" title="Aug 2020 → Apr 2026 — 1,404 trading days">
          <KV k="Total trades" v="3,832" />
          <KV k="Total PnL" v="+75,081 pts" />
          <KV k="Win rate (per-trade)" v="59.8 %" />
          <KV k="Avg win / loss" v="+67.2 / −51.1 pts" />
          <KV k="Profit factor" v="1.95" />
          <KV k="Sharpe (annualized)" v="5.81" />
          <KV k="Sortino (annualized)" v="6.56" />
          <KV k="Calmar" v="8.09" />
          <KV k="Max drawdown" v="−1,666 pts" />
          <KV k="Worst single trade" v="−616 pts" />
          <KV k="Profitable months" v="97.1 %" />
          <KV k="Day-level win rate (close &gt; 0)" v="71.9 %  (1,010 / 1,404)" />
        </Box>
        <Box tone="info" title="Path-shape distribution (recovery vs giveaway days)">
          <KV k="Red → green (recovered)" v="970 days  ·  mean depth 49 pts  ·  closed +106 avg" />
          <KV k="Green → red (gave back)" v="378 days  ·  mean peak 47 pts  ·  closed −94 avg" />
          <KV k="All-green (never dipped)" v="40 days" />
          <KV k="All-red (never green)" v="16 days" />
          <KV k="Recovery / giveaway ratio" v="2.6×  (strategy recovers from intraday red far more often than it gives back gains)" />
        </Box>
      </Section>

      <Section title="Why Tighter Far-DTE Band Works">
        <P>
          On DTE ≥ 2, the 12-leg book has plenty of theta to harvest and gamma is moderate. A tight
          band (<Code>straddle / 3</Code>) exits before adverse spot drift turns into accelerating
          gamma loss — preserves the small but consistent theta. Empirically: switching from a flat
          1.5 divisor to DTE-aware 3.0 / 2.0 lifted Sharpe from 3.47 → 5.81 and Calmar from 3.88 →
          8.09 on the full history, with 62% more trades but 34% smaller max drawdown.
        </P>
        <P>
          On DTE ≤ 1, gamma is extreme and the strategy needs to ride through whippy spot moves.
          A wider band (<Code>straddle / 2</Code>) avoids the noise-driven exits that would otherwise
          chop up final-expiry days.
        </P>
      </Section>

      <Section title="Operational Characteristics">
        <Rule num="O1" title="Up to multiple trades per day">
          With a 3-min cooldown and entries allowed until 14:05, a busy day can fit 8+ trades.
          Backtest averages ~2.7 trades/day across 1404 days.
        </Rule>
        <Rule num="O2" title="Soft SLs — fills can blow through">
          Both trade and daily SLs are soft (tick-triggered → market exit). The realized worst trade
          (−616) exceeded the −500 trade SL by ~116 pts due to 30s tick spacing and 12 legs of
          bid/ask crossing. Plan size around realistic worst-case, not the configured cap.
        </Rule>
        <Rule num="O3" title="Capacity">
          12 legs × 6 strangles per trade × ~3 trades/day ≈ 36 leg fills per side daily. At retail/
          prop scale this is light, but each ATM/OTM 1 leg moves through the book; sized large, slippage
          dominates.
        </Rule>
        <Rule num="O4" title="No overnight risk">
          Strategy is intraday-only. EOD flatten at 14:51 ensures a clean book; no positions carried.
        </Rule>
      </Section>

      <Section title="Caveats">
        <Box tone="warn" title="In-sample over the entire history">
          The DTE-aware band rule (3.0 / 2.0) was tuned using the same data it&apos;s evaluated on.
          A walk-forward / OOS split would make the headline numbers more believable.
        </Box>
        <Box tone="warn" title="Kurtosis 12.5 — fat-tailed">
          Distribution has a thin body and occasional bad days. Worst day close = −947 pts; worst
          intraday low = −1,183 pts. Inspect the worst 5–10 days before sizing aggressively.
        </Box>
        <Box tone="info" title="Frontend tabs">
          The dashboard offers Returns, Transactions, DTE, Intraday, Charts (per-day Spot + Combined
          Premium + MTM overlay), and MTM (full distribution analysis: daily OHLC candlesticks,
          per-series histograms, quantile table, by-DTE breakdown, and red→green / green→red
          path-shape frequency tables).
        </Box>
      </Section>
    </article>
  );
}

// ─── Main dispatcher ─────────────────────────────────────────────

export default function Documentation() {
  const [active, setActive] = useState<DocStrategy>("day-high-otm");

  return (
    <div>
      <div className="subtabs flex flex-wrap gap-1 mb-6">
        {STRATS.map((s) => {
          const isActive = s.id === active;
          return (
            <button
              key={s.id}
              onClick={() => setActive(s.id)}
              className={`subtab ${isActive ? "active" : ""}`}
            >
              {s.label}
            </button>
          );
        })}
      </div>

      <div className="max-w-5xl">
        {active === "atm" && <DocATM />}
        {active === "vanilla" && <DocVanilla />}
        {active === "day-high-otm" && <DocDayHighOTM />}
        {active === "day-high-otm-v4" && <DocDayHighOTMv4 />}
        {active === "day-high-otm-v5" && <DocDayHighOTMv5 />}
        {active === "day-high-otm-v6" && <DocDayHighOTMv6 />}
        {active === "day-high-otm-v7" && <DocDayHighOTMv7 />}
        {active === "day-high-spot" && <DocDayHighSpot />}
        {active === "day-high-vix" && <DocDayHighVix />}
        {active === "allrounder" && <DocAllRounder />}
        {active === "directional-op" && <DocDirectionalOp />}
        {active === "mv3" && <DocMV3 />}
        {active === "multilegdm" && <DocMultiLegDM />}
      </div>
    </div>
  );
}
