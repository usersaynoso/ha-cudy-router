"""Static wiring checks for WAN/modem dedupe and WAN fallback parsing."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SENSOR_PATH = ROOT / "custom_components" / "cudy_router" / "sensor.py"
PARSER_NETWORK_PATH = ROOT / "custom_components" / "cudy_router" / "parser_network.py"
ROUTER_DATA_PATH = ROOT / "custom_components" / "cudy_router" / "router_data.py"
SENSOR_DESCRIPTIONS_PATH = ROOT / "custom_components" / "cudy_router" / "sensor_descriptions.py"


def test_sensor_setup_skips_duplicate_wan_modem_metrics() -> None:
    """Sensor setup should avoid duplicate WAN entities for modem metrics."""
    source = SENSOR_PATH.read_text(encoding="utf-8")

    assert "_WAN_DUPLICATE_MODEM_KEYS" in source
    for key in ("connected_time", "public_ip", "session_upload", "session_download", "wan_ip"):
        assert f'"{key}"' in source

    assert "module == MODULE_WAN" in source
    assert "sensor_label in _WAN_DUPLICATE_MODEM_KEYS" in source
    assert "MODULE_MODEM in coordinator.data" in source


def test_sensor_setup_removes_stale_wan_mac_entity() -> None:
    """Sensor setup should clean up the removed WAN MAC entity from the registry."""
    source = SENSOR_PATH.read_text(encoding="utf-8")
    descriptions_source = SENSOR_DESCRIPTIONS_PATH.read_text(encoding="utf-8")

    assert "_WAN_REMOVED_SENSOR_KEYS" in source
    assert '"mac_address"' in source
    assert '_remove_sensor_by_unique_id(f"{config_entry.entry_id}-{MODULE_WAN}-{sensor_key}")' in source
    assert '(MODULE_WAN, "mac_address")' not in descriptions_source
    assert 'name_suffix="WAN MAC"' not in descriptions_source


def test_sensor_setup_skips_empty_sensor_values() -> None:
    """Sensor setup should not create entities that have no value."""
    source = SENSOR_PATH.read_text(encoding="utf-8")

    assert 'data_entry.get("value") in (None, "")' in source


def test_sensor_setup_removes_inactive_load_balancing_entities() -> None:
    """Inactive load-balancing WAN sensors should be cleaned up from the registry."""
    source = SENSOR_PATH.read_text(encoding="utf-8")

    assert "_LOAD_BALANCING_DYNAMIC_KEYS" in source
    assert "MODULE_LOAD_BALANCING" in source
    assert 'f"{config_entry.entry_id}-{MODULE_LOAD_BALANCING}-{sensor_key}"' in source


def test_wan_parser_supports_fallback_key_names() -> None:
    """WAN parser should support alternate field labels used by Cudy pages."""
    source = PARSER_NETWORK_PATH.read_text(encoding="utf-8")

    assert "normalized_lookup" in source
    assert 'key.strip().lower()' in source
    assert '"MAC-Address", "MAC Address", "MAC", "WAN MAC", "WAN MAC Address"' in source
    assert '"IP Address", "WAN IP", "IPv4 Address", "IP"' in source
    assert '"Subnet Mask", "Subnet", "Netmask", "Mask"' in source
    assert '"Gateway", "Default Gateway"' in source
    assert '"DNS", "Preferred DNS", "Primary DNS"' in source


def test_router_data_collects_wan_even_when_modem_exists() -> None:
    """WAN polling should still run on modem routers so WAN-only fields populate."""
    source = ROUTER_DATA_PATH.read_text(encoding="utf-8")

    assert "if existing_feature(device_model, MODULE_WAN) is True:" in source
    assert "if existing_feature(device_model, MODULE_WAN) is True and MODULE_MODEM not in data:" not in source


def test_router_data_uses_dhcp_fallbacks_and_filters_empty_wan_values() -> None:
    """Router data collection should enrich WAN data and avoid empty sensors."""
    source = ROUTER_DATA_PATH.read_text(encoding="utf-8")

    assert 'dhcp_data.get("dhcp_default_gateway", {}).get("value")' in source
    assert 'dhcp_data.get("dhcp_prefered_dns", {}).get("value")' in source
    assert 'wan_data.pop(duplicated_key, None)' in source
    assert '"wan_ip"' in source
    assert 'if entry.get("value") not in (None, "")' in source


def test_router_data_collects_lan_subnet_and_guards_wan_subnet_fallback() -> None:
    """Subnet masks should come from LAN config and only guarded WAN fallbacks."""
    source = ROUTER_DATA_PATH.read_text(encoding="utf-8")

    assert "parse_lan_settings" in source
    assert "admin/network/lan/config?nomodal=" in source
    assert "admin/network/lan/config/detail?nomodal=" in source
    assert "parse_wan_settings" in source
    assert "admin/network/mwan3/status?detail=" in source
    assert '"wanb"' in source
    assert '"wanc"' in source
    assert "admin/network/wan/config/detail?nomodal=&iface=wan" in source
    assert "admin/network/wan/config?nomodal=&iface=wan" in source
    assert 'status_subnet_mask in (None, "")' in source
    assert 'for key in ("public_ip", "wan_ip", "gateway", "dns")' in source


def test_sensor_descriptions_distinguish_lan_and_wan_subnet_entities() -> None:
    """Sensor descriptions should expose separate LAN and WAN subnet names."""
    source = SENSOR_DESCRIPTIONS_PATH.read_text(encoding="utf-8")

    assert '(MODULE_WAN, "subnet_mask")' in source
    assert 'name_suffix="WAN Subnet mask"' in source
    assert '(MODULE_LAN, "subnet_mask")' in source
    assert 'name_suffix="Subnet mask"' in source
