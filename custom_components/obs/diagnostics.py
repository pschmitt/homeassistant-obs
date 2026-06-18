"""Diagnostics support for OBS Studio."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import OBSConfigEntry
from .const import CONF_WS_PASSWORD

TO_REDACT = {CONF_WS_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: OBSConfigEntry,
) -> dict[str, Any]:
    coordinator = config_entry.runtime_data.coordinator
    return {
        "entry": {
            "title": config_entry.title,
            "data": async_redact_data(dict(config_entry.data), TO_REDACT),
            "options": dict(config_entry.options),
        },
        "data": asdict(coordinator.data) if coordinator.data else None,
        "ssh_tunnel": {
            "active": config_entry.runtime_data.ssh_tunnel is not None,
            "alive": (
                config_entry.runtime_data.ssh_tunnel.is_alive
                if config_entry.runtime_data.ssh_tunnel
                else None
            ),
            "local_port": (
                config_entry.runtime_data.ssh_tunnel.local_port
                if config_entry.runtime_data.ssh_tunnel
                else None
            ),
        },
    }
