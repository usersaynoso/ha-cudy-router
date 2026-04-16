"""Functional parser tests using representative multi-model fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.module_loader import load_cudy_module


const = load_cudy_module("const")
load_cudy_module("model_names")
parser = load_cudy_module("parser")
parser_network = load_cudy_module("parser_network")
parser_settings = load_cudy_module("parser_settings")


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture_text(*parts: str) -> str:
    return (FIXTURES.joinpath(*parts)).read_text(encoding="utf-8")


def test_parse_devices_supports_legacy_device_layout() -> None:
    """Legacy device rows should still produce device metrics and details."""
    parsed = parser.parse_devices(
        _fixture_text("devices", "legacy_devices.html"),
        "AA:BB:CC:DD:EE:01",
    )

    assert parsed["device_count"]["value"] == 2
    assert len(parsed[const.SECTION_DEVICE_LIST]) == 2
    assert parsed["top_downloader_hostname"]["value"] == "Office Laptop"
    assert parsed[const.SECTION_DETAILED]["AA:BB:CC:DD:EE:01"]["ip"] == "192.168.10.20"


def test_parse_devices_supports_modern_device_layout() -> None:
    """Newer Cudy connected-device tables should also be parsed."""
    parsed = parser.parse_devices(
        _fixture_text("devices", "modern_devices.html"),
        "tablet",
    )

    assert parsed["device_count"]["value"] == 2
    assert len(parsed[const.SECTION_DEVICE_LIST]) == 2
    assert parsed["top_downloader_hostname"]["value"] == "Gaming PC"
    assert parsed[const.SECTION_DETAILED]["tablet"]["mac"] == "AA:BB:CC:DD:EE:31"


def test_parse_system_status_supports_alternate_labels() -> None:
    """System parser should handle label variants seen on other Cudy models."""
    parsed = parser.parse_system_status(_fixture_text("system", "system_alt_labels.html"))

    assert parsed["firmware_version"]["value"] == "2.3.4-beta1"
    assert parsed["local_time"]["value"] == "2026-03-26 12:15:00"
    assert parsed["uptime"]["value"] == pytest.approx(97276.0)


def test_parse_wan_status_supports_alternate_labels() -> None:
    """WAN parser should accept common alternate field names."""
    parsed = parser_network.parse_wan_status(_fixture_text("wan", "wan_alt_labels.html"))

    assert parsed["protocol"]["value"] == "DHCP"
    assert parsed["mac_address"]["value"] == "AA:BB:CC:DD:EE:FF"
    assert parsed["public_ip"]["value"] == "203.0.113.10"
    assert parsed["wan_ip"]["value"] == "100.64.0.2"
    assert parsed["subnet_mask"]["value"] == "255.255.255.0"
    assert parsed["gateway"]["value"] == "100.64.0.1"
    assert parsed["dns"]["value"] == "1.1.1.1"
    assert parsed["session_upload"]["value"] == 51.6
    assert parsed["session_download"]["value"] == 368.07


def test_parse_arp_status_counts_br_lan_entries() -> None:
    """ARP parsing should count only the requested interface rows."""
    parsed = parser_network.parse_arp_status(_fixture_text("devices", "r700_arp_status.html"), "br-lan")

    assert parsed["arp_br_lan_count"]["value"] == 3


def test_parse_lan_settings_reads_subnet_mask_from_config_page() -> None:
    """LAN config parsing should expose the router subnet mask."""
    parsed = parser_settings.parse_lan_settings(_fixture_text("lan", "lan_config_subnet.html"))

    assert parsed["ip_address"]["value"] == "192.168.10.1"
    assert parsed["subnet_mask"]["value"] == "255.255.255.0"


def test_parse_lan_status_reads_byte_counters() -> None:
    """LAN status parsing should expose explicit RX/TX byte counters."""
    parsed = parser.parse_lan_status(_fixture_text("lan", "lan_status_bytes.html"))

    assert parsed["bytes_received"]["value"] == int(1.5 * 1024**3)
    assert parsed["bytes_sent"]["value"] == 512 * 1024**2


def test_parse_wan_settings_reads_protocol_and_subnet_mask_from_config_page() -> None:
    """WAN config parsing should keep the selected protocol and configured mask."""
    parsed = parser_settings.parse_wan_settings(_fixture_text("wan", "wan_config_subnet.html"))

    assert parsed["protocol"]["value"] == "dhcp"
    assert parsed["subnet_mask"]["value"] == "255.255.255.0"


def test_parse_wan_status_reads_byte_counters() -> None:
    """WAN status parsing should expose explicit receive/transmit byte counters."""
    parsed = parser_network.parse_wan_status(_fixture_text("wan", "wan_status_bytes.html"))

    assert parsed["bytes_received"]["value"] == 2 * 1024**3
    assert parsed["bytes_sent"]["value"] == 256 * 1024**2


def test_parse_vpn_status_reads_r700_pptp_fields() -> None:
    """R700 VPN status parsing should expose the PPTP protocol and tunnel IP."""
    parsed = parser_network.parse_vpn_status(_fixture_text("vpn", "vpn_r700_status.html"))

    assert parsed["protocol"]["value"] == "PPTP Client"
    assert parsed["tunnel_ip"]["value"] == "192.168.2.20"
    assert parsed["vpn_clients"]["value"] is None


def test_parse_load_balancing_status_reads_r700_interfaces() -> None:
    """R700 load-balancing status parsing should expose interface health."""
    parsed = parser_network.parse_load_balancing_status(_fixture_text("load_balancing", "r700_status.html"))

    assert set(parsed) == {"wan1_status", "wan4_status"}
    assert parsed["wan1_status"]["value"] == "Online"
    assert parsed["wan4_status"]["value"] == "Online"


def test_parse_load_balancing_status_supports_middle_wan_interfaces() -> None:
    """Load-balancing parsing should support WAN2/WAN3 without inventing other sensors."""
    parsed = parser_network.parse_load_balancing_status(_fixture_text("load_balancing", "r700_status_wan2_wan3.html"))

    assert set(parsed) == {"wan2_status", "wan3_status"}
    assert parsed["wan2_status"]["value"] == "Online"
    assert parsed["wan3_status"]["value"] == "Offline"


def test_parse_load_balancing_status_supports_protocol_annotated_interfaces() -> None:
    """Protocol text in the interface column should not hide a WAN3 status row."""
    parsed = parser_network.parse_load_balancing_status(
        _fixture_text("load_balancing", "r700_status_protocol_labels.html")
    )

    assert set(parsed) == {"wan1_status", "wan3_status"}
    assert parsed["wan1_status"]["value"] == "Online"
    assert parsed["wan3_status"]["value"] == "Online"


def test_get_sim_value_returns_none_when_status_icon_is_missing() -> None:
    """Missing SIM markup should not emit an invalid enum sensor state."""
    assert parser.get_sim_value("<html><body><p>No SIM icon</p></body></html>") is None


def test_get_signal_strength_returns_none_when_rssi_is_missing() -> None:
    """Missing RSSI should not emit a string sentinel into numeric signal handling."""
    assert parser.get_signal_strength(None) is None
