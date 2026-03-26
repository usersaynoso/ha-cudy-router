"""Tests for Home Assistant device registry metadata helpers."""

from __future__ import annotations

from types import SimpleNamespace

from tests.module_loader import load_cudy_module


device_info = load_cudy_module("device_info")


def _coordinator(data: dict, *, entry_id: str = "entry-1", model: str = "P5") -> SimpleNamespace:
    return SimpleNamespace(
        config_entry=SimpleNamespace(entry_id=entry_id, data={"model": model}),
        data=data,
    )


def test_router_device_info_includes_name_model_firmware_and_mac_connection() -> None:
    """The main router device should expose rich metadata while keeping its existing identifier."""
    coordinator = _coordinator(
        {
            "mesh": {"main_router_name": "Taylor Router"},
            "system": {"firmware_version": {"value": "2.4.25 DE"}},
            "lan": {"mac_address": {"value": "AA-BB-CC-DD-EE-FF"}},
        }
    )

    info = device_info.build_router_device_info(coordinator)

    assert info["identifiers"] == {("cudy_router", "entry-1")}
    assert info["name"] == "Taylor Router"
    assert info["manufacturer"] == "Cudy"
    assert info["model"] == "P5"
    assert info["sw_version"] == "2.4.25 DE"
    assert info["connections"] == {("mac", "aa:bb:cc:dd:ee:ff")}


def test_client_device_info_uses_client_name_and_parent_router_without_cudy_manufacturer() -> None:
    """Client devices should be attached under the router and identified by their own MAC."""
    config_entry = SimpleNamespace(entry_id="entry-1")

    info = device_info.build_client_device_info(
        config_entry,
        {"hostname": "Living Room TV", "mac": "AA:BB:CC:DD:EE:42"},
    )

    assert info["identifiers"] == {("cudy_router", "entry-1-device-aabbccddee42")}
    assert info["name"] == "Living Room TV"
    assert info["via_device"] == ("cudy_router", "entry-1")
    assert info["connections"] == {("mac", "aa:bb:cc:dd:ee:42")}
    assert "manufacturer" not in info


def test_mesh_device_info_prefixes_mesh_name_and_splits_hardware_version() -> None:
    """Mesh nodes should get distinct names and richer model metadata."""
    coordinator = _coordinator({})

    info = device_info.build_mesh_device_info(
        coordinator,
        "AA:BB:CC:DD:EE:11",
        {
            "name": "Bedroom",
            "model": "RE1200",
            "hardware": "RE1200 V1.0",
            "firmware_version": "2.4.20",
            "mac_address": "AA:BB:CC:DD:EE:11",
        },
    )

    assert info["identifiers"] == {("cudy_router", "entry-1-mesh-AA:BB:CC:DD:EE:11")}
    assert info["name"] == "Mesh Bedroom"
    assert info["manufacturer"] == "Cudy"
    assert info["model"] == "RE1200"
    assert info["hw_version"] == "V1.0"
    assert info["sw_version"] == "2.4.20"
    assert info["via_device"] == ("cudy_router", "entry-1")
    assert info["connections"] == {("mac", "aa:bb:cc:dd:ee:11")}


def test_stale_mesh_cleanup_removes_only_missing_mesh_entities() -> None:
    """Registry cleanup should remove orphaned mesh entities while leaving current nodes intact."""
    registry = SimpleNamespace(
        entities={
            "switch.mesh_old": SimpleNamespace(
                entity_id="switch.mesh_old",
                platform="cudy_router",
                domain="switch",
                unique_id="entry-1-mesh-AA:BB:CC:DD:EE:10-led",
            ),
            "switch.mesh_current": SimpleNamespace(
                entity_id="switch.mesh_current",
                platform="cudy_router",
                domain="switch",
                unique_id="entry-1-mesh-AA:BB:CC:DD:EE:11-led",
            ),
            "sensor.unrelated": SimpleNamespace(
                entity_id="sensor.unrelated",
                platform="other_domain",
                domain="sensor",
                unique_id="something-else",
            ),
        },
        removed=[],
    )

    def _remove(entity_id: str) -> None:
        registry.removed.append(entity_id)
        registry.entities.pop(entity_id, None)

    registry.async_remove = _remove
    device_info.async_get_entity_registry = lambda hass: registry

    device_info.async_cleanup_stale_mesh_entities(
        object(),
        SimpleNamespace(entry_id="entry-1"),
        "switch",
        {"AA:BB:CC:DD:EE:11"},
    )

    assert registry.removed == ["switch.mesh_old"]


def test_stale_client_cleanup_removes_only_missing_client_entities() -> None:
    """Client cleanup should prune devices that are no longer allowed."""
    device_registry = SimpleNamespace(
        devices={
            "client_old": SimpleNamespace(
                id="client_old",
                config_entries={"entry-1"},
                identifiers={("cudy_router", "entry-1-device-aabbccddee10")},
            ),
            "client_current": SimpleNamespace(
                id="client_current",
                config_entries={"entry-1"},
                identifiers={("cudy_router", "entry-1-device-aabbccddee11")},
            ),
            "router": SimpleNamespace(
                id="router",
                config_entries={"entry-1"},
                identifiers={("cudy_router", "entry-1")},
            ),
        },
        removed=[],
    )

    def _remove_device(device_id: str) -> None:
        device_registry.removed.append(device_id)
        device_registry.devices.pop(device_id, None)

    device_registry.async_remove_device = _remove_device

    registry = SimpleNamespace(
        entities={
            "sensor.client_old": SimpleNamespace(
                entity_id="sensor.client_old",
                platform="cudy_router",
                domain="sensor",
                unique_id="entry-1-device-aabbccddee10-ip",
            ),
            "sensor.client_current": SimpleNamespace(
                entity_id="sensor.client_current",
                platform="cudy_router",
                domain="sensor",
                unique_id="entry-1-device-aabbccddee11-ip",
            ),
            "sensor.legacy_manual": SimpleNamespace(
                entity_id="sensor.legacy_manual",
                platform="cudy_router",
                domain="sensor",
                unique_id="entry-1-Living-Room-mac",
            ),
        },
        removed=[],
    )

    def _remove(entity_id: str) -> None:
        registry.removed.append(entity_id)
        registry.entities.pop(entity_id, None)

    registry.async_remove = _remove
    device_info.async_get_entity_registry = lambda hass: registry
    device_info.async_get_device_registry = lambda hass: device_registry

    device_info.async_cleanup_stale_client_entities(
        object(),
        SimpleNamespace(entry_id="entry-1"),
        "sensor",
        {"AA:BB:CC:DD:EE:11"},
    )

    assert registry.removed == ["sensor.client_old"]
    assert device_registry.removed == ["client_old"]
