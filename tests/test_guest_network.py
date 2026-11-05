"""Tests for optional guest Wi-Fi client tracking."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from tests.module_loader import load_cudy_module


const = load_cudy_module("const")
parser = load_cudy_module("parser")
guest_network = load_cudy_module("guest_network")
router_data = load_cudy_module("router_data")
binary_sensor = load_cudy_module("binary_sensor")
sensor = load_cudy_module("sensor")

FIXTURES = Path(__file__).resolve().parent / "fixtures"

LAN_CONFIG_HTML = """
<input type="text" name="cbid.network.lan.ipaddr" id="cbid.network.lan.ipaddr" value="192.168.10.1" />
<input type="text" name="cbid.network.lan.netmask" id="cbid.network.lan.netmask" value="255.255.255.0" />
"""


def _fixture_text(*parts: str) -> str:
    return FIXTURES.joinpath(*parts).read_text(encoding="utf-8")


class _FakeHass:
    async def async_add_executor_job(self, func, *args):
        return func(*args)


class _FakeRouter:
    base_url = "https://192.168.10.1"

    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages
        self.requests: list[str] = []

    def get(self, path: str, silent: bool = False) -> str:
        self.requests.append(path)
        return self._pages.get(path, "")


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


def _router_pages() -> dict[str, str]:
    return {
        "admin/network/devices/devlist?detail=1": _fixture_text("devices", "guest_devices.html"),
        "admin/network/devices/status?detail=1": _fixture_text("devices", "devices_status_guest.html"),
        "admin/network/lan/config?nomodal=": LAN_CONFIG_HTML,
        guest_network.GUEST_NETWORK_SETTINGS_PATH: _fixture_text("devices", "guest_network_settings.html"),
    }


def _collect(monkeypatch, options: dict) -> tuple[dict, _FakeRouter]:
    monkeypatch.setattr(
        router_data,
        "existing_feature",
        lambda device_model, module: module in (const.MODULE_DEVICES, const.MODULE_LAN),
    )
    fake_router = _FakeRouter(_router_pages())
    data = asyncio.run(router_data.collect_router_data(fake_router, _FakeHass(), options, "P5"))
    return data, fake_router


def test_devices_status_reads_header_total_zero_counts_6g_and_guest_rows() -> None:
    """The P5-style status page should keep zero, add 6G, and use the header total."""
    parsed = parser.parse_devices_status(_fixture_text("devices", "devices_status_guest.html"))

    assert parsed["wifi_2g_clients"]["value"] == 13
    assert parsed["wifi_5g_clients"]["value"] == 0
    assert parsed["wifi_6g_clients"]["value"] == 2
    assert parsed["wired_clients"]["value"] == 2
    assert parsed["status_guest_clients"]["value"] == 1
    assert parsed["total_clients"]["value"] == 25


def test_devices_status_without_guest_or_6g_rows_omits_those_keys() -> None:
    """Routers without guests connected or without 6G should not gain empty entries."""
    html = _fixture_text("devices", "devices_status_guest.html")
    for label in ("6G WiFi", "2.4G Guest Network"):
        html = html.replace(label, "Other")

    parsed = parser.parse_devices_status(html)

    assert "wifi_6g_clients" not in parsed
    assert "status_guest_clients" not in parsed


def test_guest_network_enabled_reads_ssid_disabled_fields() -> None:
    """Any enabled guest SSID means the guest network is on."""
    html = _fixture_text("devices", "guest_network_settings.html")

    assert guest_network.parse_guest_network_enabled(html) is True
    assert guest_network.parse_guest_network_enabled(html.replace('wlan02.disabled" value="0"', 'wlan02.disabled" value="1"')) is False
    assert guest_network.parse_guest_network_enabled("") is None
    assert guest_network.parse_guest_network_enabled("<html></html>") is None


def test_guest_devices_match_guest_label_or_address_outside_main_lan() -> None:
    """Mesh-joined guests are only recognisable by their guest subnet address."""
    main_lan = guest_network.lan_network("192.168.10.1", "255.255.255.0")

    assert guest_network.is_guest_device({"connection_type": "2.4G Guest Network", "ip": None}, main_lan)
    assert guest_network.is_guest_device({"connection_type": "Mesh", "ip": "192.168.9.102"}, main_lan)
    assert not guest_network.is_guest_device({"connection_type": "Mesh", "ip": "192.168.10.31"}, main_lan)
    assert not guest_network.is_guest_device({"connection_type": "Mesh", "ip": "192.168.9.102"}, None)


def test_collect_router_data_counts_guests_when_option_enabled(monkeypatch) -> None:
    """Guest clients should merge the device list, LAN subnet, and guest settings."""
    data, fake_router = _collect(monkeypatch, {const.OPTIONS_TRACK_GUEST_NETWORK: True})

    guest_clients = data[const.MODULE_DEVICES]["guest_clients"]
    assert guest_network.GUEST_NETWORK_SETTINGS_PATH in fake_router.requests
    assert guest_clients["value"] == 2
    assert guest_clients["attributes"]["guest_network_enabled"] is True
    assert [guest["hostname"] for guest in guest_clients["attributes"]["guests"]] == [
        "Visitor Phone",
        "Visitor Laptop",
    ]
    assert data[const.MODULE_DEVICES]["total_clients"]["value"] == 25


def test_collect_router_data_falls_back_to_router_address_for_lan_subnet(monkeypatch) -> None:
    """Without LAN data the router address still identifies the main LAN."""
    monkeypatch.setattr(
        router_data,
        "existing_feature",
        lambda device_model, module: module == const.MODULE_DEVICES,
    )
    fake_router = _FakeRouter(_router_pages())

    data = asyncio.run(
        router_data.collect_router_data(
            fake_router,
            _FakeHass(),
            {const.OPTIONS_TRACK_GUEST_NETWORK: True},
            "P5",
        )
    )

    assert data[const.MODULE_DEVICES]["guest_clients"]["value"] == 2


def test_build_guest_clients_ignores_listed_guests_missing_from_arp() -> None:
    """Guests the device list still shows after leaving should not be counted."""
    main_lan = guest_network.lan_network("192.168.10.1", "255.255.255.0")
    devices = parser.get_all_devices(_fixture_text("devices", "guest_devices.html"))
    arp_ips = guest_network.parse_arp_ips(_fixture_text("devices", "guest_arp_status.html"))

    guest_clients = guest_network.build_guest_clients(devices, main_lan, True, None, arp_ips)

    assert arp_ips == {"192.168.10.30", "192.168.9.103"}
    assert guest_clients["value"] == 1
    assert guest_clients["attributes"]["stale_entries_ignored"] == 1
    assert [guest["hostname"] for guest in guest_clients["attributes"]["guests"]] == ["Visitor Laptop"]


def test_build_guest_clients_skips_arp_check_when_arp_table_is_unreadable() -> None:
    """Routers without a readable ARP table should keep counting every listed guest."""
    main_lan = guest_network.lan_network("192.168.10.1", "255.255.255.0")
    devices = parser.get_all_devices(_fixture_text("devices", "guest_devices.html"))

    assert guest_network.parse_arp_ips("") is None
    assert guest_network.parse_arp_ips("<table><tbody></tbody></table>") is None
    assert guest_network.build_guest_clients(devices, main_lan, True, None, None)["value"] == 2


def test_collect_router_data_uses_arp_table_to_drop_stale_guests(monkeypatch) -> None:
    """Collection should pass the ARP page it already fetched into guest counting."""
    monkeypatch.setattr(
        router_data,
        "existing_feature",
        lambda device_model, module: module in (const.MODULE_DEVICES, const.MODULE_LAN),
    )
    pages = _router_pages()
    pages["admin/system/status/arp"] = _fixture_text("devices", "guest_arp_status.html")
    fake_router = _FakeRouter(pages)

    data = asyncio.run(
        router_data.collect_router_data(
            fake_router,
            _FakeHass(),
            {const.OPTIONS_TRACK_GUEST_NETWORK: True},
            "P5",
        )
    )

    guest_clients = data[const.MODULE_DEVICES]["guest_clients"]
    assert guest_clients["value"] == 1
    assert guest_clients["attributes"]["stale_entries_ignored"] == 1
    assert fake_router.requests.count("admin/system/status/arp") == 1


def test_collect_router_data_skips_guest_lookup_when_option_disabled(monkeypatch) -> None:
    """With the option off there is no extra request and no guest entry."""
    data, fake_router = _collect(monkeypatch, {})

    assert guest_network.GUEST_NETWORK_SETTINGS_PATH not in fake_router.requests
    assert "guest_clients" not in data[const.MODULE_DEVICES]


def _setup_context(options: dict, devices_data: dict) -> tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]:
    config_entry = SimpleNamespace(
        entry_id="entry123",
        data={"model": "P5"},
        options=options,
        title="P5",
        async_on_unload=lambda unload: None,
    )
    coordinator = SimpleNamespace(
        api=SimpleNamespace(),
        config_entry=config_entry,
        data={const.MODULE_DEVICES: devices_data},
        async_add_listener=lambda listener: (lambda: None),
    )
    hass = SimpleNamespace(data={const.DOMAIN: {"entry123": coordinator}})
    return config_entry, coordinator, hass


def test_binary_sensor_setup_adds_guests_present_when_enabled(monkeypatch) -> None:
    """Guests present should follow the guest client count."""
    config_entry, coordinator, hass = _setup_context(
        {const.OPTIONS_TRACK_GUEST_NETWORK: True},
        {"guest_clients": {"value": 1, "attributes": {}}},
    )
    monkeypatch.setattr(binary_sensor, "async_get_entity_registry", lambda hass: _Registry())
    added = []

    asyncio.run(binary_sensor.async_setup_entry(hass, config_entry, added.extend))

    assert [entity.unique_id for entity in added] == ["entry123-devices-guests_present"]
    assert added[0].is_on is True
    coordinator.data[const.MODULE_DEVICES]["guest_clients"]["value"] = 0
    assert added[0].is_on is False


def test_guest_entities_are_removed_when_option_disabled(monkeypatch) -> None:
    """Turning the option off should remove both guest entities."""
    config_entry, _coordinator, hass = _setup_context({}, {"device_count": {"value": 0}})
    registry = _Registry(
        {
            "binary_sensor.p5_guests_present": SimpleNamespace(
                domain="binary_sensor",
                platform=const.DOMAIN,
                entity_id="binary_sensor.p5_guests_present",
                unique_id="entry123-devices-guests_present",
            ),
            "sensor.p5_guest_network_clients": SimpleNamespace(
                domain="sensor",
                platform=const.DOMAIN,
                entity_id="sensor.p5_guest_network_clients",
                unique_id="entry123-devices-guest_clients",
            ),
        }
    )
    monkeypatch.setattr(binary_sensor, "async_get_entity_registry", lambda hass: registry)
    monkeypatch.setattr(sensor, "async_get_entity_registry", lambda hass: registry)
    added_binary = []
    added_sensors = []

    asyncio.run(binary_sensor.async_setup_entry(hass, config_entry, added_binary.extend))
    asyncio.run(sensor.async_setup_entry(hass, config_entry, added_sensors.extend))

    assert added_binary == []
    assert sorted(registry.removed) == [
        "binary_sensor.p5_guests_present",
        "sensor.p5_guest_network_clients",
    ]
    assert "entry123-devices-guest_clients" not in {entity.unique_id for entity in added_sensors}


def test_sensor_setup_adds_guest_client_count_when_enabled(monkeypatch) -> None:
    """The guest count sensor should be created from coordinator data."""
    config_entry, _coordinator, hass = _setup_context(
        {const.OPTIONS_TRACK_GUEST_NETWORK: True},
        {"guest_clients": {"value": 0, "attributes": {"guests": []}}},
    )
    monkeypatch.setattr(sensor, "async_get_entity_registry", lambda hass: _Registry())
    added = []

    asyncio.run(sensor.async_setup_entry(hass, config_entry, added.extend))

    guest_sensor = next(entity for entity in added if entity.unique_id == "entry123-devices-guest_clients")
    assert guest_sensor.native_value == 0
    assert guest_sensor.extra_state_attributes == {"guests": []}
