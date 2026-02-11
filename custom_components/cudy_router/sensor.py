"""Support for Cudy Router Sensor Platform."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_MODEL,
    SIGNAL_STRENGTH_DECIBELS,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MODULE_DEVICES,
    MODULE_DHCP,
    MODULE_MESH,
    MODULE_MODEM,
    MODULE_VPN,
    MODULE_WAN,
    OPTIONS_DEVICELIST,
    SECTION_DETAILED,
)
from .coordinator import CudyRouterDataUpdateCoordinator
from .features import existing_feature

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class CudyRouterSensorEntityDescription(SensorEntityDescription):
    """Describe Cudy Router sensor entity."""

    module: str
    name_suffix: str


SIGNAL_SENSOR = CudyRouterSensorEntityDescription(
    key="signal",
    module="modem",
    name_suffix="Signal strength",
    state_class=SensorStateClass.MEASUREMENT,
)

NETWORK_SENSOR = CudyRouterSensorEntityDescription(
    key="network",
    module="modem",
    name_suffix="Network",
)

SENSOR_TYPES: dict[tuple[str, str], CudyRouterSensorEntityDescription] = {
    ("modem", "sim"): CudyRouterSensorEntityDescription(
        key="sim",
        device_class=SensorDeviceClass.ENUM,
        options=["Sim 1", "Sim 2"],
        module="modem",
        name_suffix="SIM slot",
    ),
    ("modem", "connected_time"): CudyRouterSensorEntityDescription(
        key="connected_time",
        module="modem",
        name_suffix="Connected time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("modem", "cell"): CudyRouterSensorEntityDescription(
        key="cell",
        module="modem",
        name_suffix="Cell information",
    ),
    ("modem", "rsrp"): CudyRouterSensorEntityDescription(
        key="rsrp",
        module="modem",
        name_suffix="RSRP",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("modem", "rsrq"): CudyRouterSensorEntityDescription(
        key="rsrq",
        module="modem",
        name_suffix="RSRQ",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("modem", "sinr"): CudyRouterSensorEntityDescription(
        key="sinr",
        module="modem",
        name_suffix="SINR",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("modem", "rssi"): CudyRouterSensorEntityDescription(
        key="rssi",
        module="modem",
        name_suffix="RSSI",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("modem", "band"): CudyRouterSensorEntityDescription(
        key="band",
        module="modem",
        name_suffix="Band",
    ),
    ("devices", "device_count"): CudyRouterSensorEntityDescription(
        key="device_count",
        module="devices",
        name_suffix="Device count",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("devices", "top_downloader_speed"): CudyRouterSensorEntityDescription(
        key="top_downloader_speed",
        module="devices",
        name_suffix="Top downloader speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:star-check",
    ),
    ("devices", "top_downloader_mac"): CudyRouterSensorEntityDescription(
        key="top_downloader_mac",
        module="devices",
        name_suffix="Top downloader MAC",
        icon="mdi:star-check",
    ),
    ("devices", "top_downloader_hostname"): CudyRouterSensorEntityDescription(
        key="top_downloader_hostname",
        module="devices",
        name_suffix="Top downloader hostname",
        icon="mdi:star-check",
    ),
    ("devices", "top_uploader_speed"): CudyRouterSensorEntityDescription(
        key="top_uploader_speed",
        module="devices",
        name_suffix="Top uploader speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:star-check-outline",
    ),
    ("devices", "top_uploader_mac"): CudyRouterSensorEntityDescription(
        key="top_uploader_mac",
        module="devices",
        name_suffix="Top uploader MAC",
        icon="mdi:star-check-outline",
    ),
    ("devices", "top_uploader_hostname"): CudyRouterSensorEntityDescription(
        key="top_uploader_hostname",
        module="devices",
        name_suffix="Top uploader hostname",
        icon="mdi:star-check-outline",
    ),
    ("devices", "total_down_speed"): CudyRouterSensorEntityDescription(
        key="total_down_speed",
        module="devices",
        name_suffix="Total download speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("devices", "total_up_speed"): CudyRouterSensorEntityDescription(
        key="total_up_speed",
        module="devices",
        name_suffix="Total upload speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # New modem sensors
    ("modem", "public_ip"): CudyRouterSensorEntityDescription(
        key="public_ip",
        module="modem",
        name_suffix="Public IP",
    ),
    ("modem", "wan_ip"): CudyRouterSensorEntityDescription(
        key="wan_ip",
        module="modem",
        name_suffix="WAN IP",
    ),
    ("modem", "imei"): CudyRouterSensorEntityDescription(
        key="imei",
        module="modem",
        name_suffix="IMEI",
    ),
    ("modem", "imsi"): CudyRouterSensorEntityDescription(
        key="imsi",
        module="modem",
        name_suffix="IMSI",
    ),
    ("modem", "iccid"): CudyRouterSensorEntityDescription(
        key="iccid",
        module="modem",
        name_suffix="ICCID",
    ),
    ("modem", "mode"): CudyRouterSensorEntityDescription(
        key="mode",
        module="modem",
        name_suffix="Mode",
    ),
    ("modem", "bandwidth"): CudyRouterSensorEntityDescription(
        key="bandwidth",
        module="modem",
        name_suffix="Bandwidth",
    ),
    ("modem", "session_upload"): CudyRouterSensorEntityDescription(
        key="session_upload",
        module="modem",
        name_suffix="Session upload",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    ("modem", "session_download"): CudyRouterSensorEntityDescription(
        key="session_download",
        module="modem",
        name_suffix="Session download",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # New wan sensors
    (MODULE_WAN, "protocol"): CudyRouterSensorEntityDescription(
        key="protocol",
        module=MODULE_WAN,
        name_suffix="Protocol",
        icon="mdi:protocol",
    ),
    (MODULE_WAN, "connected_time"): CudyRouterSensorEntityDescription(
        key="connected_time",
        module=MODULE_WAN,
        name_suffix="Connected time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    (MODULE_WAN, "mac_address"): CudyRouterSensorEntityDescription(
        key="mac_address",
        module=MODULE_WAN,
        name_suffix="WAN MAC",
        icon="mdi:wan",
    ),
    (MODULE_WAN, "public_ip"): CudyRouterSensorEntityDescription(
        key="public_ip",
        module=MODULE_WAN,
        name_suffix="Public IP",
        icon="mdi:ip",
    ),
    (MODULE_WAN, "wan_ip"): CudyRouterSensorEntityDescription(
        key="wan_ip",
        module=MODULE_WAN,
        name_suffix="WAN IP",
        icon="mdi:ip",
    ),
    (MODULE_WAN, "subnet_mask"): CudyRouterSensorEntityDescription(
        key="subnet_mask",
        module=MODULE_WAN,
        name_suffix="Subnet mask",
        icon="mdi:ip",
    ),
    (MODULE_WAN, "gateway"): CudyRouterSensorEntityDescription(
        key="gateway",
        module=MODULE_WAN,
        name_suffix="Gateway",
        icon="mdi:router-network",
    ),
    (MODULE_WAN, "dns"): CudyRouterSensorEntityDescription(
        key="dns",
        module=MODULE_WAN,
        name_suffix="DNS",
        icon="mdi:dns",
    ),
    (MODULE_WAN, "session_upload"): CudyRouterSensorEntityDescription(
        key="session_upload",
        module=MODULE_WAN,
        name_suffix="Session upload",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    (MODULE_WAN, "session_download"): CudyRouterSensorEntityDescription(
        key="session_download",
        module=MODULE_WAN,
        name_suffix="Session download",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # System sensors
    ("system", "uptime"): CudyRouterSensorEntityDescription(
        key="uptime",
        module="system",
        name_suffix="Uptime",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("system", "local_time"): CudyRouterSensorEntityDescription(
        key="local_time",
        module="system",
        name_suffix="Local time",
        icon="mdi:clock",
    ),
    ("system", "firmware_version"): CudyRouterSensorEntityDescription(
        key="firmware_version",
        module="system",
        name_suffix="Firmware version",
        icon="mdi:label",
    ),
    # Data usage sensors
    ("data_usage", "current_traffic"): CudyRouterSensorEntityDescription(
        key="current_traffic",
        module="data_usage",
        name_suffix="Current session traffic",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    ("data_usage", "monthly_traffic"): CudyRouterSensorEntityDescription(
        key="monthly_traffic",
        module="data_usage",
        name_suffix="Monthly traffic",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    ("data_usage", "total_traffic"): CudyRouterSensorEntityDescription(
        key="total_traffic",
        module="data_usage",
        name_suffix="Total traffic",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # SMS sensors
    ("sms", "inbox_count"): CudyRouterSensorEntityDescription(
        key="inbox_count",
        module="sms",
        name_suffix="SMS inbox",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("sms", "outbox_count"): CudyRouterSensorEntityDescription(
        key="outbox_count",
        module="sms",
        name_suffix="SMS outbox",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ("sms", "unread_count"): CudyRouterSensorEntityDescription(
        key="unread_count",
        module="sms",
        name_suffix="SMS unread",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # WiFi 2.4G sensors
    ("wifi_2g", "ssid"): CudyRouterSensorEntityDescription(
        key="ssid",
        module="wifi_2g",
        name_suffix="WiFi 2.4G SSID",
        icon="mdi:wifi",
    ),
    ("wifi_2g", "channel"): CudyRouterSensorEntityDescription(
        key="channel",
        module="wifi_2g",
        name_suffix="WiFi 2.4G channel",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wifi",
    ),
    # WiFi 5G sensors
    ("wifi_5g", "ssid"): CudyRouterSensorEntityDescription(
        key="ssid",
        module="wifi_5g",
        name_suffix="WiFi 5G SSID",
        icon="mdi:wifi",
    ),
    ("wifi_5g", "channel"): CudyRouterSensorEntityDescription(
        key="channel",
        module="wifi_5g",
        name_suffix="WiFi 5G channel",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:wifi",
    ),
    # LAN sensors
    ("lan", "ip_address"): CudyRouterSensorEntityDescription(
        key="ip_address",
        module="lan",
        name_suffix="LAN IP",
        icon="mdi:ip",
    ),
    ("lan", "mac_address"): CudyRouterSensorEntityDescription(
        key="mac_address",
        module="lan",
        name_suffix="LAN MAC",
        icon="mdi:lan",
    ),
    # Devices status sensors (client counts)
    ("devices", "wifi_2g_clients"): CudyRouterSensorEntityDescription(
        key="wifi_2g_clients",
        module="devices",
        name_suffix="WiFi 2.4G clients",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:account",
    ),
    ("devices", "wifi_5g_clients"): CudyRouterSensorEntityDescription(
        key="wifi_5g_clients",
        module="devices",
        name_suffix="WiFi 5G clients",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:account",
    ),
    ("devices", "wired_clients"): CudyRouterSensorEntityDescription(
        key="wired_clients",
        module="devices",
        name_suffix="Wired clients",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:account",
    ),
    ("devices", "total_clients"): CudyRouterSensorEntityDescription(
        key="total_clients",
        module="devices",
        name_suffix="Total clients",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:account-group",
    ),
    # Mesh sensors
    ("mesh", "mesh_count"): CudyRouterSensorEntityDescription(
        key="mesh_count",
        module="mesh",
        name_suffix="Mesh devices",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:table-network",
    ),
    (MODULE_VPN, "protocol"): CudyRouterSensorEntityDescription(
        key="protocol",
        module=MODULE_VPN,
        name_suffix="VPN protocol",
        icon="mdi:protocol",
    ),
    (MODULE_VPN, "vpn_clients"): CudyRouterSensorEntityDescription(
        key="vpn_clients",
        module=MODULE_VPN,
        name_suffix="VPN clients",
        icon="mdi:account-star",
    ),
    (MODULE_DHCP, "dhcp_ip_start"): CudyRouterSensorEntityDescription(
        key="dhcp_ip_start",
        module=MODULE_DHCP,
        name_suffix="IP Start",
        icon="mdi:ip",
    ),
    (MODULE_DHCP, "dhcp_ip_end"): CudyRouterSensorEntityDescription(
        key="dhcp_ip_end",
        module=MODULE_DHCP,
        name_suffix="IP End",
        icon="mdi:ip",
    ),
    (MODULE_DHCP, "dhcp_prefered_dns"): CudyRouterSensorEntityDescription(
        key="dhcp_prefered_dns",
        module=MODULE_DHCP,
        name_suffix="Preferred DNS",
        icon="mdi:dns",
    ),
    (MODULE_DHCP, "dhcp_default_gateway"): CudyRouterSensorEntityDescription(
        key="dhcp_default_gateway",
        module=MODULE_DHCP,
        name_suffix="Default Gateway",
        icon="mdi:router-network",
    ),
    (MODULE_DHCP, "dhcp_leasetime"): CudyRouterSensorEntityDescription(
        key="dhcp_leasetime",
        module=MODULE_DHCP,
        name_suffix="Leasetime",
        icon="mdi:timer",
    ),
}

DEVICE_MAC_SENSOR = CudyRouterSensorEntityDescription(
    key="mac",
    module="devices",
    name_suffix="MAC",
)

DEVICE_HOSTNAME_SENSOR = CudyRouterSensorEntityDescription(
    key="hostname",
    module="devices",
    name_suffix="Hostname",
)

DEVICE_UPLOAD_SENSOR = CudyRouterSensorEntityDescription(
    key="up_speed",
    module="devices",
    name_suffix="Upload speed",
    device_class=SensorDeviceClass.DATA_RATE,
    native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
    state_class=SensorStateClass.MEASUREMENT,
)

DEVICE_DOWNLOAD_SENSOR = CudyRouterSensorEntityDescription(
    key="down_speed",
    module="devices",
    name_suffix="Download speed",
    device_class=SensorDeviceClass.DATA_RATE,
    native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
    state_class=SensorStateClass.MEASUREMENT,
)

# Mesh device sensor descriptions

MESH_DEVICE_NAME_SENSOR = CudyRouterSensorEntityDescription(
    key="name",
    module="mesh",
    name_suffix="Name",
)

MESH_DEVICE_MODEL_SENSOR = CudyRouterSensorEntityDescription(
    key="model",
    module="mesh",
    name_suffix="Model",
)

MESH_DEVICE_MAC_SENSOR = CudyRouterSensorEntityDescription(
    key="mac_address",
    module="mesh",
    name_suffix="MAC address",
)

MESH_DEVICE_FIRMWARE_SENSOR = CudyRouterSensorEntityDescription(
    key="firmware_version",
    module="mesh",
    name_suffix="Firmware",
)

MESH_DEVICE_STATUS_SENSOR = CudyRouterSensorEntityDescription(
    key="status",
    module="mesh",
    name_suffix="Status",
    device_class=SensorDeviceClass.ENUM,
    options=["online", "offline"],
)

MESH_DEVICE_IP_SENSOR = CudyRouterSensorEntityDescription(
    key="ip_address",
    module="mesh",
    name_suffix="IP address",
    icon="mdi:ip",
)

MESH_DEVICE_CONNECTED_SENSOR = CudyRouterSensorEntityDescription(
    key="connected_devices",
    module="mesh",
    name_suffix="Connected devices",
    state_class=SensorStateClass.MEASUREMENT,
)


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
