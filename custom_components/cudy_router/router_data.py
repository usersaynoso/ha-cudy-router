"""Data collection helpers for Cudy routers."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    MODULE_DATA_USAGE,
    MODULE_DEVICES,
    MODULE_DHCP,
    MODULE_LAN,
    MODULE_MESH,
    MODULE_MODEM,
    MODULE_SMS,
    MODULE_SYSTEM,
    MODULE_VPN,
    MODULE_WAN,
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
from .parser_network import parse_dhcp_status, parse_vpn_status, parse_wan_status

_LOGGER = logging.getLogger(__name__)


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

    # Connected devices
    if existing_feature(device_model, MODULE_DEVICES) is True:
        data[MODULE_DEVICES] = parse_devices(
            await hass.async_add_executor_job(router.get, "admin/network/devices/devlist?detail=1"),
            options and options.get(OPTIONS_DEVICELIST),
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
        data[MODULE_SMS] = parse_sms_status(
            await hass.async_add_executor_job(router.get, "admin/network/gcom/sms/status")
        )

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

    # LAN status
    if existing_feature(device_model, MODULE_LAN) is True:
        data[MODULE_LAN] = parse_lan_status(await hass.async_add_executor_job(router.get, "admin/network/lan/status"))

    # VPN status
    if existing_feature(device_model, MODULE_VPN) is True:
        data[MODULE_VPN] = parse_vpn_status(
            await hass.async_add_executor_job(router.get, "admin/network/vpn/openvpns/status?status=")
        )

    # WAN status
    if existing_feature(device_model, MODULE_WAN) is True:
        # Probe support first; some models expose a generic/empty page.
        wan_status_html = await hass.async_add_executor_job(
            router.get,
            "admin/network/wan/status?detail=1&iface=wan",
            True,
        )
        if wan_status_html and any(
            marker in wan_status_html.lower()
            for marker in ("public ip", "ip address", "gateway", "subnet", "protocol")
        ):
            wan_data = parse_wan_status(wan_status_html)
            if any(entry.get("value") not in (None, "") for entry in wan_data.values()):
                data[MODULE_WAN] = wan_data

    # DHCP status
    if existing_feature(device_model, MODULE_DHCP) is True:
        data[MODULE_DHCP] = parse_dhcp_status(
            await hass.async_add_executor_job(router.get, "admin/services/dhcp/status?detail=1")
        )

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

            _LOGGER.info(
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

        data[MODULE_MESH] = mesh_data

    return data
