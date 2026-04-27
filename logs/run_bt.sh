#!/bin/bash
cd /Users/harsha/Desktop/Research/cipher
VERSION=$1
EXTRA_ARGS=$2
LOG=logs/${VERSION}.log
echo "START $(date)" > $LOG
if [ "$VERSION" = "v4" ]; then
  uv run python backtest/runner_day_high_v4.py --skip 3 --cost 0 >> $LOG 2>&1
elif [ "$VERSION" = "v5" ]; then
  uv run python backtest/runner_day_high_v5.py --cost 0 >> $LOG 2>&1
elif [ "$VERSION" = "v6" ]; then
  uv run python backtest/runner_day_high_v6.py --cost 0 >> $LOG 2>&1
fi
echo "DONE exit=$? $(date)" >> $LOG
