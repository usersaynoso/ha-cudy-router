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
    assert features.existing_feature("UNKNOWN MODEL", "wan") is True


def test_parse_wan_status_handles_missing_values_safely() -> None:
    parser_src = _read("custom_components/cudy_router/parser.py")
    assert "raw_public_ip = raw_data.get(\"Public IP\")" in parser_src
    assert "public_ip: str | None = None" in parser_src
    assert "connected_time: float | None = (" in parser_src


def test_mesh_json_state_maps_disconnected_to_offline() -> None:
    router_src = _read("custom_components/cudy_router/router.py")
    assert '"status": "online" if client_json.get("state") == "connected" else "offline"' in router_src


def test_wan_module_uses_endpoint_probe_for_unknown_models() -> None:
    router_src = _read("custom_components/cudy_router/router.py")
    assert "wan_status_html = await hass.async_add_executor_job(" in router_src
    assert "if wan_status_html and any(" in router_src
