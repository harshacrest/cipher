#!/bin/bash
cd /Users/harsha/Desktop/Research/cipher

MASTER=logs/sequential_master.log
echo "START $(date)" > $MASTER

run_one() {
  local VERSION=$1
  local ARGS=$2
  local LOG=logs/${VERSION}.log
  echo "[$(date)] Starting $VERSION..." | tee -a $MASTER
  echo "START $(date)" > $LOG
  uv run python backtest/runner_day_high_${VERSION}.py $ARGS >> $LOG 2>&1
  local rc=$?
  echo "DONE exit=$rc $(date)" >> $LOG
  echo "[$(date)] Finished $VERSION with exit=$rc" | tee -a $MASTER
  return $rc
}

run_one v4 "--skip 3 --cost 0"
run_one v5 "--cost 0"
run_one v6 "--cost 0"

echo "[$(date)] ALL SEQUENTIAL DONE" | tee -a $MASTER
