"""Runtime-style tests for WISP entities."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from tests.module_loader import load_cudy_module


const = load_cudy_module("const")
sensor = load_cudy_module("sensor")
switch = load_cudy_module("switch")


class _Registry:
    def __init__(self, entities: dict[str, SimpleNamespace] | None = None) -> None:
        self.entities = entities or {}
        self.removed: list[str] = []

    def async_get_entity_id(self, domain: str, platform: str, unique_id: str):
        for entity in self.entities.values():
            if entity.domain == domain and entity.platform == platform and entity.unique_id == unique_id:
                return entity.entity_id
        return None

    def async_remove(self, entity_id: str) -> None:
        self.removed.append(entity_id)
        self.entities.pop(entity_id, None)


def _config_entry(model: str = "LT300 V2.0") -> SimpleNamespace:
    return SimpleNamespace(
        entry_id="entry123",
        data={"model": model},
        options={},
        title=model,
        async_on_unload=lambda unload: None,
    )


def _coordinator(config_entry: SimpleNamespace, data: dict) -> SimpleNamespace:
    return SimpleNamespace(
        api=SimpleNamespace(),
        config_entry=config_entry,
        data=data,
        async_add_listener=lambda listener: (lambda: None),
    )


def test_sensor_setup_adds_wisp_sensors_and_removes_stale_entries(monkeypatch) -> None:
    """WISP sensors should appear only for live values on supported models."""
    config_entry = _config_entry()
    coordinator = _coordinator(
        config_entry,
        {
            const.MODULE_WISP: {
                "status": {"value": "Connected"},
                "ssid": {"value": "Barn-Link"},
                "bssid": {"value": None},
                "public_ip": {"value": "203.0.113.77"},
                "signal": {"value": 65},
                "quality": {"value": 62},
                "channel": {"value": 5},
                "channel_width": {"value": "40 MHz"},
                "protocol": {"value": "DHCP"},
                "transmit_power": {"value": -1},
            },
        },
    )
    hass = SimpleNamespace(data={const.DOMAIN: {"entry123": coordinator}})
    registry = _Registry(
        {
            "sensor.lt300_wisp_status": SimpleNamespace(
                domain="sensor",
                platform=const.DOMAIN,
                entity_id="sensor.lt300_wisp_status",
                unique_id="entry123-wisp-status",
            ),
            "sensor.lt300_wisp_bssid": SimpleNamespace(
                domain="sensor",
                platform=const.DOMAIN,
                entity_id="sensor.lt300_wisp_bssid",
                unique_id="entry123-wisp-bssid",
            ),
        }
    )
    added_entities = []

    monkeypatch.setattr(sensor, "async_get_entity_registry", lambda hass: registry)

    asyncio.run(
        sensor.async_setup_entry(
            hass,
            config_entry,
            lambda entities: added_entities.extend(entities),
        )
    )

    assert registry.removed == ["sensor.lt300_wisp_bssid"]
    assert "sensor.lt300_wisp_status" in registry.entities
    unique_ids = {entity.unique_id for entity in added_entities}
    for key in (
        "status",
        "ssid",
        "public_ip",
        "signal",
        "quality",
        "channel",
        "channel_width",
        "protocol",
        "transmit_power",
    ):
        assert f"entry123-wisp-{key}" in unique_ids
    assert "entry123-wisp-bssid" not in unique_ids


def test_switch_setup_adds_wisp_enabled_only_when_field_exists(monkeypatch) -> None:
    """The WISP enabled switch should be created only from the parsed settings field."""
    config_entry = _config_entry()
    coordinator = _coordinator(
        config_entry,
        {
            const.MODULE_WISP: {
                "status": {"value": "Connected"},
                "enabled": {"value": True},
            },
        },
    )
    hass = SimpleNamespace(data={const.DOMAIN: {"entry123": coordinator}})
    registry = _Registry()
    added_entities = []

    monkeypatch.setattr(switch, "async_get_entity_registry", lambda hass: registry)

    asyncio.run(
        switch.async_setup_entry(
            hass,
            config_entry,
            lambda entities: added_entities.extend(entities),
        )
    )

    unique_ids = {entity.unique_id for entity in added_entities}
    assert "entry123-wisp-enabled" in unique_ids


def test_switch_setup_removes_stale_wisp_enabled_when_field_disappears(monkeypatch) -> None:
    """A supported model without the config field should not keep a stale enabled switch."""
    config_entry = _config_entry()
    coordinator = _coordinator(
        config_entry,
        {
            const.MODULE_WISP: {
                "status": {"value": "Connected"},
            },
        },
    )
    hass = SimpleNamespace(data={const.DOMAIN: {"entry123": coordinator}})
    registry = _Registry(
        {
            "switch.lt300_wisp_enabled": SimpleNamespace(
                domain="switch",
                platform=const.DOMAIN,
                entity_id="switch.lt300_wisp_enabled",
                unique_id="entry123-wisp-enabled",
            ),
        }
    )
    added_entities = []

    monkeypatch.setattr(switch, "async_get_entity_registry", lambda hass: registry)

    asyncio.run(
        switch.async_setup_entry(
            hass,
            config_entry,
            lambda entities: added_entities.extend(entities),
        )
    )

    assert registry.removed == ["switch.lt300_wisp_enabled"]
    assert "switch.lt300_wisp_enabled" not in registry.entities
    assert all(entity.unique_id != "entry123-wisp-enabled" for entity in added_entities)
