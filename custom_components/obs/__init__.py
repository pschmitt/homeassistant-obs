"""The OBS Studio integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .api import OBSClient
from .const import (
    CONF_OBS_REMOTE_HOST,
    CONF_SSH_ENABLED,
    CONF_SSH_HOST,
    CONF_SSH_KEY_CONTENT,
    CONF_SSH_KEY_PATH,
    CONF_SSH_KNOWN_HOSTS,
    CONF_SSH_PORT,
    CONF_SSH_USERNAME,
    CONF_WS_PASSWORD,
    CONF_WS_PORT,
    DEFAULT_OBS_REMOTE_HOST,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_SSH_ENABLED,
    DEFAULT_SSH_KEY_PATH,
    DEFAULT_SSH_PORT,
    DEFAULT_SSH_USERNAME,
    DEFAULT_WS_PORT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import OBSCoordinator
from .events import OBSEventListener
from .services import async_setup_services
from .ssh_tunnel import OBSSSHTunnel

_LOGGER = logging.getLogger(__name__)


@dataclass
class OBSRuntimeData:
    """Runtime data stored on the config entry."""

    client: OBSClient
    coordinator: OBSCoordinator
    ssh_tunnel: OBSSSHTunnel | None
    event_listener: OBSEventListener | None


type OBSConfigEntry = ConfigEntry[OBSRuntimeData]


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate config entry to current schema version.

    v1 → v2: rename device title from "{name} OBS" to "OBS Studio {name}" and
    update entity IDs in the entity registry to match (old prefix → new prefix).
    """
    current_version = config_entry.version
    _LOGGER.debug(
        "Migrating OBS config entry %s from version %s",
        config_entry.entry_id,
        current_version,
    )

    if current_version < 2:
        old_title = config_entry.title
        # Derive a clean hostname: strip trailing " OBS" suffix if present.
        hostname = old_title.removesuffix(" OBS").strip()
        new_title = f"OBS Studio {hostname}"

        old_slug = slugify(old_title)   # e.g. "ge2_obs"
        new_slug = slugify(new_title)   # e.g. "obs_studio_ge2"

        _LOGGER.info(
            "OBS migration v1→v2: renaming '%s' → '%s' (entity prefix %s → %s)",
            old_title,
            new_title,
            old_slug,
            new_slug,
        )

        # Rename entity IDs in the registry so automations can be updated.
        entity_reg = er.async_get(hass)
        for entity_entry in list(entity_reg.entities.values()):
            if entity_entry.config_entry_id != config_entry.entry_id:
                continue
            old_eid = entity_entry.entity_id          # e.g. "select.ge2_obs_scene"
            domain, rest = old_eid.split(".", 1)      # "select", "ge2_obs_scene"
            prefix = old_slug + "_"
            if not rest.startswith(prefix):
                continue
            suffix = rest[len(prefix):]               # "scene"
            new_eid = f"{domain}.{new_slug}_{suffix}" # "select.obs_studio_ge2_scene"
            _LOGGER.debug("  renaming entity %s → %s", old_eid, new_eid)
            entity_reg.async_update_entity(old_eid, new_entity_id=new_eid)

        hass.config_entries.async_update_entry(
            config_entry, title=new_title, version=2
        )

    return True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: OBSConfigEntry) -> bool:
    """Set up OBS Studio from a config entry."""
    _LOGGER.debug(
        "Setting up OBS Studio entry '%s' (%s)",
        config_entry.title,
        config_entry.entry_id,
    )

    ssh_tunnel: OBSSSHTunnel | None = None
    ws_host: str = config_entry.data[CONF_HOST]
    ws_port: int = config_entry.data.get(CONF_WS_PORT, DEFAULT_WS_PORT)

    if config_entry.data.get(CONF_SSH_ENABLED, DEFAULT_SSH_ENABLED):
        ssh_host = config_entry.data.get(CONF_SSH_HOST) or ws_host
        _LOGGER.debug(
            "OBS SSH tunnel: %s → %s:%s",
            ssh_host,
            config_entry.data.get(CONF_OBS_REMOTE_HOST, DEFAULT_OBS_REMOTE_HOST),
            ws_port,
        )
        ssh_tunnel = OBSSSHTunnel(
            ssh_host=ssh_host,
            ssh_port=config_entry.data.get(CONF_SSH_PORT, DEFAULT_SSH_PORT),
            ssh_username=config_entry.data.get(CONF_SSH_USERNAME, DEFAULT_SSH_USERNAME),
            ssh_key_path=config_entry.data.get(CONF_SSH_KEY_PATH) or DEFAULT_SSH_KEY_PATH,
            ssh_key_content=config_entry.data.get(CONF_SSH_KEY_CONTENT) or None,
            ssh_known_hosts=config_entry.data.get(CONF_SSH_KNOWN_HOSTS) or None,
            obs_remote_host=config_entry.data.get(CONF_OBS_REMOTE_HOST, DEFAULT_OBS_REMOTE_HOST),
            obs_remote_port=ws_port,
        )
        local_port = await ssh_tunnel.async_start()
        ws_host = "127.0.0.1"
        ws_port = local_port
        _LOGGER.debug("OBS SSH tunnel ready on 127.0.0.1:%s", local_port)

    password = config_entry.data.get(CONF_WS_PASSWORD, "")

    client = OBSClient(
        host=ws_host,
        port=ws_port,
        password=password,
        timeout=DEFAULT_REQUEST_TIMEOUT,
    )

    coordinator = OBSCoordinator(
        hass,
        config_entry,
        client,
        ssh_tunnel=ssh_tunnel,
    )
    await coordinator.async_config_entry_first_refresh()

    # Start real-time event listener (best-effort; polling still works without it).
    event_listener = OBSEventListener(
        host=ws_host,
        port=ws_port,
        password=password,
        coordinator=coordinator,
    )
    event_listener.start()  # spawns an asyncio task — no executor needed
    coordinator.event_listener = event_listener
    _LOGGER.debug(
        "OBS event listener started for %s:%s", ws_host, ws_port
    )

    config_entry.runtime_data = OBSRuntimeData(
        client=client,
        coordinator=coordinator,
        ssh_tunnel=ssh_tunnel,
        event_listener=event_listener,
    )

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    config_entry.async_on_unload(config_entry.add_update_listener(_async_update_listener))
    _LOGGER.debug("OBS Studio entry '%s' setup complete", config_entry.title)
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: OBSConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading OBS Studio entry '%s'", config_entry.title)
    runtime: OBSRuntimeData = config_entry.runtime_data
    ok = await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
    if ok:
        if runtime.event_listener is not None:
            _LOGGER.debug("Stopping OBS event listener")
            await runtime.event_listener.stop()
        await hass.async_add_executor_job(runtime.client.disconnect)
        if runtime.ssh_tunnel is not None:
            _LOGGER.debug("Stopping OBS SSH tunnel")
            await runtime.ssh_tunnel.async_stop()
    return ok


async def _async_update_listener(hass: HomeAssistant, config_entry: OBSConfigEntry) -> None:
    await hass.config_entries.async_reload(config_entry.entry_id)
