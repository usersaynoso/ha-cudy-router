"""Network-focused parser helpers for Cudy routers."""

from __future__ import annotations

import re
from typing import Any

from .bs4_compat import BeautifulSoup
from .parser import (
    get_seconds_duration,
    get_upload_download_values,
    parse_data_size_bytes,
    parse_tables,
)

_LOAD_BALANCING_INTERFACE_RE = re.compile(r"\bwan\s*([1-4])\b", re.IGNORECASE)
_DATA_SIZE_TOKEN_RE = re.compile(
    r"\d[\d,.]*\s*(?:bytes?|[kmgt]?i?b|[kmgt]?b)",
    re.IGNORECASE,
)
_WAN_BYTES_RECEIVED_LABELS = (
    "Bytes Received",
    "RX Bytes",
    "Rx Bytes",
    "Bytes RX",
    "Bytes Rx",
    "Received Bytes",
    "Receive Bytes",
    "RX",
    "Rx",
    "Received",
    "Bytes In",
    "Inbound Bytes",
    "Incoming Bytes",
)
_WAN_BYTES_SENT_LABELS = (
    "Bytes Sent",
    "TX Bytes",
    "Tx Bytes",
    "Bytes TX",
    "Bytes Tx",
    "Sent Bytes",
    "Transmit Bytes",
    "Transmitted Bytes",
    "TX",
    "Tx",
    "Sent",
    "Bytes Out",
    "Outbound Bytes",
    "Outgoing Bytes",
)
_WAN_RX_TX_LABELS = (
    "RX/TX Bytes",
    "RX / TX Bytes",
    "Rx/Tx Bytes",
    "Rx / Tx Bytes",
    "Received/Sent Bytes",
    "Received / Sent Bytes",
    "Receive/Transmit Bytes",
    "Receive / Transmit Bytes",
    "Bytes Received/Sent",
    "Bytes Received / Sent",
)
_WAN_TX_RX_LABELS = (
    "TX/RX Bytes",
    "TX / RX Bytes",
    "Tx/Rx Bytes",
    "Tx / Rx Bytes",
    "Sent/Received Bytes",
    "Sent / Received Bytes",
    "Transmit/Receive Bytes",
    "Transmit / Receive Bytes",
    "Bytes Sent/Received",
    "Bytes Sent / Received",
)
_VPN_CLIENT_COUNT_LABELS = (
    "Devices",
    "Clients",
    "Client",
    "Client(s)",
    "Connected",
    "Connected Clients",
    "Online Clients",
    "Active Clients",
    "VPN Clients",
    "VPN Client",
    "VPN Client(s)",
    "Client Count",
    "No. of Clients",
    "Number of Clients",
    "Users",
    "Connected Users",
    "Online Users",
    "Active Users",
    "Peers",
    "Peer Count",
)
_VPN_CLIENT_TABLE_KEYWORDS = (
    "client",
    "peer",
    "common name",
    "username",
    "virtual",
    "real address",
    "endpoint",
    "allowed ip",
    "handshake",
)
_VPN_STATUS_VALUE_LABELS = {
    "protocol",
    "vpn protocol",
    "devices",
    "clients",
    "client",
    "client(s)",
    "connected",
    "connected clients",
    "online clients",
    "active clients",
    "vpn clients",
    "vpn client",
    "vpn client(s)",
    "client count",
    "users",
    "connected users",
    "online users",
    "active users",
    "peers",
    "peer count",
    "tunnel ip",
    "tunnel address",
    "tunnel address/ip",
}


def _pick_first_value(raw_data: dict[str, Any], *keys: str) -> Any:
    """Return the first non-empty value for the provided keys."""
    normalized_lookup = {
        raw_key.strip().lower(): value
        for raw_key, value in raw_data.items()
        if isinstance(raw_key, str) and value not in (None, "")
    }
    for key in keys:
        value = raw_data.get(key)
        if value not in (None, ""):
            return value
        value = normalized_lookup.get(key.strip().lower())
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


