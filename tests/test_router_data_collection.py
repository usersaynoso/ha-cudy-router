"""Targeted router data collection tests for model-specific status handling."""

from __future__ import annotations

import asyncio
from pathlib import Path

from tests.module_loader import load_cudy_module


const = load_cudy_module("const")
router_data = load_cudy_module("router_data")

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture_text(*parts: str) -> str:
    return FIXTURES.joinpath(*parts).read_text(encoding="utf-8")


class _FakeHass:
    async def async_add_executor_job(self, func, *args):
        return func(*args)


class _FakeRouter:
    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages
        self.requests: list[tuple[str, bool]] = []

    def get(self, path: str, silent: bool = False) -> str:
        self.requests.append((path, silent))
        return self._pages.get(path, "")


def test_collect_router_data_adds_br_lan_arp_count(monkeypatch) -> None:
    """Device data should include the br-lan ARP count from the system ARP page."""
    monkeypatch.setattr(
        router_data,
        "existing_feature",
        lambda device_model, module: module == const.MODULE_DEVICES,
    )
    fake_router = _FakeRouter(
        {
            "admin/network/devices/devlist?detail=1": _fixture_text("devices", "modern_devices.html"),
            "admin/network/devices/status?detail=1": "",
            "admin/panel": "",
            "admin/system/status/arp": _fixture_text("devices", "r700_arp_status.html"),
        }
    )

    data = asyncio.run(
        router_data.collect_router_data(
            fake_router,
            _FakeHass(),
            {},
            "R700",
        )
    )

    assert data[const.MODULE_DEVICES]["device_count"]["value"] == 2
    assert data[const.MODULE_DEVICES]["arp_br_lan_count"]["value"] == 3


def test_collect_router_data_passes_picker_style_manual_device_lists_to_parser(monkeypatch) -> None:
    """Router data collection should accept the new MAC-list device_list option shape."""
    captured_device_list: list[str] | None = None

    def _parse_devices(html: str, device_list):
        nonlocal captured_device_list
        del html
        captured_device_list = device_list
        return {
            const.SECTION_DEVICE_LIST: [],
            "device_count": {"value": 0},
        }

    monkeypatch.setattr(
        router_data,
        "existing_feature",
        lambda device_model, module: module == const.MODULE_DEVICES,
    )
    monkeypatch.setattr(router_data, "parse_devices", _parse_devices)
    monkeypatch.setattr(router_data, "parse_devices_status", lambda html: {})
    monkeypatch.setattr(router_data, "parse_arp_status", lambda html, interface: {})

    fake_router = _FakeRouter(
        {
            "admin/network/devices/devlist?detail=1": "",
            "admin/network/devices/status?detail=1": "",
            "admin/panel": "",
            "admin/system/status/arp": "",
        }
    )

    asyncio.run(
        router_data.collect_router_data(
            fake_router,
            _FakeHass(),
            {const.OPTIONS_DEVICELIST: ["aabbccddee30"]},
            "R700",
        )
    )

    assert captured_device_list == ["aabbccddee30"]


