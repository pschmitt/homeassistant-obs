"""Config flow for OBS Studio."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

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
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SSH_ENABLED,
    DEFAULT_SSH_KEY_PATH,
    DEFAULT_SSH_PORT,
    DEFAULT_SSH_USERNAME,
    DEFAULT_WS_PORT,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .exceptions import OBSAuthError, OBSConnectionError, OBSSSHError
from .ssh_tunnel import OBSSSHTunnel

_LOGGER = logging.getLogger(__name__)


async def _async_validate(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the connection.  Raises OBSAuthError / OBSConnectionError / OBSSSHError."""
    ws_host: str = data[CONF_HOST]
    ws_port: int = int(data.get(CONF_WS_PORT, DEFAULT_WS_PORT))
    password: str = data.get(CONF_WS_PASSWORD, "")
    ssh_tunnel: OBSSSHTunnel | None = None

    try:
        if data.get(CONF_SSH_ENABLED, DEFAULT_SSH_ENABLED):
            ssh_host = data.get(CONF_SSH_HOST) or ws_host
            ssh_tunnel = OBSSSHTunnel(
                ssh_host=ssh_host,
                ssh_port=int(data.get(CONF_SSH_PORT, DEFAULT_SSH_PORT)),
                ssh_username=data.get(CONF_SSH_USERNAME, DEFAULT_SSH_USERNAME),
                ssh_key_path=data.get(CONF_SSH_KEY_PATH) or DEFAULT_SSH_KEY_PATH,
                ssh_key_content=data.get(CONF_SSH_KEY_CONTENT) or None,
                ssh_known_hosts=data.get(CONF_SSH_KNOWN_HOSTS) or None,
                obs_remote_host=data.get(CONF_OBS_REMOTE_HOST, DEFAULT_OBS_REMOTE_HOST),
                obs_remote_port=ws_port,
            )
            local_port = await ssh_tunnel.async_start()
            ws_host = "127.0.0.1"
            ws_port = local_port

        client = OBSClient(host=ws_host, port=ws_port, password=password)
        await hass.async_add_executor_job(client.validate)
    finally:
        if ssh_tunnel is not None:
            await ssh_tunnel.async_stop()


def _connection_schema(defaults: dict[str, Any], *, password_optional: bool = False) -> dict:
    pw_key = vol.Optional(CONF_WS_PASSWORD) if password_optional else vol.Required(CONF_WS_PASSWORD)
    return {
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): TextSelector(),
        vol.Required(
            CONF_WS_PORT, default=defaults.get(CONF_WS_PORT, DEFAULT_WS_PORT)
        ): NumberSelector(
            NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
        ),
        pw_key: TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        vol.Required(
            CONF_SSH_ENABLED,
            default=defaults.get(CONF_SSH_ENABLED, DEFAULT_SSH_ENABLED),
        ): BooleanSelector(),
        vol.Optional(
            CONF_SSH_HOST, default=defaults.get(CONF_SSH_HOST, "")
        ): TextSelector(),
        vol.Required(
            CONF_SSH_PORT, default=defaults.get(CONF_SSH_PORT, DEFAULT_SSH_PORT)
        ): NumberSelector(
            NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
        ),
        vol.Required(
            CONF_SSH_USERNAME,
            default=defaults.get(CONF_SSH_USERNAME, DEFAULT_SSH_USERNAME),
        ): TextSelector(),
        vol.Optional(
            CONF_SSH_KEY_PATH,
            default=defaults.get(CONF_SSH_KEY_PATH, DEFAULT_SSH_KEY_PATH),
        ): TextSelector(),
        vol.Optional(
            CONF_SSH_KEY_CONTENT,
            default=defaults.get(CONF_SSH_KEY_CONTENT, ""),
        ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD, multiline=True)),
        vol.Optional(
            CONF_SSH_KNOWN_HOSTS,
            default=defaults.get(CONF_SSH_KNOWN_HOSTS, ""),
        ): TextSelector(TextSelectorConfig(multiline=True)),
        vol.Required(
            CONF_OBS_REMOTE_HOST,
            default=defaults.get(CONF_OBS_REMOTE_HOST, DEFAULT_OBS_REMOTE_HOST),
        ): TextSelector(),
    }


class OBSConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OBS Studio."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OBSOptionsFlow:
        return OBSOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input[CONF_WS_PORT] = int(user_input[CONF_WS_PORT])
            user_input[CONF_SSH_PORT] = int(user_input[CONF_SSH_PORT])
            name = user_input.pop(CONF_NAME, None) or user_input[CONF_HOST]
            try:
                await _async_validate(self.hass, user_input)
            except OBSAuthError:
                errors["base"] = "invalid_auth"
            except OBSSSHError:
                errors["base"] = "ssh_error"
            except OBSConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error validating OBS config")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(
                    f"obs:{user_input[CONF_HOST]}:{user_input[CONF_WS_PORT]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=name,
                    data=user_input,
                    options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL},
                )

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default="OBS Studio"): TextSelector(),
                **_connection_schema(user_input or {}),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            user_input[CONF_WS_PORT] = int(user_input[CONF_WS_PORT])
            user_input[CONF_SSH_PORT] = int(user_input[CONF_SSH_PORT])
            if not user_input.get(CONF_WS_PASSWORD):
                user_input[CONF_WS_PASSWORD] = entry.data.get(CONF_WS_PASSWORD, "")
            merged = {**entry.data, **user_input}
            try:
                await _async_validate(self.hass, merged)
            except OBSAuthError:
                errors["base"] = "invalid_auth"
            except OBSSSHError:
                errors["base"] = "ssh_error"
            except OBSConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error validating OBS reconfigure")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(entry, data=merged)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                _connection_schema(user_input or entry.data, password_optional=True)
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            merged = {**entry.data, CONF_WS_PASSWORD: user_input.get(CONF_WS_PASSWORD, "")}
            try:
                await _async_validate(self.hass, merged)
            except OBSAuthError:
                errors["base"] = "invalid_auth"
            except OBSConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during OBS reauth")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(entry, data=merged)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_WS_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
            description_placeholders={"name": entry.title},
        )


class OBSOptionsFlow(OptionsFlow):
    """Handle OBS options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            mode=NumberSelectorMode.BOX,
                            step=1,
                        )
                    )
                }
            ),
        )
