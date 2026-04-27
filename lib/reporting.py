"""Common output/Excel generation utilities for strategy results."""

from pathlib import Path

import numpy as np
import pandas as pd

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def compute_metrics(trades: pd.DataFrame) -> dict:
    """Compute comprehensive backtest metrics from trades dataframe."""
    if trades.empty:
        return {"Total PnL (pts)": 0, "Total Trades": 0}

    pnl = trades["pnl"]
    total_pnl = pnl.sum()
    n_trades = len(trades)
    n_winners = (pnl > 0).sum()
    n_losers = (pnl < 0).sum()
    n_flat = (pnl == 0).sum()

    win_rate = n_winners / n_trades * 100 if n_trades > 0 else 0
    avg_pnl = pnl.mean()
    avg_win = pnl[pnl > 0].mean() if n_winners > 0 else 0
    avg_loss = pnl[pnl < 0].mean() if n_losers > 0 else 0
    max_win = pnl.max()
    max_loss = pnl.min()

    # Profit factor
    gross_profit = pnl[pnl > 0].sum()
    gross_loss = abs(pnl[pnl < 0].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Expectancy
    expectancy = avg_pnl

    # Risk-reward ratio
    risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

    # Drawdown analysis on cumulative PnL
    cum_pnl = pnl.cumsum()
    running_max = cum_pnl.cummax()
    drawdown = cum_pnl - running_max
    max_drawdown = drawdown.min()

    # Drawdown duration (in trading days)
    max_dd_duration = 0
    current_dd_start = None
    for i, val in enumerate(drawdown):
        if val < 0 and current_dd_start is None:
            current_dd_start = i
        elif val >= 0 and current_dd_start is not None:
            duration = i - current_dd_start
            if duration > max_dd_duration:
                max_dd_duration = duration
            current_dd_start = None
    # Handle ongoing drawdown
    if current_dd_start is not None:
        duration = len(drawdown) - current_dd_start
        if duration > max_dd_duration:
            max_dd_duration = duration

    # Aggregate to DAILY PnL for risk metrics (multiple trades/day must be summed)
    daily_pnl = trades.groupby(trades["date"].dt.date)["pnl"].sum()
    n_days = len(daily_pnl)

    # Calmar ratio (annualized return / max drawdown)
    n_years = n_days / 252
    annualized_return = total_pnl / n_years if n_years > 0 else 0
    calmar = annualized_return / abs(max_drawdown) if max_drawdown != 0 else float("inf")

    # Sharpe ratio (daily PnL, annualized)
    if daily_pnl.std() > 0:
        sharpe = (daily_pnl.mean() / daily_pnl.std()) * np.sqrt(252)
    else:
        sharpe = 0

    # Sortino ratio (daily downside deviation, annualized)
    daily_downside = daily_pnl[daily_pnl < 0]
    if len(daily_downside) > 0 and daily_downside.std() > 0:
        sortino = (daily_pnl.mean() / daily_downside.std()) * np.sqrt(252)
    else:
        sortino = 0

    # Monthly aggregation
    trades_with_month = trades.copy()
    trades_with_month["month"] = trades["date"].dt.to_period("M")
    monthly_pnl = trades_with_month.groupby("month")["pnl"].sum()
    best_month = monthly_pnl.max()
    worst_month = monthly_pnl.min()
    pct_profitable_months = (monthly_pnl > 0).sum() / len(monthly_pnl) * 100 if len(monthly_pnl) > 0 else 0

    # Streak analysis
    streak = 0
    max_win_streak = 0
    max_loss_streak = 0
    for p in pnl:
        if p > 0:
            streak = streak + 1 if streak > 0 else 1
        elif p < 0:
            streak = streak - 1 if streak < 0 else -1
        else:
            streak = 0
        max_win_streak = max(max_win_streak, streak)
        max_loss_streak = min(max_loss_streak, streak)

    return {
        "Total PnL (pts)": round(total_pnl, 2),
        "Total Trades": n_trades,
        "Winners": n_winners,
        "Losers": n_losers,
        "Flat": n_flat,
        "Win Rate (%)": round(win_rate, 2),
        "Avg PnL (pts)": round(avg_pnl, 2),
        "Avg Win (pts)": round(avg_win, 2),
        "Avg Loss (pts)": round(avg_loss, 2),
        "Max Win (pts)": round(max_win, 2),
        "Max Loss (pts)": round(max_loss, 2),
        "Profit Factor": round(profit_factor, 3),
        "Risk-Reward Ratio": round(risk_reward, 3),
        "Expectancy (pts)": round(expectancy, 2),
        "Sharpe Ratio (ann.)": round(sharpe, 3),
        "Sortino Ratio (ann.)": round(sortino, 3),
        "Calmar Ratio": round(calmar, 3),
        "Max Drawdown (pts)": round(max_drawdown, 2),
        "Max DD Duration (days)": max_dd_duration,
        "Annualized Return (pts)": round(annualized_return, 2),
        "Best Month (pts)": round(best_month, 2),
        "Worst Month (pts)": round(worst_month, 2),
        "Profitable Months (%)": round(pct_profitable_months, 2),
        "Max Win Streak": max_win_streak,
        "Max Loss Streak": abs(max_loss_streak),
        "Std Dev (daily)": round(daily_pnl.std(), 2),
        "Skewness": round(daily_pnl.skew(), 3),
        "Kurtosis": round(daily_pnl.kurtosis(), 3),
    }


def generate_report(strategy_name: str, trades: pd.DataFrame):
    """Generate Excel report with trades, metrics, and monthly breakdown."""
    out_dir = OUTPUT_DIR / strategy_name
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics = compute_metrics(trades)

    # --- trades.xlsx ---
    trades_out = trades.copy()
    trades_out["date"] = trades_out["date"].dt.strftime("%Y-%m-%d")
    trades_out.to_excel(out_dir / "trades.xlsx", index=False, sheet_name="Trades")

    # --- performance.xlsx (metrics + monthly + yearly) ---
    with pd.ExcelWriter(out_dir / "performance.xlsx", engine="openpyxl") as writer:
        # Summary metrics
        metrics_df = pd.DataFrame(list(metrics.items()), columns=["Metric", "Value"])
        metrics_df.to_excel(writer, sheet_name="Summary", index=False)

        # Monthly PnL
        trades_m = trades.copy()
        trades_m["year"] = trades["date"].dt.year
        trades_m["month"] = trades["date"].dt.month
        monthly = trades_m.groupby(["year", "month"]).agg(
            trades=("pnl", "count"),
            total_pnl=("pnl", "sum"),
            avg_pnl=("pnl", "mean"),
            win_rate=("pnl", lambda x: (x > 0).sum() / len(x) * 100),
            max_win=("pnl", "max"),
            max_loss=("pnl", "min"),
        ).round(2).reset_index()
        monthly.to_excel(writer, sheet_name="Monthly", index=False)

        # Yearly PnL (Sharpe computed on daily-aggregated PnL per year)
        yearly = trades_m.groupby("year").agg(
            trades=("pnl", "count"),
            total_pnl=("pnl", "sum"),
            avg_pnl=("pnl", "mean"),
            win_rate=("pnl", lambda x: (x > 0).sum() / len(x) * 100),
            max_win=("pnl", "max"),
            max_loss=("pnl", "min"),
        ).round(2).reset_index()
        # Compute yearly Sharpe from daily PnL
        trades_m["date_only"] = trades_m["date"].dt.date
        yearly_sharpe = []
        for yr in yearly["year"]:
            yr_daily = trades_m[trades_m["year"] == yr].groupby("date_only")["pnl"].sum()
            if yr_daily.std() > 0:
                yearly_sharpe.append(round((yr_daily.mean() / yr_daily.std()) * np.sqrt(252), 2))
            else:
                yearly_sharpe.append(0.0)
        yearly["sharpe"] = yearly_sharpe
        yearly.to_excel(writer, sheet_name="Yearly", index=False)

        # Day-of-week analysis
        trades_dow = trades.copy()
        trades_dow["day_of_week"] = trades["date"].dt.day_name()
        dow = trades_dow.groupby("day_of_week").agg(
            trades=("pnl", "count"),
            total_pnl=("pnl", "sum"),
            avg_pnl=("pnl", "mean"),
            win_rate=("pnl", lambda x: (x > 0).sum() / len(x) * 100),
        ).round(2)
        dow = dow.reindex(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]).reset_index()
        dow.to_excel(writer, sheet_name="DayOfWeek", index=False)

        # DTE analysis
        if "dte" in trades.columns:
            dte_analysis = trades.groupby("dte").agg(
                trades=("pnl", "count"),
                total_pnl=("pnl", "sum"),
                avg_pnl=("pnl", "mean"),
                win_rate=("pnl", lambda x: (x > 0).sum() / len(x) * 100),
            ).round(2).reset_index()
            dte_analysis.to_excel(writer, sheet_name="ByDTE", index=False)

    # --- equity_curve.csv ---
    equity = trades[["date", "pnl", "cumulative_pnl"]].copy()
    equity["date"] = equity["date"].dt.strftime("%Y-%m-%d")
    equity.to_csv(out_dir / "equity_curve.csv", index=False)

    print(f"\n{'='*50}")
    print(f"  BACKTEST RESULTS: {strategy_name}")
    print(f"{'='*50}")
    for k, v in metrics.items():
        print(f"  {k:<30} {v}")
    print(f"{'='*50}")
