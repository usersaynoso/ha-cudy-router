"""Constants for the Cudy Router integration."""

DOMAIN = "cudy_router"

DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 3600

MODULE_MODEM = "modem"
MODULE_DEVICES = "devices"
MODULE_SYSTEM = "system"
MODULE_DATA_USAGE = "data_usage"
MODULE_SMS = "sms"
MODULE_WIFI_2G = "wifi_2g"
MODULE_WIFI_5G = "wifi_5g"
MODULE_LAN = "lan"
MODULE_MESH = "mesh"
MODULE_VPN = "vpn"
MODULE_WAN = "wan"
MODULE_DHCP = "dhcp"

SECTION_DETAILED = "detailed"
SECTION_MESH_DEVICES = "mesh_devices"

OPTIONS_DEVICELIST = "device_list"

# Mesh device attributes
ATTR_MESH_MAC = "mac_address"
ATTR_MESH_MODEL = "model"
ATTR_MESH_FIRMWARE = "firmware_version"
ATTR_MESH_NAME = "name"
ATTR_MESH_STATUS = "status"
ATTR_MESH_IP = "ip_address"


def normalize_scan_interval(value: object) -> int:
    """Normalize scan interval to a safe range."""
    try:
        interval = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_SCAN_INTERVAL

    return max(MIN_SCAN_INTERVAL, min(MAX_SCAN_INTERVAL, interval))
