"""The Cudy Router integration."""

from __future__ import annotations

import logging
from typing import Final

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_MODEL,
    CONF_PASSWORD,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    MODULE_DEVICES,
    OPTIONS_AUTO_ADD_CONNECTED_DEVICES,
    OPTIONS_AUTO_ADD_DEVICE_TRACKERS,
    OPTIONS_DEVICELIST,
    OPTIONS_TRACKED_DEVICE_MACS,
    SECTION_DEVICE_LIST,
)
from .coordinator import CudyRouterDataUpdateCoordinator
from .device_info import (
    async_cleanup_stale_client_entities,
    async_cleanup_stale_tracker_entities,
    known_client_devices,
    known_tracker_clients,
)
from .device_tracking import (
    configured_device_ids,
    configured_tracked_macs,
    connected_device_lookup,
    is_selected_device,
    manual_allowed_client_macs,
    normalize_mac,
    tracker_allowed_macs,
)
from .model_names import resolve_model_name
from .router import CudyRouter

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final[list[Platform]] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.DEVICE_TRACKER,
]

# Service constants
SERVICE_REBOOT: Final = "reboot_router"
SERVICE_RESTART_5G: Final = "restart_5g_connection"
SERVICE_SWITCH_BAND: Final = "switch_5g_band"
SERVICE_SEND_SMS: Final = "send_sms"
SERVICE_SEND_AT_COMMAND: Final = "send_at_command"

ATTR_ENTRY_ID: Final = "entry_id"
ATTR_BAND: Final = "band"
ATTR_PHONE_NUMBER: Final = "phone_number"
ATTR_MESSAGE: Final = "message"
ATTR_COMMAND: Final = "command"

# Service schemas
SERVICE_REBOOT_SCHEMA: Final = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)

SERVICE_RESTART_5G_SCHEMA: Final = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)

SERVICE_SWITCH_BAND_SCHEMA: Final = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_BAND): cv.string,
    }
)

SERVICE_SEND_SMS_SCHEMA: Final = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_PHONE_NUMBER): cv.string,
        vol.Required(ATTR_MESSAGE): cv.string,
    }
)

SERVICE_SEND_AT_COMMAND_SCHEMA: Final = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_COMMAND): cv.string,
    }
)


MIGRATION_VERSION: Final = 3


def _normalize_host(host: str) -> str:
    """Normalize a host to include scheme and no trailing slash."""
    host = host.strip()
    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"
    return host.rstrip("/")


