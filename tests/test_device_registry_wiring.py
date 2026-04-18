"""Static checks for device registry separation wiring."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUTTON_PATH = ROOT / "custom_components" / "cudy_router" / "button.py"
DEVICE_TRACKER_PATH = ROOT / "custom_components" / "cudy_router" / "device_tracker.py"
DEVICE_INFO_PATH = ROOT / "custom_components" / "cudy_router" / "device_info.py"
SELECT_PATH = ROOT / "custom_components" / "cudy_router" / "select.py"
SENSOR_DESCRIPTIONS_PATH = ROOT / "custom_components" / "cudy_router" / "sensor_descriptions.py"
SENSOR_PATH = ROOT / "custom_components" / "cudy_router" / "sensor.py"
SWITCH_PATH = ROOT / "custom_components" / "cudy_router" / "switch.py"


def test_platforms_use_shared_device_info_builders() -> None:
    """All entity platforms should use the centralized device-info helpers."""
    for path in (BUTTON_PATH, DEVICE_TRACKER_PATH, SELECT_PATH, SENSOR_PATH, SWITCH_PATH):
        source = path.read_text(encoding="utf-8")
        assert "build_router_device_info" in source or "build_client_device_info" in source or "build_mesh_device_info" in source


def test_device_tracker_platform_repairs_legacy_tracker_device_links() -> None:
    """Tracker setup should repair raw-MAC legacy entities that lack device links."""
    source = DEVICE_TRACKER_PATH.read_text(encoding="utf-8")

    assert "async_ensure_client_entity_device" in source
    assert '"device_tracker"' in source


def test_mesh_cleanup_runs_on_dynamic_mesh_platforms() -> None:
    """Mesh entities should prune stale registry entries when nodes disappear."""
    for path in (BUTTON_PATH, SENSOR_PATH, SWITCH_PATH):
        source = path.read_text(encoding="utf-8")
        assert "async_cleanup_stale_mesh_entities" in source


def test_settings_entities_are_marked_as_config() -> None:
    """Writable router settings should live in Home Assistant's config bucket."""
    button_source = BUTTON_PATH.read_text(encoding="utf-8")
    switch_source = SWITCH_PATH.read_text(encoding="utf-8")
    select_source = SELECT_PATH.read_text(encoding="utf-8")

    assert "EntityCategory.CONFIG" in button_source
    assert "EntityCategory.CONFIG" in switch_source
    assert "EntityCategory.CONFIG" in select_source
    assert "_attr_entity_category = EntityCategory.CONFIG" in button_source
    assert "_attr_entity_category = EntityCategory.CONFIG" in switch_source


def test_technical_metadata_sensors_are_marked_diagnostic() -> None:
    """Read-only technical sensors should be categorized as diagnostic entities."""
    source = SENSOR_DESCRIPTIONS_PATH.read_text(encoding="utf-8")

    assert "EntityCategory.DIAGNOSTIC" in source
    assert "DEVICE_IP_SENSOR" in source
    assert "MESH_DEVICE_HARDWARE_SENSOR" in source


def test_sensor_platform_prunes_retired_manual_router_level_device_sensors() -> None:
    """Legacy router-level manual device sensors should not be recreated or left behind."""
    source = SENSOR_PATH.read_text(encoding="utf-8")

    assert "def _remove_legacy_manual_device_sensors" in source
    assert 'unique_id.endswith(("-mac", "-hostname", "-up_speed", "-down_speed"))' in source
    assert "for device_id in device_list" not in source
    assert "CudyRouterDeviceSensor" not in source


def test_device_info_helper_keeps_existing_identifier_prefixes() -> None:
    """Compatibility-sensitive device identifier formats should remain unchanged."""
    source = DEVICE_INFO_PATH.read_text(encoding="utf-8")

    assert 'f"{config_entry.entry_id}-device-{normalized_mac}"' in source
    assert 'f"{coordinator.config_entry.entry_id}-mesh-{mesh_mac}"' in source
    assert '(DOMAIN, coordinator.config_entry.entry_id)' in source
