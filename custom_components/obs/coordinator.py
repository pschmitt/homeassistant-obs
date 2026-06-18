"""Data update coordinator for OBS Studio."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from typing import TYPE_CHECKING

from .api import OBSClient, OBSData
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, REPAIR_AUTH_FAILED, REPAIR_CANNOT_CONNECT, REPAIR_SSH_FAILED
from .exceptions import OBSAuthError, OBSConnectionError, OBSSSHError

if TYPE_CHECKING:
    from .events import OBSEventListener

_LOGGER = logging.getLogger(__name__)


class OBSCoordinator(DataUpdateCoordinator[OBSData]):
    """Poll OBS Studio for state on a fixed interval.

    When SSH tunnelling is in use the coordinator keeps the tunnel alive and
    updates the client endpoint whenever the tunnel restarts on a new port.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: OBSClient,
        ssh_tunnel=None,  # OBSSSHTunnel | None
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN}_{config_entry.entry_id}",
            update_interval=timedelta(
                seconds=config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self._ssh_tunnel = ssh_tunnel
        self.event_listener: OBSEventListener | None = None

    async def _async_update_data(self) -> OBSData:
        entry_id = self.config_entry.entry_id
        title = self.config_entry.title

        # Keep SSH tunnel alive and sync the client endpoint.
        if self._ssh_tunnel is not None:
            try:
                local_port = await self._ssh_tunnel.async_ensure_alive()
                prev_port = self.client._port
                self.client.update_endpoint("127.0.0.1", local_port)
                if local_port != prev_port and self.event_listener is not None:
                    self.event_listener.update_endpoint("127.0.0.1", local_port)
                ir.async_delete_issue(self.hass, DOMAIN, f"{REPAIR_SSH_FAILED}_{entry_id}")
            except OBSSSHError as err:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    f"{REPAIR_SSH_FAILED}_{entry_id}",
                    is_fixable=False,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key=REPAIR_SSH_FAILED,
                    translation_placeholders={"name": title},
                )
                raise UpdateFailed(f"SSH tunnel failure for {title}: {err}") from err

        try:
            data: OBSData = await self.hass.async_add_executor_job(self.client.fetch_data)
        except OBSAuthError as err:
            ir.async_delete_issue(self.hass, DOMAIN, f"{REPAIR_CANNOT_CONNECT}_{entry_id}")
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"{REPAIR_AUTH_FAILED}_{entry_id}",
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=REPAIR_AUTH_FAILED,
                translation_placeholders={"name": title},
            )
            raise ConfigEntryAuthFailed(f"OBS auth failed for {title}: {err}") from err
        except OBSConnectionError as err:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"{REPAIR_CANNOT_CONNECT}_{entry_id}",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=REPAIR_CANNOT_CONNECT,
                translation_placeholders={"name": title},
            )
            raise UpdateFailed(f"OBS connection error for {title}: {err}") from err

        ir.async_delete_issue(self.hass, DOMAIN, f"{REPAIR_CANNOT_CONNECT}_{entry_id}")
        ir.async_delete_issue(self.hass, DOMAIN, f"{REPAIR_AUTH_FAILED}_{entry_id}")
        return data
