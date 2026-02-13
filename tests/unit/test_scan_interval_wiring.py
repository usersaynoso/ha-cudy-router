"""Static wiring checks for scan interval usage."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG_FLOW_PATH = ROOT / "custom_components" / "cudy_router" / "config_flow.py"
COORDINATOR_PATH = ROOT / "custom_components" / "cudy_router" / "coordinator.py"


def test_config_flow_uses_shared_scan_interval_constants() -> None:
    """Options flow should use centralized constants and normalizer."""
    source = CONFIG_FLOW_PATH.read_text(encoding="utf-8")
    assert "from .const import (" in source
    assert "DEFAULT_SCAN_INTERVAL" in source
    assert "MIN_SCAN_INTERVAL" in source
    assert "MAX_SCAN_INTERVAL" in source
    assert "normalize_scan_interval(" in source


def test_coordinator_uses_normalized_scan_interval() -> None:
    """Coordinator should normalize interval before building timedelta."""
    source = COORDINATOR_PATH.read_text(encoding="utf-8")
    assert "from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, normalize_scan_interval" in source
    assert "scan_interval = normalize_scan_interval(" in source

