"""Tests for scan interval defaults and normalization."""

from __future__ import annotations

import pytest

from custom_components.cudy_router.const import (
    DEFAULT_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    normalize_scan_interval,
)


def test_scan_interval_constants() -> None:
    """Constants should match intended defaults and limits."""
    assert DEFAULT_SCAN_INTERVAL == 60
    assert MIN_SCAN_INTERVAL == 15
    assert MAX_SCAN_INTERVAL == 3600


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
    assert normalize_scan_interval(input_value) == expected

