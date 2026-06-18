"""OBS Studio WebSocket API client (wraps obsws_python.ReqClient)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .exceptions import OBSAuthError, OBSConnectionError, OBSError, OBSRequestError

_LOGGER = logging.getLogger(__name__)


@dataclass
class OBSData:
    """Complete snapshot of one OBS instance's state."""

    # Version / platform
    obs_version: str | None = None
    obs_websocket_version: str | None = None
    platform: str | None = None
    platform_description: str | None = None

    # Video settings
    base_width: int | None = None
    base_height: int | None = None
    output_width: int | None = None
    output_height: int | None = None
    fps_numerator: int | None = None
    fps_denominator: int | None = None

    # Runtime stats
    cpu_usage: float | None = None
    memory_usage: float | None = None
    available_disk_space: float | None = None
    active_fps: float | None = None
    average_frame_render_time: float | None = None
    render_skipped_frames: int | None = None
    render_total_frames: int | None = None
    output_skipped_frames: int | None = None
    output_total_frames: int | None = None

    # Scene
    current_scene: str | None = None
    scenes: list[str] = field(default_factory=list)

    # Stream
    streaming: bool = False
    stream_timecode: str | None = None
    stream_bytes: int | None = None

    # Record
    recording: bool = False
    recording_paused: bool = False
    record_timecode: str | None = None
    record_bytes: int | None = None

    # Virtual camera
    virtual_cam_active: bool = False

    # Studio mode
    studio_mode_enabled: bool = False

    # Replay buffer
    replay_buffer_active: bool = False


def _safe_get(resp, attr: str, default=None):
    """Safely get an attribute from an obsws_python response object."""
    try:
        return getattr(resp, attr, default)
    except Exception:
        return default


def _classify_error(err: Exception) -> OBSError:
    """Map a low-level exception to one of our domain exceptions."""
    err_str = str(err).lower()
    if any(kw in err_str for kw in ("auth", "password", "4009", "authentication")):
        return OBSAuthError(str(err))
    if any(kw in err_str for kw in ("timeout", "timed out")):
        return OBSConnectionError(f"Timed out connecting to OBS: {err}")
    return OBSConnectionError(str(err))


