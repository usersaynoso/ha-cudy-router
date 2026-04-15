"""Sensor descriptions for Cudy Router sensors."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.helpers.entity import EntityCategory

from .const import MODULE_DHCP, MODULE_LAN, MODULE_LOAD_BALANCING, MODULE_VPN, MODULE_WAN

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
    ("devices", "arp_br_lan_count"): CudyRouterSensorEntityDescription(
        key="arp_br_lan_count",
        module="devices",
        name_suffix="ARP br-lan count",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:table-network",
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
        name_suffix="WAN Subnet mask",
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
    (MODULE_WAN, "bytes_received"): CudyRouterSensorEntityDescription(
        key="bytes_received",
        module=MODULE_WAN,
        name_suffix="WAN bytes received",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    (MODULE_WAN, "bytes_sent"): CudyRouterSensorEntityDescription(
        key="bytes_sent",
        module=MODULE_WAN,
        name_suffix="WAN bytes sent",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
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
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ("system", "firmware_version"): CudyRouterSensorEntityDescription(
        key="firmware_version",
        module="system",
        name_suffix="Firmware version",
        icon="mdi:label",
        entity_category=EntityCategory.DIAGNOSTIC,
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
    (MODULE_LAN, "ip_address"): CudyRouterSensorEntityDescription(
        key="ip_address",
        module=MODULE_LAN,
        name_suffix="LAN IP",
        icon="mdi:ip",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (MODULE_LAN, "subnet_mask"): CudyRouterSensorEntityDescription(
        key="subnet_mask",
        module=MODULE_LAN,
        name_suffix="Subnet mask",
        icon="mdi:ip",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (MODULE_LAN, "mac_address"): CudyRouterSensorEntityDescription(
        key="mac_address",
        module=MODULE_LAN,
        name_suffix="LAN MAC",
        icon="mdi:lan",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    (MODULE_LAN, "bytes_received"): CudyRouterSensorEntityDescription(
        key="bytes_received",
        module=MODULE_LAN,
        name_suffix="Bytes received",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    (MODULE_LAN, "bytes_sent"): CudyRouterSensorEntityDescription(
        key="bytes_sent",
        module=MODULE_LAN,
        name_suffix="Bytes sent",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
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
        name_suffix="Mesh devices connected",
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
    (MODULE_VPN, "tunnel_ip"): CudyRouterSensorEntityDescription(
        key="tunnel_ip",
        module=MODULE_VPN,
        name_suffix="VPN tunnel IP",
        icon="mdi:ip",
    ),
    (MODULE_LOAD_BALANCING, "wan1_status"): CudyRouterSensorEntityDescription(
        key="wan1_status",
        module=MODULE_LOAD_BALANCING,
        name_suffix="Load balancing WAN1",
        icon="mdi:wan",
    ),
    (MODULE_LOAD_BALANCING, "wan4_status"): CudyRouterSensorEntityDescription(
        key="wan4_status",
        module=MODULE_LOAD_BALANCING,
        name_suffix="Load balancing WAN4",
        icon="mdi:wan",
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
    entity_category=EntityCategory.DIAGNOSTIC,
)

DEVICE_HOSTNAME_SENSOR = CudyRouterSensorEntityDescription(
    key="hostname",
    module="devices",
    name_suffix="Hostname",
    entity_category=EntityCategory.DIAGNOSTIC,
)

DEVICE_IP_SENSOR = CudyRouterSensorEntityDescription(
    key="ip",
    module="devices",
    name_suffix="IP address",
    icon="mdi:ip",
    entity_category=EntityCategory.DIAGNOSTIC,
)

DEVICE_CONNECTION_TYPE_SENSOR = CudyRouterSensorEntityDescription(
    key="connection_type",
    module="devices",
    name_suffix="Connection type",
    icon="mdi:lan-connect",
    entity_category=EntityCategory.DIAGNOSTIC,
)

DEVICE_SIGNAL_DETAILS_SENSOR = CudyRouterSensorEntityDescription(
    key="signal",
    module="devices",
    name_suffix="Signal",
    icon="mdi:wifi-strength-2",
    entity_category=EntityCategory.DIAGNOSTIC,
)

DEVICE_ONLINE_TIME_SENSOR = CudyRouterSensorEntityDescription(
    key="online_time",
    module="devices",
    name_suffix="Online time",
    icon="mdi:clock-outline",
    entity_category=EntityCategory.DIAGNOSTIC,
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
    entity_category=EntityCategory.DIAGNOSTIC,
)

MESH_DEVICE_MODEL_SENSOR = CudyRouterSensorEntityDescription(
    key="model",
    module="mesh",
    name_suffix="Model",
    entity_category=EntityCategory.DIAGNOSTIC,
)

MESH_DEVICE_MAC_SENSOR = CudyRouterSensorEntityDescription(
    key="mac_address",
    module="mesh",
    name_suffix="MAC address",
    entity_category=EntityCategory.DIAGNOSTIC,
)

MESH_DEVICE_FIRMWARE_SENSOR = CudyRouterSensorEntityDescription(
    key="firmware_version",
    module="mesh",
    name_suffix="Firmware",
    entity_category=EntityCategory.DIAGNOSTIC,
)

MESH_DEVICE_STATUS_SENSOR = CudyRouterSensorEntityDescription(
    key="status",
    module="mesh",
    name_suffix="Status",
    device_class=SensorDeviceClass.ENUM,
    options=["online", "offline"],
    entity_category=EntityCategory.DIAGNOSTIC,
)

MESH_DEVICE_IP_SENSOR = CudyRouterSensorEntityDescription(
    key="ip_address",
    module="mesh",
    name_suffix="IP address",
    icon="mdi:ip",
    entity_category=EntityCategory.DIAGNOSTIC,
)

MESH_DEVICE_CONNECTED_SENSOR = CudyRouterSensorEntityDescription(
    key="connected_devices",
    module="mesh",
    name_suffix="Connected devices",
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
)

MESH_DEVICE_HARDWARE_SENSOR = CudyRouterSensorEntityDescription(
    key="hardware",
    module="mesh",
    name_suffix="Hardware",
    icon="mdi:chip",
    entity_category=EntityCategory.DIAGNOSTIC,
)

MESH_DEVICE_BACKHAUL_SENSOR = CudyRouterSensorEntityDescription(
    key="backhaul",
    module="mesh",
    name_suffix="Backhaul",
    icon="mdi:lan-connect",
    entity_category=EntityCategory.DIAGNOSTIC,
)
