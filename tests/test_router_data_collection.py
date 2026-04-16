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

    def get(self, path: str, silent: bool = False) -> str:
        del silent
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


def test_collect_router_data_skips_duplicate_multi_wan_page_and_aggregates_valid_bytes(
    monkeypatch,
) -> None:
    """Multi-WAN byte counters should ignore duplicated WAN1 fallback pages."""
    monkeypatch.setattr(
        router_data,
        "existing_feature",
        lambda device_model, module: module in {const.MODULE_WAN, const.MODULE_LOAD_BALANCING},
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
            "admin/network/mwan3/status": _fixture_text("load_balancing", "r700_status.html"),
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
    assert set(data[const.MODULE_LOAD_BALANCING]) == {"wan1_status", "wan4_status"}
    assert data[const.MODULE_LOAD_BALANCING]["wan1_status"]["value"] == "Online"
    assert data[const.MODULE_LOAD_BALANCING]["wan4_status"]["value"] == "Online"
