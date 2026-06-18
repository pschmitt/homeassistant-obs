"""Sensors for OBS Studio."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfDataRate, UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import OBSConfigEntry
from .api import OBSData
from .coordinator import OBSCoordinator
from .entity import OBSEntity


@dataclass(frozen=True, kw_only=True)
class OBSSensorDescription(SensorEntityDescription):
    """Extends SensorEntityDescription with an OBSData accessor."""

    value_fn: Any = None  # Callable[[OBSData], Any]


SENSORS: tuple[OBSSensorDescription, ...] = (
    OBSSensorDescription(
        key="current_scene",
        name="Current scene",
        icon="mdi:television-play",
        value_fn=lambda d: d.current_scene,
    ),
    OBSSensorDescription(
        key="cpu_usage",
        name="CPU usage",
        icon="mdi:cpu-64-bit",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: round(d.cpu_usage, 2) if d.cpu_usage is not None else None,
    ),
    OBSSensorDescription(
        key="memory_usage",
        name="Memory usage",
        icon="mdi:memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: round(d.memory_usage, 1) if d.memory_usage is not None else None,
    ),
    OBSSensorDescription(
        key="available_disk_space",
        name="Available disk space",
        icon="mdi:harddisk",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: round(d.available_disk_space, 0) if d.available_disk_space is not None else None,
    ),
    OBSSensorDescription(
        key="active_fps",
        name="Active FPS",
        icon="mdi:speedometer",
        native_unit_of_measurement="fps",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: round(d.active_fps, 2) if d.active_fps is not None else None,
    ),
    OBSSensorDescription(
        key="render_skipped_frames",
        name="Render skipped frames",
        icon="mdi:filmstrip-off",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.render_skipped_frames,
    ),
    OBSSensorDescription(
        key="output_skipped_frames",
        name="Output skipped frames",
        icon="mdi:filmstrip-off",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.output_skipped_frames,
    ),
    OBSSensorDescription(
        key="stream_timecode",
        name="Stream duration",
        icon="mdi:timer-play",
        value_fn=lambda d: d.stream_timecode if d.streaming else None,
    ),
    OBSSensorDescription(
        key="record_timecode",
        name="Record duration",
        icon="mdi:timer-record",
        value_fn=lambda d: d.record_timecode if d.recording else None,
    ),
    OBSSensorDescription(
        key="obs_version",
        name="OBS version",
        icon="mdi:information-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.obs_version,
    ),
    OBSSensorDescription(
        key="platform",
        name="Platform",
        icon="mdi:desktop-tower",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.platform,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OBSConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = config_entry.runtime_data.coordinator
    async_add_entities(OBSSensor(coordinator, desc) for desc in SENSORS)


class OBSSensor(OBSEntity, SensorEntity):
    """A sensor derived from OBS state data."""

    entity_description: OBSSensorDescription

    def __init__(self, coordinator: OBSCoordinator, description: OBSSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
