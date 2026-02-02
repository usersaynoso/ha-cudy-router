"""Page containing the feature not implemented for each device"""

from typing import Dict, List

features_not_implemented: Dict[str, List[str]] = {
    "default": [
        "wan|protocol",
        "wan|connected_time",
        "wan|mac_address",
        "wan|public_ip",
        "wan|wan_ip",
        "wan|subnet_mask",
        "wan|gateway",
        "wan|dns",
        "wan|session_upload",
        "wan|session_download",
    ],
    "WR3000S V1.0": [
        "modem|signal",
        "modem|network",
        "modem|sim",
        "modem|connected_time",
        "modem|cell",
        "modem|rsrp",
        "modem|rsrq",
        "modem|sinr",
        "modem|rssi",
        "modem|band",
        "modem|public_ip",
        "modem|wan_ip",
        "modem|imei",
        "modem|imsi",
        "modem|iccid",
        "modem|mode",
        "modem|bandwidth",
        "modem|session_upload",
        "modem|session_download",
        "data_usage|current_traffic",
        "data_usage|monthly_traffic",
        "data_usage|total_traffic",
        "sms|inbox_count",
        "sms|outbox_count",
        "sms|unread_count",
    ],
}


def existing_feature(device_model: str, key_entity: str, model_entity: str) -> bool:
    """Check if a feature is implemented or not for a specific device."""

    if device_model not in features_not_implemented:
        device_model = "default"

    return f"{key_entity}|{model_entity}" not in features_not_implemented[device_model]
