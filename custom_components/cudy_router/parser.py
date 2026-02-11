"""Helper methods to parse HTML returned by Cudy routers"""

import logging
import re
from datetime import datetime
from typing import Any, Tuple

from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta
from homeassistant.const import STATE_UNAVAILABLE

from .const import SECTION_DETAILED

_LOGGER = logging.getLogger(__name__)


def add_unique(data: dict[str, Any], key: str, value: Any):
    """Adds a new entry with unique ID"""

    i = 1
    unique_key = key
    while data.get(unique_key):
        i += 1
        unique_key = f"{key}{i}"
    data[unique_key] = value


def parse_tables(input_html: str) -> dict[str, Any]:
    """Parses an HTML table extracting key-value pairs"""

    data: dict[str, str] = {}
    soup = BeautifulSoup(input_html, "html.parser")
    tables = soup.find_all("table")
    for table in tables:
        for row in table.find_all("tr"):
            # Try pattern 1: td p.visible-xs (common in older/some firmware)
            cols = row.css.select("td p.visible-xs")
            row_data: list[str] = []
            for col in cols:
                stripped_text = col.text.strip()
                if stripped_text:
                    row_data.append(stripped_text)

            # Try pattern 2: direct td elements (common in newer firmware)
            if len(row_data) < 2:
                row_data = []
                tds = row.find_all("td")
                for td in tds:
                    # Check for nested p or span elements first
                    inner = td.find("p") or td.find("span")
                    if inner:
                        text = inner.text.strip()
                    else:
                        text = td.text.strip()
                    if text:
                        row_data.append(text)

            # Try pattern 3: th/td pairs (label in th, value in td)
            if len(row_data) < 2:
                th = row.find("th")
                td = row.find("td")
                if th and td:
                    th_text = th.text.strip()
                    td_text = td.text.strip()
                    if th_text:
                        row_data = [th_text, td_text]

            if len(row_data) > 1:
                add_unique(data, row_data[0], re.sub("[\n]", "", row_data[1]))
            elif len(row_data) == 1:
                add_unique(data, row_data[0], "")

    # Also try to parse div-based layouts (some status pages use divs instead of tables)
    for div in soup.find_all("div", class_=re.compile(r"row|item|info")):
        label_elem = div.find(class_=re.compile(r"label|key|name|title"))
        value_elem = div.find(class_=re.compile(r"value|data|content"))
        if label_elem and value_elem:
            label = label_elem.text.strip()
            value = value_elem.text.strip()
            if label and label not in data:
                add_unique(data, label, re.sub("[\n]", "", value))

    if data:
        _LOGGER.debug("Parsed table data keys: %s", list(data.keys()))
    return data


def parse_speed(input_string: str) -> float:
    """Parses transfer speed as megabits per second"""

    if not input_string:
        return None
    if input_string.lower().endswith(" kbps"):
        return round(float(input_string.split(" ")[0]) / 1024, 2)
    if input_string.lower().endswith(" mbps"):
        return float(input_string.split(" ")[0])
    if input_string.lower().endswith(" gbps"):
        return float(input_string.split(" ")[0]) * 1024
    if input_string.lower().endswith(" bps"):
        return round(float(input_string.split(" ")[0]) / 1024 / 1024, 2)
    return 0


def get_all_devices(input_html: str) -> dict[str, Any]:
    """Parses an HTML table extracting key-value pairs"""
    devices = []
    soup = BeautifulSoup(input_html, "html.parser")
    for br_element in soup.find_all("br"):
        br_element.replace_with("\n" + br_element.text)
    tables = soup.find_all("table")
    for table in tables:
        for row in table.find_all("tr"):
            ip, mac, up_speed, down_speed, hostname = [None, None, None, None, None]
            cols = row.css.select("td div")
            for col in cols:
                div_id = col.attrs.get("id")
                content_element = col.css.select_one("p.visible-xs")
                if not div_id or not content_element:
                    continue
                content = content_element.text.strip()
                if "\n" in content:
                    if div_id.endswith("ipmac"):
                        ip, mac = [x.strip() for x in content.split("\n")]
                    if div_id.endswith("speed"):
                        up_speed, down_speed = [x.strip() for x in content.split("\n")]
                    if div_id.endswith("hostname"):
                        hostname = content.split("\n")[0].strip()
            if mac or ip:
                devices.append(
                    {
                        "hostname": hostname,
                        "ip": ip,
                        "mac": mac,
                        "up_speed": parse_speed(up_speed),
                        "down_speed": parse_speed(down_speed),
                    }
                )

    return devices


def get_sim_value(input_html: str) -> str:
    """Gets the SIM slot value out of the displayed icon"""

    soup = BeautifulSoup(input_html, "html.parser")
    sim_icon = soup.css.select_one("i.icon[class*='sim']")
    if sim_icon:
        classnames = sim_icon.attrs["class"]
        classname = next(
            iter([match for match in classnames if "sim" in match]),
            "",
        )
        if "sim1" in classname:
            return "Sim 1"
        if "sim2" in classname:
            return "Sim 2"
    return STATE_UNAVAILABLE


