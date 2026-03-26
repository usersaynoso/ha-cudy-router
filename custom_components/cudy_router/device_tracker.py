"""Device tracker platform for Cudy Router."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MODULE_DEVICES, OPTIONS_DEVICELIST, SECTION_DEVICE_LIST
from .coordinator import CudyRouterDataUpdateCoordinator
from .device_tracking import configured_device_ids, is_selected_device, normalize_mac


def _get_connected_devices(coordinator: CudyRouterDataUpdateCoordinator) -> list[dict[str, Any]]:
    """Return the parsed list of connected devices."""
    if not coordinator.data:
        return []

    module_data = coordinator.data.get(MODULE_DEVICES, {})
    devices = module_data.get(SECTION_DEVICE_LIST, [])
    return [device for device in devices if isinstance(device, dict)]

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up tracked devices for the configured router entry."""
    coordinator: CudyRouterDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    selected_ids = configured_device_ids(config_entry.options.get(OPTIONS_DEVICELIST))
    if not selected_ids:
        return

    entities: list[CudyRouterDeviceTracker] = []
    seen_macs: set[str] = set()

    for device in _get_connected_devices(coordinator):
        if not is_selected_device(device, selected_ids):
            continue

        normalized_mac = normalize_mac(device.get("mac"))
        if not normalized_mac or normalized_mac in seen_macs:
            continue

        seen_macs.add(normalized_mac)
        entities.append(CudyRouterDeviceTracker(coordinator, config_entry, device))

    async_add_entities(entities)


class CudyRouterDeviceTracker(
    CoordinatorEntity[CudyRouterDataUpdateCoordinator], TrackerEntity
):
    """Track the presence of a configured router client."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        config_entry: ConfigEntry,
        device: dict[str, Any],
    ) -> None:
        """Initialize the tracker entity."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._initial_device = device
        self._mac = device.get("mac")
        self._normalized_mac = normalize_mac(self._mac)
        self._hostname = device.get("hostname")

        self._attr_name = self._hostname or self._mac or "Tracked device"
        self._attr_unique_id = f"{config_entry.entry_id}-device-{self._normalized_mac}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{config_entry.entry_id}-device-{self._normalized_mac}")},
            manufacturer="Cudy",
            name=self._hostname or self._mac or "Tracked device",
            via_device=(DOMAIN, config_entry.entry_id),
        )

    def _find_current_device(self) -> dict[str, Any] | None:
        """Return the current device payload for this tracker."""
        for device in _get_connected_devices(self.coordinator):
            if normalize_mac(device.get("mac")) == self._normalized_mac:
                return device
        return None

    @property
    def source_type(self) -> SourceType:
        """Return the source type of the device."""
        return SourceType.ROUTER

    @property
    def mac_address(self) -> str | None:
        """Return the device MAC address."""
        return self._mac

    @property
    def ip_address(self) -> str | None:
        """Return the device IP address."""
        device = self._find_current_device() or self._initial_device
        ip_address = device.get("ip")
        return str(ip_address) if ip_address else None

    @property
    def is_connected(self) -> bool:
        """Return whether the device is currently connected."""
        return self._find_current_device() is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the current parsed device payload."""
        return self._find_current_device() or self._initial_device
