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
        const_module.STATE_UNAVAILABLE = "unavailable"
        sys.modules["homeassistant.const"] = const_module


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
