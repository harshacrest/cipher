#!/bin/bash
# Run v3, v4, v5, v6, v7 sequentially on FULL 5.5-year backtest.
# Each version produces its own log and output files.
set -u
cd /Users/harsha/Desktop/Research/cipher

MASTER=logs/full_run_master.log
echo "MASTER START $(date)" > $MASTER

run_one() {
  local VERSION=$1
  local CMD=$2
  local LOG=logs/full_${VERSION}.log
  echo "[$(date)] === START $VERSION ===" | tee -a $MASTER
  echo "CMD: $CMD" >> $LOG
  echo "START $(date)" >> $LOG
  eval "$CMD" >> $LOG 2>&1
  local rc=$?
  echo "DONE $VERSION exit=$rc $(date)" >> $LOG
  echo "[$(date)] === DONE $VERSION exit=$rc ===" | tee -a $MASTER
  return $rc
}

# v3 — baseline (qty=1, lot_size=1 via updated config)
run_one v3 "uv run python backtest/runner_day_high.py"

# v4 — phantom 1, real 1, but phantom zeroed in output; skip first 3 finalize-count
run_one v4 "uv run python backtest/runner_day_high_v4.py --skip 3 --phantom-qty 1 --real-qty 1 --cost 0"

# v5 — whole-day DH (qty=1, SL-widening bug fixed)
run_one v5 "uv run python backtest/runner_day_high_v5.py --cost 0"

# v6 — v5 + fresh-cross guard (qty=1, SL-widening bug fixed)
run_one v6 "uv run python backtest/runner_day_high_v6.py --cost 0"

# v7 — v6 + max 3 trades/day (qty=1, SL-widening bug fixed)
run_one v7 "uv run python backtest/runner_day_high_v7.py --max-trades 3 --cost 0"

echo "[$(date)] ALL DONE" | tee -a $MASTER
