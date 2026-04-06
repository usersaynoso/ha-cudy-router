"""Functional parser tests using representative multi-model fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.module_loader import load_cudy_module


const = load_cudy_module("const")
load_cudy_module("model_names")
parser = load_cudy_module("parser")
parser_network = load_cudy_module("parser_network")


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


def test_get_sim_value_returns_none_when_status_icon_is_missing() -> None:
    """Missing SIM markup should not emit an invalid enum sensor state."""
    assert parser.get_sim_value("<html><body><p>No SIM icon</p></body></html>") is None


def test_get_signal_strength_returns_none_when_rssi_is_missing() -> None:
    """Missing RSSI should not emit a string sentinel into numeric signal handling."""
    assert parser.get_signal_strength(None) is None
