"""Binary sensors for OBS Studio."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OBSConfigEntry
from .api import OBSData
from .coordinator import OBSCoordinator
from .entity import OBSEntity


@dataclass(frozen=True, kw_only=True)
class OBSBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Any = None  # Callable[[OBSData], bool | None]


BINARY_SENSORS: tuple[OBSBinarySensorDescription, ...] = (
    OBSBinarySensorDescription(
        key="streaming",
        name="Streaming",
        icon="mdi:video-wireless",
        value_fn=lambda d: d.streaming,
    ),
    OBSBinarySensorDescription(
        key="recording",
        name="Recording",
        icon="mdi:record-circle",
        value_fn=lambda d: d.recording,
    ),
    OBSBinarySensorDescription(
        key="recording_paused",
        name="Recording paused",
        icon="mdi:pause-circle",
        value_fn=lambda d: d.recording_paused,
    ),
    OBSBinarySensorDescription(
        key="virtual_cam_active",
        name="Virtual camera",
        icon="mdi:camera-outline",
        value_fn=lambda d: d.virtual_cam_active,
    ),
    OBSBinarySensorDescription(
        key="studio_mode_enabled",
        name="Studio mode",
        icon="mdi:monitor-eye",
        value_fn=lambda d: d.studio_mode_enabled,
    ),
    OBSBinarySensorDescription(
        key="replay_buffer_active",
        name="Replay buffer",
        icon="mdi:replay",
        value_fn=lambda d: d.replay_buffer_active,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OBSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = config_entry.runtime_data.coordinator
    async_add_entities(OBSBinarySensor(coordinator, desc) for desc in BINARY_SENSORS)


class OBSBinarySensor(OBSEntity, BinarySensorEntity):
    """A binary sensor derived from OBS state data."""

    entity_description: OBSBinarySensorDescription

    def __init__(
        self,
        coordinator: OBSCoordinator,
        description: OBSBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
