"""Support for Cudy Router Sensor Platform."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MODEL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MODULE_DEVICES,
    MODULE_LOAD_BALANCING,
    MODULE_MESH,
    MODULE_MODEM,
    MODULE_WAN,
    MODULE_WAN_INTERFACES,
    OPTIONS_AUTO_ADD_CONNECTED_DEVICES,
    OPTIONS_DEVICELIST,
    SECTION_DEVICE_LIST,
)
from .coordinator import CudyRouterDataUpdateCoordinator
from .device_info import (
    async_cleanup_stale_client_entities,
    async_cleanup_stale_mesh_entities,
    build_client_device_info,
    build_mesh_device_info,
    build_router_device_info,
    known_client_devices,
    mesh_display_name,
    router_display_name,
)
from .device_tracking import (
    build_client_seed_device,
    connected_device_lookup,
    manual_allowed_client_macs,
)
from .features import module_available
from .sensor_descriptions import (
    CudyRouterSensorEntityDescription,
    DEVICE_CONNECTION_TYPE_SENSOR,
    DEVICE_IP_SENSOR,
    DEVICE_ONLINE_TIME_SENSOR,
    DEVICE_SIGNAL_DETAILS_SENSOR,
    MESH_DEVICE_BACKHAUL_SENSOR,
    MESH_DEVICE_CONNECTED_SENSOR,
    MESH_DEVICE_FIRMWARE_SENSOR,
    MESH_DEVICE_HARDWARE_SENSOR,
    MESH_DEVICE_IP_SENSOR,
    MESH_DEVICE_MAC_SENSOR,
    MESH_DEVICE_MODEL_SENSOR,
    MESH_DEVICE_NAME_SENSOR,
    MESH_DEVICE_STATUS_SENSOR,
    NETWORK_SENSOR,
    SENSOR_TYPES,
    SIGNAL_SENSOR,
    WAN_INTERFACE_SENSOR_TYPES,
)

_LOGGER = logging.getLogger(__name__)

_WAN_DUPLICATE_MODEM_KEYS = {
    "connected_time",
    "public_ip",
    "session_upload",
    "session_download",
    "wan_ip",
}

_WAN_REMOVED_SENSOR_KEYS = {
    "mac_address",
}

_LOAD_BALANCING_DYNAMIC_KEYS = {f"wan{interface_number}_status" for interface_number in range(1, 5)}


def _connected_devices(coordinator: CudyRouterDataUpdateCoordinator) -> list[dict[str, Any]]:
    """Return the parsed list of connected client devices."""
    if not coordinator.data:
        return []

    devices = coordinator.data.get(MODULE_DEVICES, {}).get(SECTION_DEVICE_LIST, [])
    return [device for device in devices if isinstance(device, dict)]


def _wan_interfaces(coordinator: CudyRouterDataUpdateCoordinator) -> dict[str, dict[str, Any]]:
    """Return parsed per-WAN interface data."""
    if not coordinator.data:
        return {}

    interfaces = coordinator.data.get(MODULE_WAN_INTERFACES, {})
    if not isinstance(interfaces, dict):
        return {}

    return {
        interface_key: interface_data
        for interface_key, interface_data in interfaces.items()
        if isinstance(interface_key, str) and isinstance(interface_data, dict)
    }


def _module_entry_has_value(data: dict[str, Any] | None, module: str, key: str) -> bool:
    """Return whether a coordinator module entry has a live value."""
    if not isinstance(data, dict):
        return False
    module_data = data.get(module)
    if not isinstance(module_data, dict):
        return False
    data_entry = module_data.get(key)
    if not isinstance(data_entry, dict):
        return False
    return data_entry.get("value") not in (None, "")


def _wan_interface_label(interface_key: str) -> str:
    """Return a display label for an internal WAN interface key."""
    suffix = interface_key.removeprefix("wan")
    if suffix and suffix.isdigit():
        return f"WAN{suffix}"
    return interface_key.upper()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Cudy Router sensors."""
    coordinator: CudyRouterDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    router_name = router_display_name(config_entry, coordinator.data)

    entities: list[SensorEntity] = []

    _LOGGER.debug(
        "Setting up Cudy Router sensors, coordinator.data keys: %s",
        list(coordinator.data.keys()) if coordinator.data else "None",
    )

    device_model: str = config_entry.data.get(CONF_MODEL, "default")
    seen_unique_ids: set[str] = set()
    entity_registry = async_get_entity_registry(hass)

    def _remove_sensor_by_unique_id(unique_id: str) -> None:
        """Remove stale entities from registry by unique ID."""
        entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        if entity_id:
            entity_registry.async_remove(entity_id)

    def _remove_legacy_manual_device_sensors() -> None:
        """Remove retired router-level per-device sensors from the entity registry."""
        entry_prefix = f"{config_entry.entry_id}-"
        for entity_entry in list(entity_registry.entities.values()):
            unique_id = getattr(entity_entry, "unique_id", "") or ""
            if (
                getattr(entity_entry, "platform", None) != DOMAIN
                or getattr(entity_entry, "domain", None) != "sensor"
                or not unique_id.startswith(entry_prefix)
                or unique_id.startswith(f"{config_entry.entry_id}-device-")
                or unique_id.startswith(f"{config_entry.entry_id}-mesh-")
            ):
                continue
            if unique_id.endswith(("-mac", "-hostname", "-up_speed", "-down_speed")):
                entity_registry.async_remove(entity_entry.entity_id)

    def _active_wan_interface_sensor_unique_ids() -> set[str]:
        """Return per-WAN sensor unique IDs that still have live coordinator values."""
        if module_available(device_model, MODULE_WAN_INTERFACES, coordinator.data) is False:
            return set()

        active_unique_ids: set[str] = set()
        for interface_key, interface_data in _wan_interfaces(coordinator).items():
            for description in WAN_INTERFACE_SENSOR_TYPES:
                data_entry = interface_data.get(description.key)
                if not isinstance(data_entry, dict) or data_entry.get("value") in (None, ""):
                    continue
                active_unique_ids.add(
                    f"{config_entry.entry_id}-{MODULE_WAN_INTERFACES}-{interface_key}-{description.key}"
                )
        return active_unique_ids

    def _remove_stale_wan_interface_sensors() -> None:
        """Remove per-WAN sensors for interfaces or values no longer reported."""
        active_unique_ids = _active_wan_interface_sensor_unique_ids()
        unique_id_prefix = f"{config_entry.entry_id}-{MODULE_WAN_INTERFACES}-"
        for entity_entry in list(entity_registry.entities.values()):
            unique_id = getattr(entity_entry, "unique_id", "") or ""
            if (
                getattr(entity_entry, "platform", None) != DOMAIN
                or getattr(entity_entry, "domain", None) != "sensor"
                or not unique_id.startswith(unique_id_prefix)
                or unique_id in active_unique_ids
            ):
                continue
            entity_registry.async_remove(entity_entry.entity_id)

    def _append_entity(entity: SensorEntity) -> None:
        """Append entity once per unique ID."""
        unique_id = entity.unique_id
        if unique_id and unique_id in seen_unique_ids:
            return
        if unique_id:
            seen_unique_ids.add(unique_id)
        entities.append(entity)

    def _wan_interface_sensor_entities() -> list[SensorEntity]:
        """Build newly discovered per-WAN sensors."""
        if module_available(device_model, MODULE_WAN_INTERFACES, coordinator.data) is False:
            return []

        new_entities: list[SensorEntity] = []
        for interface_key in sorted(_wan_interfaces(coordinator)):
            interface_data = _wan_interfaces(coordinator)[interface_key]
            for description in WAN_INTERFACE_SENSOR_TYPES:
                data_entry = interface_data.get(description.key)
                if not isinstance(data_entry, dict) or data_entry.get("value") in (None, ""):
                    continue

                entity = CudyRouterWanInterfaceSensor(
                    coordinator,
                    interface_key,
                    description,
                )
                unique_id = entity.unique_id
                if unique_id and unique_id in seen_unique_ids:
                    continue
                if unique_id:
                    seen_unique_ids.add(unique_id)
                new_entities.append(entity)

        return new_entities

    # Clean up stale WAN entities that are known duplicates or have no value.
    wan_data = coordinator.data.get(MODULE_WAN, {}) if coordinator.data else {}
    for sensor_key in _WAN_REMOVED_SENSOR_KEYS:
        _remove_sensor_by_unique_id(f"{config_entry.entry_id}-{MODULE_WAN}-{sensor_key}")
    _remove_sensor_by_unique_id(f"{config_entry.entry_id}-sms-messages")
    for sensor_key in _WAN_DUPLICATE_MODEM_KEYS:
        if _module_entry_has_value(coordinator.data, MODULE_MODEM, sensor_key):
            _remove_sensor_by_unique_id(f"{config_entry.entry_id}-{MODULE_WAN}-{sensor_key}")
    for sensor_key in ("subnet_mask", "gateway", "dns"):
        if isinstance(wan_data, dict) and wan_data.get(sensor_key, {}).get("value") in (None, ""):
            _remove_sensor_by_unique_id(f"{config_entry.entry_id}-{MODULE_WAN}-{sensor_key}")
    load_balancing_data = coordinator.data.get(MODULE_LOAD_BALANCING, {}) if coordinator.data else {}
    if isinstance(load_balancing_data, dict):
        for sensor_key in _LOAD_BALANCING_DYNAMIC_KEYS:
            if load_balancing_data.get(sensor_key, {}).get("value") in (None, ""):
                _remove_sensor_by_unique_id(f"{config_entry.entry_id}-{MODULE_LOAD_BALANCING}-{sensor_key}")
    _remove_legacy_manual_device_sensors()
    _remove_stale_wan_interface_sensors()

    # Add sensors based on available data from coordinator
    if coordinator.data:
        for module, sensors in coordinator.data.items():
            if not isinstance(sensors, dict):
                continue
            if module == MODULE_WAN_INTERFACES:
                continue

            for sensor_label in sensors:
                if module_available(device_model, module, coordinator.data) is False:
                    continue

                data_entry = sensors.get(sensor_label)
                if (
                    module == MODULE_WAN
                    and sensor_label in _WAN_DUPLICATE_MODEM_KEYS
                    and _module_entry_has_value(coordinator.data, MODULE_MODEM, sensor_label)
                ):
                    continue
                if isinstance(data_entry, dict) and data_entry.get("value") in (None, ""):
                    continue

                sensor_description = SENSOR_TYPES.get((module, sensor_label))
                if sensor_description:
                    _append_entity(
                        CudyRouterSensor(
                            coordinator,
                            router_name,
                            sensor_label,
                            sensor_description,
                        )
                    )

    entities.extend(_wan_interface_sensor_entities())

    # Always add signal and network sensors
    modem_data = coordinator.data.get(MODULE_MODEM, {}) if coordinator.data else {}
    signal_value = modem_data.get("signal", {}).get("value") if isinstance(modem_data, dict) else None
    network_value = modem_data.get("network", {}).get("value") if isinstance(modem_data, dict) else None
    if (
        module_available(device_model, MODULE_MODEM, coordinator.data) is True
        and signal_value not in (None, "")
    ):
        _append_entity(CudyRouterSignalSensor(coordinator, router_name, "signal", SIGNAL_SENSOR))

    if (
        module_available(device_model, MODULE_MODEM, coordinator.data) is True
        and network_value not in (None, "")
    ):
        _append_entity(CudyRouterSignalSensor(coordinator, router_name, "network", NETWORK_SENSOR))

    # Add device-specific sensors based on options
    options = config_entry.options
    auto_add_connected_devices = options.get(OPTIONS_AUTO_ADD_CONNECTED_DEVICES, True) if options else True
    connected_devices = _connected_devices(coordinator)
    connected_devices_by_mac = connected_device_lookup(connected_devices)
    known_clients = known_client_devices(hass, config_entry)
    if auto_add_connected_devices:
        allowed_client_macs = set(connected_devices_by_mac)
    else:
        allowed_client_macs = manual_allowed_client_macs(
            connected_devices=connected_devices,
            device_list=options.get(OPTIONS_DEVICELIST) if options else None,
            known_clients=known_clients,
        )

    async_cleanup_stale_client_entities(
        hass,
        config_entry,
        "sensor",
        allowed_client_macs,
    )

    for normalized_mac in sorted(allowed_client_macs):
        device = build_client_seed_device(
            normalized_mac,
            connected_devices_by_mac,
            known_clients.get(normalized_mac, {}).get("name"),
        )
        for description in (
            DEVICE_IP_SENSOR,
            DEVICE_CONNECTION_TYPE_SENSOR,
            DEVICE_SIGNAL_DETAILS_SENSOR,
            DEVICE_ONLINE_TIME_SENSOR,
        ):
            _append_entity(
                CudyRouterConnectedDeviceSensor(
                    coordinator,
                    config_entry,
                    device,
                    description,
                )
            )

    # Add mesh device sensors
    # NOTE: Satellite mesh devices often only have name and status available.
    # Firmware, IP, and model may show as Unknown due to Cudy router limitations.
    if coordinator.data and module_available(device_model, MODULE_MESH, coordinator.data) is True:
        mesh_data = coordinator.data.get(MODULE_MESH, {})
        _LOGGER.debug("Mesh data for sensors: %s", mesh_data)
        mesh_devices = mesh_data.get("mesh_devices", {})
        async_cleanup_stale_mesh_entities(
            hass,
            config_entry,
            "sensor",
            set(mesh_devices),
        )
        _LOGGER.debug("Mesh devices found for sensors: %d devices", len(mesh_devices))
        for mesh_mac, mesh_device in mesh_devices.items():
            _LOGGER.debug(
                "Creating sensors for mesh device: %s (MAC: %s)",
                mesh_device.get("name"),
                mesh_mac,
            )
            _append_entity(
                CudyRouterMeshDeviceSensor(
                    coordinator,
                    mesh_mac,
                    mesh_device,
                    MESH_DEVICE_NAME_SENSOR,
                )
            )
            _append_entity(
                CudyRouterMeshDeviceSensor(
                    coordinator,
                    mesh_mac,
                    mesh_device,
                    MESH_DEVICE_MODEL_SENSOR,
                )
            )
            _append_entity(
                CudyRouterMeshDeviceSensor(
                    coordinator,
                    mesh_mac,
                    mesh_device,
                    MESH_DEVICE_MAC_SENSOR,
                )
            )
            _append_entity(
                CudyRouterMeshDeviceSensor(
                    coordinator,
                    mesh_mac,
                    mesh_device,
                    MESH_DEVICE_FIRMWARE_SENSOR,
                )
            )
            _append_entity(
                CudyRouterMeshDeviceSensor(
                    coordinator,
                    mesh_mac,
                    mesh_device,
                    MESH_DEVICE_STATUS_SENSOR,
                )
            )
            _append_entity(
                CudyRouterMeshDeviceSensor(
                    coordinator,
                    mesh_mac,
                    mesh_device,
                    MESH_DEVICE_IP_SENSOR,
                )
            )
            _append_entity(
                CudyRouterMeshDeviceSensor(
                    coordinator,
                    mesh_mac,
                    mesh_device,
                    MESH_DEVICE_CONNECTED_SENSOR,
                )
            )
            _append_entity(
                CudyRouterMeshDeviceSensor(
                    coordinator,
                    mesh_mac,
                    mesh_device,
                    MESH_DEVICE_HARDWARE_SENSOR,
                )
            )
            _append_entity(
                CudyRouterMeshDeviceSensor(
                    coordinator,
                    mesh_mac,
                    mesh_device,
                    MESH_DEVICE_BACKHAUL_SENSOR,
                )
            )

    @callback
    def _add_new_wan_interface_sensors() -> None:
        """Add per-WAN sensors if a later refresh discovers another interface."""
        new_entities = _wan_interface_sensor_entities()
        if new_entities:
            async_add_entities(new_entities)

    config_entry.async_on_unload(coordinator.async_add_listener(_add_new_wan_interface_sensors))
    async_add_entities(entities)