def test_collect_router_data_skips_duplicate_multi_wan_page_and_aggregates_valid_bytes(
    monkeypatch,
) -> None:
    """Multi-WAN byte counters should ignore duplicated WAN1 fallback pages."""
    monkeypatch.setattr(
        router_data,
        "existing_feature",
        lambda device_model, module: module
        in {const.MODULE_WAN, const.MODULE_WAN_INTERFACES, const.MODULE_LOAD_BALANCING},
    )
    fake_router = _FakeRouter(
        {
            "admin/network/wan/status?detail=1&iface=wan": """
            <div class="panel panel-primary">
              <div class="panel-heading"><h3 class="panel-title">WAN1</h3></div>
              <table class="table">
                <tr><td><p class="visible-xs">Protocol</p></td><td><p class="visible-xs">DHCP</p></td></tr>
                <tr><td><p class="visible-xs">IP Address</p></td><td><p class="visible-xs">192.0.2.2</p></td></tr>
                <tr><td><p class="visible-xs">Bytes Received</p></td><td><p class="visible-xs">1 GB</p></td></tr>
                <tr><td><p class="visible-xs">Bytes Sent</p></td><td><p class="visible-xs">128 MB</p></td></tr>
              </table>
            </div>
            """,
            "admin/network/wan/status?detail=1&iface=wand": _fixture_text("wan", "wan_status_bytes.html"),
            "admin/network/wan/config/detail?nomodal=&iface=wan": _fixture_text("wan", "wan_config_subnet.html"),
            "admin/network/mwan3/status?detail=": _fixture_text("load_balancing", "r700_status.html"),
        }
    )

    data = asyncio.run(
        router_data.collect_router_data(
            fake_router,
            _FakeHass(),
            {},
            "R700",
        )
    )

    assert data[const.MODULE_WAN]["wan_ip"]["value"] == "192.0.2.2"
    assert data[const.MODULE_WAN]["bytes_received"]["value"] == (1024**3) + (2 * 1024**3)
    assert data[const.MODULE_WAN]["bytes_sent"]["value"] == (128 * 1024**2) + (256 * 1024**2)
    assert data[const.MODULE_WAN_INTERFACES]["wan1"]["wan_ip"]["value"] == "192.0.2.2"
    assert data[const.MODULE_WAN_INTERFACES]["wan1"]["bytes_received"]["value"] == 1024**3
    assert data[const.MODULE_WAN_INTERFACES]["wan4"]["bytes_received"]["value"] == 2 * 1024**3
    assert data[const.MODULE_WAN_INTERFACES]["wan4"]["bytes_sent"]["value"] == 256 * 1024**2
    assert data[const.MODULE_WAN_INTERFACES]["wan1"]["status"]["value"] == "Online"
    assert data[const.MODULE_WAN_INTERFACES]["wan4"]["status"]["value"] == "Online"
    assert set(data[const.MODULE_LOAD_BALANCING]) == {"wan1_status", "wan4_status"}
    assert data[const.MODULE_LOAD_BALANCING]["wan1_status"]["value"] == "Online"
    assert data[const.MODULE_LOAD_BALANCING]["wan4_status"]["value"] == "Online"


