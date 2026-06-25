"""Services for the OBS Studio integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_set_service_schema

from .const import (
    ATTR_HOTKEY_NAME,
    ATTR_SCENE_NAME,
    DOMAIN,
    SERVICE_PAUSE_RECORD,
    SERVICE_RENDER_TEMPLATES,
    SERVICE_RESUME_RECORD,
    SERVICE_SAVE_REPLAY_BUFFER,
    SERVICE_SET_SCENE,
    SERVICE_START_RECORD,
    SERVICE_START_REPLAY_BUFFER,
    SERVICE_START_STREAM,
    SERVICE_START_VIRTUAL_CAM,
    SERVICE_STOP_RECORD,
    SERVICE_STOP_REPLAY_BUFFER,
    SERVICE_STOP_STREAM,
    SERVICE_STOP_VIRTUAL_CAM,
    SERVICE_TOGGLE_RECORD,
    SERVICE_TOGGLE_STREAM,
    SERVICE_TRIGGER_HOTKEY,
)
from .exceptions import OBSError

_LOGGER = logging.getLogger(__name__)

def _collect_scenes(hass: HomeAssistant) -> list[str]:
    """Return a sorted, deduplicated list of scenes from all loaded OBS entries."""
    scenes: set[str] = set()
    for entry in hass.config_entries.async_entries(DOMAIN):
        # Include entries that are LOADED or still in SETUP_IN_PROGRESS (first refresh done).
        if entry.state not in (ConfigEntryState.LOADED, ConfigEntryState.SETUP_IN_PROGRESS):
            continue
        if entry.runtime_data is None or entry.runtime_data.coordinator.data is None:
            continue
        scenes.update(entry.runtime_data.coordinator.data.scenes)
    return sorted(scenes)


@callback
def async_update_set_scene_options(hass: HomeAssistant) -> None:
    """Push current scene list into the set_scene service description.

    Uses async_set_service_schema so the frontend selector reflects live OBS scenes.
    Call this after a coordinator's first refresh so the dropdown is populated.
    """
    scenes = _collect_scenes(hass)
    _LOGGER.debug("Refreshing set_scene options: %s", scenes)
    async_set_service_schema(
        hass,
        DOMAIN,
        SERVICE_SET_SCENE,
        {
            "name": "Set scene",
            "description": "Switch to a specific scene in OBS Studio.",
            "target": {
                "device": [{"integration": DOMAIN}],
                "entity": [{"integration": DOMAIN}],
            },
            "fields": {
                ATTR_SCENE_NAME: {
                    "name": "Scene name",
                    "description": "Scene to switch to. Available scenes are fetched from OBS at startup.",
                    "required": True,
                    "example": "Main Scene",
                    "selector": {
                        "select": {
                            "options": scenes,
                            "custom_value": True,
                            "mode": "dropdown",
                        }
                    },
                }
            },
        },
    )


def _get_entry(hass: HomeAssistant, call: ServiceCall) -> ConfigEntry:
    """Return the OBS config entry for this service call.

    Resolution order: target entity → target device → first loaded entry.
    """
    target_entity_ids: list[str] = []
    target_device_ids: list[str] = []
    # Newer HA separates target from data; older HA merges them into call.data.
    target_source = call.target if hasattr(call, "target") and call.target else call.data
    raw = target_source.get("entity_id", [])
    if raw:
        target_entity_ids = [raw] if isinstance(raw, str) else list(raw)
    raw = target_source.get("device_id", [])
    if raw:
        target_device_ids = [raw] if isinstance(raw, str) else list(raw)

    if target_entity_ids:
        entity_reg = er.async_get(hass)
        for entity_id in target_entity_ids:
            entity_entry = entity_reg.async_get(entity_id)
            if entity_entry and entity_entry.config_entry_id:
                entry = hass.config_entries.async_get_entry(entity_entry.config_entry_id)
                if entry and entry.domain == DOMAIN and entry.state is ConfigEntryState.LOADED:
                    return entry
        raise ServiceValidationError(
            f"No loaded OBS Studio config entry found for entity {target_entity_ids[0]}"
        )

    if target_device_ids:
        device_reg = dr.async_get(hass)
        for device_id in target_device_ids:
            device_entry = device_reg.async_get(device_id)
            if device_entry:
                for entry_id in device_entry.config_entries:
                    entry = hass.config_entries.async_get_entry(entry_id)
                    if entry and entry.domain == DOMAIN and entry.state is ConfigEntryState.LOADED:
                        return entry
        raise ServiceValidationError(
            f"No loaded OBS Studio config entry found for device {target_device_ids[0]}"
        )

    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    if not entries:
        raise ServiceValidationError("No loaded OBS Studio config entry found")
    if len(entries) > 1:
        _LOGGER.warning(
            "Multiple OBS Studio entries loaded; using '%s'. "
            "Provide a target device or entity to select a specific instance.",
            entries[0].title,
        )
    return entries[0]


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register all OBS Studio services."""

    async def _exec(hass: HomeAssistant, call: ServiceCall, fn_name: str, *args) -> None:
        entry = _get_entry(hass, call)
        client = entry.runtime_data.client
        try:
            await hass.async_add_executor_job(getattr(client, fn_name), *args)
        except OBSError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_set_scene(call: ServiceCall) -> None:
        await _exec(hass, call, "set_current_scene", call.data[ATTR_SCENE_NAME])

    async def handle_start_stream(call: ServiceCall) -> None:
        await _exec(hass, call, "start_stream")

    async def handle_stop_stream(call: ServiceCall) -> None:
        await _exec(hass, call, "stop_stream")

    async def handle_toggle_stream(call: ServiceCall) -> None:
        await _exec(hass, call, "toggle_stream")

    async def handle_start_record(call: ServiceCall) -> None:
        await _exec(hass, call, "start_record")

    async def handle_stop_record(call: ServiceCall) -> None:
        await _exec(hass, call, "stop_record")

    async def handle_toggle_record(call: ServiceCall) -> None:
        await _exec(hass, call, "toggle_record")

    async def handle_pause_record(call: ServiceCall) -> None:
        await _exec(hass, call, "pause_record")

    async def handle_resume_record(call: ServiceCall) -> None:
        await _exec(hass, call, "resume_record")

    async def handle_start_virtual_cam(call: ServiceCall) -> None:
        await _exec(hass, call, "start_virtual_cam")

    async def handle_stop_virtual_cam(call: ServiceCall) -> None:
        await _exec(hass, call, "stop_virtual_cam")

    async def handle_start_replay_buffer(call: ServiceCall) -> None:
        await _exec(hass, call, "start_replay_buffer")

    async def handle_stop_replay_buffer(call: ServiceCall) -> None:
        await _exec(hass, call, "stop_replay_buffer")

    async def handle_save_replay_buffer(call: ServiceCall) -> None:
        await _exec(hass, call, "save_replay_buffer")

    async def handle_trigger_hotkey(call: ServiceCall) -> None:
        await _exec(hass, call, "trigger_hotkey", call.data[ATTR_HOTKEY_NAME])

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SCENE,
        handle_set_scene,
        schema=vol.Schema({vol.Required(ATTR_SCENE_NAME): cv.string}, extra=vol.ALLOW_EXTRA),
    )
    for name, handler in [
        (SERVICE_START_STREAM, handle_start_stream),
        (SERVICE_STOP_STREAM, handle_stop_stream),
        (SERVICE_TOGGLE_STREAM, handle_toggle_stream),
        (SERVICE_START_RECORD, handle_start_record),
        (SERVICE_STOP_RECORD, handle_stop_record),
        (SERVICE_TOGGLE_RECORD, handle_toggle_record),
        (SERVICE_PAUSE_RECORD, handle_pause_record),
        (SERVICE_RESUME_RECORD, handle_resume_record),
        (SERVICE_START_VIRTUAL_CAM, handle_start_virtual_cam),
        (SERVICE_STOP_VIRTUAL_CAM, handle_stop_virtual_cam),
        (SERVICE_START_REPLAY_BUFFER, handle_start_replay_buffer),
        (SERVICE_STOP_REPLAY_BUFFER, handle_stop_replay_buffer),
        (SERVICE_SAVE_REPLAY_BUFFER, handle_save_replay_buffer),
    ]:
        hass.services.async_register(DOMAIN, name, handler, schema=vol.Schema({}, extra=vol.ALLOW_EXTRA))

    hass.services.async_register(
        DOMAIN,
        SERVICE_TRIGGER_HOTKEY,
        handle_trigger_hotkey,
        schema=vol.Schema({vol.Required(ATTR_HOTKEY_NAME): cv.string}, extra=vol.ALLOW_EXTRA),
    )

    async def handle_render_templates(call: ServiceCall) -> None:
        entry = _get_entry(hass, call)
        runtime = entry.runtime_data
        if runtime.coordinator.data is None:
            raise HomeAssistantError(
                "OBS coordinator has no data yet — is OBS connected?"
            )
        raw = call.data.get("name")
        name_filter: set[str] | None = None
        if raw is not None:
            name_filter = {raw} if isinstance(raw, str) else set(raw)
        await runtime.renderer.async_render_all(runtime.coordinator.data, name_filter=name_filter)

    hass.services.async_register(
        DOMAIN,
        SERVICE_RENDER_TEMPLATES,
        handle_render_templates,
        schema=vol.Schema(
            {vol.Optional("name"): vol.Any(cv.string, [cv.string])},
            extra=vol.ALLOW_EXTRA,
        ),
    )
