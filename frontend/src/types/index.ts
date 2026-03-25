export interface Metric {
  Metric: string;
  Value: number | string;
}

export interface Trade {
  date: string;
  atm_strike: number;
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
  entry_straddle: number;
  exit_straddle: number;
  pnl: number;
  pnl_pct: number;
  cumulative_pnl: number;
}

export interface EquityPoint {
  date: string;
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
  atm_price: number | null;
  ce_price: number | null;
  pe_price: number | null;
}

export interface IntradayData {
  ticks: IntradayTick[];
  entry_time: string;
  exit_time: string;
  atm_strike: number;
  pnl: number | null;
}