def test_collect_router_data_uses_detailed_r700_vpn_and_multi_wan_paths(monkeypatch) -> None:
    """R700 polling should use detail pages and include wanb/wanc interfaces."""
    monkeypatch.setattr(
        router_data,
        "existing_feature",
        lambda device_model, module: module
        in {
            const.MODULE_VPN,
            const.MODULE_WAN,
            const.MODULE_WAN_INTERFACES,
            const.MODULE_LOAD_BALANCING,
        },
    )
    fake_router = _FakeRouter(
        {
            "admin/network/vpn/wireguard/status?detail=": "",
            "admin/network/vpn/openvpns/status?status=": """
            <table class="table">
              <tr><td>Protocol</td><td>OpenVPN Server</td></tr>
              <tr><td>Clients</td><td>0</td></tr>
            </table>
            """,
            "admin/network/vpn/pptp/status?detail=": _fixture_text("vpn", "vpn_r700_status.html"),
            "admin/network/vpn/status?detail=": """
            <table class="table">
              <tr><td>Connected</td><td>1 client</td></tr>
            </table>
            """,
            "admin/network/vpn/config": "",
            "admin/network/mwan3/status?detail=": _fixture_text("load_balancing", "r700_status_wan2_wan3.html"),
            "admin/network/wan/status?detail=1&iface=wan": """
            <div class="panel panel-primary">
              <div class="panel-heading"><h3 class="panel-title">WAN1</h3></div>
              <table class="table">
                <tr><td><p class="visible-xs">Protocol</p></td><td><p class="visible-xs">PPPoE</p></td></tr>
                <tr><td><p class="visible-xs">IP Address</p></td><td><p class="visible-xs">192.0.2.2</p></td></tr>
                <tr><td><p class="visible-xs">Bytes Received</p></td><td><p class="visible-xs">1 GB</p></td></tr>
                <tr><td><p class="visible-xs">Bytes Sent</p></td><td><p class="visible-xs">128 MB</p></td></tr>
              </table>
            </div>
            """,
            "admin/network/wan/status?detail=1&iface=wanb": """
            <div class="panel panel-primary">
              <div class="panel-heading"><h3 class="panel-title">WAN2</h3></div>
              <table class="table">
                <tr><td><p class="visible-xs">Protocol</p></td><td><p class="visible-xs">PPPoE</p></td></tr>
                <tr><td><p class="visible-xs">Bytes Received</p></td><td><p class="visible-xs">2 GB</p></td></tr>
                <tr><td><p class="visible-xs">Bytes Sent</p></td><td><p class="visible-xs">256 MB</p></td></tr>
              </table>
            </div>
            """,
            "admin/network/wan/status?detail=1&iface=wanc": """
            <div class="panel panel-primary">
              <div class="panel-heading"><h3 class="panel-title">WAN3</h3></div>
              <table class="table">
                <tr><td><p class="visible-xs">Protocol</p></td><td><p class="visible-xs">DHCP</p></td></tr>
                <tr><td><p class="visible-xs">Bytes Received</p></td><td><p class="visible-xs">512 MB</p></td></tr>
                <tr><td><p class="visible-xs">Bytes Sent</p></td><td><p class="visible-xs">64 MB</p></td></tr>
              </table>
            </div>
            """,
            "admin/network/wan/status?detail=1&iface=wand": """
            <div class="panel panel-primary">
              <div class="panel-heading"><h3 class="panel-title">WAN1</h3></div>
              <table class="table">
                <tr><td><p class="visible-xs">Protocol</p></td><td><p class="visible-xs">DHCP</p></td></tr>
              </table>
            </div>
            """,
            "admin/network/wan/config/detail?nomodal=&iface=wan": "",
            "admin/network/wan/config?nomodal=&iface=wan": "",
        }
    )

    data = asyncio.run(
        router_data.collect_router_data(
            fake_router,
            _FakeHass(),
            {},
            "R700",
        )
    )

    assert data[const.MODULE_VPN]["protocol"]["value"] == "PPTP Client"
    assert data[const.MODULE_VPN]["tunnel_ip"]["value"] == "192.168.2.20"
    assert data[const.MODULE_VPN]["vpn_clients"]["value"] == 1
    assert set(data[const.MODULE_LOAD_BALANCING]) == {"wan2_status", "wan3_status"}
    assert data[const.MODULE_LOAD_BALANCING]["wan2_status"]["value"] == "Online"
    assert data[const.MODULE_LOAD_BALANCING]["wan3_status"]["value"] == "Offline"
    assert data[const.MODULE_WAN]["bytes_received"]["value"] == (1024**3) + (2 * 1024**3) + (512 * 1024**2)
    assert data[const.MODULE_WAN]["bytes_sent"]["value"] == (128 * 1024**2) + (256 * 1024**2) + (64 * 1024**2)
    assert data[const.MODULE_WAN_INTERFACES]["wan1"]["bytes_received"]["value"] == 1024**3
    assert data[const.MODULE_WAN_INTERFACES]["wan2"]["bytes_received"]["value"] == 2 * 1024**3
    assert data[const.MODULE_WAN_INTERFACES]["wan3"]["bytes_received"]["value"] == 512 * 1024**2
    assert data[const.MODULE_WAN_INTERFACES]["wan2"]["status"]["value"] == "Online"
    assert data[const.MODULE_WAN_INTERFACES]["wan3"]["status"]["value"] == "Offline"
    assert "wan4" not in data[const.MODULE_WAN_INTERFACES]
    assert ("admin/network/mwan3/status?detail=", True) in fake_router.requests
    assert ("admin/network/wan/status?detail=1&iface=wanb", True) in fake_router.requests
    assert ("admin/network/wan/status?detail=1&iface=wanc", True) in fake_router.requests
    assert ("admin/network/vpn/wireguard/status?detail=", True) in fake_router.requests
    assert ("admin/network/vpn/pptp/status?detail=", True) in fake_router.requests
    assert ("admin/network/vpn/status?detail=", True) in fake_router.requests


