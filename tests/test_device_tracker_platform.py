"""Tests for pure device tracking helpers."""

from __future__ import annotations

from pathlib import Path

from tests.module_loader import load_cudy_module


device_tracking = load_cudy_module("device_tracking")
DEVICE_TRACKER_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "cudy_router" / "device_tracker.py"


def _device(hostname: str, ip: str, mac: str) -> dict[str, str]:
    return {
        "hostname": hostname,
        "ip": ip,
        "mac": mac,
        "connection_type": "wifi",
    }


def test_configured_device_ids_tracks_mac_and_hostname_values() -> None:
    """Configured identifiers should match both hostnames and MAC formats."""
    selected = device_tracking.configured_device_ids("AA:BB:CC:DD:EE:30, Tablet")

    assert "aa:bb:cc:dd:ee:30" in selected
    assert "aabbccddee30" in selected
    assert "tablet" in selected


def test_is_selected_device_matches_by_hostname_and_mac() -> None:
    """Device matching should work for both user-facing hostname and MAC inputs."""
    selected = device_tracking.configured_device_ids("gaming pc,aa-bb-cc-dd-ee-31")

    assert device_tracking.is_selected_device(
        _device("Gaming PC", "192.168.10.30", "AA:BB:CC:DD:EE:30"),
        selected,
    )
    assert device_tracking.is_selected_device(
        _device("Tablet", "192.168.10.31", "AA:BB:CC:DD:EE:31"),
        selected,
    )


def test_is_selected_device_returns_false_without_selected_ids() -> None:
    """Tracker creation stays opt-in when no device list is configured."""
    assert device_tracking.is_selected_device(
        _device("Phone", "192.168.10.20", "AA:BB:CC:DD:EE:20"),
        set(),
    ) is False


def test_device_tracker_platform_imports_option_constant() -> None:
    """The runtime platform should reference the shared device-list option safely."""
    source = DEVICE_TRACKER_PATH.read_text(encoding="utf-8")

    assert "OPTIONS_DEVICELIST" in source
    assert "config_entry.options.get(OPTIONS_DEVICELIST)" in source
