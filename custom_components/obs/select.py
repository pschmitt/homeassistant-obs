"""Scene selector entity for OBS Studio."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OBSConfigEntry
from .coordinator import OBSCoordinator
from .entity import OBSEntity
from .exceptions import OBSError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OBSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([OBSSceneSelect(config_entry.runtime_data.coordinator)])


class OBSSceneSelect(OBSEntity, SelectEntity):
    """Select entity for switching OBS scenes."""

    _attr_name = "Scene"
    _attr_icon = "mdi:monitor-screenshot"

    def __init__(self, coordinator: OBSCoordinator) -> None:
        super().__init__(coordinator, "scene")

    @property
    def options(self) -> list[str]:
        if self.coordinator.data is None:
            return []
        return self.coordinator.data.scenes or []

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.current_scene

    async def async_select_option(self, option: str) -> None:
        try:
            await self.hass.async_add_executor_job(
                self.coordinator.client.set_current_scene, option
            )
        except OBSError as err:
            raise HomeAssistantError(f"Failed to switch OBS scene: {err}") from err

        # Optimistic update
        if self.coordinator.data is not None:
            self.coordinator.data.current_scene = option
            self.coordinator.async_set_updated_data(self.coordinator.data)
        await self.coordinator.async_request_refresh()