def get_signal_strength(rssi: int) -> int:
    """Gets the signal strength from the RSSI value"""

    if rssi:
        if rssi > 20:
            return 4
        if rssi > 15:
            return 3
        if rssi > 10:
            return 2
        if rssi > 5:
            return 1
        return 0
    return STATE_UNAVAILABLE


def as_int(string: str | None):
    """Parses string as integer or returns None"""

    if not string:
        return None
    # Handle cases where value is '-' or other non-numeric
    try:
        return int(string)
    except ValueError:
        return None


def hex_as_int(string: str | None):
    """Parses hexadecimal string as integer or returns None"""

    if not string:
        return None
    # Handle cases where value is '-' or other non-hex values
    try:
        return int(string, 16)
    except ValueError:
        return None


def get_band(raw_band_info: str):
    """Gets band information"""

    if not raw_band_info:
        return None

    # Pattern 1: "BAND 3 / 20 MHz" or "BAND3 / 20MHz"
    match = re.compile(r".*BAND\s*(?P<band>\d+)\s*/\s*(?P<bandwidth>\d+)\s*MHz.*", re.IGNORECASE).match(raw_band_info)
    if match:
        return f"B{match.group('band')}"

    # Pattern 2: "B3", "B7", "n78" etc. (direct band identifier)
    match = re.compile(r"^[Bn](\d+)$", re.IGNORECASE).match(raw_band_info.strip())
    if match:
        return f"B{match.group(1)}"

    # Pattern 3: "LTE Band 3" or "NR Band 78"
    match = re.compile(r"(?:LTE|NR|5G)?\s*Band\s*(\d+)", re.IGNORECASE).search(raw_band_info)
    if match:
        return f"B{match.group(1)}"

    # Pattern 4: Just a number (band number only)
    if raw_band_info.strip().isdigit():
        return f"B{raw_band_info.strip()}"

    return None


def get_seconds_duration(raw_duration: str) -> int:
    """Parses string duration and returns it as seconds"""

    if not raw_duration:
        return None
    duration_parts = raw_duration.lower().split()
    duration = relativedelta()

    for i, part in enumerate(duration_parts):
        if part.count(":") == 2:
            hours, minutes, seconds = part.split(":")
            duration += relativedelta(hours=as_int(hours), minutes=as_int(minutes), seconds=as_int(seconds))
        elif i == 0:
            continue
        elif part.startswith("year"):
            duration += relativedelta(years=as_int(duration_parts[i - 1]))
        elif part.startswith("month"):
            duration += relativedelta(months=as_int(duration_parts[i - 1]))
        elif part.startswith("week"):
            duration += relativedelta(weeks=as_int(duration_parts[i - 1]))
        elif part.startswith("day"):
            duration += relativedelta(days=as_int(duration_parts[i - 1]))

    # Get absolute duration from relative duration (considering different month lengths)
    return (datetime.now() - (datetime.now() - duration)).total_seconds()


def parse_devices(input_html: str, device_list_str: str) -> dict[str, Any]:
    """Parses devices page"""

    devices = get_all_devices(input_html)
    data = {"device_count": {"value": len(devices)}}
    if devices:
        top_download_device = max(devices, key=lambda item: item.get("down_speed"))
        data["top_downloader_speed"] = {"value": top_download_device.get("down_speed")}
        data["top_downloader_mac"] = {"value": top_download_device.get("mac")}
        data["top_downloader_hostname"] = {"value": top_download_device.get("hostname")}
        top_upload_device = max(devices, key=lambda item: item.get("up_speed"))
        data["top_uploader_speed"] = {"value": top_upload_device.get("up_speed")}
        data["top_uploader_mac"] = {"value": top_upload_device.get("mac")}
        data["top_uploader_hostname"] = {"value": top_upload_device.get("hostname")}

        data[SECTION_DETAILED] = {}
        device_list = [x.strip() for x in (device_list_str or "").split(",")]
        for device in devices:
            if device.get("mac") in device_list:
                data[SECTION_DETAILED][device.get("mac")] = device
            if device.get("hostname") in device_list:
                data[SECTION_DETAILED][device.get("hostname")] = device

        data["total_down_speed"] = {"value": sum(device.get("down_speed") or 0 for device in devices)}
        data["total_up_speed"] = {"value": sum(device.get("up_speed") or 0 for device in devices)}
    return data


