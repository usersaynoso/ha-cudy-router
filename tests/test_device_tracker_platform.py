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


def test_configured_device_ids_accept_picker_values() -> None:
    """Picker-backed manual device selections should normalize MACs too."""
    selected = device_tracking.configured_device_ids(
        ["aabbccddee30", "AA-BB-CC-DD-EE-31"]
    )

    assert "aa:bb:cc:dd:ee:30" in selected
    assert "aabbccddee30" in selected
    assert "aa:bb:cc:dd:ee:31" in selected
    assert "aabbccddee31" in selected


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


def test_configured_tracked_macs_normalizes_picker_values() -> None:
    """Tracker-picker values should be stored as normalized MACs."""
    selected = device_tracking.configured_tracked_macs(
        ["AA:BB:CC:DD:EE:30", "aa-bb-cc-dd-ee-31", "invalid"]
    )

    assert selected == {"aabbccddee30", "aabbccddee31"}


def test_tracker_picker_options_merge_connected_and_known_tracker_clients() -> None:
    """Picker choices should include live clients and previously tracked clients."""
    options = device_tracking.tracker_picker_options(
        [
            _device("Office PC", "192.168.10.30", "AA:BB:CC:DD:EE:30"),
            _device("Phone", "192.168.10.32", "AA:BB:CC:DD:EE:32"),
        ],
        {
            "aabbccddee30": "Old Office PC",
            "aabbccddee31": "Tablet",
        },
    )

    assert options == [
        {"value": "aabbccddee30", "label": "Office PC (AA:BB:CC:DD:EE:30)"},
        {"value": "aabbccddee32", "label": "Phone (AA:BB:CC:DD:EE:32)"},
        {"value": "aabbccddee31", "label": "Tablet (AA:BB:CC:DD:EE:31)"},
    ]


def test_manual_selected_connected_devices_filters_by_hostname_ip_and_mac() -> None:
    """Manual connected-device filtering should reuse the same identifier matching rules."""
    devices = [
        _device("Office PC", "192.168.10.30", "AA:BB:CC:DD:EE:30"),
        _device("Tablet", "192.168.10.31", "AA:BB:CC:DD:EE:31"),
        _device("Phone", "192.168.10.32", "AA:BB:CC:DD:EE:32"),
    ]

    assert device_tracking.manual_selected_connected_devices(
        devices,
        "office pc,192.168.10.31,AA-BB-CC-DD-EE-32",
    ) == devices


def test_manual_allowed_client_macs_support_picker_values_and_known_offline_clients() -> None:
    """Manual selections should keep direct MAC picker values and known offline names."""
    allowed = device_tracking.manual_allowed_client_macs(
        connected_devices=[
            _device("Office PC", "192.168.10.30", "AA:BB:CC:DD:EE:30"),
        ],
        device_list=["aabbccddee30", "Kitchen HomePod"],
        known_clients={
            "aabbccddee31": {
                "mac": "AA:BB:CC:DD:EE:31",
                "name": "Kitchen HomePod",
            }
        },
    )

    assert allowed == {"aabbccddee30", "aabbccddee31"}


def test_eligible_manual_picker_devices_include_all_live_mac_bearing_devices() -> None:
    """The manual connected-device picker should show every live MAC-bearing client."""
    devices = [
        _device("Office PC", "192.168.10.30", "AA:BB:CC:DD:EE:30"),
        {"hostname": "No MAC", "ip": "192.168.10.31", "mac": ""},
    ]

    assert device_tracking.eligible_manual_picker_devices(devices) == [devices[0]]


def test_eligible_tracker_picker_devices_include_all_live_devices_in_auto_mode() -> None:
    """Auto mode should expose every MAC-bearing connected client in the picker."""
    devices = [
        _device("Office PC", "192.168.10.30", "AA:BB:CC:DD:EE:30"),
        {"hostname": "No MAC", "ip": "192.168.10.31", "mac": ""},
    ]

    assert device_tracking.eligible_tracker_picker_devices(
        auto_add_connected_devices=True,
        connected_devices=devices,
        device_list="Office PC",
    ) == [devices[0]]