def test_collect_router_data_keeps_load_balancing_only_wan_statuses_separate(monkeypatch) -> None:
    """WAN interface status entities should appear even when detail pages are absent."""
    monkeypatch.setattr(
        router_data,
        "existing_feature",
        lambda device_model, module: module
        in {const.MODULE_WAN, const.MODULE_WAN_INTERFACES, const.MODULE_LOAD_BALANCING},
    )
    fake_router = _FakeRouter(
        {
            "admin/network/mwan3/status?detail=": _fixture_text("load_balancing", "r700_status_wan2_wan3.html"),
        }
    )

    data = asyncio.run(
        router_data.collect_router_data(
            fake_router,
            _FakeHass(),
            {},
            "R700",
        )
    )

    assert const.MODULE_WAN not in data
    assert data[const.MODULE_WAN_INTERFACES]["wan2"]["status"]["value"] == "Online"
    assert data[const.MODULE_WAN_INTERFACES]["wan3"]["status"]["value"] == "Offline"


def test_collect_router_data_accepts_lettered_wan_headings_and_alt_iface_paths(monkeypatch) -> None:
    """R700 WAN polling should tolerate newer WAN B/C labels and alternate iface names."""
    monkeypatch.setattr(
        router_data,
        "existing_feature",
        lambda device_model, module: module
        in {const.MODULE_WAN, const.MODULE_WAN_INTERFACES, const.MODULE_LOAD_BALANCING},
    )
    fake_router = _FakeRouter(
        {
            "admin/network/mwan3/status?detail=": _fixture_text("load_balancing", "r700_status_wan2_wan3.html"),
            "admin/network/wan/status?detail=1&iface=wan": """
            <div class="panel panel-primary">
              <div class="panel-heading"><h3 class="panel-title">WAN1</h3></div>
              <table class="table">
                <tr><td>Protocol</td><td>DHCP</td></tr>
                <tr><td>IP Address</td><td>192.0.2.2</td></tr>
                <tr><td>Bytes Received</td><td>1 GB</td></tr>
                <tr><td>Bytes Sent</td><td>128 MB</td></tr>
              </table>
            </div>
            """,
            "admin/network/wan/status?detail=1&iface=wanb": """
            <div class="panel panel-primary">
              <div class="panel-heading"><h3 class="panel-title">WAN1</h3></div>
              <table class="table"><tr><td>Protocol</td><td>DHCP</td></tr></table>
            </div>
            """,
            "admin/network/wan/status?detail=&iface=wanb": """
            <div class="panel panel-primary">
              <div class="panel-heading"><h3 class="panel-title">WAN B</h3></div>
              <table class="table">
                <tr><td>Protocol</td><td>PPPoE</td></tr>
                <tr><td>Bytes RX</td><td>1.5 GiB</td></tr>
                <tr><td>Bytes TX</td><td>512 MiB</td></tr>
              </table>
            </div>
            """,
            "admin/network/wan/status?detail=1&iface=wanc": """
            <div class="panel panel-primary">
              <div class="panel-heading"><h3 class="panel-title">WAN1</h3></div>
              <table class="table"><tr><td>Protocol</td><td>DHCP</td></tr></table>
            </div>
            """,
            "admin/network/wan/status?detail=1&iface=wan3": """
            <div class="panel panel-primary">
              <div class="panel-heading"><h3 class="panel-title">WAN 3</h3></div>
              <table class="table">
                <tr><td>Protocol</td><td>DHCP</td></tr>
                <tr><td>RX / TX Bytes</td><td>512 MB / 64 MB</td></tr>
              </table>
            </div>
            """,
            "admin/network/wan/config/detail?nomodal=&iface=wan": "",
            "admin/network/wan/config?nomodal=&iface=wan": "",
        }
    )

    data = asyncio.run(
        router_data.collect_router_data(
            fake_router,
            _FakeHass(),
            {},
            "R700",
        )
    )

    assert data[const.MODULE_WAN]["bytes_received"]["value"] == (
        (1024**3) + int(1.5 * 1024**3) + (512 * 1024**2)
    )
    assert data[const.MODULE_WAN]["bytes_sent"]["value"] == (
        (128 * 1024**2) + (512 * 1024**2) + (64 * 1024**2)
    )
    assert data[const.MODULE_WAN_INTERFACES]["wan2"]["protocol"]["value"] == "PPPoE"
    assert data[const.MODULE_WAN_INTERFACES]["wan3"]["protocol"]["value"] == "DHCP"
    assert data[const.MODULE_WAN_INTERFACES]["wan2"]["bytes_received"]["value"] == int(1.5 * 1024**3)
    assert data[const.MODULE_WAN_INTERFACES]["wan3"]["bytes_sent"]["value"] == 64 * 1024**2
    assert ("admin/network/wan/status?detail=&iface=wanb", True) in fake_router.requests
    assert ("admin/network/wan/status?detail=1&iface=wan3", True) in fake_router.requests


