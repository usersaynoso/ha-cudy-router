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


def test_stale_client_cleanup_keeps_shared_client_device_when_tracker_entity_remains() -> None:
    """Sensor cleanup should not drop the device registry entry while a tracker still exists."""
    device_registry = SimpleNamespace(
        devices={
            "client_shared": SimpleNamespace(
                id="client_shared",
                config_entries={"entry-1"},
                identifiers={("cudy_router", "entry-1-device-aabbccddee11")},
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
            "sensor.client_shared": SimpleNamespace(
                entity_id="sensor.client_shared",
                platform="cudy_router",
                domain="sensor",
                unique_id="entry-1-device-aabbccddee11-ip",
            ),
            "device_tracker.client_shared": SimpleNamespace(
                entity_id="device_tracker.client_shared",
                platform="cudy_router",
                domain="device_tracker",
                unique_id="entry-1-device-aabbccddee11",
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
        set(),
    )

    assert registry.removed == ["sensor.client_shared"]
    assert device_registry.removed == []


def test_stale_client_cleanup_falls_back_to_entity_id_when_domain_is_missing() -> None:
    """Client cleanup should still prune stale entries when the registry omits the domain field."""
    device_registry = SimpleNamespace(
        devices={
            "client_old": SimpleNamespace(
                id="client_old",
                config_entries={"entry-1"},
                identifiers={("cudy_router", "entry-1-device-aabbccddee10")},
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
                domain=None,
                unique_id="entry-1-device-aabbccddee10-ip",
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
        set(),
    )

    assert registry.removed == ["sensor.client_old"]
    assert device_registry.removed == ["client_old"]


def test_stale_client_cleanup_removes_device_after_sensor_and_switch_pruning() -> None:
    """A client device should be removed once both live client platforms have been pruned."""
    device_registry = SimpleNamespace(
        devices={
            "client_old": SimpleNamespace(
                id="client_old",
                config_entries={"entry-1"},
                identifiers={("cudy_router", "entry-1-device-aabbccddee10")},
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
                domain=None,
                unique_id="entry-1-device-aabbccddee10-ip",
            ),
            "switch.client_old": SimpleNamespace(
                entity_id="switch.client_old",
                platform="cudy_router",
                domain=None,
                unique_id="entry-1-device-aabbccddee10-internet",
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
        set(),
    )
    assert registry.removed == ["sensor.client_old"]
    assert device_registry.removed == []

    device_info.async_cleanup_stale_client_entities(
        object(),
        SimpleNamespace(entry_id="entry-1"),
        "switch",
        set(),
    )

    assert registry.removed == ["sensor.client_old", "switch.client_old"]
    assert device_registry.removed == ["client_old"]


def test_known_client_devices_collect_names_and_switch_features() -> None:
    """Known clients should expose names and previously seen per-client switch features."""
    device_registry = SimpleNamespace(
        devices={
            "client_1": SimpleNamespace(
                id="client_1",
                config_entries={"entry-1"},
                identifiers={("cudy_router", "entry-1-device-aabbccddee42")},
                name="Living Room TV",
                name_by_user=None,
            )
        }
    )
    registry = SimpleNamespace(
        entities={
            "switch.client_internet": SimpleNamespace(
                entity_id="switch.client_internet",
                platform="cudy_router",
                domain=None,
                unique_id="entry-1-device-aabbccddee42-internet",
                device_id="client_1",
                name=None,
                original_name="Internet access",
            ),
            "device_tracker.client_tracker": SimpleNamespace(
                entity_id="device_tracker.client_tracker",
                platform="cudy_router",
                domain=None,
                unique_id="entry-1-device-aabbccddee42",
                device_id="client_1",
                name=None,
                original_name="Living Room TV",
            ),
        }
    )

    device_info.async_get_entity_registry = lambda hass: registry
    device_info.async_get_device_registry = lambda hass: device_registry

    known_clients = device_info.known_client_devices(
        object(),
        SimpleNamespace(entry_id="entry-1"),
    )

    assert known_clients == {
        "aabbccddee42": {
            "mac": "AA:BB:CC:DD:EE:42",
            "name": "Living Room TV",
            "switch_features": {"internet"},
        }
    }


def test_known_client_devices_ignore_non_client_domains_with_mac_like_unique_ids() -> None:
    """Only client sensor, switch, and tracker entities should contribute known clients."""
    device_registry = SimpleNamespace(devices={})
    registry = SimpleNamespace(
        entities={
            "select.not_a_client": SimpleNamespace(
                entity_id="select.not_a_client",
                platform="cudy_router",
                domain="select",
                unique_id="entry-1-device-aabbccddee42-mode",
                device_id=None,
                name="Router mode",
                original_name="Router mode",
            )
        }
    )

    device_info.async_get_entity_registry = lambda hass: registry
    device_info.async_get_device_registry = lambda hass: device_registry

    known_clients = device_info.known_client_devices(
        object(),
        SimpleNamespace(entry_id="entry-1"),
    )

    assert known_clients == {}


def test_known_tracker_clients_reads_tracker_entities_from_registries() -> None:
    """Known tracker choices should come from tracker entities and their device metadata."""
    device_registry = SimpleNamespace(
        devices={
            "client_tracker": SimpleNamespace(
                id="client_tracker",
                name="Living Room TV",
                name_by_user=None,
            )
        }
    )
    registry = SimpleNamespace(
        entities={
            "device_tracker.client_tracker": SimpleNamespace(
                entity_id="device_tracker.client_tracker",
                platform="cudy_router",
                domain="device_tracker",
                unique_id="entry-1-device-aabbccddee42",
                device_id="client_tracker",
                name=None,
                original_name="Living Room TV",
            )
        }
    )

    device_info.async_get_entity_registry = lambda hass: registry
    device_info.async_get_device_registry = lambda hass: device_registry

    known_clients = device_info.known_tracker_clients(
        object(),
        SimpleNamespace(entry_id="entry-1"),
    )

    assert known_clients == {
        "aabbccddee42": {
            "mac": "AA:BB:CC:DD:EE:42",
            "name": "Living Room TV",
        }
    }


def test_known_tracker_clients_reads_legacy_mac_unique_ids() -> None:
    """Legacy raw-MAC tracker IDs should remain selectable after upgrade."""
    device_registry = SimpleNamespace(
        devices={
            "legacy_tracker": SimpleNamespace(
                id="legacy_tracker",
                name="Tablet",
                name_by_user=None,
            )
        }
    )
    registry = SimpleNamespace(
        entities={
            "device_tracker.legacy_tracker": SimpleNamespace(
                entity_id="device_tracker.legacy_tracker",
                platform="cudy_router",
                domain="device_tracker",
                unique_id="AA:BB:CC:DD:EE:99",
                device_id="legacy_tracker",
                name=None,
                original_name="Tablet",
            )
        }
    )

    device_info.async_get_entity_registry = lambda hass: registry
    device_info.async_get_device_registry = lambda hass: device_registry

    known_clients = device_info.known_tracker_clients(
        object(),
        SimpleNamespace(entry_id="entry-1"),
    )

    assert known_clients == {
        "aabbccddee99": {
            "mac": "AA:BB:CC:DD:EE:99",
            "name": "Tablet",
        }
    }


def test_async_ensure_client_entity_device_links_legacy_tracker_entries() -> None:
    """Existing raw-MAC tracker entities should be re-linked to their client device."""
    create_calls: list[dict[str, object]] = []
    update_calls: list[tuple[str, dict[str, str]]] = []

    device_registry = SimpleNamespace(
        async_get_or_create=lambda **kwargs: (
            create_calls.append(kwargs) or SimpleNamespace(id="client_tracker")
        )
    )
    registry = SimpleNamespace(
        entities={
            "device_tracker.client_tracker": SimpleNamespace(
                entity_id="device_tracker.client_tracker",
                platform="cudy_router",
                domain="device_tracker",
                unique_id="AA:BB:CC:DD:EE:42",
                device_id=None,
            )
        }
    )
    registry.async_get_entity_id = (
        lambda domain, platform, unique_id: "device_tracker.client_tracker"
        if (domain, platform, unique_id)
        == ("device_tracker", "cudy_router", "AA:BB:CC:DD:EE:42")
        else None
    )

    def _update_entity(entity_id: str, **changes: str) -> None:
        update_calls.append((entity_id, changes))
        registry.entities[entity_id].device_id = changes["device_id"]

    registry.async_update_entity = _update_entity

    device_info.async_get_entity_registry = lambda hass: registry
    device_info.async_get_device_registry = lambda hass: device_registry

    device_id = device_info.async_ensure_client_entity_device(
        object(),
        SimpleNamespace(entry_id="entry-1"),
        "device_tracker",
        "AA:BB:CC:DD:EE:42",
        {"hostname": "Living Room TV", "mac": "AA:BB:CC:DD:EE:42"},
    )

    assert device_id == "client_tracker"
    assert create_calls == [
        {
            "config_entry_id": "entry-1",
            "identifiers": {("cudy_router", "entry-1-device-aabbccddee42")},
            "connections": {("mac", "aa:bb:cc:dd:ee:42")},
            "name": "Living Room TV",
            "via_device": ("cudy_router", "entry-1"),
        }
    ]
    assert update_calls == [
        ("device_tracker.client_tracker", {"device_id": "client_tracker"})
    ]


def test_known_tracker_clients_ignore_plain_client_devices_without_tracker_entities() -> None:
    """Tracker lookups should not be expanded by non-tracker client registry entries."""
    device_registry = SimpleNamespace(
        devices={
            "client_only": SimpleNamespace(
                id="client_only",
                config_entries={"entry-1"},
                identifiers={("cudy_router", "entry-1-device-aabbccddee55")},
                name="Kitchen TV",
                name_by_user=None,
            )
        }
    )
    registry = SimpleNamespace(entities={})

    device_info.async_get_entity_registry = lambda hass: registry
    device_info.async_get_device_registry = lambda hass: device_registry

    known_clients = device_info.known_tracker_clients(
        object(),
        SimpleNamespace(entry_id="entry-1"),
    )

    assert known_clients == {}


def test_stale_tracker_cleanup_removes_only_disallowed_tracker_entities() -> None:
    """Tracker cleanup should keep selected trackers and shared client devices."""
    device_registry = SimpleNamespace(
        devices={
            "client_old": SimpleNamespace(
                id="client_old",
                config_entries={"entry-1"},
                identifiers={("cudy_router", "entry-1-device-aabbccddee10")},
            ),
            "client_selected": SimpleNamespace(
                id="client_selected",
                config_entries={"entry-1"},
                identifiers={("cudy_router", "entry-1-device-aabbccddee11")},
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
            "device_tracker.client_old": SimpleNamespace(
                entity_id="device_tracker.client_old",
                platform="cudy_router",
                domain="device_tracker",
                unique_id="entry-1-device-aabbccddee10",
                device_id="client_old",
            ),
            "device_tracker.client_selected": SimpleNamespace(
                entity_id="device_tracker.client_selected",
                platform="cudy_router",
                domain="device_tracker",
                unique_id="entry-1-device-aabbccddee11",
                device_id="client_selected",
            ),
            "sensor.client_selected": SimpleNamespace(
                entity_id="sensor.client_selected",
                platform="cudy_router",
                domain="sensor",
                unique_id="entry-1-device-aabbccddee11-ip",
                device_id="client_selected",
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

    device_info.async_cleanup_stale_tracker_entities(
        object(),
        SimpleNamespace(entry_id="entry-1"),
        "device_tracker",
        {"AA:BB:CC:DD:EE:11"},
    )

    assert registry.removed == ["device_tracker.client_old"]
    assert device_registry.removed == ["client_old"]


def test_stale_tracker_cleanup_removes_legacy_mac_unique_id_entities() -> None:
    """Legacy raw-MAC tracker entities should be pruned when no longer allowed."""
    device_registry = SimpleNamespace(devices={}, removed=[])
    device_registry.async_remove_device = lambda device_id: device_registry.removed.append(device_id)

    registry = SimpleNamespace(
        entities={
            "device_tracker.legacy_old": SimpleNamespace(
                entity_id="device_tracker.legacy_old",
                platform="cudy_router",
                domain="device_tracker",
                unique_id="AA:BB:CC:DD:EE:10",
                device_id=None,
            ),
            "device_tracker.legacy_keep": SimpleNamespace(
                entity_id="device_tracker.legacy_keep",
                platform="cudy_router",
                domain="device_tracker",
                unique_id="AA:BB:CC:DD:EE:11",
                device_id=None,
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

    device_info.async_cleanup_stale_tracker_entities(
        object(),
        SimpleNamespace(entry_id="entry-1"),
        "device_tracker",
        {"AA:BB:CC:DD:EE:11"},
    )

    assert registry.removed == ["device_tracker.legacy_old"]


def test_stale_tracker_cleanup_prunes_noncanonical_duplicates_for_allowed_macs() -> None:
    """Allowed trackers should keep the preserved raw-MAC unique ID and drop duplicates."""
    device_registry = SimpleNamespace(devices={}, removed=[])
    device_registry.async_remove_device = lambda device_id: device_registry.removed.append(device_id)

    registry = SimpleNamespace(
        entities={
            "device_tracker.client_current": SimpleNamespace(
                entity_id="device_tracker.client_current",
                platform="cudy_router",
                domain="device_tracker",
                unique_id="AA:BB:CC:DD:EE:11",
                device_id=None,
            ),
            "device_tracker.client_duplicate": SimpleNamespace(
                entity_id="device_tracker.client_duplicate",
                platform="cudy_router",
                domain="device_tracker",
                unique_id="entry-1-device-aabbccddee11",
                device_id=None,
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

    device_info.async_cleanup_stale_tracker_entities(
        object(),
        SimpleNamespace(entry_id="entry-1"),
        "device_tracker",
        {"AA:BB:CC:DD:EE:11"},
    )

    assert registry.removed == ["device_tracker.client_duplicate"]
