"""Network-focused parser helpers for Cudy routers."""

from __future__ import annotations

from typing import Any

from .parser import get_seconds_duration, get_upload_download_values, parse_tables


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
        raw_data.get("Upload / Download") or raw_data.get("Upload/Download") or ""
    )

    raw_public_ip = raw_data.get("Public IP")
    public_ip: str | None = None
    if isinstance(raw_public_ip, str):
        cleaned_public_ip = raw_public_ip.replace("*", "").strip()
        public_ip = cleaned_public_ip or None

    raw_connected_time = raw_data.get("Connected Time")
    connected_time: float | None = (
        get_seconds_duration(raw_connected_time) if raw_connected_time else None
    )

    return {
        "protocol": {"value": raw_data.get("Protocol")},
        "connected_time": {"value": connected_time},
        "mac_address": {"value": raw_data.get("MAC-Address")},
        "public_ip": {"value": public_ip},
        "wan_ip": {"value": raw_data.get("IP Address")},
        "subnet_mask": {"value": raw_data.get("Subnet Mask")},
        "gateway": {"value": raw_data.get("Gateway")},
        "dns": {"value": raw_data.get("DNS")},
        "session_upload": {"value": session_upload},
        "session_download": {"value": session_download},
    }


def parse_dhcp_status(input_html: str) -> dict[str, Any]:
    """Parse DHCP status page."""
    raw_data = parse_tables(input_html)

    return {
        "dhcp_ip_start": {"value": raw_data.get("IP Start")},
        "dhcp_ip_end": {"value": raw_data.get("IP End")},
        "dhcp_prefered_dns": {"value": raw_data.get("Preferred DNS")},
        "dhcp_default_gateway": {"value": raw_data.get("Default Gateway")},
        "dhcp_leasetime": {"value": raw_data.get("Leasetime")},
    }
