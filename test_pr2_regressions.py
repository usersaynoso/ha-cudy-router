"""Regression tests for PR #2 merge-safety fixes."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parent


def _read(relpath: str) -> str:
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


def _load_module(relpath: str, name: str) -> ModuleType:
    path = REPO_ROOT / relpath
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_conf_model_uses_safe_default_fallback() -> None:
    init_src = _read("custom_components/cudy_router/__init__.py")
    coordinator_src = _read("custom_components/cudy_router/coordinator.py")
    sensor_src = _read("custom_components/cudy_router/sensor.py")

    assert 'data.get(CONF_MODEL, "default")' in init_src
    assert 'self.config_entry.data.get(CONF_MODEL, "default")' in coordinator_src
    assert 'config_entry.data.get(CONF_MODEL, "default")' in sensor_src


def test_devices_count_sensor_is_present_and_not_skipped() -> None:
    sensor_src = _read("custom_components/cudy_router/sensor.py")

    assert '("devices", "device_count")' in sensor_src
    assert 'if module in ["modem", "data_usage", "sms"]' not in sensor_src


def test_parse_devices_reports_device_count() -> None:
    parser_src = _read("custom_components/cudy_router/parser.py")
    assert 'data = {"device_count": {"value": len(devices)}}' in parser_src


def test_feature_gating_still_excludes_expected_wr3000s_modules() -> None:
    features = _load_module("custom_components/cudy_router/features.py", "features_module")

    assert features.existing_feature("WR3000S V1.0", "modem") is False
    assert features.existing_feature("WR3000S V1.0", "data_usage") is False
    assert features.existing_feature("WR3000S V1.0", "sms") is False
    assert features.existing_feature("WR3000S V1.0", "devices") is True
