"""Tests for diagnostics entity catalog generation."""

from __future__ import annotations

from types import SimpleNamespace

from tests.module_loader import load_cudy_module


const = load_cudy_module("const")
load_cudy_module("model_names")
load_cudy_module("features")
entity_catalog = load_cudy_module("entity_catalog")


def _catalog(data, *, model: str = "WR6500", options: dict | None = None):
    config_entry = SimpleNamespace(
        entry_id="entry123",
        data={"model": model},
        options=options or {},
    )
    coordinator = SimpleNamespace(
        config_entry=config_entry,
        data=data,
    )
    return entity_catalog.build_entity_catalog(
        SimpleNamespace(),
        config_entry,
        coordinator,
    )


def test_entity_catalog_marks_empty_cpu_and_ram_sensors_blocked() -> None:
    """Diagnostics should explain empty system values without implying entity support."""
    catalog = _catalog(
        {
            const.MODULE_SYSTEM: {
                "uptime": {"value": 120},
                "cpu_usage": {"value": None},
                "ram_usage": {"value": ""},
            },
        }
    )

    entries = catalog["entities"]
    assert any(
        entry["domain"] == "sensor"
        and entry["module"] == const.MODULE_SYSTEM
        and entry["key"] == "uptime"
        and entry["status"] in {"available", "created"}
        for entry in entries
    )
    assert any(
        entry["domain"] == "sensor"
        and entry["module"] == const.MODULE_SYSTEM
        and entry["key"] == "cpu_usage"
        and entry["status"] == "blocked"
        and entry["reason"] == "empty_value"
        for entry in entries
    )
    assert any(
        entry["domain"] == "sensor"
        and entry["module"] == const.MODULE_SYSTEM
        and entry["key"] == "ram_usage"
        and entry["status"] == "blocked"
        and entry["reason"] == "empty_value"
        for entry in entries
    )


def test_entity_catalog_allows_live_data_without_enabling_unrelated_modules() -> None:
    """Live parsed data should prove one module without opening unrelated modules."""
    catalog = _catalog(
        {
            const.MODULE_WAN: {
                "protocol": {"value": "DHCP"},
            },
        },
        model="RE1500",
    )

    entries = catalog["entities"]
    assert any(
        entry["module"] == const.MODULE_WAN
        and entry["key"] == "protocol"
        and entry["status"] in {"available", "created"}
        for entry in entries
    )
    assert any(
        entry["module"] == const.MODULE_WIFI_2G
        and entry["status"] == "blocked"
        and entry["reason"] in {"missing_page", "empty_value"}
        for entry in entries
    )
    assert any(
        entry["module"] == const.MODULE_VPN
        and entry["status"] == "blocked"
        and entry["reason"] == "unsupported_model"
        for entry in entries
    )


def test_entity_catalog_reports_created_registry_entries(monkeypatch) -> None:
    """Created registry entities should be marked as created in the catalog."""
    monkeypatch.setattr(
        entity_catalog,
        "_registry_index",
        lambda hass, config_entry: {
            "entry123-system-uptime": {
                "entity_id": "sensor.router_uptime",
                "domain": "sensor",
                "platform": const.DOMAIN,
                "unique_id": "entry123-system-uptime",
                "disabled_by": None,
                "entity_category": "diagnostic",
            }
        },
    )

    catalog = _catalog(
        {
            const.MODULE_SYSTEM: {
                "uptime": {"value": 120},
            },
        }
    )

    uptime = next(
        entry
        for entry in catalog["entities"]
        if entry["unique_id"] == "entry123-system-uptime"
    )
    assert uptime["status"] == "created"
    assert uptime["entity_id"] == "sensor.router_uptime"
