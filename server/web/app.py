"""
FastAPI app factory and WebSocket hub for the ccoli web dashboard.
Shares state with server.py via injected lambda references to globals.
"""
import asyncio
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .auth import auth_required, token_matches

# ── Forward references to server.py globals ──────────────────────────────────
# These are set by create_app() and always return the live global values.
_agent_ref: Callable = lambda: None
_robot_ref: Callable = lambda: None
_mode_ref: Callable = lambda: "agent"
_default_dashboard_state: dict = {}
_dashboard_state_ref: Callable = lambda: _default_dashboard_state

# ── WebSocket client registry ─────────────────────────────────────────────────
_ws_clients: Set[WebSocket] = set()
_ws_lock = threading.Lock()
WS_AUTH_TIMEOUT_SECONDS = 5.0
WS_AUTH_MAX_BYTES = 4096

# ── Event loop reference (set during lifespan) ───────────────────────────────
_loop: Optional[asyncio.AbstractEventLoop] = None


def get_agent():
    """Return the live agent_handler or raise HTTP 503 if not yet ready."""
    handler = _agent_ref()
    if handler is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Agent not initialized yet")
    return handler


def get_mode() -> str:
    return _mode_ref()


def get_dashboard_state() -> dict:
    state = _dashboard_state_ref()
    return state if isinstance(state, dict) else {}


async def broadcast(event: dict):
    """Fan-out a JSON event to all connected WebSocket clients."""
    msg = json.dumps(event, ensure_ascii=False, default=str)
    dead: Set[WebSocket] = set()
    with _ws_lock:
        clients = set(_ws_clients)
    for ws in clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    if dead:
        with _ws_lock:
            _ws_clients.difference_update(dead)


async def _authenticate_socket(websocket: WebSocket) -> bool:
    """Read one bounded auth frame before registering a live event subscriber."""
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=WS_AUTH_TIMEOUT_SECONDS)
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > WS_AUTH_MAX_BYTES:
            return False
        frame = json.loads(raw)
    except (asyncio.TimeoutError, WebSocketDisconnect, KeyError, RuntimeError, ValueError):
        return False
    return (
        isinstance(frame, dict)
        and set(frame) == {"event", "token"}
        and frame["event"] == "authenticate"
        and token_matches(frame["token"])
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop
    _loop = asyncio.get_event_loop()
    # Wire event loop + broadcast into log_handler for cross-thread log streaming
    from . import log_handler
    log_handler.set_loop(_loop)
    log_handler.set_broadcast(broadcast)
    # Start background status poller
    task = asyncio.ensure_future(_status_poller())
    yield
    task.cancel()


async def _status_poller():
    """Poll agent state every 5 seconds and broadcast diffs."""
    last_emotion = None
    last_conv_count = -1
    while True:
        await asyncio.sleep(5)
        try:
            agent = _agent_ref()
            if agent is None:
                continue
            cur_emotion = agent.emotion_system.current_emotion
            cur_count = agent.conversation_count
            if cur_emotion != last_emotion or cur_count != last_conv_count:
                if cur_emotion != last_emotion:
                    await broadcast({
                        "event": "emotion_change",
                        "emotion": cur_emotion,
                        "previous": last_emotion,
                    })
                await broadcast({
                    "event": "status_update",
                    "mode": _mode_ref(),
                    "emotion": cur_emotion,
                    "conversation_count": cur_count,
                })
                last_emotion = cur_emotion
                last_conv_count = cur_count
        except Exception:
            pass


def create_app(
    agent_fn: Callable,
    robot_fn: Callable,
    mode_fn: Callable,
    dashboard_state_fn: Callable | None = None,
) -> FastAPI:
    global _agent_ref, _robot_ref, _mode_ref, _dashboard_state_ref
    _agent_ref = agent_fn
    _robot_ref = robot_fn
    _mode_ref = mode_fn
    _dashboard_state_ref = dashboard_state_fn or (lambda: _default_dashboard_state)

    app = FastAPI(title="ccoli dashboard", docs_url="/api/docs", lifespan=lifespan)

    # Mount REST routers
    from .routes import (
        api_status, api_memory, api_conversation,
        api_schedules, api_config, api_integrations,
        api_chat, api_logs, api_diagnostics, api_agent, api_dialogue, api_robotics, api_home_setup,
    )
    for mod in (
        api_status, api_memory, api_conversation,
        api_schedules, api_config, api_integrations,
        api_chat, api_logs, api_diagnostics, api_agent, api_dialogue, api_robotics, api_home_setup,
    ):
        app.include_router(mod.router)

    # WebSocket endpoint
    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        if auth_required() and not await _authenticate_socket(websocket):
            await websocket.close(code=4401)
            return
        with _ws_lock:
            _ws_clients.add(websocket)
        try:
            while True:
                await websocket.receive_text()  # keep-alive; client sends pings
        except WebSocketDisconnect:
            pass
        finally:
            with _ws_lock:
                _ws_clients.discard(websocket)

    # Serve SPA — must be last so it doesn't shadow API routes
    static_dir = Path(__file__).parent / "static"
    brand_assets_dir = Path(__file__).resolve().parents[2] / "assets"
    docs_assets_dir = Path(__file__).resolve().parents[2] / "docs" / "assets"
    if brand_assets_dir.exists():
        app.mount("/brand-assets", StaticFiles(directory=str(brand_assets_dir)), name="brand-assets")
    if docs_assets_dir.exists():
        app.mount("/brand-docs", StaticFiles(directory=str(docs_assets_dir)), name="brand-docs")
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
