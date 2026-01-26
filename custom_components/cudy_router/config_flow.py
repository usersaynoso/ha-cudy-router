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
    CONF_NAME,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .const import DOMAIN, OPTIONS_DEVICELIST
from .router import CudyRouter

_LOGGER = logging.getLogger(__name__)

DEFAULT_SCAN_INTERVAL = 15
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 3600

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME): str,
        vol.Required(CONF_HOST): str,
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
        authenticated = await hass.async_add_executor_job(router.authenticate)
    except Exception as err:
        _LOGGER.exception("Error connecting to router: %s", err)
        raise CannotConnect from err

    if not authenticated:
        raise InvalidAuth

    return {"title": data.get(CONF_NAME) or host, "host": host}


class CudyRouterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cudy Router."""

    VERSION = 1

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
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
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
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
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
