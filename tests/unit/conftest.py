"""Test package bootstrap for unit tests without importing integration __init__.py."""

from __future__ import annotations

import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CUSTOM_COMPONENTS_DIR = ROOT / "custom_components"
CUDY_DIR = CUSTOM_COMPONENTS_DIR / "cudy_router"


custom_components_pkg = sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
custom_components_pkg.__path__ = [str(CUSTOM_COMPONENTS_DIR)]

cudy_pkg = sys.modules.setdefault("custom_components.cudy_router", types.ModuleType("custom_components.cudy_router"))
cudy_pkg.__path__ = [str(CUDY_DIR)]

homeassistant_pkg = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
homeassistant_pkg.__path__ = []
homeassistant_const = sys.modules.setdefault("homeassistant.const", types.ModuleType("homeassistant.const"))
homeassistant_const.STATE_UNAVAILABLE = "unavailable"
