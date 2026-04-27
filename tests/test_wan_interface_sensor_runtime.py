"""Runtime-style tests for per-WAN interface sensors."""

from __future__ import annotations

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
