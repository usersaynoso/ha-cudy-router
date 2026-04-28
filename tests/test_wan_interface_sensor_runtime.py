"""Runtime-style tests for per-WAN interface sensors."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from tests.module_loader import load_cudy_module


const = load_cudy_module("const")
sensor_descriptions = load_cudy_module("sensor_descriptions")
sensor = load_cudy_module("sensor")


def _wan_description(key: str):
    return next(
        description
        for description in sensor_descriptions.WAN_INTERFACE_SENSOR_TYPES
        if description.key == key
    )


def test_wan_interface_sensor_reads_current_interface_value() -> None:
    """Per-WAN sensors should read live values from their own interface bucket."""
    coordinator = SimpleNamespace(
        config_entry=SimpleNamespace(entry_id="entry123", data={"model": "R700"}),
        data={
            const.MODULE_WAN_INTERFACES: {
                "wan2": {
                    "bytes_received": {
                        "value": 1234,
                        "attributes": {"source_path": "admin/network/wan/status?detail=1&iface=wanb"},
                    },
                    "status": {"value": "Online"},
                },
                "wan3": {
                    "bytes_received": {"value": 5678},
                },
            },
        },
    )

    entity = sensor.CudyRouterWanInterfaceSensor(
        coordinator,
        "wan2",
        _wan_description("bytes_received"),
    )

    assert entity.unique_id == "entry123-wan_interfaces-wan2-bytes_received"
    assert entity._attr_name == "WAN2 bytes received"
    assert entity.native_value == 1234
    assert entity.extra_state_attributes == {
        "source_path": "admin/network/wan/status?detail=1&iface=wanb",
    }

    coordinator.data[const.MODULE_WAN_INTERFACES]["wan2"]["bytes_received"]["value"] = 4321
    assert entity.native_value == 4321


def test_wan_interface_sensor_returns_none_when_interface_disappears() -> None:
    """Existing per-WAN entities should become unknown instead of reading another WAN."""
    coordinator = SimpleNamespace(
        config_entry=SimpleNamespace(entry_id="entry123", data={"model": "R700"}),
        data={
            const.MODULE_WAN_INTERFACES: {
                "wan3": {
                    "status": {"value": "Offline"},
                },
            },
        },
    )

    entity = sensor.CudyRouterWanInterfaceSensor(
        coordinator,
        "wan2",
        _wan_description("status"),
    )

    assert entity.unique_id == "entry123-wan_interfaces-wan2-status"
    assert entity._attr_name == "WAN2 status"
    assert entity.native_value is None
    assert entity.extra_state_attributes == {}


def test_sensor_setup_removes_stale_wan_interface_registry_entries(monkeypatch) -> None:
    """Setup should remove per-WAN sensors for interfaces no longer in coordinator data."""
    config_entry = SimpleNamespace(
        entry_id="entry123",
        data={"model": "R700"},
        options={},
        title="R700",
        async_on_unload=lambda unload: None,
    )
    coordinator = SimpleNamespace(
        config_entry=config_entry,
        data={
            const.MODULE_WAN_INTERFACES: {
                "wan2": {
                    "status": {"value": "Online"},
                },
            },
        },
        async_add_listener=lambda listener: (lambda: None),
    )
    hass = SimpleNamespace(data={const.DOMAIN: {"entry123": coordinator}})

    class _Registry:
        def __init__(self) -> None:
            self.entities = {
                "sensor.r700_wan2_status": SimpleNamespace(
                    domain="sensor",
                    platform=const.DOMAIN,
                    entity_id="sensor.r700_wan2_status",
                    unique_id="entry123-wan_interfaces-wan2-status",
                ),
                "sensor.r700_wan4_protocol": SimpleNamespace(
                    domain="sensor",
                    platform=const.DOMAIN,
                    entity_id="sensor.r700_wan4_protocol",
                    unique_id="entry123-wan_interfaces-wan4-protocol",
                ),
            }
            self.removed: list[str] = []

        def async_get_entity_id(self, domain: str, platform: str, unique_id: str):
            for entity in self.entities.values():
                if entity.domain == domain and entity.platform == platform and entity.unique_id == unique_id:
                    return entity.entity_id
            return None

        def async_remove(self, entity_id: str) -> None:
            self.removed.append(entity_id)
            self.entities.pop(entity_id, None)

    registry = _Registry()
    added_entities = []

    monkeypatch.setattr(sensor, "async_get_entity_registry", lambda hass: registry)
    monkeypatch.setattr(
        sensor,
        "module_available",
        lambda device_model, module, data=None: module == const.MODULE_WAN_INTERFACES,
    )

    asyncio.run(
        sensor.async_setup_entry(
            hass,
            config_entry,
            lambda entities: added_entities.extend(entities),
        )
    )

    assert registry.removed == ["sensor.r700_wan4_protocol"]
    assert "sensor.r700_wan2_status" in registry.entities
    assert [entity.unique_id for entity in added_entities] == ["entry123-wan_interfaces-wan2-status"]


def test_sensor_setup_uses_live_wan_data_without_creating_unrelated_entities(monkeypatch) -> None:
    """Live parsed data should create only the entity with a real value."""
    config_entry = SimpleNamespace(
        entry_id="entry123",
        data={"model": "RE1500"},
        options={},
        title="RE1500",
        async_on_unload=lambda unload: None,
    )
    coordinator = SimpleNamespace(
        config_entry=config_entry,
        data={
            const.MODULE_WAN: {
                "protocol": {"value": "DHCP"},
                "gateway": {"value": None},
            },
        },
        async_add_listener=lambda listener: (lambda: None),
    )
    hass = SimpleNamespace(data={const.DOMAIN: {"entry123": coordinator}})

    class _Registry:
        entities = {}

        def async_get_entity_id(self, domain: str, platform: str, unique_id: str):
            return None

        def async_remove(self, entity_id: str) -> None:
            raise AssertionError(f"Unexpected removal: {entity_id}")

    added_entities = []

    monkeypatch.setattr(sensor, "async_get_entity_registry", lambda hass: _Registry())

    asyncio.run(
        sensor.async_setup_entry(
            hass,
            config_entry,
            lambda entities: added_entities.extend(entities),
        )
    )

    unique_ids = [entity.unique_id for entity in added_entities]
    assert "entry123-wan-protocol" in unique_ids
    assert "entry123-wan-gateway" not in unique_ids
    assert all("-wifi_2g-" not in unique_id for unique_id in unique_ids)
