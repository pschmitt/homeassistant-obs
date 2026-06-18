"""Switch entities for OBS Studio."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OBSConfigEntry
from .api import OBSClient, OBSData
from .coordinator import OBSCoordinator
from .entity import OBSEntity
from .exceptions import OBSError

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class OBSSwitchDescription(SwitchEntityDescription):
    is_on_fn: Any = None   # Callable[[OBSData], bool]
    turn_on_fn: Any = None   # Callable[[OBSClient], None]
    turn_off_fn: Any = None  # Callable[[OBSClient], None]


SWITCHES: tuple[OBSSwitchDescription, ...] = (
    OBSSwitchDescription(
        key="virtual_camera",
        name="Virtual camera",
        icon="mdi:camera-outline",
        is_on_fn=lambda d: d.virtual_cam_active,
        turn_on_fn=lambda c: c.start_virtual_cam(),
        turn_off_fn=lambda c: c.stop_virtual_cam(),
    ),
    OBSSwitchDescription(
        key="studio_mode",
        name="Studio mode",
        icon="mdi:monitor-eye",
        is_on_fn=lambda d: d.studio_mode_enabled,
        turn_on_fn=lambda c: c.set_studio_mode_enabled(True),
        turn_off_fn=lambda c: c.set_studio_mode_enabled(False),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OBSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = config_entry.runtime_data.coordinator
    async_add_entities(OBSSwitch(coordinator, desc) for desc in SWITCHES)


class OBSSwitch(OBSEntity, SwitchEntity):
    """A switch that controls an OBS feature."""

    entity_description: OBSSwitchDescription

    def __init__(self, coordinator: OBSCoordinator, description: OBSSwitchDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.is_on_fn(self.coordinator.data)

    async def _async_set(self, enabled: bool) -> None:
        desc = self.entity_description
        fn = desc.turn_on_fn if enabled else desc.turn_off_fn
        try:
            await self.hass.async_add_executor_job(fn, self.coordinator.client)
        except OBSError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)
