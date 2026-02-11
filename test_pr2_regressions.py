"""Behavior regression tests for Cudy Router integration."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parent
COMPONENT_ROOT = REPO_ROOT / "custom_components" / "cudy_router"


def _load_module(fullname: str, relpath: str) -> ModuleType:
    """Load a module from path without importing package __init__."""
    spec = importlib.util.spec_from_file_location(fullname, COMPONENT_ROOT / relpath)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = module
    spec.loader.exec_module(module)
    return module


def _ensure_package_stubs() -> None:
    """Register package stubs so relative imports resolve."""
    custom_components = sys.modules.setdefault("custom_components", ModuleType("custom_components"))
    custom_components.__path__ = [str(REPO_ROOT / "custom_components")]

    cudy_router = sys.modules.setdefault(
        "custom_components.cudy_router",
        ModuleType("custom_components.cudy_router"),
    )
    cudy_router.__path__ = [str(COMPONENT_ROOT)]


def _ensure_homeassistant_const_stub() -> None:
    """Provide minimal Home Assistant constants for parser imports."""
    homeassistant = sys.modules.setdefault("homeassistant", ModuleType("homeassistant"))
    const_mod = sys.modules.setdefault("homeassistant.const", ModuleType("homeassistant.const"))
    const_mod.STATE_UNAVAILABLE = "unavailable"
    homeassistant.const = const_mod


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="parser.py requires newer Python syntax; exercised in CI on Python 3.13",
)
def test_parse_devices_reports_device_count() -> None:
    _ensure_package_stubs()
    _ensure_homeassistant_const_stub()
    _load_module("custom_components.cudy_router.const", "const.py")
    parser = _load_module("custom_components.cudy_router.parser", "parser.py")

    data = parser.parse_devices("<html><body>No clients</body></html>", "")
    assert data["device_count"]["value"] == 0


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="parser.py requires newer Python syntax; exercised in CI on Python 3.13",
)
def test_parse_wan_status_handles_missing_values() -> None:
    _ensure_package_stubs()
    _ensure_homeassistant_const_stub()
    _load_module("custom_components.cudy_router.const", "const.py")
    _load_module("custom_components.cudy_router.parser", "parser.py")
    parser_network = _load_module("custom_components.cudy_router.parser_network", "parser_network.py")

    data = parser_network.parse_wan_status("<html><body><table></table></body></html>")
    assert data["public_ip"]["value"] is None
    assert data["connected_time"]["value"] is None


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="parser.py requires newer Python syntax; exercised in CI on Python 3.13",
)
def test_parse_wan_status_extracts_values() -> None:
    _ensure_package_stubs()
    _ensure_homeassistant_const_stub()
    _load_module("custom_components.cudy_router.const", "const.py")
    _load_module("custom_components.cudy_router.parser", "parser.py")
    parser_network = _load_module("custom_components.cudy_router.parser_network", "parser_network.py")

    html = """
    <table>
      <tr><th>Protocol</th><td>DHCP</td></tr>
      <tr><th>Public IP</th><td>*1.2.3.4</td></tr>
      <tr><th>Connected Time</th><td>01:02:03</td></tr>
    </table>
    """
    data = parser_network.parse_wan_status(html)
    assert data["public_ip"]["value"] == "1.2.3.4"
    assert isinstance(data["connected_time"]["value"], float)
    assert data["connected_time"]["value"] > 0


def test_feature_gating_default_and_wr3000s() -> None:
    _ensure_package_stubs()
    features = _load_module("custom_components.cudy_router.features", "features.py")

    assert features.existing_feature("UNKNOWN MODEL", "wan") is True
    assert features.existing_feature("WR3000S V1.0", "modem") is False
    assert features.existing_feature("WR3000S V1.0", "devices") is True


def test_coordinator_uses_default_model_when_missing() -> None:
    _ensure_package_stubs()

    homeassistant = sys.modules.setdefault("homeassistant", ModuleType("homeassistant"))
    const_mod = sys.modules.setdefault("homeassistant.const", ModuleType("homeassistant.const"))
    const_mod.CONF_HOST = "host"
    const_mod.CONF_MODEL = "model"
    const_mod.CONF_SCAN_INTERVAL = "scan_interval"
    homeassistant.const = const_mod

    config_entries = sys.modules.setdefault(
        "homeassistant.config_entries",
        ModuleType("homeassistant.config_entries"),
    )
    config_entries.ConfigEntry = object

    core_mod = sys.modules.setdefault("homeassistant.core", ModuleType("homeassistant.core"))
    core_mod.HomeAssistant = object

    helpers_mod = sys.modules.setdefault("homeassistant.helpers", ModuleType("homeassistant.helpers"))
    update_mod = sys.modules.setdefault(
        "homeassistant.helpers.update_coordinator",
        ModuleType("homeassistant.helpers.update_coordinator"),
    )

    class FakeDataUpdateCoordinator:
        """Minimal coordinator base for tests."""

        @classmethod
        def __class_getitem__(cls, _item: Any) -> type["FakeDataUpdateCoordinator"]:
            return cls

        def __init__(self, hass: Any, _logger: Any, name: str, update_interval: Any) -> None:
            self.hass = hass
            self.name = name
            self.update_interval = update_interval

    class FakeUpdateFailed(Exception):
        """Minimal UpdateFailed exception."""

    update_mod.DataUpdateCoordinator = FakeDataUpdateCoordinator
    update_mod.UpdateFailed = FakeUpdateFailed
    helpers_mod.update_coordinator = update_mod

    class FakeRouter:
        """Placeholder router type for imports."""

    router_stub = ModuleType("custom_components.cudy_router.router")
    router_stub.CudyRouter = FakeRouter
    sys.modules["custom_components.cudy_router.router"] = router_stub

    _load_module("custom_components.cudy_router.const", "const.py")
    coordinator_mod = _load_module("custom_components.cudy_router.coordinator", "coordinator.py")

    class AsyncNoopTimeout:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> bool:
            return False

    coordinator_mod.asyncio.timeout = lambda _seconds: AsyncNoopTimeout()

    class FakeEntry:
        data = {"host": "https://router.local"}
        options = {}

    class FakeAPI:
        def __init__(self) -> None:
            self.model_seen: str | None = None

        async def get_data(self, _hass: Any, _options: dict[str, Any], model: str) -> dict[str, Any]:
            self.model_seen = model
            return {"ok": True}

    api = FakeAPI()
    coordinator = coordinator_mod.CudyRouterDataUpdateCoordinator(object(), FakeEntry(), api)
    result = asyncio.run(coordinator._async_update_data())

    assert result == {"ok": True}
    assert api.model_seen == "default"
