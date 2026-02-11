"""Integration-style data collection tests using fixture HTML."""

from __future__ import annotations

import asyncio
from pathlib import Path

from custom_components.cudy_router.const import MODULE_MESH, MODULE_MODEM, MODULE_WAN
import custom_components.cudy_router.router_data as router_data


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


class _FakeHass:
    async def async_add_executor_job(self, func, *args):  # noqa: ANN001, ANN002
        return func(*args)


class _FakeRouter:
    def __init__(self, responses: dict[str, str]) -> None:
        self._responses = responses

    def get(self, path: str, _silent: bool = False) -> str:
        return self._responses.get(path, "")


def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_collect_router_data_with_fixture_pages(monkeypatch) -> None:  # noqa: ANN001
    """Collector should parse WAN/modem/mesh data from realistic fixture pages."""

    enabled_modules = {MODULE_MODEM, MODULE_WAN, MODULE_MESH}

    def _feature_gate(_model: str, module: str, *_args: str) -> bool:
        return module in enabled_modules

    monkeypatch.setattr(router_data, "existing_feature", _feature_gate)

    router = _FakeRouter(
        {
            "admin/network/gcom/status": _read_fixture("modem_status.html"),
            "admin/network/gcom/status?detail=1&iface=4g": "",
            "admin/network/wan/status?detail=1&iface=wan": _read_fixture("wan_status.html"),
            "admin/network/mesh/status": _read_fixture("mesh_status.html"),
            "admin/network/mesh/clients?clients=all": "",
        }
    )

    data = asyncio.run(router_data.collect_router_data(router, _FakeHass(), {}, "TEST-MODEL"))

    assert data[MODULE_MODEM]["network"]["value"] == "5G-SA"
    assert data[MODULE_WAN]["public_ip"]["value"] == "203.0.113.10"
    assert data[MODULE_MESH]["main_router_name"] == "Home Router"
    assert data[MODULE_MESH]["mesh_count"]["value"] == 1
