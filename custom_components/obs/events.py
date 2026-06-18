"""OBS Studio real-time event listener with fast-path state patching.

obsws_python's Callback.trigger() dispatches only to functions whose __name__
matches on_<snake_case_event>.  We bypass that by monkey-patching
callback.trigger with a plain closure that feeds all events into our single
_on_event handler.

For known events (scene change, stream/record/vcam/studio/replay state) we
patch the coordinator's OBSData in-place and call async_set_updated_data() —
zero network I/O, entities update in milliseconds.

For events that change the scene list we fall back to a full coordinator
refresh (async_request_refresh), which re-fetches everything over the wire.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .coordinator import OBSCoordinator

_LOGGER = logging.getLogger(__name__)

# Events handled inline by patching coordinator data (fast path).
_FAST_EVENTS: frozenset[str] = frozenset(
    {
        "CurrentProgramSceneChanged",
        "CurrentPreviewSceneChanged",  # not tracked — no-op, but don't slow-path it
        "StreamStateChanged",
        "RecordStateChanged",
        "VirtualcamStateChanged",
        "StudioModeStateChanged",
        "ReplayBufferStateChanged",
        "ReplayBufferSaved",  # informational — no state change needed
    }
)

# Events that require a full re-fetch (scene list isn't in the payload).
_SLOW_EVENTS: frozenset[str] = frozenset(
    {
        "SceneCreated",
        "SceneRemoved",
        "SceneNameChanged",
    }
)


def _safe(event, attr, default=None):
    return getattr(event, attr, default)


def _patch_data(data, event_type: str, event):
    """Return an updated OBSData copy from the event payload, or None if no-op."""
    if event_type == "CurrentProgramSceneChanged":
        scene = _safe(event, "scene_name")
        if scene is None or scene == data.current_scene:
            return None
        return dataclasses.replace(data, current_scene=scene)

    if event_type == "StreamStateChanged":
        active = bool(_safe(event, "output_active", data.streaming))
        if active == data.streaming:
            return None
        return dataclasses.replace(data, streaming=active)

    if event_type == "RecordStateChanged":
        active = bool(_safe(event, "output_active", data.recording))
        # outputState is e.g. "OBS_WEBSOCKET_OUTPUT_PAUSED" when paused.
        state_str = _safe(event, "output_state", "")
        paused = state_str == "OBS_WEBSOCKET_OUTPUT_PAUSED"
        if active == data.recording and paused == data.recording_paused:
            return None
        return dataclasses.replace(data, recording=active, recording_paused=paused)

    if event_type == "VirtualcamStateChanged":
        active = bool(_safe(event, "output_active", data.virtual_cam_active))
        if active == data.virtual_cam_active:
            return None
        return dataclasses.replace(data, virtual_cam_active=active)

    if event_type == "StudioModeStateChanged":
        enabled = bool(_safe(event, "studio_mode_enabled", data.studio_mode_enabled))
        if enabled == data.studio_mode_enabled:
            return None
        return dataclasses.replace(data, studio_mode_enabled=enabled)

    if event_type == "ReplayBufferStateChanged":
        active = bool(_safe(event, "output_active", data.replay_buffer_active))
        if active == data.replay_buffer_active:
            return None
        return dataclasses.replace(data, replay_buffer_active=active)

    return None  # no-op (ReplayBufferSaved, CurrentPreviewSceneChanged, etc.)


class OBSEventListener:
    """Subscribes to OBS WebSocket events and updates coordinator state inline.

    obsws_python.EventClient delivers events in a background thread; we bridge
    back to the HA event loop via asyncio.run_coroutine_threadsafe.
    """

    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        loop: asyncio.AbstractEventLoop,
        coordinator: "OBSCoordinator",
    ) -> None:
        self._host = host
        self._port = port
        self._password = password
        self._loop = loop
        self._coordinator = coordinator
        self._client = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_endpoint(self, host: str, port: int) -> None:
        """Update host/port and restart the listener if the endpoint changed."""
        if host == self._host and port == self._port:
            return
        _LOGGER.debug(
            "OBS event listener endpoint changed to %s:%s – reconnecting", host, port
        )
        self._host = host
        self._port = port
        self.stop()
        self.start()

    def start(self) -> None:
        """Connect the event client (synchronous; call via async_add_executor_job)."""
        if self._client is not None:
            return
        try:
            import obsws_python as obsws
            from obsws_python.util import as_dataclass

            cl = obsws.EventClient(
                host=self._host,
                port=self._port,
                password=self._password,
            )

            # obsws_python's Callback.trigger() dispatches only to functions
            # whose __name__ matches on_<snake_case_event>.  Monkey-patch it
            # with a closure that forwards every event to our handler instead.
            def _dispatch(event_type, data):
                event_obj = as_dataclass(event_type, data) if data else None
                self._on_event(event_type, event_obj)

            cl.callback.trigger = _dispatch
            self._client = cl
            _LOGGER.debug(
                "OBS event listener connected to %s:%s", self._host, self._port
            )
        except Exception as err:
            _LOGGER.warning(
                "OBS event listener failed to connect to %s:%s – events disabled: %s",
                self._host,
                self._port,
                err,
            )
            self._client = None

    def stop(self) -> None:
        """Disconnect the event client."""
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_event(self, event_type: str, event) -> None:
        """Called from the obsws_python background thread for every OBS event."""
        if event_type in _FAST_EVENTS:
            data = self._coordinator.data
            if data is not None:
                updated = _patch_data(data, event_type, event)
                if updated is not None:
                    _LOGGER.debug("OBS fast-path event: %s", event_type)
                    asyncio.run_coroutine_threadsafe(
                        self._async_set_data(updated), self._loop
                    )
            return

        if event_type in _SLOW_EVENTS:
            _LOGGER.debug("OBS slow-path event: %s (full refresh)", event_type)
            asyncio.run_coroutine_threadsafe(
                self._coordinator.async_request_refresh(), self._loop
            )

    async def _async_set_data(self, data) -> None:
        self._coordinator.async_set_updated_data(data)