class CudyRouterWanInterfaceSensor(
    CoordinatorEntity[CudyRouterDataUpdateCoordinator], SensorEntity
):
    """Sensor backed by a specific WAN interface payload."""

    _attr_has_entity_name = True
    entity_description: CudyRouterSensorEntityDescription

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        interface_key: str,
        description: CudyRouterSensorEntityDescription,
    ) -> None:
        """Initialize the per-WAN sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._interface_key = interface_key
        self._attr_name = f"{_wan_interface_label(interface_key)} {description.name_suffix}"
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}-{MODULE_WAN_INTERFACES}-{interface_key}-{description.key}"
        )
        self._attr_device_info = build_router_device_info(coordinator)

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        interface_data = _wan_interfaces(self.coordinator).get(self._interface_key, {})
        data_entry = interface_data.get(self.entity_description.key)
        if not isinstance(data_entry, dict):
            return None
        return data_entry.get("value")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        interface_data = _wan_interfaces(self.coordinator).get(self._interface_key, {})
        data_entry = interface_data.get(self.entity_description.key)
        if not isinstance(data_entry, dict):
            return {}
        return data_entry.get("attributes", {})


class CudyRouterConnectedDeviceSensor(
    CoordinatorEntity[CudyRouterDataUpdateCoordinator], SensorEntity
):
    """Sensor backed by the live connected-device list."""

    _attr_has_entity_name = True
    entity_description: CudyRouterSensorEntityDescription

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        config_entry: ConfigEntry,
        device: dict[str, Any],
        description: CudyRouterSensorEntityDescription,
    ) -> None:
        """Initialize the connected-device sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._normalized_mac = (device.get("mac") or "").replace(":", "").replace("-", "").lower()
        self._fallback_device = device
        self._attr_name = description.name_suffix
        self._attr_unique_id = (
            f"{config_entry.entry_id}-device-{self._normalized_mac}-{description.key}"
        )
        self._attr_device_info = build_client_device_info(config_entry, device)

    def _current_device(self) -> dict[str, Any]:
        """Return the latest device payload."""
        for device in _connected_devices(self.coordinator):
            current_mac = (device.get("mac") or "").replace(":", "").replace("-", "").lower()
            if current_mac == self._normalized_mac:
                return device
        return self._fallback_device

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self._current_device().get(self.entity_description.key)

    @property
    def available(self) -> bool:
        """Report availability based on current device presence."""
        return any(
            (device.get("mac") or "").replace(":", "").replace("-", "").lower() == self._normalized_mac
            for device in _connected_devices(self.coordinator)
        )


