"""File modification poller for OBS template source files."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_TEMPLATE_FILE_PATH,
    CONF_TEMPLATE_FROM_FILE,
    CONF_TEMPLATES,
    DEFAULT_TEMPLATE_SOURCE_DIR,
)

if TYPE_CHECKING:
    from .coordinator import OBSCoordinator
    from .template_renderer import OBSTemplateRenderer

_LOGGER = logging.getLogger(__name__)
_POLL_INTERVAL = 1.0  # seconds between stat() checks


class OBSFileWatcher:
    """Polls template source files for modification and triggers re-render on change.

    Uses asyncio polling rather than inotify/watchdog so it works reliably in all
    environments: VMs, containers, SSHFS mounts, and network filesystems.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: OBSCoordinator,
        renderer: OBSTemplateRenderer,
        config_entry: ConfigEntry,
    ) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._renderer = renderer
        self._config_entry = config_entry
        self._task: asyncio.Task | None = None
        self._mtimes: dict[str, float] = {}

    def _tracked_files(self) -> list[str]:
        """Return all file paths to poll."""
        files: list[str] = []
        # Auto-discovered source directory: watch all *.html.j2 files
        src_dir = Path(DEFAULT_TEMPLATE_SOURCE_DIR)
        if src_dir.is_dir():
            files.extend(str(p) for p in src_dir.glob("*.html.j2"))
        # Registered file-source templates
        for tpl in self._config_entry.options.get(CONF_TEMPLATES, []):
            if tpl.get(CONF_TEMPLATE_FROM_FILE):
                fp = tpl.get(CONF_TEMPLATE_FILE_PATH, "").strip()
                if fp and fp not in files:
                    files.append(fp)
        return files

    def _check_modifications(self) -> list[str]:
        """Blocking: stat() all tracked files, return paths that changed."""
        changed: list[str] = []
        for path_str in self._tracked_files():
            try:
                mtime = Path(path_str).stat().st_mtime
            except OSError:
                continue
            prev = self._mtimes.get(path_str)
            self._mtimes[path_str] = mtime
            if prev is not None and prev != mtime:
                changed.append(path_str)
        return changed

    async def _poll_loop(self) -> None:
        _LOGGER.debug("OBS file watcher: polling started (interval %.1fs)", _POLL_INTERVAL)
        # Seed mtimes without triggering on first pass
        await self._hass.async_add_executor_job(self._check_modifications)
        while True:
            await asyncio.sleep(_POLL_INTERVAL)
            changed = await self._hass.async_add_executor_job(self._check_modifications)
            if changed:
                _LOGGER.warning(
                    "OBS file watcher: change detected in %s — re-rendering",
                    [Path(p).name for p in changed],
                )
                if self._coordinator.data is not None:
                    await self._renderer.async_render_all(self._coordinator.data)

    def start(self) -> None:
        """Start the polling loop as a background task."""
        self._task = self._hass.async_create_background_task(
            self._poll_loop(),
            name="obs_studio_file_watcher",
        )

    def stop(self) -> None:
        """Cancel the polling task."""
        if self._task is not None:
            self._task.cancel()
            self._task = None
            _LOGGER.debug("OBS file watcher: stopped")
