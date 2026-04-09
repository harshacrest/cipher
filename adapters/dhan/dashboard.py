"""Dashboard WebSocket server — broadcasts status to frontend on port 1156.

Runs in a daemon thread with its own asyncio event loop. The live runner
starts it before node.run(). Frontend connects to ws://localhost:1156/ws.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time

from aiohttp import web

log = logging.getLogger(__name__)

_clients: set[web.WebSocketResponse] = set()
_log_buffer: list[dict] = []
_start_time: float = 0.0
_ws_loop: asyncio.AbstractEventLoop | None = None
_runner: web.AppRunner | None = None

MAX_LOGS = 100


def add_log(level: str, message: str) -> None:
    """Add a log entry and broadcast to connected clients."""
    entry = {"level": level, "msg": message, "ts": int(time.time() * 1000)}
    _log_buffer.append(entry)
    if len(_log_buffer) > MAX_LOGS:
        del _log_buffer[: len(_log_buffer) - MAX_LOGS]
    broadcast({"type": "log", "data": entry})


def broadcast(msg: dict) -> None:
    """Thread-safe broadcast to all WebSocket clients."""
    if not _clients or not _ws_loop:
        return
    payload = json.dumps(msg)
    for ws in list(_clients):
        if not ws.closed:
            _ws_loop.call_soon_threadsafe(
                asyncio.ensure_future, ws.send_str(payload)
            )


async def _ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    _clients.add(ws)
    log.info("Dashboard client connected (%d total)", len(_clients))

    await ws.send_json({
        "type": "init",
        "data": {
            "status": "running",
            "uptime_secs": int(time.time() - _start_time),
            "logs": _log_buffer[-50:],
        },
    })

    try:
        async for _ in ws:
            pass
    finally:
        _clients.discard(ws)
        log.info("Dashboard client disconnected (%d remaining)", len(_clients))
    return ws


async def _health_handler(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "running",
        "uptime_secs": int(time.time() - _start_time),
        "clients": len(_clients),
    })


def _run_server(host: str, port: int) -> None:
    """Run aiohttp server in a new event loop (called in daemon thread)."""
    global _ws_loop, _runner

    _ws_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_ws_loop)

    app = web.Application()
    app.router.add_get("/ws", _ws_handler)
    app.router.add_get("/health", _health_handler)

    _runner = web.AppRunner(app)
    _ws_loop.run_until_complete(_runner.setup())
    site = web.TCPSite(_runner, host, port)
    _ws_loop.run_until_complete(site.start())

    print(f"[Dashboard] WebSocket server started on ws://{host}:{port}/ws", flush=True)
    add_log("INFO", "Dashboard WebSocket server started")

    _ws_loop.run_forever()


def start_dashboard_server(host: str = "localhost", port: int = 1156) -> None:
    """Start the dashboard WS server in a daemon thread."""
    global _start_time
    _start_time = time.time()
    t = threading.Thread(target=_run_server, args=(host, port), daemon=True)
    t.start()
    print(f"[Dashboard] Server thread started (port {port})", flush=True)
