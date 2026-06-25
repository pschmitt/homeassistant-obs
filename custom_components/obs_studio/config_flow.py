"""Config flow for OBS Studio."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import OBSClient
from .const import (
    CONF_DISABLE_OFFLINE_REPAIRS,
    CONF_OBS_REMOTE_HOST,
    CONF_SSH_ENABLED,
    CONF_SSH_HOST,
    CONF_SSH_KEY_CONTENT,
    CONF_SSH_KEY_PATH,
    CONF_SSH_KNOWN_HOSTS,
    CONF_SSH_PORT,
    CONF_SSH_USERNAME,
    CONF_TEMPLATE_CONTENT,
    CONF_TEMPLATE_FILE_PATH,
    CONF_TEMPLATE_FROM_FILE,
    CONF_TEMPLATE_NAME,
    CONF_TEMPLATE_OUTPUT_DIR,
    CONF_TEMPLATES,
    CONF_WS_PASSWORD,
    CONF_WS_PORT,
    DEFAULT_DISABLE_OFFLINE_REPAIRS,
    DEFAULT_OBS_REMOTE_HOST,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SSH_ENABLED,
    DEFAULT_SSH_KEY_PATH,
    DEFAULT_SSH_PORT,
    DEFAULT_SSH_USERNAME,
    DEFAULT_TEMPLATE_OUTPUT_DIR,
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


_ACTION_ADD = "__add__"
_CONF_TEMPLATE_DELETE = "delete"


def _local_url_path(output_dir: str, name: str) -> str:
    """Derive /local/… URL path from /config/www/… output directory."""
    if output_dir.startswith("/config/www/"):
        suffix = output_dir[len("/config/www/"):].strip("/")
        web_path = f"/local/{suffix}" if suffix else "/local"
    else:
        web_path = output_dir.rstrip("/")
    return f"{web_path}/{name}.html"


def _overlay_url(hass: HomeAssistant, output_dir: str, name: str) -> str:
    """Build the full browser-source URL, using the HA instance URL as base."""
    path = _local_url_path(output_dir, name)
    try:
        base = get_url(hass, prefer_external=False).rstrip("/")
    except NoURLAvailableError:
        base = "http://homeassistant.local:8123"
    return f"{base}{path}"


class OBSOptionsFlow(OptionsFlow):
    """Handle OBS options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["settings", "manage_templates"],
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={**self.config_entry.options, **user_input},
            )
        options = self.config_entry.options
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            mode=NumberSelectorMode.BOX,
                            step=1,
                        )
                    ),
                    vol.Required(
                        CONF_DISABLE_OFFLINE_REPAIRS,
                        default=options.get(
                            CONF_DISABLE_OFFLINE_REPAIRS, DEFAULT_DISABLE_OFFLINE_REPAIRS
                        ),
                    ): BooleanSelector(),
                }
            ),
        )

    async def async_step_manage_templates(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        templates: list[dict] = self.config_entry.options.get(CONF_TEMPLATES, [])

        if user_input is not None:
            action: str = user_input["template_action"]
            self._tpl_editing_idx: int | None = (
                None
                if action == _ACTION_ADD
                else next(
                    i
                    for i, t in enumerate(templates)
                    if t.get(CONF_TEMPLATE_NAME) == action
                )
            )
            return await self.async_step_template_edit()

        choices = [
            {"value": _ACTION_ADD, "label": "+ Add template"},
            *[
                {"value": t[CONF_TEMPLATE_NAME], "label": t[CONF_TEMPLATE_NAME]}
                for t in templates
            ],
        ]
        return self.async_show_form(
            step_id="manage_templates",
            data_schema=vol.Schema(
                {
                    vol.Required("template_action"): SelectSelector(
                        SelectSelectorConfig(
                            options=choices,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            description_placeholders={"template_count": str(len(templates))},
        )

    async def async_step_template_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Meta step: name, source type, output directory, and optional delete."""
        templates: list[dict] = list(
            self.config_entry.options.get(CONF_TEMPLATES, [])
        )
        editing_idx: int | None = getattr(self, "_tpl_editing_idx", None)
        existing = templates[editing_idx] if editing_idx is not None else {}

        if user_input is not None:
            if user_input.get(_CONF_TEMPLATE_DELETE) and editing_idx is not None:
                templates.pop(editing_idx)
                return self.async_create_entry(
                    title="",
                    data={**self.config_entry.options, CONF_TEMPLATES: templates},
                )
            self._tpl_name: str = user_input[CONF_TEMPLATE_NAME].strip()
            self._tpl_from_file: bool = user_input[CONF_TEMPLATE_FROM_FILE]
            self._tpl_output_dir: str = (
                user_input[CONF_TEMPLATE_OUTPUT_DIR].strip()
                or DEFAULT_TEMPLATE_OUTPUT_DIR
            )
            if self._tpl_from_file:
                return await self.async_step_template_edit_file()
            return await self.async_step_template_edit_inline()

        schema_dict: dict = {
            vol.Required(
                CONF_TEMPLATE_NAME,
                default=existing.get(CONF_TEMPLATE_NAME, ""),
            ): TextSelector(),
            vol.Required(
                CONF_TEMPLATE_FROM_FILE,
                default=existing.get(CONF_TEMPLATE_FROM_FILE, False),
            ): BooleanSelector(),
            vol.Required(
                CONF_TEMPLATE_OUTPUT_DIR,
                default=existing.get(CONF_TEMPLATE_OUTPUT_DIR, DEFAULT_TEMPLATE_OUTPUT_DIR),
            ): TextSelector(),
        }
        if editing_idx is not None:
            schema_dict[vol.Optional(_CONF_TEMPLATE_DELETE, default=False)] = BooleanSelector()

        return self.async_show_form(
            step_id="template_edit",
            data_schema=vol.Schema(schema_dict),
        )

    async def async_step_template_edit_file(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step for file-based template source."""
        templates: list[dict] = list(
            self.config_entry.options.get(CONF_TEMPLATES, [])
        )
        editing_idx: int | None = getattr(self, "_tpl_editing_idx", None)
        existing = templates[editing_idx] if editing_idx is not None else {}

        if user_input is not None:
            tpl = {
                CONF_TEMPLATE_NAME: self._tpl_name,
                CONF_TEMPLATE_FROM_FILE: True,
                CONF_TEMPLATE_FILE_PATH: user_input[CONF_TEMPLATE_FILE_PATH].strip(),
                CONF_TEMPLATE_OUTPUT_DIR: self._tpl_output_dir,
            }
            if editing_idx is not None:
                templates[editing_idx] = tpl
            else:
                templates.append(tpl)
            return self.async_create_entry(
                title="",
                data={**self.config_entry.options, CONF_TEMPLATES: templates},
            )

        return self.async_show_form(
            step_id="template_edit_file",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TEMPLATE_FILE_PATH,
                        default=existing.get(CONF_TEMPLATE_FILE_PATH, ""),
                    ): TextSelector(),
                }
            ),
            description_placeholders={
                "url": _overlay_url(self.hass, self._tpl_output_dir, self._tpl_name),
            },
        )

    async def async_step_template_edit_inline(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step for inline (pasted) template content."""
        templates: list[dict] = list(
            self.config_entry.options.get(CONF_TEMPLATES, [])
        )
        editing_idx: int | None = getattr(self, "_tpl_editing_idx", None)
        existing = templates[editing_idx] if editing_idx is not None else {}

        if user_input is not None:
            tpl = {
                CONF_TEMPLATE_NAME: self._tpl_name,
                CONF_TEMPLATE_FROM_FILE: False,
                CONF_TEMPLATE_CONTENT: user_input[CONF_TEMPLATE_CONTENT],
                CONF_TEMPLATE_OUTPUT_DIR: self._tpl_output_dir,
            }
            if editing_idx is not None:
                templates[editing_idx] = tpl
            else:
                templates.append(tpl)
            return self.async_create_entry(
                title="",
                data={**self.config_entry.options, CONF_TEMPLATES: templates},
            )

        return self.async_show_form(
            step_id="template_edit_inline",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TEMPLATE_CONTENT,
                        default=existing.get(CONF_TEMPLATE_CONTENT, ""),
                    ): TextSelector(TextSelectorConfig(multiline=True)),
                }
            ),
            description_placeholders={
                "url": _overlay_url(self.hass, self._tpl_output_dir, self._tpl_name),
            },
        )
