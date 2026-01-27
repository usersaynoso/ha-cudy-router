"""Helper methods to parse HTML returned by Cudy routers"""

import logging
import re
from typing import Any
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta
from datetime import datetime

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
    match = re.compile(
        r".*BAND\s*(?P<band>\d+)\s*/\s*(?P<bandwidth>\d+)\s*MHz.*", re.IGNORECASE
    ).match(raw_band_info)
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
            duration += relativedelta(
                hours=as_int(hours), minutes=as_int(minutes), seconds=as_int(seconds)
            )
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

        data["total_down_speed"] = {
            "value": sum(device.get("down_speed") or 0 for device in devices)
        }
        data["total_up_speed"] = {
            "value": sum(device.get("up_speed") or 0 for device in devices)
        }
    return data


def parse_modem_info(input_html: str) -> dict[str, Any]:
    """Parses modem info page"""

    raw_data = parse_tables(input_html)
    cellid = hex_as_int(raw_data.get("Cell ID") or raw_data.get("CellID"))
    
    # Try to get band info from various possible keys
    band_value = (
        raw_data.get("Band") or
        raw_data.get("Current Band") or
        raw_data.get("LTE Band") or
        raw_data.get("Active Band")
    )
    dl_bandwidth = (
        raw_data.get("DL Bandwidth") or
        raw_data.get("Bandwidth") or
        raw_data.get("DL BW")
    )
    
    pcc = raw_data.get("PCC") or (
        f"BAND {band_value} / {dl_bandwidth}"
        if (band_value and dl_bandwidth)
        else band_value  # Use band_value directly if no bandwidth
    )
    scc1 = raw_data.get("SCC") or raw_data.get("SCC1")
    scc2 = raw_data.get("SCC2")
    scc3 = raw_data.get("SCC3")
    scc4 = raw_data.get("SCC4")
    
    # Parse upload/download from "51.60 MB / 368.07 MB" format
    upload_download = raw_data.get("Upload / Download") or raw_data.get("Upload/Download") or ""
    session_upload = None
    session_download = None
    if " / " in upload_download:
        parts = upload_download.split(" / ")
        session_upload = parse_data_size(parts[0].strip())
        session_download = parse_data_size(parts[1].strip())
    
    data: dict[str, dict[str, Any]] = {
        "network": {
            "value": (raw_data.get("Network Type") or "").replace(" ...", ""),
            "attributes": {"mcc": raw_data.get("MCC"), "mnc": raw_data.get("MNC")},
        },
        "connected_time": {
            "value": get_seconds_duration(raw_data.get("Connected Time"))
        },
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
            ) or None,
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
    
    _LOGGER.debug("System status parsed keys: %s", list(raw_data.keys()))
    
    # Parse uptime from format like "03:01:16" (HH:MM:SS) or "1 Day 03:01:16"
    uptime_str = raw_data.get("Uptime") or raw_data.get("System Uptime") or ""
    uptime_seconds = get_seconds_duration(uptime_str)
    
    # Try multiple possible key names for firmware version
    firmware = (
        raw_data.get("Firmware Version") or
        raw_data.get("Firmware") or
        raw_data.get("Software Version") or
        raw_data.get("Version") or
        raw_data.get("FW Version") or
        raw_data.get("Firmware Ver") or
        raw_data.get("Firmware Ver.") or
        raw_data.get("System Version") or
        raw_data.get("Router Firmware") or
        raw_data.get("Current Version")
    )
    
    # Try to extract firmware from JavaScript or hidden elements if not found
    if not firmware and input_html:
        # Pattern: firmware version in JS variable or data attribute
        fw_patterns = [
            r'["\']?(?:firmware|fw|version)["\']?\s*[=:]\s*["\']([\d\.]+[^"\']*)["\'\s,]',
            r'data-firmware=["\']([^"\']*)["\'\s]',
            r'>\s*([vV]?\d+\.\d+\.\d+[^<]*)\s*<',  # Version number in element
        ]
        for pattern in fw_patterns:
            match = re.search(pattern, input_html, re.IGNORECASE)
            if match:
                firmware = match.group(1).strip()
                break
    
    local_time = (
        raw_data.get("Local Time") or
        raw_data.get("System Time") or
        raw_data.get("Time") or
        raw_data.get("Current Time") or
        raw_data.get("Router Time")
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
    
    # Try multiple possible key names for client counts
    wifi_2g = (
        as_int(raw_data.get("2.4G Clients")) or
        as_int(raw_data.get("2.4G clients")) or
        as_int(raw_data.get("2.4GHz Clients")) or
        as_int(raw_data.get("WiFi 2.4G Clients")) or
        as_int(raw_data.get("Wireless 2.4G")) or
        as_int(raw_data.get("2.4G")) or
        as_int(raw_data.get("2.4 GHz")) or
        as_int(raw_data.get("2.4GHz")) or
        as_int(raw_data.get("WLAN 2.4G")) or
        as_int(raw_data.get("Wi-Fi 2.4G"))
    )
    wifi_5g = (
        as_int(raw_data.get("5G Clients")) or
        as_int(raw_data.get("5G clients")) or
        as_int(raw_data.get("5GHz Clients")) or
        as_int(raw_data.get("WiFi 5G Clients")) or
        as_int(raw_data.get("Wireless 5G")) or
        as_int(raw_data.get("5G")) or
        as_int(raw_data.get("5 GHz")) or
        as_int(raw_data.get("5GHz")) or
        as_int(raw_data.get("WLAN 5G")) or
        as_int(raw_data.get("Wi-Fi 5G"))
    )
    total = (
        as_int(raw_data.get("Total Clients")) or
        as_int(raw_data.get("Total clients")) or
        as_int(raw_data.get("Total")) or
        as_int(raw_data.get("Connected Clients")) or
        as_int(raw_data.get("Online Clients")) or
        as_int(raw_data.get("All Clients")) or
        as_int(raw_data.get("Clients")) or
        as_int(raw_data.get("Online")) or
        as_int(raw_data.get("Connected"))
    )
    
    # Try to extract from JavaScript if table parsing didn't work
    if input_html and (wifi_2g is None and wifi_5g is None and total is None):
        # Look for client counts in JS variables or JSON data
        patterns_2g = [
            r'["\']?(?:wifi_?2g|wlan_?2g|clients_?2g|2g_?clients)["\']?\s*[=:]\s*(\d+)',
            r'2\.4[Gg].*?(\d+)\s*(?:client|device)',
        ]
        patterns_5g = [
            r'["\']?(?:wifi_?5g|wlan_?5g|clients_?5g|5g_?clients)["\']?\s*[=:]\s*(\d+)',
            r'5[Gg].*?(\d+)\s*(?:client|device)',
        ]
        patterns_total = [
            r'["\']?(?:total_?clients|clients_?total|online_?clients)["\']?\s*[=:]\s*(\d+)',
            r'(?:total|all).*?(\d+)\s*(?:client|device)',
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
    
    return {
        "wifi_2g_clients": {"value": wifi_2g},
        "wifi_5g_clients": {"value": wifi_5g},
        "total_clients": {"value": total},
    }


def parse_mesh_devices(input_html: str) -> dict[str, Any]:
    """Parses mesh devices page to extract mesh router information.
    
    Returns a dict with:
    - mesh_count: number of mesh devices
    - mesh_devices: dict of mesh devices keyed by MAC address
    """
    data: dict[str, Any] = {
        "mesh_count": {"value": 0},
        "mesh_devices": {},
    }
    
    if not input_html:
        return data
    
    soup = BeautifulSoup(input_html, "html.parser")
    mesh_devices: list[dict[str, Any]] = []
    
    # Pattern 1: Look for mesh device cards/panels (common layout)
    # Mesh devices are often in div panels with device info
    for panel in soup.find_all("div", class_=re.compile(r"panel|card|device|node", re.IGNORECASE)):
        device_info = _extract_mesh_device_info(panel)
        if device_info and device_info.get("mac_address"):
            mesh_devices.append(device_info)
    
    # Pattern 2: Look in tables for mesh device rows
    if not mesh_devices:
        tables = soup.find_all("table")
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
    
    # Remove duplicates by MAC address
    seen_macs: set[str] = set()
    unique_devices: list[dict[str, Any]] = []
    for device in mesh_devices:
        mac = device.get("mac_address", "").upper()
        if mac and mac not in seen_macs:
            seen_macs.add(mac)
            unique_devices.append(device)
    
    data["mesh_count"] = {"value": len(unique_devices)}
    data["mesh_devices"] = {
        device.get("mac_address", f"mesh_{i}"): device 
        for i, device in enumerate(unique_devices)
    }
    
    if unique_devices:
        _LOGGER.debug("Found %d mesh devices: %s", len(unique_devices), 
                     [d.get("name") or d.get("mac_address") for d in unique_devices])
    
    return data


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
                            mac = (
                                item.get("mac") or 
                                item.get("mac_address") or 
                                item.get("macAddress") or
                                ""
                            )
                            if mac:
                                devices.append({
                                    "mac_address": mac.upper().replace("-", ":"),
                                    "name": item.get("name") or item.get("hostname"),
                                    "model": item.get("model") or item.get("device_model"),
                                    "firmware_version": item.get("firmware") or item.get("fw_version") or item.get("version"),
                                    "status": item.get("status", "online"),
                                    "ip_address": item.get("ip") or item.get("ip_address"),
                                })
            except (json.JSONDecodeError, ValueError):
                pass
    
    return devices
    