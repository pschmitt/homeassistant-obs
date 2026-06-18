"""OBS Studio real-time event listener.

Keeps a persistent WebSocket connection via obsws_python.EventClient and
triggers coordinator refreshes when OBS state changes occur, giving
near-real-time sensor updates alongside the regular polling cycle.
"""

from __future__ import annotations

import asyncio
import logging

_LOGGER = logging.getLogger(__name__)

# Events that are meaningful to expose in HA.
_INTERESTING_EVENTS = frozenset(
    {
        "CurrentProgramSceneChanged",
        "CurrentPreviewSceneChanged",
        "StreamStateChanged",
        "RecordStateChanged",
        "RecordFileChanged",
        "VirtualcamStateChanged",
        "StudioModeStateChanged",
        "ReplayBufferStateChanged",
        "ReplayBufferSaved",
        "SceneCreated",
        "SceneRemoved",
        "SceneNameChanged",
    }
)


class OBSEventListener:
    """Subscribes to OBS events and fires coordinator refreshes.

    obsws_python.EventClient delivers callbacks from a background thread;
    we bridge them to the HA event loop via asyncio.run_coroutine_threadsafe.
    """

    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        loop: asyncio.AbstractEventLoop,
        refresh_callback,  # async callable (no args) that triggers a coordinator refresh
    ) -> None:
        self._host = host
        self._port = port
        self._password = password
        self._loop = loop
        self._refresh_callback = refresh_callback
        self._client = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_endpoint(self, host: str, port: int) -> None:
        """Update connection info and restart the listener if endpoint changed."""
        if host != self._host or port != self._port:
            self._host = host
            self._port = port
            self.stop()
            self.start()

    def start(self) -> None:
        """Connect the event client (synchronous; runs in executor)."""
        if self._client is not None:
            return
        try:
            import obsws_python as obsws

            cl = obsws.EventClient(
                host=self._host,
                port=self._port,
                password=self._password,
            )
            # Register a catch-all callback; filter by event type inside.
            cl.callback.register(self._on_event)
            self._client = cl
            _LOGGER.debug(
                "OBS event listener connected to %s:%s", self._host, self._port
            )
        except Exception as err:
            _LOGGER.warning(
                "OBS event listener failed to connect to %s:%s: %s",
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

    def _on_event(self, event) -> None:
        """Called by obsws_python from its event thread."""
        event_type = type(event).__name__
        if event_type not in _INTERESTING_EVENTS:
            return
        _LOGGER.debug("OBS event received: %s", event_type)
        # Bridge to the HA async event loop from the obsws_python thread.
        try:
            asyncio.run_coroutine_threadsafe(self._refresh_callback(), self._loop)
        except Exception as err:
            _LOGGER.debug("Failed to schedule coordinator refresh for event %s: %s", event_type, err)
