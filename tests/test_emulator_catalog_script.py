"""Tests for the Cudy emulator catalog maintainer script."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "cudy_emulator_catalog.py"
FIXTURES = ROOT / "tests" / "fixtures" / "emulator"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("cudy_emulator_catalog", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


catalog_script = _load_script_module()


def _fixture_text(name: str) -> str:
    return FIXTURES.joinpath(name).read_text(encoding="utf-8")


def test_parse_catalog_extracts_public_emulator_models() -> None:
    """The script should parse model links from the public catalog shape."""
    models = catalog_script.parse_catalog(_fixture_text("catalog.html"))

    assert [model["model"] for model in models] == ["P5", "R700", "WR11000"]
    assert models[0]["path"] == "/emulator/P5/"


def test_extract_luci_paths_and_infer_modules_from_panel_fixture() -> None:
    """Panel links should map back to integration module families."""
    panel_html = _fixture_text("wr11000_panel.html")
    paths = catalog_script.extract_luci_paths(panel_html)
    modules = catalog_script.infer_modules_from_paths(paths)
    metadata = catalog_script.extract_metadata(panel_html)

    assert "admin/network/lan/config" in paths
    assert "admin/setup?active=vpn" in paths
    assert catalog_script.const.MODULE_LAN in modules
    assert catalog_script.const.MODULE_DHCP in modules
    assert catalog_script.const.MODULE_WIRELESS_SETTINGS in modules
    assert catalog_script.const.MODULE_VPN in modules
    assert metadata["hardware"] == "WR11000 V1.0"
    assert metadata["firmware"] == "2.2.19-20250415-200805"