def _clean_count(value: Any) -> int | None:
    """Extract an integer count from a status value."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    cleaned = _clean_text(value)
    if cleaned is None:
        return None

    match = re.search(r"\d+", cleaned)
    if not match:
        return None
    return int(match.group(0))


def _parse_data_size_pair(value: Any) -> tuple[int | None, int | None]:
    """Parse the first two byte-size values from a combined counter field."""
    cleaned = _clean_text(value)
    if cleaned is None:
        return None, None

    tokens = _DATA_SIZE_TOKEN_RE.findall(cleaned)
    if len(tokens) < 2 and "/" in cleaned:
        tokens = re.findall(r"\d[\d,]*", cleaned)
    if len(tokens) < 2:
        return None, None

    return parse_data_size_bytes(tokens[0]), parse_data_size_bytes(tokens[1])


def _cell_strings(element: Any) -> list[str]:
    """Extract unique text chunks from a table cell."""
    parts: list[str] = []
    for text in element.stripped_strings:
        normalized = text.strip()
        if not normalized or normalized in parts:
            continue
        parts.append(normalized)
    return parts


def _extract_load_balancing_interface(values: list[str]) -> str | None:
    """Return the WAN interface number embedded in a load-balancing cell."""
    for value in values:
        match = _LOAD_BALANCING_INTERFACE_RE.search(value.strip())
        if match:
            return match.group(1)
    return None


def _extract_load_balancing_status(values: list[str]) -> str | None:
    """Return the first non-interface status value from a load-balancing cell."""
    for value in values:
        cleaned = _clean_text(value)
        if cleaned is None or _LOAD_BALANCING_INTERFACE_RE.search(cleaned):
            continue
        return cleaned
    return None


def _contains_interface_name(values: list[str], interface: str) -> bool:
    """Return whether any cell value references the requested interface."""
    wanted_interface = interface.strip().lower()
    for value in values:
        normalized = value.strip().lower()
        if not normalized:
            continue
        if normalized == wanted_interface:
            return True
        if re.search(rf"\b{re.escape(wanted_interface)}\b", normalized):
            return True
    return False


def _vpn_client_table_count(input_html: str) -> int | None:
    """Count VPN client rows when the status page renders a client table."""
    soup = BeautifulSoup(input_html, "html.parser")
    total_clients = 0

    for table in soup.find_all("table"):
        header_values: list[str] = []
        for header in table.find_all("th"):
            header_values.extend(_cell_strings(header))
        header_text = " ".join(header_values).lower()
        if not any(keyword in header_text for keyword in _VPN_CLIENT_TABLE_KEYWORDS):
            continue

        table_clients = 0
        rows = table.select("tbody tr") or table.find_all("tr")
        for row in rows:
            if row.find("th") is not None:
                continue
            columns = row.find_all("td")
            values = [
                value
                for column in columns
                for value in (_cell_strings(column) or [column.get_text(" ", strip=True)])
                if value
            ]
            if len(values) < 2:
                continue

            row_text = " ".join(values).strip().lower()
            if any(
                placeholder in row_text
                for placeholder in ("no data", "no clients", "no client", "no peers", "not connected")
            ):
                continue
            if len(values) == 2 and values[0].strip().lower().rstrip(":") in _VPN_STATUS_VALUE_LABELS:
                continue

            table_clients += 1

        total_clients += table_clients

    return total_clients if total_clients > 0 else None


def parse_vpn_status(input_html: str) -> dict[str, Any]:
    """Parse VPN status page."""
    raw_data = parse_tables(input_html)
    vpn_clients = _clean_count(_pick_first_value(raw_data, *_VPN_CLIENT_COUNT_LABELS))
    if vpn_clients is None:
        vpn_clients = _vpn_client_table_count(input_html)

    return {
        "protocol": {"value": _clean_text(_pick_first_value(raw_data, "Protocol", "VPN Protocol"))},
        "vpn_clients": {"value": vpn_clients},
        "tunnel_ip": {
            "value": _clean_text(_pick_first_value(raw_data, "Tunnel IP", "Tunnel Address", "Tunnel Address/IP"))
        },
    }


def parse_arp_status(input_html: str, interface: str) -> dict[str, Any]:
    """Parse an ARP table page and count entries for a specific interface."""
    soup = BeautifulSoup(input_html, "html.parser")
    interface_count = 0

    for row in soup.select("tbody tr[id^='cbi-table-']"):
        columns = row.find_all("td")
        if len(columns) < 2:
            continue

        if any(_contains_interface_name(_cell_strings(column), interface) for column in columns):
            interface_count += 1

    return {
        f"arp_{interface.replace('-', '_')}_count": {"value": interface_count},
    }


def parse_load_balancing_status(input_html: str) -> dict[str, Any]:
    """Parse load-balancing status page."""
    soup = BeautifulSoup(input_html, "html.parser")
    parsed: dict[str, Any] = {}

    for row in soup.select("table tr"):
        columns = row.find_all("td")
        if len(columns) < 2:
            continue

        column_values = [_cell_strings(column) for column in columns]
        interface_column_index: int | None = None
        interface_number: str | None = None
        for index, values in enumerate(column_values):
            interface_number = _extract_load_balancing_interface(values)
            if interface_number is not None:
                interface_column_index = index
                break

        if interface_number is None or interface_column_index is None:
            continue

        for index, values in enumerate(column_values):
            if index == interface_column_index:
                continue

            status = _extract_load_balancing_status(values)
            if status is not None:
                parsed[f"wan{interface_number}_status"] = {"value": status}
                break

    if parsed:
        return parsed

    raw_data = parse_tables(input_html)
    for interface_number in range(1, 5):
        status: str | None = _clean_text(
            _pick_first_value(
                raw_data,
                f"WAN{interface_number}",
                f"WAN {interface_number}",
            )
        )
        if status is None:
            for raw_key, raw_value in raw_data.items():
                if not isinstance(raw_key, str):
                    continue
                match = _LOAD_BALANCING_INTERFACE_RE.search(raw_key.strip())
                if match and match.group(1) == str(interface_number):
                    status = _clean_text(raw_value)
                    if status is not None:
                        break
        if status is not None:
            parsed[f"wan{interface_number}_status"] = {"value": status}

    return parsed


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
    bytes_received = parse_data_size_bytes(_pick_first_value(raw_data, *_WAN_BYTES_RECEIVED_LABELS))
    bytes_sent = parse_data_size_bytes(_pick_first_value(raw_data, *_WAN_BYTES_SENT_LABELS))
    if bytes_received is None or bytes_sent is None:
        rx_value, tx_value = _parse_data_size_pair(_pick_first_value(raw_data, *_WAN_RX_TX_LABELS))
        bytes_received = bytes_received if bytes_received is not None else rx_value
        bytes_sent = bytes_sent if bytes_sent is not None else tx_value
    if bytes_received is None or bytes_sent is None:
        tx_value, rx_value = _parse_data_size_pair(_pick_first_value(raw_data, *_WAN_TX_RX_LABELS))
        bytes_received = bytes_received if bytes_received is not None else rx_value
        bytes_sent = bytes_sent if bytes_sent is not None else tx_value

    return {
        "protocol": {
            "value": _clean_text(
                _pick_first_value(raw_data, "Protocol", "Connection Type", "WAN Protocol")
            )
        },
        "connected_time": {"value": connected_time},
        "mac_address": {
            "value": _clean_text(
                _pick_first_value(raw_data, "MAC-Address", "MAC Address", "MAC", "WAN MAC", "WAN MAC Address")
            )
        },
        "public_ip": {
            "value": _clean_text(_pick_first_value(raw_data, "Public IP", "Public IPv4", "WAN Public IP"))
        },
        "wan_ip": {
            "value": _clean_text(_pick_first_value(raw_data, "IP Address", "WAN IP", "IPv4 Address", "IP"))
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
        "bytes_received": {"value": bytes_received},
        "bytes_sent": {"value": bytes_sent},
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