class CudyRouterMeshDeviceSensor(CoordinatorEntity[CudyRouterDataUpdateCoordinator], SensorEntity):
    """Implementation of a Cudy Router mesh device sensor."""

    _attr_has_entity_name = True
    entity_description: CudyRouterSensorEntityDescription

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        mesh_mac: str,
        mesh_device: dict[str, Any],
        description: CudyRouterSensorEntityDescription,
    ) -> None:
        """Initialize the mesh device sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._mesh_mac = mesh_mac
        self._mesh_name = mesh_display_name(mesh_device.get("name"), mesh_mac)
        self._attr_name = description.name_suffix
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}-mesh-{mesh_mac}-{description.key}"
        self._attr_device_info = build_mesh_device_info(coordinator, mesh_mac, mesh_device)

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        mesh_data = self.coordinator.data.get(MODULE_MESH, {})
        mesh_devices = mesh_data.get("mesh_devices", {})
        device = mesh_devices.get(self._mesh_mac)
        if not device:
            return None
        return device.get(self.entity_description.key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}
        mesh_data = self.coordinator.data.get(MODULE_MESH, {})
        mesh_devices = mesh_data.get("mesh_devices", {})
        device = mesh_devices.get(self._mesh_mac)
        if not device:
            return {}
        # Return all mesh device info as attributes
        return {
            "mac_address": device.get("mac_address"),
            "model": device.get("model"),
            "hardware": device.get("hardware"),
            "firmware_version": device.get("firmware_version"),
            "status": device.get("status"),
            "ip_address": device.get("ip_address"),
            "backhaul": device.get("backhaul"),
        }


class CudyRouterSensor(CoordinatorEntity[CudyRouterDataUpdateCoordinator], SensorEntity):
    """Implementation of a Cudy Router sensor."""

    _attr_has_entity_name = True
    entity_description: CudyRouterSensorEntityDescription

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        router_name: str | None,
        sensor_key: str,
        description: CudyRouterSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._sensor_key = sensor_key
        self._attr_name = description.name_suffix
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}-{description.module}-{description.key}"
        self._attr_device_info = build_router_device_info(coordinator)

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        module_data = self.coordinator.data.get(self.entity_description.module, {})
        data_entry = module_data.get(self.entity_description.key)
        if data_entry is None:
            return None
        return data_entry.get("value")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}
        module_data = self.coordinator.data.get(self.entity_description.module, {})
        data_entry = module_data.get(self.entity_description.key)
        if data_entry is None:
            return {}
        return data_entry.get("attributes", {})


class CudyRouterSignalSensor(CudyRouterSensor):
    """Implementation of a Cudy Router sensor with dynamic icon."""

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        data = self.coordinator.data
        if not data:
            self._attr_icon = "mdi:network-strength-off-outline"
        else:
            modem_data = data.get(MODULE_MODEM, {})
            signal_data = modem_data.get("signal", {})
            value = signal_data.get("value") if signal_data else None
            if not isinstance(value, (int, float)):
                self._attr_icon = "mdi:network-strength-off-outline"
            elif value <= 0:
                self._attr_icon = "mdi:network-strength-off-outline"
            elif value == 1:
                self._attr_icon = "mdi:network-strength-1"
            elif value == 2:
                self._attr_icon = "mdi:network-strength-2"
            elif value == 3:
                self._attr_icon = "mdi:network-strength-3"
            elif value >= 4:
                self._attr_icon = "mdi:network-strength-4"
            else:
                self._attr_icon = "mdi:network-strength-outline"
        super()._handle_coordinator_update()
