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
    MODULE_DEVICES,
    OPTIONS_AUTO_ADD_CONNECTED_DEVICES,
    OPTIONS_AUTO_ADD_DEVICE_TRACKERS,
    OPTIONS_DEVICELIST,
    OPTIONS_TRACKED_DEVICE_MACS,
    SECTION_DEVICE_LIST,
    normalize_scan_interval,
)
from .device_info import known_client_devices
from .device_tracking import (
    configured_tracked_macs,
    eligible_manual_picker_devices,
    eligible_tracker_picker_devices,
    manual_allowed_client_macs,
    next_options_flow_step,
    tracker_picker_options,
)
from .model_names import resolve_model_name
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

    device_model = resolve_model_name(device_model)

    try:
        authenticated = await hass.async_add_executor_job(router.authenticate)
    except Exception as err:
        _LOGGER.exception("Error connecting to router: %s", err)
        raise CannotConnect from err

    if not authenticated:
        raise InvalidAuth

    # Default title to "Cudy Router"
    return {"title": "Cudy Router", "host": router.base_url, "device_model": device_model}


def _connected_devices(hass: HomeAssistant, config_entry: ConfigEntry) -> list[dict[str, Any]]:
    """Return connected devices from the active coordinator, if available."""
    coordinator = hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
    if coordinator is None or not getattr(coordinator, "data", None):
        return []

    devices = coordinator.data.get(MODULE_DEVICES, {}).get(SECTION_DEVICE_LIST, [])
    return [device for device in devices if isinstance(device, dict)]


class CudyRouterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cudy Router."""

    VERSION = 3

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
                user_input[CONF_HOST] = info["host"]
                await self.async_set_unique_id(info["host"])
                self._abort_if_unique_id_configured()
                user_input[CONF_MODEL] = info["device_model"]
                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                    options={
                        OPTIONS_AUTO_ADD_CONNECTED_DEVICES: False,
                        OPTIONS_AUTO_ADD_DEVICE_TRACKERS: False,
                        OPTIONS_TRACKED_DEVICE_MACS: [],
                    },
                )

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
        # Home Assistant now exposes `config_entry` as read-only on options
        # flows, so store our reference under a private attribute.
        self._config_entry = config_entry
        self._pending_options: dict[str, Any] | None = None

    def _default_pending_options(self) -> dict[str, Any]:
        """Return options state used to drive the multi-step flow."""
        options = self._config_entry.options
        return {
            OPTIONS_AUTO_ADD_CONNECTED_DEVICES: options.get(
                OPTIONS_AUTO_ADD_CONNECTED_DEVICES,
                True,
            ),
            OPTIONS_DEVICELIST: options.get(OPTIONS_DEVICELIST, []),
            OPTIONS_AUTO_ADD_DEVICE_TRACKERS: options.get(
                OPTIONS_AUTO_ADD_DEVICE_TRACKERS,
                False,
            ),
            OPTIONS_TRACKED_DEVICE_MACS: options.get(OPTIONS_TRACKED_DEVICE_MACS, []),
            CONF_SCAN_INTERVAL: normalize_scan_interval(
                options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        }

    def _pending_options_state(self) -> dict[str, Any]:
        """Return the in-progress options payload."""
        if self._pending_options is None:
            self._pending_options = self._default_pending_options()
        return self._pending_options

    def _next_step(self, *, after_manual_devices: bool = False) -> str | None:
        """Return the next step id for the current pending options."""
        pending_options = self._pending_options_state()
        return next_options_flow_step(
            auto_add_connected_devices=pending_options.get(
                OPTIONS_AUTO_ADD_CONNECTED_DEVICES,
                True,
            ),
            auto_add_device_trackers=pending_options.get(
                OPTIONS_AUTO_ADD_DEVICE_TRACKERS,
                False,
            ),
            after_manual_devices=after_manual_devices,
        )

    def _async_create_entry_from_pending_options(self) -> ConfigFlowResult:
        """Persist the current pending options without altering skipped fields."""
        return self.async_create_entry(
            title="",
            data=dict(self._pending_options_state()),
        )

    @staticmethod
    def _multi_select_dropdown(
        options: list[selector.SelectOptionDict],
    ) -> selector.SelectSelector:
        """Return a consistent multi-select dropdown selector."""
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=options,
                multiple=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage base connected-device and polling options."""
        options = self._config_entry.options

        if user_input is not None:
            self._pending_options = self._default_pending_options()
            self._pending_options[OPTIONS_AUTO_ADD_CONNECTED_DEVICES] = user_input.get(
                OPTIONS_AUTO_ADD_CONNECTED_DEVICES,
                options.get(OPTIONS_AUTO_ADD_CONNECTED_DEVICES, True),
            )
            self._pending_options[OPTIONS_AUTO_ADD_DEVICE_TRACKERS] = user_input.get(
                OPTIONS_AUTO_ADD_DEVICE_TRACKERS,
                options.get(OPTIONS_AUTO_ADD_DEVICE_TRACKERS, False),
            )
            self._pending_options[CONF_SCAN_INTERVAL] = normalize_scan_interval(
                user_input.get(
                    CONF_SCAN_INTERVAL,
                    options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                )
            )

            next_step = self._next_step()
            if next_step == "manual_devices":
                return await self.async_step_manual_devices()
            if next_step == "trackers":
                return await self.async_step_trackers()
            return self._async_create_entry_from_pending_options()

        schema = vol.Schema(
            {
                vol.Optional(OPTIONS_AUTO_ADD_CONNECTED_DEVICES): selector.BooleanSelector(),
                vol.Optional(OPTIONS_AUTO_ADD_DEVICE_TRACKERS): selector.BooleanSelector(),
                vol.Optional(CONF_SCAN_INTERVAL): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="seconds",
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=5,
                    ),
                ),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    OPTIONS_AUTO_ADD_CONNECTED_DEVICES: options.get(
                        OPTIONS_AUTO_ADD_CONNECTED_DEVICES,
                        True,
                    ),
                    OPTIONS_AUTO_ADD_DEVICE_TRACKERS: options.get(
                        OPTIONS_AUTO_ADD_DEVICE_TRACKERS,
                        False,
                    ),
                    CONF_SCAN_INTERVAL: normalize_scan_interval(
                        options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                    ),
                },
            ),
        )

    async def async_step_manual_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage manual connected-device selections."""
        pending_options = self._pending_options_state()

        if pending_options.get(OPTIONS_AUTO_ADD_CONNECTED_DEVICES, True):
            next_step = self._next_step()
            if next_step == "trackers":
                return await self.async_step_trackers()
            return self._async_create_entry_from_pending_options()

        connected_devices = _connected_devices(self.hass, self._config_entry)
        known_clients = known_client_devices(self.hass, self._config_entry)
        stored_manual_macs = manual_allowed_client_macs(
            connected_devices=connected_devices,
            device_list=pending_options.get(OPTIONS_DEVICELIST),
            known_clients=known_clients,
        )
        manual_device_names = {
            normalized_mac: known_clients.get(normalized_mac, {}).get("name")
            for normalized_mac in stored_manual_macs
        }
        manual_device_options = [
            selector.SelectOptionDict(label=option["label"], value=option["value"])
            for option in tracker_picker_options(
                eligible_manual_picker_devices(connected_devices),
                manual_device_names,
            )
        ]

        if user_input is not None:
            self._pending_options[OPTIONS_DEVICELIST] = sorted(
                configured_tracked_macs(user_input.get(OPTIONS_DEVICELIST))
            )
            next_step = self._next_step(after_manual_devices=True)
            if next_step == "trackers":
                return await self.async_step_trackers()
            return self._async_create_entry_from_pending_options()

        schema = vol.Schema(
            {
                vol.Optional(OPTIONS_DEVICELIST): self._multi_select_dropdown(
                    manual_device_options
                ),
            }
        )

        return self.async_show_form(
            step_id="manual_devices",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    OPTIONS_DEVICELIST: sorted(stored_manual_macs),
                },
            ),
        )

    async def async_step_trackers(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage tracker selection options."""
        pending_options = self._pending_options_state()
        if pending_options.get(OPTIONS_AUTO_ADD_DEVICE_TRACKERS, False):
            return self._async_create_entry_from_pending_options()

        known_clients = known_client_devices(self.hass, self._config_entry)
        stored_tracked_macs = configured_tracked_macs(
            pending_options.get(OPTIONS_TRACKED_DEVICE_MACS)
        )
        eligible_tracker_macs = set(stored_tracked_macs)
        if not pending_options.get(OPTIONS_AUTO_ADD_CONNECTED_DEVICES, True):
            eligible_tracker_macs.update(
                manual_allowed_client_macs(
                    connected_devices=_connected_devices(self.hass, self._config_entry),
                    device_list=pending_options.get(OPTIONS_DEVICELIST),
                    known_clients=known_clients,
                )
            )
        tracker_names = {
            normalized_mac: known_clients.get(normalized_mac, {}).get("name")
            for normalized_mac in eligible_tracker_macs
        }
        tracked_device_options = [
            selector.SelectOptionDict(label=option["label"], value=option["value"])
            for option in tracker_picker_options(
                eligible_tracker_picker_devices(
                    auto_add_connected_devices=pending_options.get(
                        OPTIONS_AUTO_ADD_CONNECTED_DEVICES,
                        True,
                    ),
                    connected_devices=_connected_devices(self.hass, self._config_entry),
                    device_list=pending_options.get(OPTIONS_DEVICELIST),
                ),
                tracker_names,
            )
        ]
        suggested_tracked_macs = sorted(stored_tracked_macs)

        if user_input is not None:
            updated_options = dict(pending_options)
            updated_options[OPTIONS_TRACKED_DEVICE_MACS] = sorted(
                configured_tracked_macs(user_input.get(OPTIONS_TRACKED_DEVICE_MACS))
            )
            self._pending_options = updated_options
            return self._async_create_entry_from_pending_options()

        schema = vol.Schema(
            {
                vol.Optional(
                    OPTIONS_TRACKED_DEVICE_MACS
                ): self._multi_select_dropdown(tracked_device_options),
            }
        )

        return self.async_show_form(
            step_id="trackers",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    OPTIONS_TRACKED_DEVICE_MACS: suggested_tracked_macs,
                },
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
