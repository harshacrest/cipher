"""Process manager for the live trading node.

Called by Next.js API routes to start/stop the trading process and manage config.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
PID_FILE = PROJECT_ROOT / "output" / "live" / "pid"
CONFIG_FILE = PROJECT_ROOT / "config" / "dhan_live.toml"
RUN_LIVE_SCRIPT = PROJECT_ROOT / "scripts" / "run_live.py"
LOG_FILE = PROJECT_ROOT / "output" / "live" / "engine.log"


def _ensure_dirs() -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)


def is_running() -> tuple[bool, int | None]:
    """Check if the live process is running. Returns (running, pid)."""
    if not PID_FILE.exists():
        return False, None
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)  # Signal 0 = check if alive
        return True, pid
    except (OSError, ValueError):
        PID_FILE.unlink(missing_ok=True)
        return False, None


def start() -> dict:
    """Start the live trading process."""
    _ensure_dirs()
    running, pid = is_running()
    if running:
        return {"status": "already_running", "pid": pid}

    log_file = open(LOG_FILE, "w")
    proc = subprocess.Popen(
        [sys.executable, str(RUN_LIVE_SCRIPT)],
        cwd=str(PROJECT_ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid))
    return {"status": "started", "pid": proc.pid}


def stop() -> dict:
    """Stop the live trading process."""
    running, pid = is_running()
    if not running:
        return {"status": "not_running"}

    try:
        os.kill(pid, signal.SIGTERM)
        PID_FILE.unlink(missing_ok=True)
        return {"status": "stopped", "pid": pid}
    except OSError as e:
        return {"status": "error", "message": str(e)}


def get_status() -> dict:
    """Get current status of the live process."""
    running, pid = is_running()
    result = {"running": running, "pid": pid}

    if LOG_FILE.exists():
        # Read last 50 lines of log
        lines = LOG_FILE.read_text().splitlines()
        result["recent_logs"] = lines[-50:]

    return result


def load_config() -> dict:
    """Load config from dhan_live.toml."""
    if not CONFIG_FILE.exists():
        return {
            "dhan": {"access_token": "", "client_id": ""},
            "strategy": {"entry_time": "09:21:00", "exit_time": "15:00:00", "num_lots": 1},
        }
    try:
        import tomllib
        with open(CONFIG_FILE, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {"dhan": {"access_token": "", "client_id": ""}, "strategy": {}}


def save_config(data: dict) -> dict:
    """Save config to dhan_live.toml."""
    _ensure_dirs()
    lines = ["[dhan]"]
    dhan = data.get("dhan", {})
    lines.append(f'access_token = "{dhan.get("access_token", "")}"')
    lines.append(f'client_id = "{dhan.get("client_id", "")}"')
    lines.append("")
    lines.append("[strategy]")
    strategy = data.get("strategy", {})
    lines.append(f'entry_time = "{strategy.get("entry_time", "09:21:00")}"')
    lines.append(f'exit_time = "{strategy.get("exit_time", "15:00:00")}"')
    lines.append(f'num_lots = {strategy.get("num_lots", 1)}')

    CONFIG_FILE.write_text("\n".join(lines) + "\n")
    return {"status": "saved"}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(json.dumps(get_status()))
    elif sys.argv[1] == "start":
        print(json.dumps(start()))
    elif sys.argv[1] == "stop":
        print(json.dumps(stop()))
    elif sys.argv[1] == "status":
        print(json.dumps(get_status()))
    elif sys.argv[1] == "config":
        print(json.dumps(load_config()))
