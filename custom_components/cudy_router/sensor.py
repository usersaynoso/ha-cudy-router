"""Support for Cudy Router Sensor Platform."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MODEL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MODULE_DEVICES,
    MODULE_MESH,
    MODULE_MODEM,
    OPTIONS_DEVICELIST,
    SECTION_DETAILED,
)
from .coordinator import CudyRouterDataUpdateCoordinator
from .features import existing_feature
from .sensor_descriptions import (
    CudyRouterSensorEntityDescription,
    DEVICE_DOWNLOAD_SENSOR,
    DEVICE_HOSTNAME_SENSOR,
    DEVICE_MAC_SENSOR,
    DEVICE_UPLOAD_SENSOR,
    MESH_DEVICE_CONNECTED_SENSOR,
    MESH_DEVICE_FIRMWARE_SENSOR,
    MESH_DEVICE_IP_SENSOR,
    MESH_DEVICE_MAC_SENSOR,
    MESH_DEVICE_MODEL_SENSOR,
    MESH_DEVICE_NAME_SENSOR,
    MESH_DEVICE_STATUS_SENSOR,
    NETWORK_SENSOR,
    SENSOR_TYPES,
    SIGNAL_SENSOR,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Cudy Router sensors."""
    coordinator: CudyRouterDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    # Use mesh main_router_name, or default to "Cudy Router"
    mesh_data = coordinator.data.get(MODULE_MESH, {}) if coordinator.data else {}
    main_router_mesh_name = mesh_data.get("main_router_name")

    # Priority: mesh main_router_name > "Cudy Router"
    router_name = main_router_mesh_name or "Cudy Router"

    entities: list[SensorEntity] = []

    _LOGGER.debug(
        "Setting up Cudy Router sensors, coordinator.data keys: %s",
        list(coordinator.data.keys()) if coordinator.data else "None",
    )

    device_model: str = config_entry.data.get(CONF_MODEL, "default")

    # Add sensors based on available data from coordinator
    if coordinator.data:
        for module, sensors in coordinator.data.items():
            if not isinstance(sensors, dict):
                continue

            for sensor_label in sensors:
                if existing_feature(device_model, module) is False:
                    continue
                sensor_description = SENSOR_TYPES.get((module, sensor_label))
                if sensor_description:
                    entities.append(
                        CudyRouterSensor(
                            coordinator,
                            router_name,
                            sensor_label,
                            sensor_description,
                        )
                    )

    # Always add signal and network sensors
    if existing_feature(device_model, "modem", "signal") is True:
        entities.append(CudyRouterSignalSensor(coordinator, router_name, "signal", SIGNAL_SENSOR))

    if existing_feature(device_model, "modem", "network") is True:
        entities.append(CudyRouterSignalSensor(coordinator, router_name, "network", NETWORK_SENSOR))

    # Add device-specific sensors based on options
    options = config_entry.options
    device_list_str = options.get(OPTIONS_DEVICELIST, "") if options else ""
    device_list = [x.strip() for x in device_list_str.split(",") if x.strip()]

    for device_id in device_list:
        entities.extend(
            [
                CudyRouterDeviceSensor(coordinator, router_name, device_id, DEVICE_MAC_SENSOR),
                CudyRouterDeviceSensor(coordinator, router_name, device_id, DEVICE_HOSTNAME_SENSOR),
                CudyRouterDeviceSensor(coordinator, router_name, device_id, DEVICE_UPLOAD_SENSOR),
                CudyRouterDeviceSensor(coordinator, router_name, device_id, DEVICE_DOWNLOAD_SENSOR),
            ]
        )

    # Add mesh device sensors
    # NOTE: Satellite mesh devices often only have name and status available.
    # Firmware, IP, and model may show as Unknown due to Cudy router limitations.
    if coordinator.data and existing_feature(device_model, MODULE_MESH) is True:
        mesh_data = coordinator.data.get(MODULE_MESH, {})
        _LOGGER.debug("Mesh data for sensors: %s", mesh_data)
        mesh_devices = mesh_data.get("mesh_devices", {})
        _LOGGER.debug("Mesh devices found for sensors: %d devices", len(mesh_devices))
        for mesh_mac, mesh_device in mesh_devices.items():
            _LOGGER.debug(
                "Creating sensors for mesh device: %s (MAC: %s)",
                mesh_device.get("name"),
                mesh_mac,
            )
            # Create a friendly name for the mesh device
            mesh_name = mesh_device.get("name") or mesh_mac
            entities.extend(
                [
                    CudyRouterMeshDeviceSensor(
                        coordinator,
                        router_name,
                        mesh_mac,
                        mesh_name,
                        MESH_DEVICE_NAME_SENSOR,
                    ),
                    CudyRouterMeshDeviceSensor(
                        coordinator,
                        router_name,
                        mesh_mac,
                        mesh_name,
                        MESH_DEVICE_MODEL_SENSOR,
                    ),
                    CudyRouterMeshDeviceSensor(
                        coordinator,
                        router_name,
                        mesh_mac,
                        mesh_name,
                        MESH_DEVICE_MAC_SENSOR,
                    ),
                    CudyRouterMeshDeviceSensor(
                        coordinator,
                        router_name,
                        mesh_mac,
                        mesh_name,
                        MESH_DEVICE_FIRMWARE_SENSOR,
                    ),
                    CudyRouterMeshDeviceSensor(
                        coordinator,
                        router_name,
                        mesh_mac,
                        mesh_name,
                        MESH_DEVICE_STATUS_SENSOR,
                    ),
                    CudyRouterMeshDeviceSensor(
                        coordinator,
                        router_name,
                        mesh_mac,
                        mesh_name,
                        MESH_DEVICE_IP_SENSOR,
                    ),
                    CudyRouterMeshDeviceSensor(
                        coordinator,
                        router_name,
                        mesh_mac,
                        mesh_name,
                        MESH_DEVICE_CONNECTED_SENSOR,
                    ),
                ]
            )

    async_add_entities(entities)