CudyRouterConfigEntry = ConfigEntry[CudyRouterDataUpdateCoordinator]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to the latest schema."""
    if entry.version > MIGRATION_VERSION:
        _LOGGER.error(
            "Config entry version %s is newer than supported version %s",
            entry.version,
            MIGRATION_VERSION,
        )
        return False

    if entry.version in (1, 2):
        new_data = dict(entry.data)
        host = new_data.get(CONF_HOST)
        if isinstance(host, str):
            new_data[CONF_HOST] = _normalize_host(host)
        new_data[CONF_MODEL] = resolve_model_name(new_data.get(CONF_MODEL))

        hass.config_entries.async_update_entry(
            entry,
            data=new_data,
            version=MIGRATION_VERSION,
        )
        _LOGGER.info(
            "Migrated %s config entry from version %s to %s",
            DOMAIN,
            entry.version,
            MIGRATION_VERSION,
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: CudyRouterConfigEntry) -> bool:
    """Set up Cudy Router from a config entry."""
    data = entry.data
    api = CudyRouter(
        hass,
        data[CONF_HOST],
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        data.get(CONF_MODEL, "default"),
    )

    # Verify we can authenticate
    try:
        authenticated = await hass.async_add_executor_job(api.authenticate)
    except Exception as err:
        raise ConfigEntryNotReady(
            f"Unable to connect to router at {data[CONF_HOST]}"
        ) from err

    if not authenticated:
        raise ConfigEntryAuthFailed("Invalid authentication credentials")

    coordinator = CudyRouterDataUpdateCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    await _async_setup_services(hass)

    # Reload entry when options are updated
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    connected_devices = []
    if coordinator is not None and getattr(coordinator, "data", None):
        connected_devices = [
            device
            for device in coordinator.data.get(MODULE_DEVICES, {}).get(
                SECTION_DEVICE_LIST,
                [],
            )
            if isinstance(device, dict)
        ]

    if entry.options.get(OPTIONS_AUTO_ADD_CONNECTED_DEVICES, True):
        allowed_client_macs = set(connected_device_lookup(connected_devices))
    else:
        allowed_client_macs = manual_allowed_client_macs(
            connected_devices=connected_devices,
            device_list=entry.options.get(OPTIONS_DEVICELIST),
            known_clients=known_client_devices(hass, entry),
        )

    async_cleanup_stale_client_entities(
        hass,
        entry,
        Platform.SENSOR.value,
        allowed_client_macs,
    )
    async_cleanup_stale_client_entities(
        hass,
        entry,
        Platform.SWITCH.value,
        allowed_client_macs,
    )

    known_trackers = known_tracker_clients(hass, entry)
    tracker_options_configured = (
        OPTIONS_AUTO_ADD_DEVICE_TRACKERS in entry.options
        or OPTIONS_TRACKED_DEVICE_MACS in entry.options
    )
    legacy_tracked_macs = set(known_trackers)
    if not entry.options.get(OPTIONS_AUTO_ADD_CONNECTED_DEVICES, True):
        selected_ids = configured_device_ids(entry.options.get(OPTIONS_DEVICELIST))
        legacy_tracked_macs.update(
            normalize_mac(device.get("mac"))
            for device in connected_devices
            if is_selected_device(device, selected_ids) and normalize_mac(device.get("mac"))
        )

    async_cleanup_stale_tracker_entities(
        hass,
        entry,
        Platform.DEVICE_TRACKER.value,
        tracker_allowed_macs(
            auto_add_device_trackers=entry.options.get(
                OPTIONS_AUTO_ADD_DEVICE_TRACKERS,
                False,
            ),
            connected_devices=connected_devices,
            tracked_device_macs=configured_tracked_macs(
                entry.options.get(OPTIONS_TRACKED_DEVICE_MACS)
            ),
            legacy_tracked_macs=legacy_tracked_macs,
            tracker_options_configured=tracker_options_configured,
        ),
    )
    await hass.config_entries.async_reload(entry.entry_id)


def _get_coordinator(
    hass: HomeAssistant, entry_id: str | None
) -> CudyRouterDataUpdateCoordinator | None:
    """Get coordinator for the given entry_id or the first one if not specified."""
    if entry_id:
        return hass.data[DOMAIN].get(entry_id)
    # Return the first coordinator if no entry_id specified
    coordinators = hass.data.get(DOMAIN, {})
    if coordinators:
        return next(iter(coordinators.values()))
    return None


async def _async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Cudy Router integration."""

    async def handle_reboot(call: ServiceCall) -> None:
        """Handle the reboot service call."""
        coordinator = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        if not coordinator:
            _LOGGER.error("No Cudy Router coordinator found")
            return
        await hass.async_add_executor_job(coordinator.api.reboot_router)

    async def handle_restart_5g(call: ServiceCall) -> None:
        """Handle the restart 5G service call."""
        coordinator = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        if not coordinator:
            _LOGGER.error("No Cudy Router coordinator found")
            return
        await hass.async_add_executor_job(coordinator.api.restart_5g_connection)

    async def handle_switch_band(call: ServiceCall) -> None:
        """Handle the switch band service call."""
        coordinator = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        if not coordinator:
            _LOGGER.error("No Cudy Router coordinator found")
            return
        band = call.data[ATTR_BAND]
        await hass.async_add_executor_job(coordinator.api.switch_5g_band, band)

    async def handle_send_sms(call: ServiceCall) -> None:
        """Handle the send SMS service call."""
        coordinator = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        if not coordinator:
            _LOGGER.error("No Cudy Router coordinator found")
            return
        phone = call.data[ATTR_PHONE_NUMBER]
        message = call.data[ATTR_MESSAGE]
        await hass.async_add_executor_job(coordinator.api.send_sms, phone, message)

    async def handle_send_at_command(call: ServiceCall) -> None:
        """Handle the send AT command service call."""
        coordinator = _get_coordinator(hass, call.data.get(ATTR_ENTRY_ID))
        if not coordinator:
            _LOGGER.error("No Cudy Router coordinator found")
            return
        command = call.data[ATTR_COMMAND]
        result = await hass.async_add_executor_job(
            coordinator.api.send_at_command, command
        )
        _LOGGER.info("AT command '%s' result: %s", command, result)

    # Only register services if not already registered
    if hass.services.has_service(DOMAIN, SERVICE_REBOOT):
        return

    hass.services.async_register(
        DOMAIN, SERVICE_REBOOT, handle_reboot, schema=SERVICE_REBOOT_SCHEMA
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESTART_5G,
        handle_restart_5g,
        schema=SERVICE_RESTART_5G_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SWITCH_BAND,
        handle_switch_band,
        schema=SERVICE_SWITCH_BAND_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_SMS, handle_send_sms, schema=SERVICE_SEND_SMS_SCHEMA
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_AT_COMMAND,
        handle_send_at_command,
        schema=SERVICE_SEND_AT_COMMAND_SCHEMA,
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        # Unregister services if no more entries
        if not hass.data[DOMAIN]:
            del hass.data[DOMAIN]
            for service in (
                SERVICE_REBOOT,
                SERVICE_RESTART_5G,
                SERVICE_SWITCH_BAND,
                SERVICE_SEND_SMS,
                SERVICE_SEND_AT_COMMAND,
            ):
                hass.services.async_remove(DOMAIN, service)
    return unload_ok
