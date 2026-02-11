"""Fixture-backed parser behavior tests."""

from __future__ import annotations

from pathlib import Path

from custom_components.cudy_router.parser import parse_mesh_devices, parse_modem_info
from custom_components.cudy_router.parser_network import parse_wan_status


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_parse_wan_status_fixture() -> None:
    """WAN parser should extract key network values from router HTML."""
    data = parse_wan_status(_read_fixture("wan_status.html"))

    assert data["protocol"]["value"] == "DHCP"
    assert data["public_ip"]["value"] == "203.0.113.10"
    assert data["gateway"]["value"] == "192.0.2.1"
    assert data["session_upload"]["value"] == 10.0
    assert data["session_download"]["value"] == 200.5


def test_parse_modem_status_fixture() -> None:
    """Modem parser should normalize network/band/sim/session details."""
    data = parse_modem_info(_read_fixture("modem_status.html"))

    assert data["network"]["value"] == "5G-SA"
    assert data["sim"]["value"] == "Sim 1"
    assert data["band"]["value"] == "B78"
    assert data["public_ip"]["value"] == "198.51.100.20"
    assert data["session_upload"]["value"] == 51.6
    assert data["session_download"]["value"] == 368.07


def test_parse_mesh_status_fixture() -> None:
    """Mesh parser should detect main router metadata and satellites."""
    data = parse_mesh_devices(_read_fixture("mesh_status.html"))

    assert data["main_router_name"] == "Home Router"
    assert data["mesh_count"]["value"] == 1
    assert data["mesh_devices"]
