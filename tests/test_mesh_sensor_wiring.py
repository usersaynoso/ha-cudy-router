"""Static wiring checks for the main-router mesh count sensor."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SENSOR_DESCRIPTIONS_PATH = ROOT / "custom_components" / "cudy_router" / "sensor_descriptions.py"
ROUTER_DATA_PATH = ROOT / "custom_components" / "cudy_router" / "router_data.py"
README_PATH = ROOT / "README.md"


def test_mesh_count_sensor_uses_connected_wording() -> None:
    """The main-router mesh count sensor should have a clear user-facing name."""
    source = SENSOR_DESCRIPTIONS_PATH.read_text(encoding="utf-8")

    assert '("mesh", "mesh_count")' in source
    assert 'name_suffix="Mesh devices connected"' in source


def test_router_data_recomputes_mesh_count_after_client_merge() -> None:
    """Final mesh count should reflect the merged mesh device list."""
    source = ROUTER_DATA_PATH.read_text(encoding="utf-8")

    assert 'mesh_data["mesh_count"] = {"value": len(mesh_data.get("mesh_devices", {}))}' in source


def test_readme_documents_mesh_devices_connected_sensor() -> None:
    """README should describe the main-router mesh count sensor accurately."""
    source = README_PATH.read_text(encoding="utf-8")

    assert "| Mesh Devices Connected |" in source
