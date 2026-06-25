"""HTML template renderer for OBS Studio overlays."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import template as template_helper

from .const import (
    CONF_TEMPLATE_CONTENT,
    CONF_TEMPLATE_FILE_PATH,
    CONF_TEMPLATE_FROM_FILE,
    CONF_TEMPLATE_NAME,
    CONF_TEMPLATE_OUTPUT_DIR,
    CONF_TEMPLATES,
    DEFAULT_TEMPLATE_OUTPUT_DIR,
    DEFAULT_TEMPLATE_SOURCE_DIR,
)

if TYPE_CHECKING:
    from .api import OBSData

_LOGGER = logging.getLogger(__name__)


class OBSTemplateRenderer:
    """Renders Jinja2 HTML templates with OBS state and writes them to www/obs-studio/.

    Templates are sourced from two places (merged, inline wins on name+output_dir collision):
    - File-based: *.html.j2 files in the default output directory, auto-discovered.
    - Inline: templates defined in the integration options flow (content or file path).
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self.hass = hass
        self.config_entry = config_entry
        self._auto_dir = Path(DEFAULT_TEMPLATE_SOURCE_DIR)

    def _scan_file_templates(self) -> list[tuple[str, str]]:
        """Blocking: scan default output dir for *.html.j2 files. Returns (name, content) pairs."""
        if not self._auto_dir.is_dir():
            return []
        result = []
        for path in sorted(self._auto_dir.glob("*.html.j2")):
            try:
                content = path.read_text("utf-8")
                name = path.name.removesuffix(".html.j2")
                result.append((name, content))
                _LOGGER.debug("OBS overlay: found file template %s → %s.html", path.name, name)
            except OSError:
                _LOGGER.warning("OBS overlay: could not read template file %s", path)
        return result

    def _read_file(self, file_path: str) -> str | None:
        """Blocking: read template content from the given path."""
        try:
            content = Path(file_path).read_text("utf-8")
            _LOGGER.debug("OBS overlay: read file-source template %s", file_path)
            return content
        except OSError:
            _LOGGER.warning("OBS overlay: could not read template source file %s", file_path)
            return None

    async def async_render_all(
        self,
        obs_data: OBSData,
        name_filter: set[str] | None = None,
    ) -> None:
        # Phase 1: auto-discovered *.html.j2 → default output dir
        templates: dict[tuple[str, str], str] = {}  # (name, output_dir) -> content
        for name, content in await self.hass.async_add_executor_job(self._scan_file_templates):
            templates[(name, DEFAULT_TEMPLATE_OUTPUT_DIR)] = content

        # Phase 2: inline / file-sourced templates from options (override auto by name+dir)
        for tpl_def in self.config_entry.options.get(CONF_TEMPLATES, []):
            name: str = tpl_def.get(CONF_TEMPLATE_NAME, "").strip()
            out_dir: str = (
                tpl_def.get(CONF_TEMPLATE_OUTPUT_DIR) or DEFAULT_TEMPLATE_OUTPUT_DIR
            ).strip()
            if not name:
                continue
            if tpl_def.get(CONF_TEMPLATE_FROM_FILE):
                file_path: str = tpl_def.get(CONF_TEMPLATE_FILE_PATH, "").strip()
                if not file_path:
                    continue
                content = await self.hass.async_add_executor_job(self._read_file, file_path)
                if content is None:
                    continue
            else:
                content = tpl_def.get(CONF_TEMPLATE_CONTENT, "")
                if not content:
                    continue
            templates[(name, out_dir)] = content

        if name_filter is not None:
            templates = {k: v for k, v in templates.items() if k[0] in name_filter}

        if not templates:
            return

        # Phase 3: ensure all required output dirs exist
        for out_dir in {d for _, d in templates}:
            await self.hass.async_add_executor_job(Path(out_dir).mkdir, 0o755, True, True)

        # Phase 4: render and write
        obs_vars = {
            "obs_scene": obs_data.current_scene,
            "obs_streaming": obs_data.streaming,
            "obs_recording": obs_data.recording,
            "obs_fps": obs_data.active_fps,
            "obs_cpu": obs_data.cpu_usage,
            "obs_mem": obs_data.memory_usage,
        }

        for (name, out_dir), content in templates.items():
            try:
                tpl = template_helper.Template(content, self.hass)
                html: str = tpl.async_render(variables=obs_vars, parse_result=False)
            except Exception:
                _LOGGER.exception("OBS overlay: failed to render template %r", name)
                continue

            out = Path(out_dir) / f"{name}.html"
            try:
                await self.hass.async_add_executor_job(out.write_text, html, "utf-8")
                _LOGGER.debug("OBS overlay: wrote %s", out)
            except OSError:
                _LOGGER.exception("OBS overlay: failed to write %s", out)
