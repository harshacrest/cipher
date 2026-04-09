export interface Metric {
  Metric: string;
  Value: number | string;
}

export interface Trade {
  date: string;
  ce_strike: number;
  pe_strike: number;
  entry_time: string;
  exit_time: string;
  spot_at_entry: number;
  spot_at_exit: number;
  spot_move: number;
  spot_move_pct: number;
  entry_ce: number;
  entry_pe: number;
  exit_ce: number;
  exit_pe: number;
  ce_sl: number;
  pe_sl: number;
  ce_pnl: number;
  pe_pnl: number;
  ce_exit_reason: string;
  pe_exit_reason: string;
  ce_exit_time: string;
  pe_exit_time: string;
  pnl: number;
  pnl_pct: number;
  cumulative_pnl: number;
}

export interface EquityPoint {
  date: string;
  trade_num: number;
  pnl: number;
  cumulative_pnl: number;
}

export interface MonthlyRow {
  year: number;
  month: number;
  trades: number;
  total_pnl: number;
  avg_pnl: number;
  win_rate: number;
  max_win: number;
  max_loss: number;
}

export interface YearlyRow {
  year: number;
  trades: number;
  total_pnl: number;
  avg_pnl: number;
  win_rate: number;
  max_win: number;
  max_loss: number;
  sharpe: number;
}

export interface DowRow {
  day_of_week: string;
  trades: number;
  total_pnl: number;
  avg_pnl: number;
  win_rate: number;
}

export interface DteRow {
  dte: number;
  trades: number;
  total_pnl: number;
  avg_pnl: number;
  win_rate: number;
}

export interface IntradayTick {
  time: string;
  spot: number;
  ce_price: number | null;
  pe_price: number | null;
}

export interface IntradayData {
  ticks: IntradayTick[];
  entry_time: string;
  ce_strike: number;
  pe_strike: number;
  ce_sl: number | null;
  pe_sl: number | null;
  entry_ce: number | null;
  entry_pe: number | null;
  exit_ce: number | null;
  exit_pe: number | null;
  ce_exit_time: string;
  pe_exit_time: string;
  ce_exit_reason: string;
  pe_exit_reason: string;
  ce_pnl: number | null;
  pe_pnl: number | null;
  pnl: number;
}

// Day High OTM Sell Strategy types — each trade is ONE leg (CE or PE)
export interface DayHighTrade {
  date: string;
  trade_num: number;
  side: string;        // "CE" or "PE"
  strike: number;
  day_high: number;    // option price day high at signal
  pullback_level: number;
  sl_level: number;
  entry_time: string | null;
  exit_time: string | null;
  exit_reason: string;
  spot_at_entry: number;
  spot_at_exit: number;
  entry_px: number;
  exit_px: number;
  pnl: number;
  pnl_pct: number;
  cumulative_pnl: number;
}

export interface DayHighIntradayTick {
  time: string;
  spot: number;
}

export interface DayHighPriceTick {
  time: string;
  price: number;
}

export interface DayHighIntradayTrade {
  trade_num: number;
  side: string;
  strike: number;
  entry_time: string | null;
  exit_time: string | null;
  day_high: number;
  pullback_level: number;
  sl_level: number;
  exit_reason: string;
  entry_px: number;
  exit_px: number;
  pnl: number;
  price_ticks: DayHighPriceTick[];
}

export interface DayHighIntradayData {
  ticks: DayHighIntradayTick[];
  trades: DayHighIntradayTrade[];
  total_pnl: number;
}