def parse_modem_info(input_html: str) -> dict[str, Any]:
    """Parses modem info page"""

    raw_data = parse_tables(input_html)
    cellid = hex_as_int(raw_data.get("Cell ID") or raw_data.get("CellID"))

    # Try to get band info from various possible keys
    band_value = (
        raw_data.get("Band") or raw_data.get("Current Band") or raw_data.get("LTE Band") or raw_data.get("Active Band")
    )
    dl_bandwidth = raw_data.get("DL Bandwidth") or raw_data.get("Bandwidth") or raw_data.get("DL BW")

    pcc = raw_data.get("PCC") or (
        f"BAND {band_value} / {dl_bandwidth}"
        if (band_value and dl_bandwidth)
        else band_value  # Use band_value directly if no bandwidth
    )
    scc1 = raw_data.get("SCC") or raw_data.get("SCC1")
    scc2 = raw_data.get("SCC2")
    scc3 = raw_data.get("SCC3")
    scc4 = raw_data.get("SCC4")

    session_upload = None
    session_download = None

    # Parse upload/download from "51.60 MB / 368.07 MB" format
    (session_upload, session_download) = get_upload_download_values(
        raw_data.get("Upload / Download") or raw_data.get("Upload/Download") or ""
    )

    data: dict[str, dict[str, Any]] = {
        "network": {
            "value": (raw_data.get("Network Type") or "").replace(" ...", ""),
            "attributes": {"mcc": raw_data.get("MCC"), "mnc": raw_data.get("MNC")},
        },
        "connected_time": {"value": get_seconds_duration(raw_data.get("Connected Time"))},
        "signal": {"value": get_signal_strength(as_int(raw_data.get("RSSI")))},
        "rssi": {"value": as_int(raw_data.get("RSSI"))},
        "rsrp": {"value": as_int(raw_data.get("RSRP"))},
        "rsrq": {"value": as_int(raw_data.get("RSRQ"))},
        "sinr": {"value": as_int(raw_data.get("SINR"))},
        "sim": {"value": get_sim_value(input_html)},
        "band": {
            "value": "+".join(
                filter(
                    None,
                    (get_band(pcc), get_band(scc1), get_band(scc2), get_band(scc3)),
                )
            )
            or None,
            "attributes": {
                "pcc": get_band(pcc),
                "scc1": get_band(scc1),
                "scc2": get_band(scc2),
                "scc3": get_band(scc3),
                "scc4": get_band(scc4),
            },
        },
        "cell": {
            "value": raw_data.get("Cell ID"),
            "attributes": {
                "id": cellid,
                "enb": cellid // 256 if cellid else None,
                "sector": cellid % 256 if cellid else None,
                "pcid": as_int(raw_data.get("PCID")),
            },
        },
        # New fields
        "public_ip": {"value": raw_data.get("Public IP")},
        "wan_ip": {"value": (raw_data.get("IP Address") or "").strip()},
        "imsi": {"value": raw_data.get("IMSI")},
        "imei": {"value": raw_data.get("IMEI")},
        "iccid": {"value": raw_data.get("ICCID")},
        "mode": {"value": (raw_data.get("Mode") or "").strip()},
        "bandwidth": {"value": raw_data.get("DL Bandwidth")},
        "session_upload": {"value": session_upload},
        "session_download": {"value": session_download},
    }
    return data


def get_upload_download_values(upload_download: str) -> Tuple[float | None, float | None]:
    """..."""

    # Parse upload/download from "51.60 MB / 368.07 MB" format
    session_upload = None
    session_download = None

    if " / " in upload_download:
        parts = upload_download.split(" / ")
        session_upload = parse_data_size(parts[0].strip())
        session_download = parse_data_size(parts[1].strip())

    return (session_upload, session_download)


def parse_data_size(size_str: str) -> float:
    """Parse data size string like '219.49 GB' to MB as float."""
    if not size_str:
        return None
    size_str = size_str.strip()
    match = re.match(r"([\d.]+)\s*(KB|MB|GB|TB|B)", size_str, re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).upper()
    if unit == "B":
        return value / 1024 / 1024
    if unit == "KB":
        return value / 1024
    if unit == "MB":
        return value
    if unit == "GB":
        return value * 1024
    if unit == "TB":
        return value * 1024 * 1024
    return value


def parse_system_status(input_html: str) -> dict[str, Any]:
    """Parses system status page."""
    raw_data = parse_tables(input_html)

    _LOGGER.debug(
        "System status parsed keys: %s (HTML len: %d)",
        list(raw_data.keys()),
        len(input_html) if input_html else 0,
    )

    # Parse uptime from format like "03:01:16" (HH:MM:SS) or "1 Day 03:01:16"
    uptime_str = raw_data.get("Uptime") or raw_data.get("System Uptime") or ""
    uptime_seconds = get_seconds_duration(uptime_str)

    # Try multiple possible key names for firmware version
    firmware = (
        raw_data.get("Firmware Version")
        or raw_data.get("Firmware")
        or raw_data.get("Software Version")
        or raw_data.get("Version")
        or raw_data.get("FW Version")
        or raw_data.get("Firmware Ver")
        or raw_data.get("Firmware Ver.")
        or raw_data.get("System Version")
        or raw_data.get("Router Firmware")
        or raw_data.get("Current Version")
        or raw_data.get("SW Version")
        or raw_data.get("Build Version")
        or raw_data.get("Release")
    )

    # Try to extract firmware from JavaScript or hidden elements if not found
    if not firmware and input_html:
        # Pattern: firmware version in JS variable or data attribute
        fw_patterns = [
            r'["\']?(?:firmware|fw|version)["\']?\s*[=:]\s*["\']([\d\.]+[^"\']*)["\'\s,]',
            r'data-firmware=["\']([^"\']*)["\'\s]',
            r">\s*([vV]?\d+\.\d+\.\d+[^<]*)\s*<",  # Version number in element
            r"Firmware[:\s]+([vV]?\d+\.\d+\.\d+[^\s<]*)",  # Cudy format
            r"Firmware Version</th><th[^>]*>([^<]+)<",  # Cudy P5 specific format
        ]
        for pattern in fw_patterns:
            match = re.search(pattern, input_html, re.IGNORECASE)
            if match:
                firmware = match.group(1).strip()
                break

    local_time = (
        raw_data.get("Local Time")
        or raw_data.get("System Time")
        or raw_data.get("Time")
        or raw_data.get("Current Time")
        or raw_data.get("Router Time")
    )

    return {
        "uptime": {"value": uptime_seconds},
        "local_time": {"value": local_time},
        "firmware_version": {"value": firmware},
    }


