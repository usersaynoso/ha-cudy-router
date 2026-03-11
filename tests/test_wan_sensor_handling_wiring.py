"""Static wiring checks for WAN/modem dedupe and WAN fallback parsing."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SENSOR_PATH = ROOT / "custom_components" / "cudy_router" / "sensor.py"
PARSER_NETWORK_PATH = ROOT / "custom_components" / "cudy_router" / "parser_network.py"
ROUTER_DATA_PATH = ROOT / "custom_components" / "cudy_router" / "router_data.py"


def test_sensor_setup_skips_duplicate_wan_modem_metrics() -> None:
    """Sensor setup should avoid duplicate WAN entities for modem metrics."""
    source = SENSOR_PATH.read_text(encoding="utf-8")

    assert "_WAN_DUPLICATE_MODEM_KEYS" in source
    for key in ("connected_time", "public_ip", "session_upload", "session_download"):
        assert f'"{key}"' in source

    assert "module == MODULE_WAN" in source
    assert "sensor_label in _WAN_DUPLICATE_MODEM_KEYS" in source
    assert "MODULE_MODEM in coordinator.data" in source


def test_sensor_setup_skips_empty_sensor_values() -> None:
    """Sensor setup should not create entities that have no value."""
    source = SENSOR_PATH.read_text(encoding="utf-8")

    assert 'data_entry.get("value") in (None, "")' in source


def test_wan_parser_supports_fallback_key_names() -> None:
    """WAN parser should support alternate field labels used by Cudy pages."""
    source = PARSER_NETWORK_PATH.read_text(encoding="utf-8")

    assert '"Subnet Mask", "Subnet", "Netmask", "Mask"' in source
    assert '"Gateway", "Default Gateway"' in source
    assert '"DNS", "Preferred DNS", "Primary DNS"' in source


def test_router_data_uses_dhcp_fallbacks_and_filters_empty_wan_values() -> None:
    """Router data collection should enrich WAN data and avoid empty sensors."""
    source = ROUTER_DATA_PATH.read_text(encoding="utf-8")

    assert 'dhcp_data.get("dhcp_default_gateway", {}).get("value")' in source
    assert 'dhcp_data.get("dhcp_prefered_dns", {}).get("value")' in source
    assert 'wan_data.pop(duplicated_key, None)' in source
    assert 'if entry.get("value") not in (None, "")' in source
