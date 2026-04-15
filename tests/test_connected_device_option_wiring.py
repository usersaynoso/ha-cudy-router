"""Static wiring checks for the connected-device auto creation option."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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


def test_options_flow_exposes_connected_device_auto_add_toggle() -> None:
    """Users should be able to disable automatic client-device creation."""
    source = CONFIG_FLOW_PATH.read_text(encoding="utf-8")

    assert "OPTIONS_AUTO_ADD_CONNECTED_DEVICES" in source
    assert "selector.BooleanSelector()" in source
    assert "self.add_suggested_values_to_schema" in source
    assert "options={" in source
    assert "OPTIONS_AUTO_ADD_CONNECTED_DEVICES: False" in source
    assert 'updated_options[OPTIONS_DEVICELIST] = (' in source


def test_client_platforms_gate_auto_created_entities_on_option() -> None:
    """Client sensors, switches, and trackers should honor the new auto-add setting."""
    sensor_source = SENSOR_PATH.read_text(encoding="utf-8")
    switch_source = SWITCH_PATH.read_text(encoding="utf-8")
    tracker_source = DEVICE_TRACKER_PATH.read_text(encoding="utf-8")

    assert "auto_add_connected_devices = options.get(OPTIONS_AUTO_ADD_CONNECTED_DEVICES, True)" in sensor_source
    assert "matched_connected_devices = [" in sensor_source
    assert "async_cleanup_stale_client_entities" in sensor_source
    assert "auto_add_connected_devices = config_entry.options.get(" in switch_source
    assert "matched_connected_devices = [" in switch_source
    assert "async_cleanup_stale_client_entities" in switch_source
    assert "if auto_add_connected_devices or not selected_ids:" in tracker_source
    assert "async_cleanup_stale_client_entities" in tracker_source
    assert "if not auto_add_connected_devices:" in tracker_source


def test_translations_describe_connected_device_auto_add_toggle() -> None:
    """The options UI strings should explain the toggle clearly."""
    strings = json.loads(STRINGS_PATH.read_text(encoding="utf-8"))
    translations = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))

    for payload in (strings, translations):
        data = payload["options"]["step"]["init"]["data"]
        descriptions = payload["options"]["step"]["init"]["data_description"]
        assert data["auto_add_connected_devices"] == "Automatically add connected devices"
        assert data["device_list"] == "Manually add connected devices"
        assert "currently connected device" in descriptions["auto_add_connected_devices"]
        assert "Disabled by default for new integrations" in descriptions["auto_add_connected_devices"]
        assert "turned off" in descriptions["device_list"]


def test_translations_do_not_require_remote_management() -> None:
    """Config flow copy should not mention the old remote-management prerequisite."""
    translations = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))

    user_step = translations["config"]["step"]["user"]
    invalid_auth = translations["config"]["error"]["invalid_auth"]

    assert "Remote Management" not in user_step["description"]
    assert "Remote Management" not in invalid_auth