def parse_data_usage(input_html: str) -> dict[str, Any]:
    """Parses data usage/statistics page."""
    raw_data = parse_tables(input_html)

    return {
        "current_traffic": {"value": parse_data_size(raw_data.get("Current Traffic:"))},
        "monthly_traffic": {"value": parse_data_size(raw_data.get("Monthly Traffic:"))},
        "total_traffic": {"value": parse_data_size(raw_data.get("Total Traffic:"))},
    }


def parse_sms_status(input_html: str) -> dict[str, Any]:
    """Parses SMS status page."""
    raw_data = parse_tables(input_html)

    # Parse new message count from header (look for "New Message" with number)
    new_messages = 0
    soup = BeautifulSoup(input_html, "html.parser")
    header = soup.find("th", class_="text-primary")
    if header:
        next_th = header.find_next_sibling("th")
        if next_th:
            try:
                new_messages = int(next_th.text.strip())
            except ValueError:
                pass

    return {
        "inbox_count": {"value": as_int(raw_data.get("Inbox"))},
        "outbox_count": {"value": as_int(raw_data.get("Outbox"))},
        "unread_count": {"value": new_messages},
    }


def parse_wifi_status(input_html: str) -> dict[str, Any]:
    """Parses WiFi status page."""
    raw_data = parse_tables(input_html)

    # Check if enabled from header
    enabled = "Enabled" in input_html

    return {
        "ssid": {"value": raw_data.get("SSID")},
        "channel": {"value": as_int(raw_data.get("Channel"))},
        "enabled": {"value": enabled},
    }


def parse_lan_status(input_html: str) -> dict[str, Any]:
    """Parses LAN status page."""
    raw_data = parse_tables(input_html)

    return {
        "ip_address": {"value": raw_data.get("IP Address")},
        "mac_address": {"value": raw_data.get("MAC-Address")},
    }


def parse_devices_status(input_html: str) -> dict[str, Any]:
    """Parses connected devices status summary."""
    raw_data = parse_tables(input_html)

    _LOGGER.debug("Devices status parsed keys: %s", list(raw_data.keys()))
    # Log actual values for debugging
    for k in ["2.4G WiFi", "5G WiFi", "2.4G Clients", "5G Clients", "Wired", "Total"]:
        if k in raw_data:
            _LOGGER.debug("Devices status %s = '%s'", k, raw_data.get(k))

    # Try multiple possible key names for client counts
    wifi_2g = (
        as_int(raw_data.get("2.4G Clients"))
        or as_int(raw_data.get("2.4G clients"))
        or as_int(raw_data.get("2.4GHz Clients"))
        or as_int(raw_data.get("WiFi 2.4G Clients"))
        or as_int(raw_data.get("Wireless 2.4G"))
        or as_int(raw_data.get("2.4G"))
        or as_int(raw_data.get("2.4 GHz"))
        or as_int(raw_data.get("2.4GHz"))
        or as_int(raw_data.get("WLAN 2.4G"))
        or as_int(raw_data.get("Wi-Fi 2.4G"))
        or as_int(raw_data.get("2.4G WiFi"))  # Cudy P5 format
    )
    wifi_5g = (
        as_int(raw_data.get("5G Clients"))
        or as_int(raw_data.get("5G clients"))
        or as_int(raw_data.get("5GHz Clients"))
        or as_int(raw_data.get("WiFi 5G Clients"))
        or as_int(raw_data.get("Wireless 5G"))
        or as_int(raw_data.get("5G"))
        or as_int(raw_data.get("5 GHz"))
        or as_int(raw_data.get("5GHz"))
        or as_int(raw_data.get("WLAN 5G"))
        or as_int(raw_data.get("Wi-Fi 5G"))
        or as_int(raw_data.get("5G WiFi"))  # Cudy P5 format
    )
    wired = as_int(raw_data.get("Wired"))
    total = (
        as_int(raw_data.get("Total Clients"))
        or as_int(raw_data.get("Total clients"))
        or as_int(raw_data.get("Total"))
        or as_int(raw_data.get("Connected Clients"))
        or as_int(raw_data.get("Online Clients"))
        or as_int(raw_data.get("All Clients"))
        or as_int(raw_data.get("Clients"))
        or as_int(raw_data.get("Online"))
        or as_int(raw_data.get("Connected"))
    )

    # Try to extract from JavaScript if table parsing didn't work
    if input_html and (wifi_2g is None and wifi_5g is None and total is None):
        # Look for client counts in JS variables or JSON data
        patterns_2g = [
            r'["\']?(?:wifi_?2g|wlan_?2g|clients_?2g|2g_?clients)["\']?\s*[=:]\s*(\d+)',
            r"2\.4[Gg].*?(\d+)\s*(?:client|device)",
        ]
        patterns_5g = [
            r'["\']?(?:wifi_?5g|wlan_?5g|clients_?5g|5g_?clients)["\']?\s*[=:]\s*(\d+)',
            r"5[Gg].*?(\d+)\s*(?:client|device)",
        ]
        patterns_total = [
            r'["\']?(?:total_?clients|clients_?total|online_?clients)["\']?\s*[=:]\s*(\d+)',
            r"(?:total|all).*?(\d+)\s*(?:client|device)",
        ]

        for pattern in patterns_2g:
            match = re.search(pattern, input_html, re.IGNORECASE)
            if match:
                wifi_2g = as_int(match.group(1))
                break

        for pattern in patterns_5g:
            match = re.search(pattern, input_html, re.IGNORECASE)
            if match:
                wifi_5g = as_int(match.group(1))
                break

        for pattern in patterns_total:
            match = re.search(pattern, input_html, re.IGNORECASE)
            if match:
                total = as_int(match.group(1))
                break

    # Calculate total if not provided explicitly but we have 2G and 5G counts
    if total is None and (wifi_2g is not None or wifi_5g is not None):
        total = (wifi_2g or 0) + (wifi_5g or 0) + (wired or 0)

    _LOGGER.debug(
        "Devices status parsed: wifi_2g=%s, wifi_5g=%s, wired=%s, total=%s",
        wifi_2g,
        wifi_5g,
        wired,
        total,
    )

    return {
        "wifi_2g_clients": {"value": wifi_2g},
        "wifi_5g_clients": {"value": wifi_5g},
        "wired_clients": {"value": wired},
        "total_clients": {"value": total},
    }