def test_collect_router_data_reads_auto_update_from_r700_setup_page_fallback(monkeypatch) -> None:
    """Auto-update settings should fall back to admin/setup when the legacy page is absent."""
    monkeypatch.setattr(
        router_data,
        "existing_feature",
        lambda device_model, module: module == const.MODULE_AUTO_UPDATE_SETTINGS,
    )
    fake_router = _FakeRouter(
        {
            "admin/system/autoupgrade": "",
            "admin/setup": """
            <form>
              <input type="hidden" name="cbid.setup.firmware.auto_upgrade" value="1" />
              <select name="cbid.setup.firmware.upgrade_time">
                <option value="2" selected="selected">02:00 - 04:00</option>
              </select>
            </form>
            """,
        }
    )

    data = asyncio.run(
        router_data.collect_router_data(
            fake_router,
            _FakeHass(),
            {},
            "R700",
        )
    )

    assert data[const.MODULE_AUTO_UPDATE_SETTINGS]["auto_update"]["value"] is True
    assert data[const.MODULE_AUTO_UPDATE_SETTINGS]["update_time"]["value"] == "2"


def test_collect_router_data_falls_back_to_alternate_r700_subnet_config_paths(monkeypatch) -> None:
    """LAN/WAN subnet collection should tolerate alternate config endpoints on newer R700 firmware."""
    monkeypatch.setattr(
        router_data,
        "existing_feature",
        lambda device_model, module: module in {const.MODULE_LAN, const.MODULE_WAN, const.MODULE_DHCP},
    )
    fake_router = _FakeRouter(
        {
            "admin/network/lan/status?detail=1": """
            <table class="table">
              <tr><td><p class="visible-xs">IP Address</p></td><td><p class="visible-xs">192.168.10.1</p></td></tr>
            </table>
            """,
            "admin/network/lan/config?nomodal=": "",
            "admin/network/lan/config/detail?nomodal=": """
            <form>
              <select name="cbid.setup.lan.netmask">
                <option value="255.255.255.0" selected="selected">255.255.255.0</option>
              </select>
            </form>
            """,
            "admin/services/dhcp/status?detail=1": "",
            "admin/network/wan/status?detail=1&iface=wan": """
            <table class="table">
              <tr><td><p class="visible-xs">Protocol</p></td><td><p class="visible-xs">DHCP client</p></td></tr>
              <tr><td><p class="visible-xs">IP Address</p></td><td><p class="visible-xs">192.0.2.2</p></td></tr>
            </table>
            """,
            "admin/network/wan/config/detail?nomodal=&iface=wan": "",
            "admin/network/wan/config?nomodal=&iface=wan": """
            <form>
              <select name="cbid.setup.wan.netmask">
                <option value="255.255.255.0" selected="selected">255.255.255.0</option>
              </select>
            </form>
            """,
        }
    )

    data = asyncio.run(
        router_data.collect_router_data(
            fake_router,
            _FakeHass(),
            {},
            "R700",
        )
    )

    assert data[const.MODULE_LAN]["subnet_mask"]["value"] == "255.255.255.0"
    assert data[const.MODULE_WAN]["subnet_mask"]["value"] == "255.255.255.0"