class OBSClient:
    """Synchronous OBS Studio WebSocket client.

    Wraps obsws_python.ReqClient with lazy connect / auto-reconnect on error.
    All public methods are synchronous and meant to be called via
    hass.async_add_executor_job.
    """

    def __init__(
        self,
        host: str,
        port: int,
        password: str = "",
        timeout: int = 15,
    ) -> None:
        self._host = host
        self._port = port
        self._password = password
        self._timeout = timeout
        self._client = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def update_endpoint(self, host: str, port: int) -> None:
        """Update host/port and drop the current connection so the next call reconnects."""
        if host != self._host or port != self._port:
            _LOGGER.debug("OBS endpoint changed to %s:%s – reconnecting", host, port)
            self._host = host
            self._port = port
            self.disconnect()

    def _ensure_connected(self) -> None:
        """Create a new obsws_python client if we don't have one."""
        if self._client is not None:
            return
        try:
            import obsws_python as obsws

            self._client = obsws.ReqClient(
                host=self._host,
                port=self._port,
                password=self._password,
                timeout=self._timeout,
            )
            _LOGGER.debug("Connected to OBS at %s:%s", self._host, self._port)
        except Exception as err:
            self._client = None
            raise _classify_error(err) from err

    def disconnect(self) -> None:
        """Disconnect from OBS WebSocket."""
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client = None

    def _call(self, method_name: str, *args, **kwargs):
        """Call a method on the inner client, reconnecting once on failure."""
        self._ensure_connected()
        try:
            return getattr(self._client, method_name)(*args, **kwargs)
        except Exception as err:
            # Drop client so we reconnect next time.
            self._client = None
            raise _classify_error(err) from err

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    def fetch_data(self) -> OBSData:
        """Fetch a complete state snapshot from OBS."""
        self._ensure_connected()
        data = OBSData()
        client = self._client

        try:
            ver = client.get_version()
            data.obs_version = _safe_get(ver, "obs_version")
            data.obs_websocket_version = _safe_get(ver, "obs_web_socket_version")
            data.platform = _safe_get(ver, "platform")
            data.platform_description = _safe_get(ver, "platform_description")
        except Exception as err:
            self._client = None
            raise _classify_error(err) from err

        try:
            stats = client.get_stats()
            data.cpu_usage = _safe_get(stats, "cpu_usage")
            data.memory_usage = _safe_get(stats, "memory_usage")
            data.available_disk_space = _safe_get(stats, "available_disk_space")
            data.active_fps = _safe_get(stats, "active_fps")
            data.average_frame_render_time = _safe_get(stats, "average_frame_render_time")
            data.render_skipped_frames = _safe_get(stats, "render_skipped_frames")
            data.render_total_frames = _safe_get(stats, "render_total_frames")
            data.output_skipped_frames = _safe_get(stats, "output_skipped_frames")
            data.output_total_frames = _safe_get(stats, "output_total_frames")
        except Exception as err:
            _LOGGER.warning("Failed to fetch OBS stats: %s", err)

        try:
            video = client.get_video_settings()
            data.base_width = _safe_get(video, "base_width")
            data.base_height = _safe_get(video, "base_height")
            data.output_width = _safe_get(video, "output_width")
            data.output_height = _safe_get(video, "output_height")
            data.fps_numerator = _safe_get(video, "fps_numerator")
            data.fps_denominator = _safe_get(video, "fps_denominator")
        except Exception as err:
            _LOGGER.debug("Failed to fetch OBS video settings: %s", err)

        try:
            scenes = client.get_scene_list()
            data.current_scene = _safe_get(scenes, "current_program_scene_name")
            raw_scenes = _safe_get(scenes, "scenes") or []
            data.scenes = sorted(
                (s.get("sceneName") for s in raw_scenes if s.get("sceneName")),
                key=lambda n: n.lower(),
            )
        except Exception as err:
            _LOGGER.warning("Failed to fetch OBS scene list: %s", err)

        try:
            stream = client.get_stream_status()
            data.streaming = bool(_safe_get(stream, "output_active", False))
            data.stream_timecode = _safe_get(stream, "output_timecode")
            data.stream_bytes = _safe_get(stream, "output_bytes")
        except Exception as err:
            _LOGGER.debug("Failed to fetch OBS stream status: %s", err)

        try:
            record = client.get_record_status()
            data.recording = bool(_safe_get(record, "output_active", False))
            data.recording_paused = bool(_safe_get(record, "output_paused", False))
            data.record_timecode = _safe_get(record, "output_timecode")
            data.record_bytes = _safe_get(record, "output_bytes")
        except Exception as err:
            _LOGGER.debug("Failed to fetch OBS record status: %s", err)

        try:
            vcam = client.get_virtual_cam_status()
            data.virtual_cam_active = bool(_safe_get(vcam, "output_active", False))
        except Exception as err:
            _LOGGER.debug("Failed to fetch OBS virtual cam status: %s", err)

        try:
            studio = client.get_studio_mode_enabled()
            data.studio_mode_enabled = bool(_safe_get(studio, "studio_mode_enabled", False))
        except Exception as err:
            _LOGGER.debug("Failed to fetch OBS studio mode: %s", err)

        try:
            replay = client.get_replay_buffer_status()
            data.replay_buffer_active = bool(_safe_get(replay, "output_active", False))
        except Exception:
            pass  # Replay buffer may not be configured

        return data

    # ------------------------------------------------------------------
    # Scene control
    # ------------------------------------------------------------------

    def set_current_scene(self, scene_name: str) -> None:
        """Switch to a named scene."""
        _LOGGER.debug("OBS set_current_scene → %r", scene_name)
        self._call("set_current_program_scene", scene_name)

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def start_stream(self) -> None:
        _LOGGER.debug("OBS start_stream")
        self._call("start_stream")

    def stop_stream(self) -> None:
        _LOGGER.debug("OBS stop_stream")
        self._call("stop_stream")

    def toggle_stream(self) -> None:
        _LOGGER.debug("OBS toggle_stream")
        self._call("toggle_stream")

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def start_record(self) -> None:
        _LOGGER.debug("OBS start_record")
        self._call("start_record")

    def stop_record(self) -> None:
        _LOGGER.debug("OBS stop_record")
        self._call("stop_record")

    def toggle_record(self) -> None:
        _LOGGER.debug("OBS toggle_record")
        self._call("toggle_record")

    def pause_record(self) -> None:
        _LOGGER.debug("OBS pause_record")
        self._call("pause_record")

    def resume_record(self) -> None:
        _LOGGER.debug("OBS resume_record")
        self._call("resume_record")

    # ------------------------------------------------------------------
    # Virtual camera
    # ------------------------------------------------------------------

    def start_virtual_cam(self) -> None:
        _LOGGER.debug("OBS start_virtual_cam")
        self._call("start_virtual_cam")

    def stop_virtual_cam(self) -> None:
        _LOGGER.debug("OBS stop_virtual_cam")
        self._call("stop_virtual_cam")

    def toggle_virtual_cam(self) -> None:
        _LOGGER.debug("OBS toggle_virtual_cam")
        self._call("toggle_virtual_cam")

    # ------------------------------------------------------------------
    # Studio mode
    # ------------------------------------------------------------------

    def set_studio_mode_enabled(self, enabled: bool) -> None:
        _LOGGER.debug("OBS set_studio_mode_enabled → %s", enabled)
        self._call("set_studio_mode_enabled", enabled)

    # ------------------------------------------------------------------
    # Replay buffer
    # ------------------------------------------------------------------

    def start_replay_buffer(self) -> None:
        _LOGGER.debug("OBS start_replay_buffer")
        self._call("start_replay_buffer")

    def stop_replay_buffer(self) -> None:
        _LOGGER.debug("OBS stop_replay_buffer")
        self._call("stop_replay_buffer")

    def save_replay_buffer(self) -> None:
        _LOGGER.debug("OBS save_replay_buffer")
        self._call("save_replay_buffer")

    # ------------------------------------------------------------------
    # Hotkeys
    # ------------------------------------------------------------------

    def trigger_hotkey(self, hotkey_name: str) -> None:
        _LOGGER.debug("OBS trigger_hotkey %r", hotkey_name)
        self._call("trigger_hot_key_by_name", hotkey_name)

    # ------------------------------------------------------------------
    # Validation helper
    # ------------------------------------------------------------------

    def validate(self) -> OBSData:
        """Connect and do a minimal data fetch; raise on error."""
        data = self.fetch_data()
        self.disconnect()
        return data
