"""Binary sensor for guest Wi-Fi presence."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MODULE_DEVICES, OPTIONS_TRACK_GUEST_NETWORK
from .coordinator import CudyRouterDataUpdateCoordinator
from .device_info import build_router_device_info


def _guest_clients_entry(coordinator: CudyRouterDataUpdateCoordinator) -> dict | None:
    devices_data = (coordinator.data or {}).get(MODULE_DEVICES)
    if not isinstance(devices_data, dict):
        return None
    entry = devices_data.get("guest_clients")
    return entry if isinstance(entry, dict) else None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Cudy Router binary sensors."""
    coordinator: CudyRouterDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    unique_id = f"{config_entry.entry_id}-devices-guests_present"

    if not config_entry.options.get(OPTIONS_TRACK_GUEST_NETWORK, False):
        entity_registry = async_get_entity_registry(hass)
        entity_id = entity_registry.async_get_entity_id("binary_sensor", DOMAIN, unique_id)
        if entity_id:
            entity_registry.async_remove(entity_id)
        async_add_entities([])
        return

    entities = []
    if _guest_clients_entry(coordinator) is not None:
        entities.append(CudyGuestsPresentBinarySensor(coordinator, unique_id))
    async_add_entities(entities)


class CudyGuestsPresentBinarySensor(
    CoordinatorEntity[CudyRouterDataUpdateCoordinator], BinarySensorEntity
):
    """On while at least one device is connected to the guest Wi-Fi."""

    _attr_has_entity_name = True
    _attr_name = "Guests present"
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_icon = "mdi:account-multiple-check-outline"

    def __init__(self, coordinator: CudyRouterDataUpdateCoordinator, unique_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = unique_id
        self._attr_device_info = build_router_device_info(coordinator)

    @property
    def is_on(self) -> bool | None:
        entry = _guest_clients_entry(self.coordinator)
        if entry is None or entry.get("value") is None:
            return None
        return entry["value"] > 0
