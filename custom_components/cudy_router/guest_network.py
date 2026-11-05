"""Guest Wi-Fi client detection for the Cudy Router integration."""

from __future__ import annotations

import ipaddress
import re
from typing import Any

from .bs4_compat import BeautifulSoup

GUEST_NETWORK_SETTINGS_PATH = "admin/network/wireless/guest"

_GUEST_DISABLED_INPUT_RE = re.compile(r"^cbid\.wireless\.[^.]+\.disabled$")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def parse_guest_network_enabled(input_html: str | None) -> bool | None:
    """Return whether any guest SSID is enabled, or None when the page is unreadable."""
    if not input_html:
        return None

    soup = BeautifulSoup(input_html, "html.parser")
    disabled_values = [
        str(field.get("value") or "").strip()
        for field in soup.find_all("input")
        if _GUEST_DISABLED_INPUT_RE.match(str(field.get("id") or field.get("name") or ""))
    ]
    if not disabled_values:
        return None
    return any(value == "0" for value in disabled_values)


def parse_arp_ips(input_html: str | None) -> set[str] | None:
    """Return the IP addresses in the router's ARP table, or None when it has no rows."""
    if not input_html:
        return None

    soup = BeautifulSoup(input_html, "html.parser")
    rows = soup.select("tbody tr[id^='cbi-table-']")
    if not rows:
        return None
    return {ip for row in rows for ip in _IPV4_RE.findall(row.get_text(" "))}


def lan_network(ip_address: str | None, subnet_mask: str | None) -> ipaddress.IPv4Network | None:
    """Build the router's main LAN network from its address and mask."""
    if not ip_address:
        return None
    try:
        return ipaddress.IPv4Network(f"{ip_address}/{subnet_mask or '255.255.255.0'}", strict=False)
    except ValueError:
        return None


def is_guest_device(device: dict[str, Any], main_lan: ipaddress.IPv4Network | None) -> bool:
    """Return whether a connected-device row belongs to the guest network.

    Guests joined to the main unit are labelled as a guest network. Guests
    joined through a mesh satellite are labelled ``Mesh``, so they are only
    recognisable by their address sitting outside the main LAN.
    """
    if "guest" in str(device.get("connection_type") or "").lower():
        return True
    if main_lan is None or not device.get("ip"):
        return False
    try:
        return ipaddress.IPv4Address(str(device["ip"]).strip()) not in main_lan
    except ValueError:
        return False


def build_guest_clients(
    devices: list[dict[str, Any]],
    main_lan: ipaddress.IPv4Network | None,
    guest_network_enabled: bool | None,
    status_guest_count: int | None = None,
    arp_ips: set[str] | None = None,
) -> dict[str, Any]:
    """Build the guest client count entry with per-guest attributes.

    The router keeps guests in its device list for several minutes after they
    leave, so when the ARP table is readable a guest must also appear there.
    """
    listed_guests = [device for device in devices if is_guest_device(device, main_lan)]
    guests = [
        device
        for device in listed_guests
        if arp_ips is None or not device.get("ip") or str(device["ip"]).strip() in arp_ips
    ]
    count = max(len(guests), status_guest_count or 0)
    return {
        "value": count,
        "attributes": {
            "guest_network_enabled": guest_network_enabled,
            "stale_entries_ignored": len(listed_guests) - len(guests),
            "guests": [
                {
                    "hostname": device.get("hostname"),
                    "ip": device.get("ip"),
                    "mac": device.get("mac"),
                    "connection_type": device.get("connection_type"),
                }
                for device in guests
            ],
        },
    }
