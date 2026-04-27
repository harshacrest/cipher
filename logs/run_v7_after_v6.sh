#!/bin/bash
cd /Users/harsha/Desktop/Research/cipher
MASTER=logs/v7_queue.log
echo "WAITING for v6 to finish $(date)" > $MASTER

# Wait for v6 to finish (check every 30 seconds)
while pgrep -f "runner_day_high_v6\.py" > /dev/null; do
  sleep 30
done
echo "v6 finished $(date). Starting v7..." >> $MASTER

LOG=logs/v7.log
echo "START $(date)" > $LOG
uv run python backtest/runner_day_high_v7.py --max-trades 3 --cost 0 >> $LOG 2>&1
rc=$?
echo "DONE exit=$rc $(date)" >> $LOG
echo "v7 finished exit=$rc $(date)" >> $MASTER