class CudyRouterDeviceSensor(CoordinatorEntity[CudyRouterDataUpdateCoordinator], SensorEntity):
    """Implementation of a Cudy Router device sensor."""

    _attr_has_entity_name = True
    entity_description: CudyRouterSensorEntityDescription

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        router_name: str | None,
        device_id: str,
        description: CudyRouterSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device_id = device_id
        self._attr_name = f"{device_id} {description.name_suffix}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}-{device_id}-{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            manufacturer="Cudy",
            name=router_name,
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        detailed = self.coordinator.data.get(MODULE_DEVICES, {}).get(SECTION_DETAILED)
        if not detailed:
            return None
        device = detailed.get(self._device_id)
        if not device:
            return None
        return device.get(self.entity_description.key)


class CudyRouterMeshDeviceSensor(CoordinatorEntity[CudyRouterDataUpdateCoordinator], SensorEntity):
    """Implementation of a Cudy Router mesh device sensor."""

    _attr_has_entity_name = True
    entity_description: CudyRouterSensorEntityDescription

    def __init__(
        self,
        coordinator: CudyRouterDataUpdateCoordinator,
        router_name: str | None,
        mesh_mac: str,
        mesh_name: str,
        description: CudyRouterSensorEntityDescription,
    ) -> None:
        """Initialize the mesh device sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._mesh_mac = mesh_mac
        self._mesh_name = mesh_name
        self._attr_name = f"{mesh_name} {description.name_suffix}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}-mesh-{mesh_mac}-{description.key}"
        # Create a separate device entry for each mesh node
        # Use just the mesh device name, not "Mesh <name>"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.config_entry.entry_id}-mesh-{mesh_mac}")},
            manufacturer="Cudy",
            name=mesh_name,
            via_device=(DOMAIN, coordinator.config_entry.entry_id),
        )

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
            "firmware_version": device.get("firmware_version"),
            "status": device.get("status"),
            "ip_address": device.get("ip_address"),
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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            manufacturer="Cudy",
            name=router_name,
        )

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
            if not value:
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
