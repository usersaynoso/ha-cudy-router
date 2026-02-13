"""Config flow for Cudy Router integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_MODEL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    OPTIONS_DEVICELIST,
    normalize_scan_interval,
)
from .router import CudyRouter

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default="192.168.10.1"): str,
        vol.Required(CONF_USERNAME, default="admin"): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


def _normalize_host(host: str) -> str:
    """Normalize the host URL to ensure https:// prefix."""
    host = host.strip()
    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"
    return host.rstrip("/")


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    host = _normalize_host(data[CONF_HOST])
    router = CudyRouter(hass, host, data[CONF_USERNAME], data[CONF_PASSWORD])

    try:
        device_model: str = await hass.async_add_executor_job(router.get_model)
    except Exception as err:
        _LOGGER.exception("Error connecting to router: %s", err)
        raise CannotConnect from err

    if not device_model:
        device_model = "default"

    try:
        authenticated = await hass.async_add_executor_job(router.authenticate)
    except Exception as err:
        _LOGGER.exception("Error connecting to router: %s", err)
        raise CannotConnect from err

    if not authenticated:
        raise InvalidAuth

    # Default title to "Cudy Router"
    return {"title": "Cudy Router", "host": host, "device_model": device_model}


class CudyRouterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cudy Router."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize config flow."""
        self._reauth_entry: ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Get the options flow for this handler."""
        return CudyRouterOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Normalize the host URL
            user_input[CONF_HOST] = _normalize_host(user_input[CONF_HOST])

            # Set unique ID based on host to prevent duplicates
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                user_input[CONF_MODEL] = info["device_model"]
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauthentication flow."""
        del entry_data
        entry_id = self.context.get("entry_id")
        if entry_id is None:
            return self.async_abort(reason="unknown")

        self._reauth_entry = self.hass.config_entries.async_get_entry(entry_id)
        if self._reauth_entry is None:
            return self.async_abort(reason="unknown")

        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm and process updated credentials."""
        if self._reauth_entry is None:
            return self.async_abort(reason="unknown")

        errors: dict[str, str] = {}
        current_data = dict(self._reauth_entry.data)

        if user_input is not None:
            updated_data = dict(current_data)
            updated_data[CONF_USERNAME] = user_input[CONF_USERNAME]
            updated_data[CONF_PASSWORD] = user_input[CONF_PASSWORD]

            try:
                info = await validate_input(self.hass, updated_data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception during reauth")
                errors["base"] = "unknown"
            else:
                updated_data[CONF_HOST] = info["host"]
                updated_data[CONF_MODEL] = info["device_model"]
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data=updated_data,
                )
                await self.hass.config_entries.async_reload(
                    self._reauth_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=current_data.get(CONF_USERNAME, "admin"),
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )


class CudyRouterOptionsFlowHandler(OptionsFlow):
    """Handle Cudy Router options flow."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            if CONF_SCAN_INTERVAL in user_input:
                user_input[CONF_SCAN_INTERVAL] = normalize_scan_interval(
                    user_input[CONF_SCAN_INTERVAL]
                )
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        OPTIONS_DEVICELIST,
                        default=options.get(OPTIONS_DEVICELIST, ""),
                    ): str,
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=normalize_scan_interval(
                            options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="seconds",
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=5,
                        ),
                    ),
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