def _generate_pseudo_mac(name: str) -> str:
    """Generate a deterministic pseudo-MAC address from a device name.

    Uses MD5 hash which is deterministic across Python sessions.
    """
    import hashlib

    # Use MD5 for deterministic hash (not for security, just for consistency)
    name_bytes = name.encode("utf-8")
    hash_bytes = hashlib.md5(name_bytes).digest()
    # Take first 6 bytes and format as MAC address
    # Set locally administered bit (second nibble = 2, 6, A, or E)
    mac_bytes = list(hash_bytes[:6])
    mac_bytes[0] = (mac_bytes[0] & 0xFC) | 0x02  # Set locally administered, unicast
    return ":".join(f"{b:02X}" for b in mac_bytes)


def parse_mesh_devices(input_html: str) -> dict[str, Any]:
    """Parses mesh devices page to extract mesh router information.

    Returns a dict with:
    - mesh_count: number of mesh devices (satellites only)
    - mesh_devices: dict of mesh devices keyed by MAC address
    - main_router_name: the device name set for the main router in mesh settings
    """
    data: dict[str, Any] = {
        "mesh_count": {"value": 0},
        "mesh_devices": {},
        "main_router_name": None,
    }

    if not input_html:
        _LOGGER.debug("Mesh: No HTML to parse")
        return data

    _LOGGER.debug("Mesh HTML length: %d chars", len(input_html))

    soup = BeautifulSoup(input_html, "html.parser")
    mesh_devices: list[dict[str, Any]] = []

    # First try to parse tables to see what data is available
    raw_data = parse_tables(input_html)
    if raw_data:
        _LOGGER.debug("Mesh page table keys: %s", list(raw_data.keys()))
        # Log the actual values for debugging
        for key, value in raw_data.items():
            _LOGGER.debug(
                "Mesh table: %s = %s",
                key,
                value[:100] if len(str(value)) > 100 else value,
            )

    # Check if this is a Cudy mesh page with "Device Name" and "Mesh Units"
    if raw_data.get("Device Name") or raw_data.get("Mesh Units"):
        # This appears to be a simple mesh status page
        device_name = raw_data.get("Device Name")
        mesh_units = raw_data.get("Mesh Units")
        _LOGGER.debug("Mesh: Device Name=%s, Mesh Units=%s", device_name, mesh_units)

        # Try to extract mesh unit count (subtract 1 for main router which is already added)
        if mesh_units:
            try:
                mesh_count = int(mesh_units)
                # Mesh count represents satellite devices only (exclude main router)
                satellite_count = max(0, mesh_count - 1)
                data["mesh_count"] = {"value": satellite_count}
            except (ValueError, TypeError):
                pass

        # Store the main router's device name from mesh settings
        # This can be used to name the main device in Home Assistant
        if device_name:
            data["main_router_name"] = device_name

        # NOTE: We do NOT add the "Main Router" as a mesh device here
        # because it's already represented by the main integration device.
        # Only satellite/additional mesh devices should be added.

    # Pattern 1: Look for mesh device cards/panels (common layout)
    # Mesh devices are often in div panels with device info
    # Look for complete panel structures, not individual panel parts
    panels = soup.find_all("div", class_="panel")
    _LOGGER.debug("Mesh: Found %d complete panel divs", len(panels))

    for i, panel in enumerate(panels):
        panel_text = panel.get_text(separator=" ", strip=True)[:300]
        _LOGGER.debug("Mesh panel %d text preview: %s", i, panel_text)

        device_info = _extract_mesh_device_info(panel)
        if device_info and device_info.get("mac_address"):
            mesh_devices.append(device_info)
        else:
            # Try Cudy-specific extraction without requiring MAC
            device_info = _extract_cudy_mesh_device(panel, i)
            if device_info:
                mesh_devices.append(device_info)

    # Pattern 2: Look in tables for mesh device rows
    if not mesh_devices:
        tables = soup.find_all("table")
        _LOGGER.debug("Mesh: Found %d tables", len(tables))
        for table in tables:
            for row in table.find_all("tr"):
                device_info = _extract_mesh_device_from_row(row)
                if device_info and device_info.get("mac_address"):
                    mesh_devices.append(device_info)

    # Pattern 3: Look for mesh topology/list divs
    if not mesh_devices:
        for div in soup.find_all("div", id=re.compile(r"mesh|node|satellite", re.IGNORECASE)):
            device_info = _extract_mesh_device_info(div)
            if device_info and device_info.get("mac_address"):
                mesh_devices.append(device_info)

    # Pattern 4: Parse from JavaScript data if present
    if not mesh_devices:
        mesh_devices = _extract_mesh_from_script(input_html)

    # Remove duplicates by MAC address and filter out main router devices
    seen_macs: set[str] = set()
    unique_devices: list[dict[str, Any]] = []
    for device in mesh_devices:
        mac = device.get("mac_address", "").upper()
        name = (device.get("name") or "").lower()

        # Skip the main router - it's already represented by the main integration device
        if device.get("is_main_router"):
            continue
        if name in ["main router", "mainrouter", "main_router", "router"]:
            continue

        if mac and mac not in seen_macs:
            seen_macs.add(mac)
            unique_devices.append(device)

    # Update mesh count to reflect only satellite devices
    if unique_devices:
        data["mesh_count"] = {"value": len(unique_devices)}

    data["mesh_devices"] = {device.get("mac_address", f"mesh_{i}"): device for i, device in enumerate(unique_devices)}

    if unique_devices:
        _LOGGER.debug(
            "Found %d mesh devices: %s",
            len(unique_devices),
            [d.get("name") or d.get("mac_address") for d in unique_devices],
        )

    return data


