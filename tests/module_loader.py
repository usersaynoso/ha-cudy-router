"""Helpers for loading integration modules without importing package __init__."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "custom_components" / "cudy_router"


def _ensure_package_stub(name: str, path: Path) -> None:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = module


def _ensure_homeassistant_stub() -> None:
    homeassistant = sys.modules.get("homeassistant")
    if homeassistant is None:
        homeassistant = types.ModuleType("homeassistant")
        sys.modules["homeassistant"] = homeassistant

    const_module = sys.modules.get("homeassistant.const")
    if const_module is None:
        const_module = types.ModuleType("homeassistant.const")
        const_module.CONF_MODEL = "model"
        const_module.STATE_UNAVAILABLE = "unavailable"
        sys.modules["homeassistant.const"] = const_module

    core_module = sys.modules.get("homeassistant.core")
    if core_module is None:
        core_module = types.ModuleType("homeassistant.core")

        class HomeAssistant:  # noqa: D401
            """Minimal HomeAssistant stub for pure helper imports."""

        core_module.HomeAssistant = HomeAssistant
        sys.modules["homeassistant.core"] = core_module

    helpers_module = sys.modules.get("homeassistant.helpers")
    if helpers_module is None:
        helpers_module = types.ModuleType("homeassistant.helpers")
        sys.modules["homeassistant.helpers"] = helpers_module

    device_registry_module = sys.modules.get("homeassistant.helpers.device_registry")
    if device_registry_module is None:
        device_registry_module = types.ModuleType("homeassistant.helpers.device_registry")

        class DeviceInfo(dict):
            """Minimal DeviceInfo stub that preserves kwargs for assertions."""

            def __init__(self, **kwargs):
                super().__init__(**kwargs)

        class _DeviceRegistry:
            def __init__(self) -> None:
                self.devices = {}

            def async_remove_device(self, device_id: str) -> None:
                self.devices.pop(device_id, None)

        device_registry_module.CONNECTION_NETWORK_MAC = "mac"
        device_registry_module.DeviceInfo = DeviceInfo
        device_registry_module._registry = _DeviceRegistry()
        device_registry_module.async_get = lambda hass: device_registry_module._registry
        sys.modules["homeassistant.helpers.device_registry"] = device_registry_module

    entity_registry_module = sys.modules.get("homeassistant.helpers.entity_registry")
    if entity_registry_module is None:
        entity_registry_module = types.ModuleType("homeassistant.helpers.entity_registry")

        class _Registry:
            def __init__(self) -> None:
                self.entities = {}

            def async_remove(self, entity_id: str) -> None:
                self.entities.pop(entity_id, None)

        entity_registry_module._registry = _Registry()
        entity_registry_module.async_get = lambda hass: entity_registry_module._registry
        sys.modules["homeassistant.helpers.entity_registry"] = entity_registry_module


def load_cudy_module(module_name: str):
    """Load a custom_components.cudy_router module directly from disk."""
    _ensure_package_stub("custom_components", ROOT / "custom_components")
    _ensure_package_stub("custom_components.cudy_router", PACKAGE_ROOT)
    _ensure_homeassistant_stub()

    qualified_name = f"custom_components.cudy_router.{module_name}"
    module_path = PACKAGE_ROOT / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(qualified_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)
    return module
