"""Data collection helpers for Cudy routers."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from .bs4_compat import BeautifulSoup
from .const import (
    MODULE_AUTO_UPDATE_SETTINGS,
    MODULE_CELLULAR_SETTINGS,
    MODULE_DATA_USAGE,
    MODULE_DEVICES,
    MODULE_DHCP,
    MODULE_LAN,
    MODULE_LOAD_BALANCING,
    MODULE_MESH,
    MODULE_MODEM,
    MODULE_SMS,
    MODULE_SYSTEM,
    MODULE_VPN,
    MODULE_VPN_SETTINGS,
    MODULE_WAN,
    MODULE_WAN_INTERFACES,
    MODULE_WIRELESS_SETTINGS,
    MODULE_WISP,
    MODULE_WIFI_2G,
    MODULE_WIFI_5G,
    OPTIONS_DEVICELIST,
)
from .features import existing_feature
from .parser import (
    parse_data_usage,
    parse_devices,
    parse_devices_status,
    parse_lan_status,
    parse_mesh_client_status,
    parse_mesh_devices,
    parse_modem_info,
    parse_sms_status,
    parse_system_status,
    parse_wifi_status,
)
from .parser_network import (
    parse_arp_status,
    parse_dhcp_status,
    parse_load_balancing_status,
    parse_vpn_status,
    parse_wan_status,
    parse_wisp_data,
    parse_wisp_status,
)
from .parser_settings import (
    parse_auto_update_settings,
    parse_cellular_settings,
    parse_lan_settings,
    parse_vpn_settings,
    parse_wan_settings,
    parse_wisp_settings,
    parse_wireless_settings,
)

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


_VPN_STATUS_PATHS: tuple[str, ...] = (
    "admin/network/vpn/wireguard/status?detail=",
    "admin/network/vpn/openvpns/status?status=",
    "admin/network/vpn?mvpn=",
    "admin/network/vpn/pptp/status?detail=",
    "admin/network/vpn/status?detail=",
    "admin/network/vpn/pptp/status",
    "admin/network/vpn/status",
)
_VPN_STATUS_PATH_PROTOCOLS: dict[str, frozenset[str]] = {
    "admin/network/vpn/wireguard/status?detail=": frozenset({"wireguard", "wireguards"}),
    "admin/network/vpn/openvpns/status?status=": frozenset({"openvpns"}),
    "admin/network/vpn/pptp/status?detail=": frozenset({"pptp", "pptps"}),
    "admin/network/vpn/pptp/status": frozenset({"pptp", "pptps"}),
}

_LOAD_BALANCING_STATUS_PATHS: tuple[str, ...] = (
    "admin/network/mwan3/status?detail=",
    "admin/network/mwan3/status",
)
_WISP_STATUS_PATHS: tuple[str, ...] = (
    "admin/network/wireless/wds/status",
    "admin/network/wireless/wds/status?mode=wisp",
)
_WISP_DATA_PATHS: tuple[str, ...] = (
    "admin/network/wireless/wds/data",
    "admin/network/wireless/wds/data?iface=wlan11",
    "admin/network/wireless/wds/data?iface=wlan01",
)
_WISP_CONFIG_PATHS: tuple[str, ...] = (
    "admin/network/wireless/wds/config?nomodal=&mode=wisp",
    "admin/network/wireless/wds/config/nomodal/wisp",
)

_WAN_STATUS_PATH_FORMATS: tuple[str, ...] = (
    "admin/network/wan/status?detail=1&iface={iface_name}",
    "admin/network/wan/status?detail=&iface={iface_name}",
    "admin/network/wan/status?iface={iface_name}&detail=1",
    "admin/network/wan/status?iface={iface_name}",
)

_WAN_STATUS_IFACES: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("wan", "wan1", (), ("wan", "wan1")),
    ("wanb", "wan2", ("2", "b"), ("wanb", "wan2")),
    ("wanc", "wan3", ("3", "c"), ("wanc", "wan3")),
    ("wand", "wan4", ("4", "d"), ("wand", "wan4")),
)
_WAN_INTERFACE_REFERENCE_RE = re.compile(r"(?<![a-z0-9])wan[\s_-]*([1-4a-d])(?![a-z0-9])", re.IGNORECASE)
_WAN_STATUS_VALUE_MARKERS: tuple[str, ...] = (
    "public ip",
    "ip address",
    "gateway",
    "subnet",
    "protocol",
    "bytes received",
    "bytes sent",
    "rx bytes",
    "tx bytes",
    "bytes rx",
    "bytes tx",
    "rx/tx",
    "rx / tx",
    "tx/rx",
    "tx / rx",
    "connected time",
    "upload / download",
    "upload/download",
    "mac-address",
    "mac address",
)
_WAN_RICH_STATUS_KEYS: tuple[str, ...] = (
    "connected_time",
    "dns",
    "gateway",
    "mac_address",
    "public_ip",
    "subnet_mask",
    "bytes_received",
    "bytes_sent",
    "session_upload",
    "session_download",
)


def _entry_value(parsed: dict[str, Any], key: str) -> Any:
    """Return the nested value for a parsed coordinator entry."""
    entry = parsed.get(key, {})
    if isinstance(entry, dict):
        return entry.get("value")
    return None


def _non_empty_entries(parsed: dict[str, Any]) -> dict[str, Any]:
    """Return parsed entries that contain live values."""
    return {
        key: entry
        for key, entry in parsed.items()
        if isinstance(entry, dict) and entry.get("value") not in (None, "")
    }


def _merge_module_entries(
    target: dict[str, Any],
    source: dict[str, Any],
) -> None:
    """Merge parsed module entries while preserving the first live state value."""
    for key, entry in source.items():
        if not isinstance(entry, dict) or entry.get("value") in (None, ""):
            continue
        if key not in target or target.get(key, {}).get("value") in (None, ""):
            target[key] = dict(entry)
            continue

        existing_entry = target[key]
        if not isinstance(existing_entry, dict):
            continue
        existing_attributes = existing_entry.get("attributes")
        new_attributes = entry.get("attributes")
        if isinstance(new_attributes, dict):
            merged_attributes = dict(existing_attributes) if isinstance(existing_attributes, dict) else {}
            merged_attributes.update(new_attributes)
            existing_entry["attributes"] = merged_attributes


def _wisp_data_score(module_data: dict[str, Any]) -> tuple[int, int]:
    """Score parsed WISP data so richer endpoint responses are preferred."""
    rich_fields = sum(
        _entry_value(module_data, key) not in (None, "")
        for key in (
            "status",
            "ssid",
            "bssid",
            "signal",
            "quality",
            "channel",
            "channel_width",
            "protocol",
            "transmit_power",
        )
    )
    populated_fields = sum(
        entry.get("value") not in (None, "")
        for entry in module_data.values()
        if isinstance(entry, dict)
    )
    return rich_fields, populated_fields


def _module_entry_has_value(data: dict[str, Any], module: str, key: str) -> bool:
    """Return whether a parsed module entry has a live value."""
    module_data = data.get(module)
    if not isinstance(module_data, dict):
        return False
    return _entry_value(module_data, key) not in (None, "")


def _apply_load_balancing_statuses(
    wan_interfaces: dict[str, dict[str, Any]],
    load_balancing_data: dict[str, Any],
) -> None:
    """Copy load-balancing WAN statuses into per-interface WAN data."""
    if not isinstance(load_balancing_data, dict):
        return

    for interface_number in range(1, 5):
        status = _entry_value(load_balancing_data, f"wan{interface_number}_status")
        if status not in (None, ""):
            interface_data = wan_interfaces.setdefault(f"wan{interface_number}", {})
            interface_data.setdefault("status", {"value": status})


def _load_balancing_has_interface(load_balancing_data: dict[str, Any], interface_key: str) -> bool:
    """Return whether load-balancing status lists an interface."""
    return _entry_value(load_balancing_data, f"{interface_key}_status") not in (None, "")


def _vpn_candidate_score(parsed: dict[str, Any]) -> tuple[int, int, int, int, int]:
    """Score VPN pages so richer active-session pages win over placeholder ones."""
    protocol = _entry_value(parsed, "protocol")
    tunnel_ip = _entry_value(parsed, "tunnel_ip")
    vpn_clients = _entry_value(parsed, "vpn_clients")
    populated_fields = sum(value not in (None, "") for value in (protocol, vpn_clients, tunnel_ip))
    numeric_clients = vpn_clients if isinstance(vpn_clients, int) else -1
    return (
        1 if tunnel_ip not in (None, "") else 0,
        1 if numeric_clients > 0 else 0,
        1 if protocol not in (None, "") else 0,
        populated_fields,
        numeric_clients,
    )


def _vpn_device_client_count(data: dict[str, Any]) -> int:
    """Count devices currently routed over VPN when VPN status pages omit that total."""
    devices_data = data.get(MODULE_DEVICES, {})
    if not isinstance(devices_data, dict):
        return 0

    device_list = devices_data.get("device_list", [])
    if not isinstance(device_list, list):
        return 0

    count = 0
    for device in device_list:
        if not isinstance(device, dict):
            continue

        vpn_value = device.get("vpn")
        if vpn_value is True:
            count += 1
        elif isinstance(vpn_value, str) and vpn_value.strip().lower() in {"1", "true", "yes", "on"}:
            count += 1
    return count


def _vpn_active_protocol(vpn_settings: dict[str, Any]) -> str | None:
    """Return the selected VPN protocol key when VPN settings expose one."""
    if _entry_value(vpn_settings, "enabled") is False:
        return None

    protocol = _entry_value(vpn_settings, "protocol")
    if not isinstance(protocol, str) or not protocol.strip():
        return None
    return protocol.strip()


def _vpn_protocol_label(vpn_settings: dict[str, Any], protocol: str | None) -> str | None:
    """Return the display label for a VPN protocol setting value."""
    if not protocol:
        return None

    protocol_entry = vpn_settings.get("protocol", {})
    if not isinstance(protocol_entry, dict):
        return None

    options = protocol_entry.get("options", {})
    if not isinstance(options, dict):
        return None

    label = options.get(protocol)
    if not isinstance(label, str) or not label.strip():
        return None
    return label.strip()


def _vpn_status_path_matches_protocol(path: str, active_protocol: str | None) -> bool:
    """Return whether a VPN status endpoint belongs to the selected protocol."""
    if active_protocol is None:
        return True

    path_protocols = _VPN_STATUS_PATH_PROTOCOLS.get(path)
    return path_protocols is None or active_protocol in path_protocols


def _vpn_status_path_is_protocol_specific(path: str) -> bool:
    """Return whether a VPN status endpoint belongs to a named protocol."""
    return path in _VPN_STATUS_PATH_PROTOCOLS


def _contains_wan_iface_reference(text: str, expected_suffixes: tuple[str, ...]) -> bool:
    """Return whether text references the expected WAN number or letter."""
    expected = {suffix.lower() for suffix in expected_suffixes}
    for match in _WAN_INTERFACE_REFERENCE_RE.finditer(text):
        if match.group(1).lower() in expected:
            return True
    return False


def _contains_any_wan_iface_reference(text: str) -> bool:
    """Return whether text references a specific WAN interface."""
    return _WAN_INTERFACE_REFERENCE_RE.search(text) is not None


def _wan_status_has_conflicting_iface_reference(input_html: str, expected_suffixes: tuple[str, ...]) -> bool:
    """Return whether a WAN status page explicitly references a different iface."""
    if not expected_suffixes:
        return False

    soup = BeautifulSoup(input_html, "html.parser")
    heading_texts = [
        " ".join(element.stripped_strings)
        for element in soup.select(".panel-title, .panel-heading, h1, h2, h3, h4, legend")
    ]
    heading_texts = [text for text in heading_texts if text]
    for text in heading_texts:
        if _contains_any_wan_iface_reference(text) and not _contains_wan_iface_reference(
            text,
            expected_suffixes,
        ):
            return True

    return _contains_any_wan_iface_reference(input_html) and not _contains_wan_iface_reference(
        input_html,
        expected_suffixes,
    )


def _wan_status_matches_iface(input_html: str, expected_suffixes: tuple[str, ...]) -> bool:
    """Return whether a WAN status page appears to belong to the requested iface."""
    if not expected_suffixes:
        return True

    soup = BeautifulSoup(input_html, "html.parser")
    heading_texts = [
        " ".join(element.stripped_strings)
        for element in soup.select(".panel-title, .panel-heading, h1, h2, h3, h4, legend")
    ]
    heading_texts = [text for text in heading_texts if text]
    for text in heading_texts:
        if _contains_wan_iface_reference(text, expected_suffixes):
            return True
    if any(_contains_any_wan_iface_reference(text) for text in heading_texts):
        return False

    return _contains_wan_iface_reference(input_html, expected_suffixes)


def _wan_status_paths(iface_name: str) -> tuple[str, ...]:
    """Return WAN status endpoint candidates for an interface."""
    return tuple(path.format(iface_name=iface_name) for path in _WAN_STATUS_PATH_FORMATS)


def _wan_status_has_values(input_html: str) -> bool:
    """Return whether a WAN status page contains fields worth parsing."""
    normalized_html = input_html.lower()
    return any(marker in normalized_html for marker in _WAN_STATUS_VALUE_MARKERS)


def _wan_status_data_score(interface_data: dict[str, Any]) -> tuple[int, int]:
    """Score parsed WAN data so confirmed summaries can prefer earlier rich detail pages."""
    rich_fields = sum(
        interface_data.get(key, {}).get("value") not in (None, "")
        for key in _WAN_RICH_STATUS_KEYS
    )
    populated_fields = sum(
        entry.get("value") not in (None, "")
        for entry in interface_data.values()
        if isinstance(entry, dict)
    )
    return (rich_fields, populated_fields)


async def collect_router_data(
    router: Any,
    hass: HomeAssistant,
    options: dict[str, Any],
    device_model: str,
) -> dict[str, Any]:
    """Retrieve data from the router and parse feature modules."""

    data: dict[str, Any] = {}

    # Modem status (5G/LTE info)
    if existing_feature(device_model, MODULE_MODEM) is True:
        data[MODULE_MODEM] = parse_modem_info(
            f"{await hass.async_add_executor_job(router.get, 'admin/network/gcom/status')}{await hass.async_add_executor_job(router.get, 'admin/network/gcom/status?detail=1&iface=4g')}"
        )
        cellular_settings_html = await hass.async_add_executor_job(
            router.get,
            "admin/network/gcom/config/apn",
            True,
        )
        if cellular_settings_html:
            cellular_settings = parse_cellular_settings(cellular_settings_html)
            if cellular_settings:
                data[MODULE_CELLULAR_SETTINGS] = cellular_settings

    # Connected devices
    if existing_feature(device_model, MODULE_DEVICES) is True:
        data[MODULE_DEVICES] = parse_devices(
            await hass.async_add_executor_job(router.get, "admin/network/devices/devlist?detail=1"),
            options.get(OPTIONS_DEVICELIST) if options else None,
        )

        # Add device client counts to the devices module
        # Try multiple possible endpoints for device status
        devices_status_html = await hass.async_add_executor_job(router.get, "admin/network/devices/status?detail=1")
        # Also try the main panel which sometimes has client counts
        if not devices_status_html or "client" not in devices_status_html.lower():
            panel_html = await hass.async_add_executor_job(router.get, "admin/panel")
            devices_status_html = f"{devices_status_html}{panel_html}"

        devices_status = parse_devices_status(devices_status_html)
        data[MODULE_DEVICES].update(devices_status)

        arp_status_html = await hass.async_add_executor_job(
            router.get,
            "admin/system/status/arp",
            True,
        )
        if arp_status_html:
            data[MODULE_DEVICES].update(parse_arp_status(arp_status_html, "br-lan"))

    if existing_feature(device_model, MODULE_SYSTEM) is True:
        # System status (uptime, firmware, local time)
        # Fetch from multiple endpoints to increase chances of finding firmware
        system_html = await hass.async_add_executor_job(router.get, "admin/system/status")
        # Also try the main panel which often has firmware info
        panel_html = await hass.async_add_executor_job(router.get, "admin/panel")
        # Try overview page which sometimes has firmware (silently)
        overview_html = await hass.async_add_executor_job(
            router.get,
            "admin/status/overview",
            True,  # silent
        )
        # Try system page which sometimes has firmware (silently)
        system_page_html = await hass.async_add_executor_job(
            router.get,
            "admin/system/system",
            True,  # silent
        )
        data[MODULE_SYSTEM] = parse_system_status(
            f"{system_html}{panel_html}{overview_html or ''}{system_page_html or ''}"
        )

    # Data usage statistics
    if existing_feature(device_model, MODULE_DATA_USAGE) is True:
        data[MODULE_DATA_USAGE] = parse_data_usage(
            await hass.async_add_executor_job(router.get, "admin/network/gcom/statistics?iface=4g")
        )

    # SMS status
    if existing_feature(device_model, MODULE_SMS) is True:
        sms_status = parse_sms_status(
            await hass.async_add_executor_job(router.get, "admin/network/gcom/sms/status")
        )
        if sms_status is not None:
            data[MODULE_SMS] = sms_status

    # WiFi 2.4G status
    if existing_feature(device_model, MODULE_WIFI_2G) is True:
        data[MODULE_WIFI_2G] = parse_wifi_status(
            await hass.async_add_executor_job(router.get, "admin/network/wireless/status?iface=wlan00")
        )

    # WiFi 5G status
    if existing_feature(device_model, MODULE_WIFI_5G) is True:
        data[MODULE_WIFI_5G] = parse_wifi_status(
            await hass.async_add_executor_job(router.get, "admin/network/wireless/status?iface=wlan10")
        )

    # WISP / host-network uplink status
    if existing_feature(device_model, MODULE_WISP) is True:
        wisp_data: dict[str, Any] = {}

        best_wisp_status: dict[str, Any] = {}
        best_wisp_status_score = (-1, -1)
        for wisp_status_path in _WISP_STATUS_PATHS:
            wisp_status_html = await hass.async_add_executor_job(
                router.get,
                wisp_status_path,
                True,
            )
            if not wisp_status_html:
                continue

            parsed_wisp_status = _non_empty_entries(parse_wisp_status(wisp_status_html))
            candidate_score = _wisp_data_score(parsed_wisp_status)
            if candidate_score > best_wisp_status_score:
                best_wisp_status = parsed_wisp_status
                best_wisp_status_score = candidate_score
        _merge_module_entries(wisp_data, best_wisp_status)

        best_wisp_data: dict[str, Any] = {}
        best_wisp_data_score = (-1, -1)
        for wisp_data_path in _WISP_DATA_PATHS:
            wisp_data_payload = await hass.async_add_executor_job(
                router.get,
                wisp_data_path,
                True,
            )
            if not wisp_data_payload:
                continue

            parsed_wisp_data = _non_empty_entries(parse_wisp_data(wisp_data_payload))
            candidate_score = _wisp_data_score(parsed_wisp_data)
            if candidate_score > best_wisp_data_score:
                best_wisp_data = parsed_wisp_data
                best_wisp_data_score = candidate_score
        _merge_module_entries(wisp_data, best_wisp_data)

        for wisp_config_path in _WISP_CONFIG_PATHS:
            wisp_config_html = await hass.async_add_executor_job(
                router.get,
                wisp_config_path,
                True,
            )
            if not wisp_config_html:
                continue

            parsed_wisp_settings = _non_empty_entries(parse_wisp_settings(wisp_config_html))
            if parsed_wisp_settings:
                _merge_module_entries(wisp_data, parsed_wisp_settings)
                break

        if wisp_data:
            data[MODULE_WISP] = wisp_data

    # LAN status
    if existing_feature(device_model, MODULE_LAN) is True:
        lan_status_html = await hass.async_add_executor_job(
            router.get,
            "admin/network/lan/status?detail=1",
            True,
        )
        if not lan_status_html or "ip address" not in lan_status_html.lower():
            lan_status_html = await hass.async_add_executor_job(router.get, "admin/network/lan/status")

        lan_data = parse_lan_status(lan_status_html)
        for lan_settings_path in (
            "admin/network/lan/config?nomodal=",
            "admin/network/lan/config/detail?nomodal=",
        ):
            lan_settings_html = await hass.async_add_executor_job(
                router.get,
                lan_settings_path,
                True,
            )
            if not lan_settings_html:
                continue

            lan_settings = parse_lan_settings(lan_settings_html)
            if lan_settings:
                lan_data.update(lan_settings)
                break
        data[MODULE_LAN] = lan_data

    # VPN status
    if existing_feature(device_model, MODULE_VPN) is True:
        vpn_settings: dict[str, Any] = {}
        vpn_settings_html = await hass.async_add_executor_job(
            router.get,
            "admin/network/vpn/config",
            True,
        )
        if vpn_settings_html:
            vpn_settings = parse_vpn_settings(vpn_settings_html)
            if vpn_settings:
                data[MODULE_VPN_SETTINGS] = vpn_settings

        active_vpn_protocol = _vpn_active_protocol(vpn_settings)
        active_vpn_protocol_label = _vpn_protocol_label(vpn_settings, active_vpn_protocol)
        vpn_status_html = ""
        best_vpn_data: dict[str, Any] | None = None
        best_vpn_score = (-1, -1, -1, -1, -1)
        best_specific_vpn_data: dict[str, Any] | None = None
        best_specific_vpn_score = (-1, -1, -1, -1, -1)
        fallback_vpn_data: dict[str, Any] | None = None
        fallback_vpn_score = (-1, -1, -1, -1, -1)
        vpn_status_client_counts: list[int] = []
        vpn_specific_client_counts: list[int] = []
        for vpn_status_path in _VPN_STATUS_PATHS:
            candidate_html = await hass.async_add_executor_job(
                router.get,
                vpn_status_path,
                True,
            )
            if not candidate_html:
                continue

            if not vpn_status_html:
                vpn_status_html = candidate_html

            parsed_candidate = parse_vpn_status(candidate_html)
            candidate_score = _vpn_candidate_score(parsed_candidate)
            if candidate_score > fallback_vpn_score:
                fallback_vpn_data = parsed_candidate
                fallback_vpn_score = candidate_score

            if not _vpn_status_path_matches_protocol(vpn_status_path, active_vpn_protocol):
                continue

            if candidate_score > best_vpn_score:
                best_vpn_data = parsed_candidate
                best_vpn_score = candidate_score
            if (
                active_vpn_protocol is not None
                and _vpn_status_path_is_protocol_specific(vpn_status_path)
                and candidate_score > best_specific_vpn_score
            ):
                best_specific_vpn_data = parsed_candidate
                best_specific_vpn_score = candidate_score

            vpn_clients = _entry_value(parsed_candidate, "vpn_clients")
            if isinstance(vpn_clients, int):
                if active_vpn_protocol is not None and _vpn_status_path_is_protocol_specific(vpn_status_path):
                    vpn_specific_client_counts.append(vpn_clients)
                else:
                    vpn_status_client_counts.append(vpn_clients)

        if best_specific_vpn_data is not None:
            selected_vpn_data = best_specific_vpn_data
        elif best_vpn_data is not None:
            selected_vpn_data = best_vpn_data
        elif fallback_vpn_data is not None:
            selected_vpn_data = fallback_vpn_data
        else:
            selected_vpn_data = parse_vpn_status(vpn_status_html)

        vpn_data = dict(selected_vpn_data)
        if active_vpn_protocol_label is not None:
            vpn_data["protocol"] = {"value": active_vpn_protocol_label}

        vpn_client_counts = vpn_specific_client_counts or vpn_status_client_counts
        if not vpn_client_counts and (vpn_device_client_count := _vpn_device_client_count(data)):
            vpn_client_counts.append(vpn_device_client_count)
        if vpn_client_counts:
            vpn_data["vpn_clients"] = {"value": max(vpn_client_counts)}
        data[MODULE_VPN] = vpn_data

    # DHCP status
    if existing_feature(device_model, MODULE_DHCP) is True:
        data[MODULE_DHCP] = parse_dhcp_status(
            await hass.async_add_executor_job(router.get, "admin/services/dhcp/status?detail=1")
        )

    # Load-balancing status
    if existing_feature(device_model, MODULE_LOAD_BALANCING) is True:
        load_balancing_status_html = ""
        for load_balancing_status_path in _LOAD_BALANCING_STATUS_PATHS:
            load_balancing_status_html = await hass.async_add_executor_job(
                router.get,
                load_balancing_status_path,
                True,
            )
            if load_balancing_status_html:
                break
        data[MODULE_LOAD_BALANCING] = parse_load_balancing_status(load_balancing_status_html)

    # WAN status
    if existing_feature(device_model, MODULE_WAN) is True:
        # Probe support first; some models expose a generic/empty page.
        wan_candidates: list[tuple[str, str, dict[str, Any]]] = []
        wan_interfaces: dict[str, dict[str, Any]] = {}
        load_balancing_data = data.get(MODULE_LOAD_BALANCING, {})
        for iface_name, interface_key, expected_suffixes, query_iface_names in _WAN_STATUS_IFACES:
            if iface_name != "wan" and existing_feature(device_model, MODULE_LOAD_BALANCING) is not True:
                continue
            if (
                iface_name != "wan"
                and isinstance(load_balancing_data, dict)
                and load_balancing_data
                and not _load_balancing_has_interface(load_balancing_data, interface_key)
            ):
                continue

            for query_iface_name in query_iface_names:
                matched_status = False
                provisional_status: dict[str, Any] | None = None
                provisional_score = (-1, -1)
                for wan_status_path in _wan_status_paths(query_iface_name):
                    wan_status_html = await hass.async_add_executor_job(
                        router.get,
                        wan_status_path,
                        True,
                    )
                    if not wan_status_html:
                        continue

                    if not _wan_status_has_values(wan_status_html):
                        continue

                    parsed_wan_status = parse_wan_status(wan_status_html)
                    interface_data = _non_empty_entries(parsed_wan_status)
                    if not interface_data:
                        continue

                    if _wan_status_matches_iface(wan_status_html, expected_suffixes):
                        if provisional_status is not None and provisional_score > _wan_status_data_score(
                            interface_data
                        ):
                            interface_data = provisional_status
                        wan_candidates.append((iface_name, interface_key, interface_data))
                        wan_interfaces[interface_key] = dict(interface_data)
                        matched_status = True
                        break

                    # Some R700 detail endpoints for wanb/wanc contain the right
                    # rich data but no WAN label. Keep it until a later summary
                    # endpoint confirms the iface, while still rejecting default
                    # WAN1 fallback pages for unknown names.
                    if not _wan_status_has_conflicting_iface_reference(wan_status_html, expected_suffixes):
                        candidate_score = _wan_status_data_score(interface_data)
                        if candidate_score > provisional_score:
                            provisional_status = dict(interface_data)
                            provisional_score = candidate_score
                if matched_status:
                    break

        _apply_load_balancing_statuses(
            wan_interfaces,
            load_balancing_data,
        )

        if wan_candidates:
            wan_data = dict(wan_candidates[0][2])
            for byte_key in ("bytes_received", "bytes_sent"):
                byte_values = [
                    entry.get(byte_key, {}).get("value")
                    for _, _, entry in wan_candidates
                    if entry.get(byte_key, {}).get("value") is not None
                ]
                if byte_values:
                    wan_data[byte_key] = {"value": sum(byte_values)}

            for wan_settings_path in (
                "admin/network/wan/config/detail?nomodal=&iface=wan",
                "admin/network/wan/config?nomodal=&iface=wan",
            ):
                wan_settings_html = await hass.async_add_executor_job(
                    router.get,
                    wan_settings_path,
                    True,
                )
                if not wan_settings_html:
                    continue

                wan_settings = parse_wan_settings(wan_settings_html)
                config_subnet_mask = wan_settings.get("subnet_mask", {}).get("value")
                status_subnet_mask = wan_data.get("subnet_mask", {}).get("value")
                has_live_wan_addressing = any(
                    wan_data.get(key, {}).get("value") not in (None, "")
                    for key in ("public_ip", "wan_ip", "gateway", "dns")
                )
                # PPPoE WAN status can legitimately report a /32 mask. Only use the
                # config fallback when the live status page omits the mask entirely.
                if (
                    has_live_wan_addressing
                    and config_subnet_mask not in (None, "")
                    and status_subnet_mask in (None, "")
                ):
                    wan_data["subnet_mask"] = {"value": config_subnet_mask}
                    if "wan1" in wan_interfaces:
                        wan_interfaces["wan1"]["subnet_mask"] = {"value": config_subnet_mask}
                if wan_settings:
                    break

            # Some firmware only exposes DNS/Gateway on DHCP status.
            dhcp_data = data.get(MODULE_DHCP, {})
            dhcp_gateway = dhcp_data.get("dhcp_default_gateway", {}).get("value")
            dhcp_dns = dhcp_data.get("dhcp_prefered_dns", {}).get("value")
            if wan_data.get("gateway", {}).get("value") in (None, "") and dhcp_gateway not in (None, ""):
                wan_data["gateway"] = {"value": dhcp_gateway}
                if "wan1" in wan_interfaces:
                    wan_interfaces["wan1"].setdefault("gateway", {"value": dhcp_gateway})
            if wan_data.get("dns", {}).get("value") in (None, "") and dhcp_dns not in (None, ""):
                wan_data["dns"] = {"value": dhcp_dns}
                if "wan1" in wan_interfaces:
                    wan_interfaces["wan1"].setdefault("dns", {"value": dhcp_dns})

            # If modem metrics exist, avoid duplicate WAN entities for the same values.
            for duplicated_key in (
                "connected_time",
                "public_ip",
                "session_upload",
                "session_download",
                "wan_ip",
            ):
                if _module_entry_has_value(data, MODULE_MODEM, duplicated_key):
                    wan_data.pop(duplicated_key, None)

            # Skip empty WAN sensors to avoid persistent Unknown entities.
            wan_data = {
                key: entry
                for key, entry in wan_data.items()
                if entry.get("value") not in (None, "")
            }
            if wan_data:
                data[MODULE_WAN] = wan_data

        if wan_interfaces and existing_feature(device_model, MODULE_WAN_INTERFACES) is True:
            data[MODULE_WAN_INTERFACES] = {
                interface_key: interface_data
                for interface_key, interface_data in wan_interfaces.items()
                if interface_data
            }

    if existing_feature(device_model, MODULE_WIRELESS_SETTINGS) is True:
        wireless_combo_html = await hass.async_add_executor_job(
            router.get,
            "admin/network/wireless/config/combo",
            True,
        )
        if wireless_combo_html:
            wireless_combine_html = await hass.async_add_executor_job(
                router.get,
                "admin/network/wireless/config/combine",
                True,
            )
            wireless_uncombine_html = await hass.async_add_executor_job(
                router.get,
                "admin/network/wireless/config/uncombine",
                True,
            )
            wireless_settings = parse_wireless_settings(
                wireless_combo_html,
                wireless_combine_html,
                wireless_uncombine_html,
            )
            if wireless_settings:
                data[MODULE_WIRELESS_SETTINGS] = wireless_settings

    if existing_feature(device_model, MODULE_AUTO_UPDATE_SETTINGS) is True:
        for auto_update_path in ("admin/system/autoupgrade", "admin/setup"):
            auto_update_html = await hass.async_add_executor_job(
                router.get,
                auto_update_path,
                True,
            )
            if not auto_update_html:
                continue

            auto_update_settings = parse_auto_update_settings(auto_update_html)
            if auto_update_settings:
                data[MODULE_AUTO_UPDATE_SETTINGS] = auto_update_settings
                break

    # Mesh devices - try multiple possible endpoints (silent since mesh is optional)
    if existing_feature(device_model, MODULE_MESH) is True:
        mesh_html = ""
        mesh_endpoints = [
            "admin/network/mesh/status",
            "admin/network/mesh",
            "admin/network/mesh/topology",
            "admin/network/mesh/nodes",
            "admin/easymesh/status",
            "admin/easymesh",
        ]
        for endpoint in mesh_endpoints:
            result = await hass.async_add_executor_job(
                router.get,
                endpoint,
                True,  # silent=True
            )
            if result and ("mesh" in result.lower() or "node" in result.lower() or "satellite" in result.lower()):
                mesh_html += result  # Combine results from multiple endpoints
                _LOGGER.debug(
                    "Found mesh data at endpoint: %s (length: %d)",
                    endpoint,
                    len(result),
                )

        # Parse basic mesh data first to get list of satellites
        mesh_data = parse_mesh_devices(mesh_html)

        # Try to get list of mesh clients via JSON endpoint
        import json
        import re

        client_macs = []
        clients_json_data = []

        # First try the clients JSON endpoint - this returns rich data!
        clients_result = await hass.async_add_executor_job(router.get, "admin/network/mesh/clients?clients=all", True)
        if clients_result:
            _LOGGER.debug(
                "Mesh clients endpoint result (first 500): %s",
                clients_result[:500] if clients_result else "None",
            )
            # Try to parse as JSON - get the full array
            try:
                # The response should be a JSON array
                json_match = re.search(r"\[.*\]", clients_result, re.DOTALL)
                if json_match:
                    clients_json_data = json.loads(json_match.group(0))
                    for client in clients_json_data:
                        if isinstance(client, dict) and client.get("id"):
                            client_macs.append(client["id"])
            except (json.JSONDecodeError, TypeError) as e:
                _LOGGER.debug("Could not parse clients JSON: %s", e)

        # Also look for client MAC addresses in tab IDs from mesh HTML
        html_macs = re.findall(r"tab-([0-9A-Fa-f]{12})-", mesh_html)
        html_macs.extend(re.findall(r"client=([0-9A-Fa-f]{12})", mesh_html))
        client_macs.extend(html_macs)

        # Remove duplicates and filter out invalid entries
        client_macs = list(set(mac for mac in client_macs if len(mac) == 12))
        _LOGGER.debug("Found mesh client MACs: %s", client_macs)

        # First, extract data from JSON for each client
        json_client_data: dict[str, dict] = {}
        for client_json in clients_json_data:
            if not isinstance(client_json, dict):
                continue
            client_id = client_json.get("id", "")
            if not client_id:
                continue

            # Format MAC
            formatted_mac = ":".join(client_id[i : i + 2] for i in range(0, 12, 2)).upper()

            # Extract data from JSON
            sysreport = client_json.get("sysreport", {})
            # Use hardware name (e.g. "RE1200 V1.0") as model if available, fall back to model code
            hardware = sysreport.get("hardware", "")
            model_name = hardware.split(" ")[0] if hardware else sysreport.get("board") or sysreport.get("model")
            json_client_data[formatted_mac] = {
                "name": client_json.get("name"),
                "model": model_name,
                "firmware_version": sysreport.get("firmware"),
                "ip_address": sysreport.get("ipaddr"),
                "mac_address": formatted_mac,
                "hardware": hardware,
                "status": "online" if client_json.get("state") == "connected" else "offline",
                "led_status": sysreport.get("ledstatus"),
                "backhaul": sysreport.get("backhaul"),
            }
            _LOGGER.debug(
                "Parsed mesh client from JSON: %s -> %s",
                client_id,
                json_client_data[formatted_mac],
            )

        for client_mac in client_macs:
            # Skip the main router (id=000000000000) for mesh devices
            # but extract its LED status for the main router LED switch
            if client_mac == "000000000000":
                formatted_mac = ":".join(client_mac[i : i + 2] for i in range(0, 12, 2)).upper()
                _LOGGER.debug(
                    "Skipping main router in mesh client loop, formatted_mac=%s, in json_data=%s",
                    formatted_mac,
                    formatted_mac in json_client_data,
                )
                if formatted_mac in json_client_data:
                    main_router_data = json_client_data[formatted_mac]
                    mesh_data["main_router_led_status"] = main_router_data.get("led_status")
                    _LOGGER.debug(
                        "Main router LED status: %s",
                        mesh_data["main_router_led_status"],
                    )
                continue

            # Format MAC address with colons
            formatted_mac = ":".join(client_mac[i : i + 2] for i in range(0, 12, 2)).upper()

            # Start with JSON data if available
            client_info = {}
            if formatted_mac in json_client_data:
                client_info = json_client_data[formatted_mac].copy()
                _LOGGER.debug("Using JSON data for %s: %s", formatted_mac, client_info)

            # Fetch device status for this mesh client to get additional details
            devstatus_url = f"admin/network/mesh/client/devstatus?embedded=&client={client_mac}"
            devstatus_html = await hass.async_add_executor_job(router.get, devstatus_url, True)

            # Fetch device list (connected devices) for this mesh client
            devlist_url = f"admin/network/mesh/client/devlist?embedded=&client={client_mac}"
            devlist_html = await hass.async_add_executor_job(router.get, devlist_url, True)

            if devstatus_html:
                _LOGGER.debug(
                    "Got mesh client devstatus for %s (length: %d)",
                    client_mac,
                    len(devstatus_html),
                )
                # Parse HTML for additional info (backhaul, pre-hop, connected_devices count)
                html_info = parse_mesh_client_status(devstatus_html, devlist_html)
                if html_info:
                    _LOGGER.debug("Parsed HTML info for %s: %s", formatted_mac, html_info)
                    # Merge HTML data, but prefer JSON data for fields that exist in both
                    for key, value in html_info.items():
                        # For connected_devices, always use HTML value (JSON doesn't have this)
                        if key == "connected_devices":
                            client_info[key] = value
                        elif (
                            key not in client_info or not client_info.get(key) or client_info.get(key) == "Unknown"
                        ):
                            client_info[key] = value

            # Ensure we have required fields
            if not client_info.get("name"):
                client_info["name"] = f"Mesh Device {client_mac[-6:]}"
            client_info["mac_address"] = formatted_mac

            _LOGGER.debug(
                "Final mesh device info for %s: name=%s, model=%s, firmware=%s, ip=%s, connected=%s",
                formatted_mac,
                client_info.get("name"),
                client_info.get("model"),
                client_info.get("firmware_version"),
                client_info.get("ip_address"),
                client_info.get("connected_devices"),
            )

            # Find matching device in mesh_data or add new one
            found = False
            for mac, device in list(mesh_data.get("mesh_devices", {}).items()):
                # Match by MAC or by name
                if mac.replace(":", "").upper() == client_mac.upper():
                    device.update(client_info)
                    found = True
                    _LOGGER.debug("Updated existing device by MAC: %s", mac)
                    break
                elif device.get("name", "").lower() == client_info.get("name", "").lower() and mac.startswith(
                    "mesh_"
                ):
                    # Found by name with placeholder MAC - remove old entry and add new one
                    mesh_data["mesh_devices"].pop(mac)
                    mesh_data["mesh_devices"][formatted_mac] = client_info
                    found = True
                    _LOGGER.debug(
                        "Replaced placeholder device %s with real MAC %s",
                        mac,
                        formatted_mac,
                    )
                    break

            if not found:
                # Add as new device with real MAC
                mesh_data["mesh_devices"][formatted_mac] = client_info
                _LOGGER.debug("Added new mesh device: %s", formatted_mac)

        mesh_data["mesh_count"] = {"value": len(mesh_data.get("mesh_devices", {}))}
        data[MODULE_MESH] = mesh_data

    return data