def test_eligible_tracker_picker_devices_use_manual_list_when_auto_mode_off() -> None:
    """Manual mode should only expose devices that match the manual device list."""
    devices = [
        _device("Office PC", "192.168.10.30", "AA:BB:CC:DD:EE:30"),
        _device("Tablet", "192.168.10.31", "AA:BB:CC:DD:EE:31"),
    ]

    assert device_tracking.eligible_tracker_picker_devices(
        auto_add_connected_devices=False,
        connected_devices=devices,
        device_list="Tablet",
    ) == [devices[1]]


def test_eligible_tracker_picker_devices_fall_back_to_all_live_devices_without_manual_selection() -> None:
    """Manual mode should still allow explicit tracker selection when no manual clients are chosen."""
    devices = [
        _device("Office PC", "192.168.10.30", "AA:BB:CC:DD:EE:30"),
        _device("Tablet", "192.168.10.31", "AA:BB:CC:DD:EE:31"),
        {"hostname": "No MAC", "ip": "192.168.10.32", "mac": ""},
    ]

    assert device_tracking.eligible_tracker_picker_devices(
        auto_add_connected_devices=False,
        connected_devices=devices,
        device_list=[],
    ) == devices[:2]


def test_next_options_flow_step_routes_through_manual_picker_when_connected_auto_add_is_off() -> None:
    """Disabling automatic connected devices should always show the manual picker first."""
    assert device_tracking.next_options_flow_step(
        auto_add_connected_devices=False,
        auto_add_device_trackers=True,
    ) == "manual_devices"
    assert device_tracking.next_options_flow_step(
        auto_add_connected_devices=False,
        auto_add_device_trackers=False,
    ) == "manual_devices"


def test_next_options_flow_step_skips_tracker_picker_when_auto_tracker_mode_is_enabled() -> None:
    """Auto tracker mode should save directly once the manual step is complete."""
    assert device_tracking.next_options_flow_step(
        auto_add_connected_devices=True,
        auto_add_device_trackers=True,
    ) is None
    assert device_tracking.next_options_flow_step(
        auto_add_connected_devices=False,
        auto_add_device_trackers=True,
        after_manual_devices=True,
    ) is None


def test_next_options_flow_step_uses_tracker_picker_only_when_auto_tracker_mode_is_disabled() -> None:
    """Tracker selection should only appear when explicit tracker selection is needed."""
    assert device_tracking.next_options_flow_step(
        auto_add_connected_devices=True,
        auto_add_device_trackers=False,
    ) == "trackers"
    assert device_tracking.next_options_flow_step(
        auto_add_connected_devices=False,
        auto_add_device_trackers=False,
        after_manual_devices=True,
    ) == "trackers"


def test_tracker_picker_options_keep_stored_selected_trackers_outside_filtered_live_scope() -> None:
    """Stored tracker selections should remain visible even if not in the filtered live set."""
    options = device_tracking.tracker_picker_options(
        [_device("Bedroom Apple TV", "192.168.10.30", "AA:BB:CC:DD:EE:30")],
        {"aabbccddee31": "Kitchen HomePod"},
    )

    assert options == [
        {"value": "aabbccddee30", "label": "Bedroom Apple TV (AA:BB:CC:DD:EE:30)"},
        {"value": "aabbccddee31", "label": "Kitchen HomePod (AA:BB:CC:DD:EE:31)"},
    ]


def test_picker_options_include_stored_manual_devices_without_showing_unselected_registry_clients() -> None:
    """Manual picker options should only use registry names for already selected devices."""
    options = device_tracking.tracker_picker_options(
        [_device("Bedroom Apple TV", "192.168.10.30", "AA:BB:CC:DD:EE:30")],
        {"aabbccddee31": "Kitchen HomePod"},
    )

    assert {"value": "aabbccddee31", "label": "Kitchen HomePod (AA:BB:CC:DD:EE:31)"} in options
    assert all(option["value"] != "aabbccddee32" for option in options)


