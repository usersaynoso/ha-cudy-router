"""Device tracker platform for Cudy Router."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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
    async_ensure_client_entity_device,
    async_cleanup_stale_tracker_entities,
    build_client_device_info,
    client_display_name,
    known_tracker_clients,
)
from .device_tracking import (
    build_tracker_seed_device,
    configured_device_ids,
    configured_tracked_macs,
    connected_device_lookup,
    format_mac,
    is_selected_device,
    normalize_mac,
    tracker_allowed_macs,
)


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
    connected_devices = _get_connected_devices(coordinator)
    connected_devices_by_mac = connected_device_lookup(connected_devices)
    known_trackers = known_tracker_clients(hass, config_entry)
    tracker_options_configured = (
        OPTIONS_AUTO_ADD_DEVICE_TRACKERS in config_entry.options
        or OPTIONS_TRACKED_DEVICE_MACS in config_entry.options
    )
    legacy_tracked_macs = set(known_trackers)

    if not config_entry.options.get(OPTIONS_AUTO_ADD_CONNECTED_DEVICES, True):
        selected_ids = configured_device_ids(config_entry.options.get(OPTIONS_DEVICELIST))
        legacy_tracked_macs.update(
            normalize_mac(device.get("mac"))
            for device in connected_devices
            if is_selected_device(device, selected_ids) and normalize_mac(device.get("mac"))
        )

    allowed_tracker_macs = tracker_allowed_macs(
        auto_add_device_trackers=config_entry.options.get(
            OPTIONS_AUTO_ADD_DEVICE_TRACKERS,
            False,
        ),
        connected_devices=connected_devices,
        tracked_device_macs=configured_tracked_macs(
            config_entry.options.get(OPTIONS_TRACKED_DEVICE_MACS)
        ),
        legacy_tracked_macs=legacy_tracked_macs,
        tracker_options_configured=tracker_options_configured,
    )

    async_cleanup_stale_tracker_entities(
        hass,
        config_entry,
        "device_tracker",
        allowed_tracker_macs,
    )

    if not allowed_tracker_macs:
        return

    entities: list[CudyRouterDeviceTracker] = []
    for normalized_mac in sorted(allowed_tracker_macs):
        device = build_tracker_seed_device(
            normalized_mac,
            connected_devices_by_mac,
            known_trackers.get(normalized_mac, {}).get("name"),
        )
        async_ensure_client_entity_device(
            hass,
            config_entry,
            "device_tracker",
            format_mac(normalized_mac) or normalized_mac,
            device,
        )
        entities.append(
            CudyRouterDeviceTracker(
                coordinator,
                config_entry,
                device,
                normalized_mac=normalized_mac,
            )
        )

    async_add_entities(entities)


class CudyRouterDeviceTracker(
    CoordinatorEntity[CudyRouterDataUpdateCoordinator], ScannerEntity
):
    """Track the presence of a configured router client."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        config_entry: ConfigEntry,
        device: dict[str, Any],
        *,
        normalized_mac: str | None = None,
    ) -> None:
        """Initialize the tracker entity."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._initial_device = device
        self._normalized_mac = normalized_mac or normalize_mac(device.get("mac"))
        self._mac = format_mac(device.get("mac")) or format_mac(self._normalized_mac)
        self._hostname = device.get("hostname")

        self._attr_name = client_display_name(
            {
                "hostname": self._hostname,
                "mac": self._mac,
            }
        )
        self._attr_unique_id = self._mac or self._normalized_mac
        self._attr_device_info = build_client_device_info(config_entry, device)

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