def parse_mesh_client_status(devstatus_html: str, devlist_html: str | None = None) -> dict[str, Any] | None:
    """Parse mesh client device status page to extract detailed info.

    Args:
        devstatus_html: HTML from /admin/network/mesh/client/devstatus endpoint
        devlist_html: Optional HTML from /admin/network/mesh/client/devlist endpoint

    Returns:
        Dict with device info: model, name, ip_address, mac_address, firmware_version,
        backhaul, connected_devices, status
    """
    if not devstatus_html:
        return None

    device_info: dict[str, Any] = {
        "model": None,
        "name": None,
        "ip_address": None,
        "mac_address": None,
        "firmware_version": None,
        "backhaul": None,
        "connected_devices": 0,
        "status": "online",
    }

    # Parse the status page table
    soup = BeautifulSoup(devstatus_html, "html.parser")

    # The status table has rows with "content" (label) and "data" (value) divs
    # Pattern: <td><div id="cbi-table-X-content">Label</div></td><td><div id="cbi-table-X-data">Value</div></td>
    for row in soup.find_all("tr"):
        content_div = row.find("div", id=re.compile(r"cbi-table-\d+-content"))
        data_div = row.find("div", id=re.compile(r"cbi-table-\d+-data"))

        if content_div and data_div:
            label = content_div.get_text(strip=True)
            value = data_div.get_text(strip=True)

            label_lower = label.lower()

            if label_lower == "model":
                device_info["model"] = value
            elif label_lower in ["device name", "name"]:
                device_info["name"] = value
            elif label_lower in ["ip address", "ip-address", "ipaddress"]:
                device_info["ip_address"] = value
            elif label_lower in ["mac-address", "mac address", "macaddress"]:
                device_info["mac_address"] = value.upper()
            elif label_lower in ["firmware version", "firmware"]:
                device_info["firmware_version"] = value
            elif label_lower == "backhaul":
                device_info["backhaul"] = value
            elif label_lower == "status":
                # Check if online/offline
                if "online" in value.lower():
                    device_info["status"] = "online"
                elif "offline" in value.lower():
                    device_info["status"] = "offline"

    # Parse connected devices count from devlist page
    if devlist_html:
        devlist_soup = BeautifulSoup(devlist_html, "html.parser")
        # Count rows in the device table (excluding header)
        device_rows = devlist_soup.find_all("tr", id=re.compile(r"cbi-table-\d+"))
        device_info["connected_devices"] = len(device_rows)
        _LOGGER.debug(
            "Mesh client %s has %d connected devices",
            device_info.get("name") or device_info.get("mac_address"),
            device_info["connected_devices"],
        )

    # Return if we found any meaningful data (name, mac, model, or connected_devices)
    if (
        device_info.get("name")
        or device_info.get("mac_address")
        or device_info.get("model")
        or device_info.get("connected_devices")
    ):
        _LOGGER.debug("Parsed mesh client status: %s", device_info)
        return device_info

    return None


