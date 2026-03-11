"""Tests for scan interval defaults and normalization."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONST_PATH = ROOT / "custom_components" / "cudy_router" / "const.py"


def _load_const_module():
    spec = importlib.util.spec_from_file_location("cudy_router_const", CONST_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scan_interval_constants() -> None:
    """Constants should match the intended defaults and limits."""
    const = _load_const_module()
    assert const.DEFAULT_SCAN_INTERVAL == 60
    assert const.MIN_SCAN_INTERVAL == 15
    assert const.MAX_SCAN_INTERVAL == 3600


@pytest.mark.parametrize(
    ("input_value", "expected"),
    [
        (None, 60),
        (15, 15),
        (60, 60),
        (5, 15),
        ("invalid", 60),
        (5000, 3600),
    ],
)
def test_normalize_scan_interval(input_value: object, expected: int) -> None:
    """Normalize should clamp and fall back safely."""
    const = _load_const_module()
    assert const.normalize_scan_interval(input_value) == expected