def test_tracker_picker_options_do_not_include_unselected_known_trackers_when_not_passed_in() -> None:
    """Registry-known trackers should stay hidden unless they are explicitly supplied."""
    options = device_tracking.tracker_picker_options(
        [_device("Bedroom Apple TV", "192.168.10.30", "AA:BB:CC:DD:EE:30")],
        {},
    )

    assert options == [
        {"value": "aabbccddee30", "label": "Bedroom Apple TV (AA:BB:CC:DD:EE:30)"},
    ]


def test_tracker_allowed_macs_include_all_current_clients_when_auto_enabled() -> None:
    """Auto tracker mode should cover every current MAC-bearing client."""
    allowed = device_tracking.tracker_allowed_macs(
        auto_add_device_trackers=True,
        connected_devices=[
            _device("Office PC", "192.168.10.30", "AA:BB:CC:DD:EE:30"),
            _device("Tablet", "192.168.10.31", "AA:BB:CC:DD:EE:31"),
        ],
        tracked_device_macs=set(),
        tracker_options_configured=True,
    )

    assert allowed == {"aabbccddee30", "aabbccddee31"}


def test_tracker_allowed_macs_keep_selected_clients_without_auto_mode() -> None:
    """Explicit selections should keep trackers even when auto mode is off."""
    allowed = device_tracking.tracker_allowed_macs(
        auto_add_device_trackers=False,
        connected_devices=[
            _device("Office PC", "192.168.10.30", "AA:BB:CC:DD:EE:30"),
        ],
        tracked_device_macs={"aabbccddee31"},
        tracker_options_configured=True,
    )

    assert allowed == {"aabbccddee31"}


def test_tracker_allowed_macs_preserve_legacy_trackers_until_new_options_are_saved() -> None:
    """Existing manual trackers should survive upgrade until new tracker options are configured."""
    allowed = device_tracking.tracker_allowed_macs(
        auto_add_device_trackers=False,
        connected_devices=[],
        tracked_device_macs=set(),
        legacy_tracked_macs={"aabbccddee30"},
        tracker_options_configured=False,
    )

    assert allowed == {"aabbccddee30"}


def test_build_tracker_seed_device_keeps_offline_tracker_identity() -> None:
    """Offline trackers should still have a MAC-backed payload for not_home state."""
    seed_device = device_tracking.build_tracker_seed_device(
        "aabbccddee30",
        {},
        "Living Room TV",
    )

    assert seed_device == {
        "hostname": "Living Room TV",
        "mac": "AA:BB:CC:DD:EE:30",
    }


def test_build_client_seed_device_keeps_offline_manual_identity() -> None:
    """Offline manual client entities should still have a MAC-backed payload."""
    seed_device = device_tracking.build_client_seed_device(
        "aabbccddee31",
        {},
        "Kitchen HomePod",
    )

    assert seed_device == {
        "hostname": "Kitchen HomePod",
        "mac": "AA:BB:CC:DD:EE:31",
    }


def test_device_tracker_platform_imports_option_constant() -> None:
    """The runtime platform should reference the shared device-list option safely."""
    source = DEVICE_TRACKER_PATH.read_text(encoding="utf-8")

    assert "OPTIONS_DEVICELIST" in source
    assert "OPTIONS_AUTO_ADD_DEVICE_TRACKERS" in source
    assert "OPTIONS_TRACKED_DEVICE_MACS" in source
    assert "config_entry.options.get(OPTIONS_DEVICELIST)" in source
    assert "config_entry.options.get(OPTIONS_TRACKED_DEVICE_MACS)" in source


def test_device_tracker_platform_uses_scanner_entity_for_router_presence() -> None:
    """Router-backed device trackers should report home/not_home via ScannerEntity."""
    source = DEVICE_TRACKER_PATH.read_text(encoding="utf-8")

    assert "from homeassistant.components.device_tracker.config_entry import ScannerEntity" in source
    assert "CoordinatorEntity[CudyRouterDataUpdateCoordinator], ScannerEntity" in source


def test_device_tracker_platform_preserves_mac_based_unique_ids() -> None:
    """Tracker unique IDs should keep the existing MAC format for registry continuity."""
    source = DEVICE_TRACKER_PATH.read_text(encoding="utf-8")

    assert "_attr_unique_id = self._mac or self._normalized_mac" in source