def test_collect_router_data_keeps_sms_counts_summary_only(monkeypatch) -> None:
    """SMS-capable routers should keep summary counts in coordinator data only."""
    monkeypatch.setattr(
        router_data,
        "existing_feature",
        lambda device_model, module: module == const.MODULE_SMS,
    )
    fake_router = _FakeRouter(
        {
            "admin/network/gcom/sms/status": _fixture_text("sms", "status.html"),
            "admin/network/gcom/sms/smslist?smsbox=rec&iface=4g": _fixture_text("sms", "inbox_list.html"),
            "admin/network/gcom/sms/smslist?smsbox=sto&iface=4g": _fixture_text("sms", "outbox_list.html"),
            "admin/network/gcom/sms/readsms?iface=4g&cfg=cfginbox1&smsbox=rec": _fixture_text(
                "sms",
                "inbox_detail.html",
            ),
            "admin/network/gcom/sms/readsms?iface=4g&cfg=cfgoutbox1&smsbox=sto": _fixture_text(
                "sms",
                "outbox_detail.html",
            ),
        }
    )

    data = asyncio.run(
        router_data.collect_router_data(
            fake_router,
            _FakeHass(),
            {},
            "P5",
        )
    )

    assert data[const.MODULE_SMS]["inbox_count"]["value"] == 1
    assert data[const.MODULE_SMS]["outbox_count"]["value"] == 1
    assert data[const.MODULE_SMS]["unread_count"]["value"] == 1
    assert "messages" not in data[const.MODULE_SMS]
    assert fake_router.requests == [("admin/network/gcom/sms/status", False)]


def test_collect_router_data_does_not_fetch_detailed_sms_pages(monkeypatch) -> None:
    """Coordinator polling should no longer fetch SMS inbox or outbox details."""
    monkeypatch.setattr(
        router_data,
        "existing_feature",
        lambda device_model, module: module == const.MODULE_SMS,
    )
    fake_router = _FakeRouter(
        {
            "admin/network/gcom/sms/status": _fixture_text("sms", "status.html"),
            "admin/network/gcom/sms/smslist?smsbox=rec&iface=4g": "",
            "admin/network/gcom/sms/smslist?smsbox=sto&iface=4g": "",
        }
    )

    data = asyncio.run(
        router_data.collect_router_data(
            fake_router,
            _FakeHass(),
            {},
            "P5",
        )
    )

    assert data[const.MODULE_SMS]["inbox_count"]["value"] == 1
    assert data[const.MODULE_SMS]["outbox_count"]["value"] == 1
    assert "messages" not in data[const.MODULE_SMS]
    assert all("/smslist?" not in path and "/readsms?" not in path for path, _ in fake_router.requests)


def test_collect_router_data_skips_sms_module_when_status_page_is_not_sms(monkeypatch) -> None:
    """A missing or unrelated SMS status page should not keep the SMS panel enabled."""
    monkeypatch.setattr(
        router_data,
        "existing_feature",
        lambda device_model, module: module == const.MODULE_SMS,
    )
    fake_router = _FakeRouter(
        {
            "admin/network/gcom/sms/status": "<html><body><h1>Status</h1><p>No modem tools here.</p></body></html>",
        }
    )

    data = asyncio.run(
        router_data.collect_router_data(
            fake_router,
            _FakeHass(),
            {},
            "Some Future Model V1.0",
        )
    )

    assert const.MODULE_SMS not in data
    assert fake_router.requests == [("admin/network/gcom/sms/status", False)]


def test_collect_router_data_skips_sms_module_for_non_sms_models(monkeypatch) -> None:
    """Routers without SMS support should not attempt to build SMS sensors."""
    monkeypatch.setattr(
        router_data,
        "existing_feature",
        lambda device_model, module: False,
    )
    fake_router = _FakeRouter(
        {
            "admin/network/gcom/sms/status": _fixture_text("sms", "status.html"),
        }
    )

    data = asyncio.run(
        router_data.collect_router_data(
            fake_router,
            _FakeHass(),
            {},
            "WR6500 V1.0",
        )
    )

    assert const.MODULE_SMS not in data
