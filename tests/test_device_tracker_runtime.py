"""Runtime tests for the device tracker platform setup."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from tests.module_loader import load_cudy_module


const = load_cudy_module("const")
device_tracker = load_cudy_module("device_tracker")

ENTRY_ID = "entry123"
LAPTOP = {"mac": "AA:BB:CC:DD:EE:01", "hostname": "laptop", "ip": "192.0.2.10"}


def _set_up(monkeypatch, devices, options):
    config_entry = SimpleNamespace(entry_id=ENTRY_ID, data={"model": "WR3000"}, options=options, title="WR3000")
    coordinator = SimpleNamespace(
        config_entry=config_entry,
        data={const.MODULE_DEVICES: {const.SECTION_DEVICE_LIST: [dict(device) for device in devices]}},
    )
    hass = SimpleNamespace(data={const.DOMAIN: {ENTRY_ID: coordinator}})
    ensured = []

    monkeypatch.setattr(device_tracker, "known_tracker_clients", lambda hass, config_entry: {})
    monkeypatch.setattr(device_tracker, "async_cleanup_stale_tracker_entities", lambda *args: None)
    monkeypatch.setattr(
        device_tracker,
        "async_ensure_client_entity_device",
        lambda hass, config_entry, domain, unique_id, device: ensured.append((domain, unique_id)),
    )

    added = []
    asyncio.run(device_tracker.async_setup_entry(hass, config_entry, lambda entities: added.extend(entities)))
    return added, ensured


def test_tracker_takes_client_device_name_and_stays_enabled(monkeypatch) -> None:
    """Trackers should be unnamed (device name only), enabled, and attached to the client device."""
    added, ensured = _set_up(
        monkeypatch,
        [LAPTOP],
        {const.OPTIONS_AUTO_ADD_DEVICE_TRACKERS: True},
    )

    assert len(added) == 1
    tracker = added[0]
    assert tracker._attr_has_entity_name is True
    assert tracker._attr_name is None
    assert tracker._attr_entity_registry_enabled_default is True
    assert tracker._attr_unique_id == "AA:BB:CC:DD:EE:01"
    assert tracker._attr_device_info["name"] == "laptop"
    assert ("mac", "aa:bb:cc:dd:ee:01") in tracker._attr_device_info["connections"]
    assert ensured == [("device_tracker", "AA:BB:CC:DD:EE:01")]
    assert tracker.is_connected is True
    assert tracker.ip_address == "192.0.2.10"


def test_selected_offline_tracker_is_still_created_without_a_name(monkeypatch) -> None:
    """Explicitly selected trackers stay registered while offline and still use the device name."""
    added, _ensured = _set_up(
        monkeypatch,
        [],
        {
            const.OPTIONS_AUTO_ADD_DEVICE_TRACKERS: False,
            const.OPTIONS_TRACKED_DEVICE_MACS: ["aabbccddee01"],
        },
    )

    assert len(added) == 1
    assert added[0]._attr_name is None
    assert added[0].is_connected is False
