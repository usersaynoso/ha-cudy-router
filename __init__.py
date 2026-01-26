"""The Cudy Router integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import CudyRouterDataUpdateCoordinator
from .router import CudyRouter

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Cudy Router from a config entry."""

    data = entry.data
    api = CudyRouter(hass, data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD])
    coordinator = CudyRouterDataUpdateCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register control services for this integration (if not already registered)
    async def _call_service(callable_name: str, *args, **kwargs):
        # helper to call api method in executor
        api: CudyRouter = coordinator.api if hasattr(coordinator, "api") else CudyRouter(hass, entry.data[CONF_HOST], entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
        return await hass.async_add_executor_job(getattr(api, callable_name), *args)

    async def handle_reboot(call):
        entry_id = call.data.get("entry_id")
        target_coordinator = hass.data[DOMAIN].get(entry_id) if entry_id else coordinator
        if not target_coordinator:
            _LOGGER.error("No coordinator found for reboot request")
            return
        await hass.async_add_executor_job(target_coordinator.api.reboot_router)

    async def handle_restart_5g(call):
        entry_id = call.data.get("entry_id")
        target_coordinator = hass.data[DOMAIN].get(entry_id) if entry_id else coordinator
        if not target_coordinator:
            _LOGGER.error("No coordinator found for restart_5g request")
            return
        await hass.async_add_executor_job(target_coordinator.api.restart_5g_connection)

    async def handle_switch_band(call):
        band = call.data.get("band")
        entry_id = call.data.get("entry_id")
        target_coordinator = hass.data[DOMAIN].get(entry_id) if entry_id else coordinator
        if not target_coordinator:
            _LOGGER.error("No coordinator found for switch_band request")
            return
        await hass.async_add_executor_job(target_coordinator.api.switch_5g_band, band)

    async def handle_send_sms(call):
        phone = call.data.get("phone_number")
        message = call.data.get("message")
        entry_id = call.data.get("entry_id")
        target_coordinator = hass.data[DOMAIN].get(entry_id) if entry_id else coordinator
        if not target_coordinator:
            _LOGGER.error("No coordinator found for send_sms request")
            return
        if not phone or not message:
            _LOGGER.error("send_sms requires phone_number and message")
            return
        await hass.async_add_executor_job(target_coordinator.api.send_sms, phone, message)

    async def handle_send_at_command(call):
        command = call.data.get("command")
        entry_id = call.data.get("entry_id")
        target_coordinator = hass.data[DOMAIN].get(entry_id) if entry_id else coordinator
        if not target_coordinator:
            _LOGGER.error("No coordinator found for send_at_command request")
            return
        if not command:
            _LOGGER.error("send_at_command requires command")
            return
        result = await hass.async_add_executor_job(target_coordinator.api.send_at_command, command)
        _LOGGER.info("AT command '%s' result: %s", command, result)

    # Register services only once per hass instance
    if not hass.services.async_services().get(DOMAIN):
        hass.services.async_register(DOMAIN, "reboot_router", handle_reboot)
        hass.services.async_register(DOMAIN, "restart_5g_connection", handle_restart_5g)
        hass.services.async_register(DOMAIN, "switch_5g_band", handle_switch_band)
        hass.services.async_register(DOMAIN, "send_sms", handle_send_sms)
        hass.services.async_register(DOMAIN, "send_at_command", handle_send_at_command)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            del hass.data[DOMAIN]
    return unload_ok
