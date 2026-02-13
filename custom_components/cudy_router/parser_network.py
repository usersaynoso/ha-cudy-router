"""Network-focused parser helpers for Cudy routers."""

from __future__ import annotations

from typing import Any

from .parser import get_seconds_duration, get_upload_download_values, parse_tables


def _pick_first_value(raw_data: dict[str, Any], *keys: str) -> Any:
    """Return the first non-empty value for the provided keys."""
    for key in keys:
        value = raw_data.get(key)
        if value not in (None, ""):
            return value
    return None


def _clean_text(value: Any) -> str | None:
    """Normalize plain text values and drop placeholders."""
    if not isinstance(value, str):
        return None

    cleaned = value.replace("*", "").strip()
    if not cleaned:
        return None
    if cleaned.lower() in {"-", "--", "n/a", "na", "unknown"}:
        return None
    return cleaned


def parse_vpn_status(input_html: str) -> dict[str, Any]:
    """Parse VPN status page."""
    raw_data = parse_tables(input_html)

    return {
        "protocol": {"value": raw_data.get("Protocol")},
        "vpn_clients": {"value": raw_data.get("Devices")},
    }


def parse_wan_status(input_html: str) -> dict[str, Any]:
    """Parse WAN status page."""
    raw_data = parse_tables(input_html)

    (session_upload, session_download) = get_upload_download_values(
        _pick_first_value(raw_data, "Upload / Download", "Upload/Download", "Upload/Down") or ""
    )

    raw_connected_time = _pick_first_value(raw_data, "Connected Time", "Connect Time", "Connection Time")
    connected_time_input = str(raw_connected_time) if raw_connected_time is not None else None
    connected_time: float | None = (
        get_seconds_duration(connected_time_input) if connected_time_input else None
    )

    return {
        "protocol": {
            "value": _clean_text(
                _pick_first_value(raw_data, "Protocol", "Connection Type", "WAN Protocol")
            )
        },
        "connected_time": {"value": connected_time},
        "mac_address": {
            "value": _clean_text(_pick_first_value(raw_data, "MAC-Address", "MAC Address", "WAN MAC"))
        },
        "public_ip": {
            "value": _clean_text(_pick_first_value(raw_data, "Public IP", "Public IPv4", "WAN Public IP"))
        },
        "wan_ip": {
            "value": _clean_text(_pick_first_value(raw_data, "IP Address", "WAN IP", "IP"))
        },
        "subnet_mask": {
            "value": _clean_text(_pick_first_value(raw_data, "Subnet Mask", "Subnet", "Netmask", "Mask"))
        },
        "gateway": {
            "value": _clean_text(_pick_first_value(raw_data, "Gateway", "Default Gateway"))
        },
        "dns": {
            "value": _clean_text(_pick_first_value(raw_data, "DNS", "Preferred DNS", "Primary DNS"))
        },
        "session_upload": {"value": session_upload},
        "session_download": {"value": session_download},
    }


def parse_dhcp_status(input_html: str) -> dict[str, Any]:
    """Parse DHCP status page."""
    raw_data = parse_tables(input_html)

    return {
        "dhcp_ip_start": {"value": _clean_text(_pick_first_value(raw_data, "IP Start", "Start IP"))},
        "dhcp_ip_end": {"value": _clean_text(_pick_first_value(raw_data, "IP End", "End IP"))},
        "dhcp_prefered_dns": {
            "value": _clean_text(_pick_first_value(raw_data, "Preferred DNS", "DNS", "Primary DNS"))
        },
        "dhcp_default_gateway": {
            "value": _clean_text(_pick_first_value(raw_data, "Default Gateway", "Gateway"))
        },
        "dhcp_leasetime": {"value": _clean_text(_pick_first_value(raw_data, "Leasetime", "Lease Time"))},
    }
