"""Services for the OBS Studio integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_HOTKEY_NAME,
    ATTR_SCENE_NAME,
    DOMAIN,
    SERVICE_PAUSE_RECORD,
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


def _get_entry(hass: HomeAssistant) -> ConfigEntry:
    """Return the first loaded OBS config entry, or raise ServiceValidationError."""
    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    if not entries:
        raise ServiceValidationError("No loaded OBS config entry found")
    if len(entries) > 1:
        _LOGGER.warning(
            "Multiple OBS entries loaded; using the first one (%s)", entries[0].title
        )
    return entries[0]


def _client(hass: HomeAssistant):
    return _get_entry(hass).runtime_data.client


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register all OBS services."""

    async def _exec(hass: HomeAssistant, call: ServiceCall, fn_name: str, *args) -> None:
        client = _client(hass)
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
        schema=vol.Schema({vol.Required(ATTR_SCENE_NAME): cv.string}),
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
        hass.services.async_register(DOMAIN, name, handler, schema=vol.Schema({}))

    hass.services.async_register(
        DOMAIN,
        SERVICE_TRIGGER_HOTKEY,
        handle_trigger_hotkey,
        schema=vol.Schema({vol.Required(ATTR_HOTKEY_NAME): cv.string}),
    )
