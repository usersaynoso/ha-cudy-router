"""Static wiring checks for the connected-device auto creation option."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = ROOT / "custom_components" / "cudy_router" / "__init__.py"
CONFIG_FLOW_PATH = ROOT / "custom_components" / "cudy_router" / "config_flow.py"
CONST_PATH = ROOT / "custom_components" / "cudy_router" / "const.py"
DEVICE_TRACKER_PATH = ROOT / "custom_components" / "cudy_router" / "device_tracker.py"
SENSOR_PATH = ROOT / "custom_components" / "cudy_router" / "sensor.py"
STRINGS_PATH = ROOT / "custom_components" / "cudy_router" / "strings.json"
SWITCH_PATH = ROOT / "custom_components" / "cudy_router" / "switch.py"
TRANSLATIONS_PATH = ROOT / "custom_components" / "cudy_router" / "translations" / "en.json"


def test_const_declares_connected_device_auto_add_option() -> None:
    """The new options key should be defined centrally."""
    source = CONST_PATH.read_text(encoding="utf-8")

    assert 'OPTIONS_AUTO_ADD_CONNECTED_DEVICES = "auto_add_connected_devices"' in source
    assert 'OPTIONS_AUTO_ADD_DEVICE_TRACKERS = "auto_add_device_trackers"' in source
    assert 'OPTIONS_TRACKED_DEVICE_MACS = "tracked_device_macs"' in source


def test_options_flow_exposes_connected_device_auto_add_toggle() -> None:
    """Users should be able to disable automatic client-device creation."""
    source = CONFIG_FLOW_PATH.read_text(encoding="utf-8")

    assert "OPTIONS_AUTO_ADD_CONNECTED_DEVICES" in source
    assert "OPTIONS_AUTO_ADD_DEVICE_TRACKERS" in source
    assert "OPTIONS_TRACKED_DEVICE_MACS" in source
    assert "selector.BooleanSelector()" in source
    assert "selector.SelectSelector(" in source
    assert "selector.SelectSelectorConfig(" in source
    assert "multiple=True" in source
    assert "selector.SelectSelectorMode.DROPDOWN" in source
    assert "self.add_suggested_values_to_schema" in source
    assert "async_step_manual_devices" in source
    assert "async_step_trackers" in source
    assert "self._pending_options" in source
    assert "_multi_select_dropdown" in source
    assert "options={" in source
    assert "OPTIONS_AUTO_ADD_CONNECTED_DEVICES: False" in source
    assert "OPTIONS_AUTO_ADD_DEVICE_TRACKERS: False" in source
    assert "OPTIONS_TRACKED_DEVICE_MACS: []" in source
    assert "known_client_devices" in source
    assert "eligible_manual_picker_devices" in source
    assert "manual_allowed_client_macs" in source
    assert "configured_tracked_macs" in source
    assert "eligible_tracker_picker_devices" in source
    assert "next_options_flow_step" in source
    assert "_async_create_entry_from_pending_options" in source
    assert "OPTIONS_TRACKED_DEVICE_MACS: options.get(OPTIONS_TRACKED_DEVICE_MACS, [])" in source
    assert 'step_id="manual_devices"' in source
    assert "step_id=\"trackers\"" in source


def test_options_flow_skips_tracker_step_when_auto_tracker_mode_is_enabled() -> None:
    """Auto tracker mode should save directly instead of showing the tracker picker."""
    source = CONFIG_FLOW_PATH.read_text(encoding="utf-8")

    assert 'if next_step == "manual_devices":' in source
    assert 'if next_step == "trackers":' in source
    assert "return self._async_create_entry_from_pending_options()" in source
    assert "if pending_options.get(OPTIONS_AUTO_ADD_DEVICE_TRACKERS, False):" in source
    assert "pending_options.get(OPTIONS_TRACKED_DEVICE_MACS)" in source


def test_client_platforms_gate_auto_created_entities_on_option() -> None:
    """Client sensors, switches, and trackers should honor the new auto-add setting."""
    sensor_source = SENSOR_PATH.read_text(encoding="utf-8")
    switch_source = SWITCH_PATH.read_text(encoding="utf-8")
    tracker_source = DEVICE_TRACKER_PATH.read_text(encoding="utf-8")

    assert "auto_add_connected_devices = options.get(OPTIONS_AUTO_ADD_CONNECTED_DEVICES, True)" in sensor_source
    assert "allowed_client_macs = set(connected_devices_by_mac)" in sensor_source
    assert "manual_allowed_client_macs(" in sensor_source
    assert "build_client_seed_device(" in sensor_source
    assert "known_client_devices(hass, config_entry)" in sensor_source
    assert "async_cleanup_stale_client_entities" in sensor_source
    assert "auto_add_connected_devices = config_entry.options.get(" in switch_source
    assert "allowed_client_macs = set(connected_devices_by_mac)" in switch_source
    assert "manual_allowed_client_macs(" in switch_source
    assert "build_client_seed_device(" in switch_source
    assert "known_client_devices(hass, config_entry)" in switch_source
    assert "def available(self) -> bool:" in switch_source
    assert "device is offline" in switch_source
    assert "async_cleanup_stale_client_entities" in switch_source
    assert "OPTIONS_AUTO_ADD_DEVICE_TRACKERS" in tracker_source
    assert "OPTIONS_TRACKED_DEVICE_MACS" in tracker_source
    assert "known_tracker_clients" in tracker_source
    assert "tracker_allowed_macs" in tracker_source
    assert "build_tracker_seed_device" in tracker_source
    assert "async_cleanup_stale_tracker_entities" in tracker_source


def test_options_update_listener_prunes_stale_client_entities_before_reload() -> None:
    """Options updates should clean stale client entities immediately, not only after restart."""
    source = INIT_PATH.read_text(encoding="utf-8")

    assert "async_cleanup_stale_client_entities" in source
    assert "async_cleanup_stale_tracker_entities" in source
    assert "entry.add_update_listener(_async_update_listener)" in source
    assert "await hass.config_entries.async_reload(entry.entry_id)" in source


def test_translations_describe_connected_device_auto_add_toggle() -> None:
    """The options UI strings should explain the toggle clearly."""
    strings = json.loads(STRINGS_PATH.read_text(encoding="utf-8"))
    translations = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))

    for payload in (strings, translations):
        init_data = payload["options"]["step"]["init"]["data"]
        init_descriptions = payload["options"]["step"]["init"]["data_description"]
        manual_data = payload["options"]["step"]["manual_devices"]["data"]
        manual_descriptions = payload["options"]["step"]["manual_devices"]["data_description"]
        trackers_data = payload["options"]["step"]["trackers"]["data"]
        trackers_descriptions = payload["options"]["step"]["trackers"]["data_description"]
        assert init_data["auto_add_connected_devices"] == "Automatically add connected devices"
        assert init_data["auto_add_device_trackers"] == "Automatically add device trackers for connected devices"
        assert "device_list" not in init_data
        assert "tracked_device_macs" not in init_data
        assert manual_data["device_list"] == "Manually add connected devices"
        assert trackers_data["tracked_device_macs"] == "Tracked devices"
        assert "currently connected device" in init_descriptions["auto_add_connected_devices"]
        assert "Disabled by default for new integrations" in init_descriptions["auto_add_connected_devices"]
        assert "device_tracker entities" in init_descriptions["auto_add_device_trackers"]
        assert "Disabled by default" in init_descriptions["auto_add_device_trackers"]
        assert "from a list" in manual_descriptions["device_list"]
        assert "become unavailable" in manual_descriptions["device_list"]
        assert "Legacy text-based values" in manual_descriptions["device_list"]
        assert "previous step" in trackers_descriptions["tracked_device_macs"]
        assert "all live connected clients" in trackers_descriptions["tracked_device_macs"]
        assert "away/not_home" in trackers_descriptions["tracked_device_macs"]


def test_translations_do_not_require_remote_management() -> None:
    """Config flow copy should not mention the old remote-management prerequisite."""
    translations = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))

    user_step = translations["config"]["step"]["user"]
    invalid_auth = translations["config"]["error"]["invalid_auth"]

    assert "Remote Management" not in user_step["description"]
    assert "Remote Management" not in invalid_auth