def _extract_mesh_device_info(element) -> dict[str, Any] | None:
    """Extract mesh device information from a DOM element."""
    text_content = element.get_text(separator="\n", strip=True)

    # Look for MAC address pattern
    mac_match = re.search(r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", text_content)
    if not mac_match:
        return None

    device_info: dict[str, Any] = {
        "mac_address": mac_match.group(0).upper().replace("-", ":"),
        "name": None,
        "model": None,
        "firmware_version": None,
        "status": "online",
        "ip_address": None,
    }

    # Try to find device name from various patterns
    name_patterns = [
        r"(?:Device\s*Name|Name|Hostname)[:\s]*([^\n]+)",
        r"(?:Node\s*Name)[:\s]*([^\n]+)",
    ]
    for pattern in name_patterns:
        match = re.search(pattern, text_content, re.IGNORECASE)
        if match:
            device_info["name"] = match.group(1).strip()
            break

    # Look for model
    model_patterns = [
        r"(?:Model|Device\s*Model|Product)[:\s]*([^\n]+)",
        r"(Cudy\s*[A-Z0-9]+)",
    ]
    for pattern in model_patterns:
        match = re.search(pattern, text_content, re.IGNORECASE)
        if match:
            device_info["model"] = match.group(1).strip()
            break

    # Look for firmware version
    firmware_patterns = [
        r"(?:Firmware|FW|Version|Firmware\s*Version)[:\s]*([^\n]+)",
        r"(\d+\.\d+\.\d+[^\n]*)",
    ]
    for pattern in firmware_patterns:
        match = re.search(pattern, text_content, re.IGNORECASE)
        if match:
            device_info["firmware_version"] = match.group(1).strip()
            break

    # Look for IP address
    ip_match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", text_content)
    if ip_match:
        device_info["ip_address"] = ip_match.group(1)

    # Look for status
    if re.search(r"(?:offline|disconnected)", text_content, re.IGNORECASE):
        device_info["status"] = "offline"
    elif re.search(r"(?:online|connected)", text_content, re.IGNORECASE):
        device_info["status"] = "online"

    return device_info


def _extract_cudy_mesh_device(element, index: int) -> dict[str, Any] | None:
    """Extract Cudy mesh device info without requiring MAC address.

    Cudy mesh pages may show devices without MAC addresses visible.

    NOTE: Cudy routers typically only provide device names for satellite mesh units
    in the static HTML. Firmware version, IP address, and model information are often
    loaded via JavaScript/AJAX and not available in the page source. These fields
    will show as None/Unknown for satellite devices.
    """
    text_content = element.get_text(separator="\n", strip=True)
    text_lower = text_content.lower().strip()

    # Check if this is a short panel with just a device name (common for Cudy satellites)
    # Satellite devices may just show as "Mesh", "Satellite", "Node1", etc.
    short_device_names = ["mesh", "satellite", "node", "extender", "repeater"]
    is_short_device_name = any(text_lower == name or text_lower.startswith(name + " ") for name in short_device_names)

    # Skip if this doesn't look like a device panel (too short or no useful content)
    # BUT allow short valid device names
    if len(text_content) < 20 and not is_short_device_name:
        return None

    # Skip navigation/menu/header panels
    skip_patterns = ["logout", "menu", "settings", "wizard", "more details"]
    if any(skip in text_lower for skip in skip_patterns):
        # But check if it ALSO contains an actual device name like "Main Router"
        if not re.search(r"(Main\s*Router|Satellite|Node\s*\d+|^Mesh$)", text_content, re.IGNORECASE):
            return None

    # Skip if this is just a label panel without actual device data
    # These panels just contain duplicate headers like "Device Name Device Name"
    if text_lower.count("device name") > 1 and "main router" not in text_lower:
        return None

    device_info: dict[str, Any] = {
        "mac_address": None,
        "name": None,
        "model": None,
        "firmware_version": None,
        "status": "online",
        "ip_address": None,
    }

    # Look for MAC address (might be present in some layouts)
    mac_match = re.search(r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", text_content)
    if mac_match:
        device_info["mac_address"] = mac_match.group(0).upper().replace("-", ":")

    # Try to find actual device names (not labels)
    # First check if this is a short panel with just a device name like "Mesh"
    if is_short_device_name:
        # The panel text IS the device name
        device_info["name"] = text_content.strip()
        _LOGGER.debug("Mesh: Found short device name panel: %s", device_info["name"])
    else:
        # Look for specific device type names first
        specific_name_match = re.search(r"(Main\s*Router|Satellite|Node\s*\d+|^Mesh$)", text_content, re.IGNORECASE)
        if specific_name_match:
            device_info["name"] = specific_name_match.group(1).strip()
        else:
            # Try to extract from "Device Name: Value" pattern
            # Match pattern where we have Device Name followed by an actual value
            name_match = re.search(
                r"Device\s*Name[:\s]+([A-Za-z][A-Za-z0-9\s\-_]+?)(?:\s+(?:Mesh|Device|Status|More)|$)",
                text_content,
                re.IGNORECASE,
            )
            if name_match:
                potential_name = name_match.group(1).strip()
                # Skip if the "name" is just another label
                if potential_name.lower() not in [
                    "device name",
                    "name",
                    "hostname",
                    "device",
                ]:
                    device_info["name"] = potential_name

    # Look for model (Cudy models often like M1800, P5, etc.)
    model_match = re.search(r"((?:Cudy\s*)?[A-Z]?\d{3,4}[A-Z]?)", text_content)
    if model_match:
        device_info["model"] = model_match.group(1).strip()

    # Look for firmware version
    fw_match = re.search(r"(\d+\.\d+\.\d+(?:\.\d+)?)", text_content)
    if fw_match:
        device_info["firmware_version"] = fw_match.group(1)

    # Look for IP address
    ip_match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", text_content)
    if ip_match:
        device_info["ip_address"] = ip_match.group(1)

    # Look for status
    if re.search(r"(?:offline|disconnected|down)", text_content, re.IGNORECASE):
        device_info["status"] = "offline"
    elif re.search(r"(?:online|connected|up)", text_content, re.IGNORECASE):
        device_info["status"] = "online"

    # Only proceed if we found an actual device name
    if not device_info.get("name"):
        return None

    # Generate a pseudo-MAC if needed (based on name)
    if not device_info["mac_address"]:
        device_info["mac_address"] = _generate_pseudo_mac(device_info["name"])

    return device_info


def _extract_mesh_device_from_row(row) -> dict[str, Any] | None:
    """Extract mesh device info from a table row."""
    cells = row.find_all(["td", "th"])
    if len(cells) < 2:
        return None

    text_content = " ".join(cell.get_text(strip=True) for cell in cells)

    # Must have a MAC address to be a mesh device entry
    mac_match = re.search(r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", text_content)
    if not mac_match:
        return None

    device_info: dict[str, Any] = {
        "mac_address": mac_match.group(0).upper().replace("-", ":"),
        "name": None,
        "model": None,
        "firmware_version": None,
        "status": "online",
        "ip_address": None,
    }

    # Try to extract name (usually first column)
    if cells:
        first_cell = cells[0].get_text(strip=True)
        # If first cell doesn't look like a MAC address, use it as name
        if not re.match(r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", first_cell):
            device_info["name"] = first_cell

    # Look for IP in any cell
    for cell in cells:
        cell_text = cell.get_text(strip=True)
        ip_match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", cell_text)
        if ip_match:
            device_info["ip_address"] = ip_match.group(1)
            break

    # Look for model patterns
    model_match = re.search(r"(Cudy\s*[A-Z0-9]+|M[0-9]{4})", text_content, re.IGNORECASE)
    if model_match:
        device_info["model"] = model_match.group(1)

    # Look for firmware version
    fw_match = re.search(r"(\d+\.\d+\.\d+)", text_content)
    if fw_match:
        device_info["firmware_version"] = fw_match.group(1)

    return device_info


def _extract_mesh_from_script(html: str) -> list[dict[str, Any]]:
    """Extract mesh devices from embedded JavaScript data."""
    devices: list[dict[str, Any]] = []

    # Look for JSON-like mesh data in scripts
    # Common patterns: meshNodes = [...], nodes: [...], devices: [...]
    patterns = [
        r"(?:meshNodes|mesh_nodes|nodes)\s*[=:]\s*(\[[\s\S]*?\])\s*[;,]",
        r"(?:satellites|mesh_devices)\s*[=:]\s*(\[[\s\S]*?\])\s*[;,]",
        r"(?:unit_list|mesh_units)\s*[=:]\s*(\[[\s\S]*?\])\s*[;,]",
        r'"nodes"\s*:\s*(\[[\s\S]*?\])',
        r'"devices"\s*:\s*(\[[\s\S]*?\])',
    ]

    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            try:
                import json

                data = json.loads(match.group(1))
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            mac = item.get("mac") or item.get("mac_address") or item.get("macAddress") or ""
                            if mac:
                                devices.append(
                                    {
                                        "mac_address": mac.upper().replace("-", ":"),
                                        "name": item.get("name") or item.get("hostname"),
                                        "model": item.get("model") or item.get("device_model"),
                                        "firmware_version": item.get("firmware")
                                        or item.get("fw_version")
                                        or item.get("version"),
                                        "status": item.get("status", "online"),
                                        "ip_address": item.get("ip") or item.get("ip_address"),
                                    }
                                )
            except (json.JSONDecodeError, ValueError):
                pass

    return devices
