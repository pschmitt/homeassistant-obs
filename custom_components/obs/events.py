"""OBS Studio real-time event listener — native asyncio implementation.

Replaces the obsws_python.EventClient (background thread + callback dispatch)
with a plain aiohttp WebSocket that runs directly on the HA event loop.  This
means:
  - no thread crossing, no run_coroutine_threadsafe / call_soon_threadsafe
  - coordinator.async_set_updated_data() called directly — entities update the
    same event-loop iteration the WS frame arrives
  - full auto-reconnect with exponential back-off
  - endpoint hot-swap: cancel old task, spin up new one

OBS WebSocket v5 wire format used directly so we avoid obsws_python entirely
for the event path (it's still used for requests via ReqClient).
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import OBSCoordinator

_LOGGER = logging.getLogger(__name__)

# eventSubscriptions bitmask — LOW_VOLUME covers everything we care about.
# (GENERAL=1 | CONFIG=2 | SCENES=4 | INPUTS=8 | TRANSITIONS=16 |
#  FILTERS=32 | OUTPUTS=64 | SCENEITEMS=128 | MEDIAINPUTS=256 |
#  VENDORS=512 | UI=1024)
_SUBS = 2047

# Reconnect delays (seconds): 1, 2, 4, 8, 16, 30, 30, ...
_BACKOFF = [1, 2, 4, 8, 16, 30]

# Fast-path: payload carries all state we need → patch coordinator data inline.
_FAST_EVENTS: frozenset[str] = frozenset(
    {
        "CurrentProgramSceneChanged",
        "CurrentPreviewSceneChanged",
        "StreamStateChanged",
        "RecordStateChanged",
        "VirtualcamStateChanged",
        "StudioModeStateChanged",
        "ReplayBufferStateChanged",
        "ReplayBufferSaved",
    }
)

# Slow-path: payload doesn't include the full scene list — full re-fetch needed.
_SLOW_EVENTS: frozenset[str] = frozenset(
    {
        "SceneCreated",
        "SceneRemoved",
        "SceneNameChanged",
    }
)


# ---------------------------------------------------------------------------
# OBS WebSocket v5 authentication
# ---------------------------------------------------------------------------

def _obs_auth(password: str, salt: str, challenge: str) -> str:
    secret = base64.b64encode(
        hashlib.sha256((password + salt).encode()).digest()
    ).decode()
    return base64.b64encode(
        hashlib.sha256((secret + challenge).encode()).digest()
    ).decode()


# ---------------------------------------------------------------------------
# State patching — same logic as before, zero dependencies on obsws_python
# ---------------------------------------------------------------------------

def _safe(d: dict, key: str, default=None):
    return d.get(key, default)


def _patch_data(data, event_type: str, event_data: dict):
    """Return an updated OBSData from event payload, or None if no-op."""
    if event_type == "CurrentProgramSceneChanged":
        scene = _safe(event_data, "sceneName")
        if scene is None or scene == data.current_scene:
            return None
        return dataclasses.replace(data, current_scene=scene)

    if event_type == "StreamStateChanged":
        active = bool(_safe(event_data, "outputActive", data.streaming))
        if active == data.streaming:
            return None
        return dataclasses.replace(data, streaming=active)

    if event_type == "RecordStateChanged":
        active = bool(_safe(event_data, "outputActive", data.recording))
        state_str = _safe(event_data, "outputState", "")
        paused = state_str == "OBS_WEBSOCKET_OUTPUT_PAUSED"
        if active == data.recording and paused == data.recording_paused:
            return None
        return dataclasses.replace(data, recording=active, recording_paused=paused)

    if event_type == "VirtualcamStateChanged":
        active = bool(_safe(event_data, "outputActive", data.virtual_cam_active))
        if active == data.virtual_cam_active:
            return None
        return dataclasses.replace(data, virtual_cam_active=active)

    if event_type == "StudioModeStateChanged":
        enabled = bool(_safe(event_data, "studioModeEnabled", data.studio_mode_enabled))
        if enabled == data.studio_mode_enabled:
            return None
        return dataclasses.replace(data, studio_mode_enabled=enabled)

    if event_type == "ReplayBufferStateChanged":
        active = bool(_safe(event_data, "outputActive", data.replay_buffer_active))
        if active == data.replay_buffer_active:
            return None
        return dataclasses.replace(data, replay_buffer_active=active)

    return None  # no-op


# ---------------------------------------------------------------------------
# Event listener
# ---------------------------------------------------------------------------

class OBSEventListener:
    """Maintains a persistent OBS WebSocket connection on the HA event loop.

    All event processing happens on the event loop — no threads, no futures.
    """

    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        coordinator: "OBSCoordinator",
    ) -> None:
        self._host = host
        self._port = port
        self._password = password
        self._coordinator = coordinator
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle (called from the event loop — no executor needed)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Spawn the background asyncio task."""
        if self._task is not None:
            return
        self._task = asyncio.ensure_future(self._run())
        _LOGGER.debug(
            "OBS event listener task started for %s:%s", self._host, self._port
        )

    async def stop(self) -> None:
        """Cancel and await the background task."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def update_endpoint(self, host: str, port: int) -> None:
        """Hot-swap the endpoint: cancel current task and restart."""
        if host == self._host and port == self._port:
            return
        _LOGGER.debug(
            "OBS event listener endpoint changed to %s:%s – restarting", host, port
        )
        self._host = host
        self._port = port
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.start()

    @property
    def is_connected(self) -> bool:
        return self._task is not None and not self._task.done()

    # ------------------------------------------------------------------
    # Internal async machinery
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Outer loop: connect, listen, reconnect on failure."""
        attempt = 0
        while True:
            try:
                await self._connect_and_listen()
                attempt = 0  # reset on clean exit (shouldn't normally happen)
            except asyncio.CancelledError:
                _LOGGER.debug("OBS event listener task cancelled")
                return
            except Exception as err:
                delay = _BACKOFF[min(attempt, len(_BACKOFF) - 1)]
                if attempt == 0:
                    # First failure — log at ERROR so it's visible without debug mode.
                    _LOGGER.error(
                        "OBS event listener failed to connect to %s:%s (%s) – retrying in %ss",
                        self._host,
                        self._port,
                        err,
                        delay,
                    )
                else:
                    _LOGGER.warning(
                        "OBS event listener disconnected from %s:%s (%s) – reconnecting in %ss",
                        self._host,
                        self._port,
                        err,
                        delay,
                    )
                attempt += 1
                await asyncio.sleep(delay)

    async def _connect_and_listen(self) -> None:
        """Single connection attempt: handshake + event loop."""
        import aiohttp

        url = f"ws://{self._host}:{self._port}"
        _LOGGER.debug("OBS event listener connecting to %s", url)
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                url,
                heartbeat=30,
                receive_timeout=None,
            ) as ws:
                await self._handshake(ws)
                _LOGGER.debug(
                    "OBS event listener connected and identified at %s:%s",
                    self._host,
                    self._port,
                )
                await self._event_loop(ws)
        _LOGGER.debug("OBS event listener WebSocket closed cleanly")

    async def _handshake(self, ws) -> None:
        """Perform the OBS WebSocket v5 Hello/Identify exchange."""
        import aiohttp

        msg = await ws.receive()
        if msg.type not in (
            getattr(aiohttp.WSMsgType, "TEXT", None),
            getattr(aiohttp.WSMsgType, "BINARY", None),
        ):
            raise RuntimeError(f"Unexpected WS msg type during handshake: {msg.type}")

        hello = json.loads(msg.data)
        if hello.get("op") != 0:
            raise RuntimeError(f"Expected Hello (op=0), got op={hello.get('op')}")

        auth_info = hello.get("d", {}).get("authentication")
        auth_str = None
        if auth_info and self._password:
            auth_str = _obs_auth(
                self._password, auth_info["salt"], auth_info["challenge"]
            )

        await ws.send_json(
            {
                "op": 1,
                "d": {
                    "rpcVersion": 1,
                    "authentication": auth_str,
                    "eventSubscriptions": _SUBS,
                },
            }
        )

        ident = await ws.receive_json()
        if ident.get("op") != 2:
            raise RuntimeError(
                f"Expected Identified (op=2), got op={ident.get('op')}"
            )

    async def _event_loop(self, ws) -> None:
        """Read OBS events and dispatch them."""
        import aiohttp

        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    packet = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                if packet.get("op") == 5:  # Event opcode
                    d = packet.get("d", {})
                    self._dispatch(d.get("eventType", ""), d.get("eventData") or {})
            elif msg.type in (
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.ERROR,
            ):
                raise RuntimeError(f"WebSocket closed/error: {msg.type}")

    def _dispatch(self, event_type: str, event_data: dict) -> None:
        """Route an OBS event — all on the event loop, no thread crossing."""
        if event_type in _FAST_EVENTS:
            data = self._coordinator.data
            if data is not None:
                updated = _patch_data(data, event_type, event_data)
                if updated is not None:
                    _LOGGER.debug("OBS fast-path event: %s → state updated", event_type)
                    # Direct call — we ARE on the event loop
                    self._coordinator.async_set_updated_data(updated)
                else:
                    _LOGGER.debug("OBS fast-path event: %s → no-op (state unchanged)", event_type)
            return

        if event_type in _SLOW_EVENTS:
            _LOGGER.debug("OBS slow-path event: %s → triggering full refresh", event_type)
            asyncio.ensure_future(self._coordinator.async_request_refresh())
            return

        _LOGGER.debug("OBS event ignored (not subscribed): %s", event_type)
