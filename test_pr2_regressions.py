"""Behavior regression tests for Cudy Router integration."""

from __future__ import annotations

import sys

import pytest


pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 13),
    reason="Integration runtime tests require Python 3.13+ (same as CI).",
)


def test_parse_devices_reports_device_count() -> None:
    """Device parser should always expose a device_count entry."""
    from custom_components.cudy_router.parser import parse_devices

    data = parse_devices("<html><body>No clients</body></html>", "")
    assert data["device_count"]["value"] == 0


def test_parse_wan_status_handles_missing_values() -> None:
    """WAN parser should not emit stringified None values."""
    from custom_components.cudy_router.parser_network import parse_wan_status

    data = parse_wan_status("<html><body><table></table></body></html>")
    assert data["public_ip"]["value"] is None
    assert data["connected_time"]["value"] is None


def test_parse_wan_status_extracts_values() -> None:
    """WAN parser should normalize public IP and parse connected time."""
    from custom_components.cudy_router.parser_network import parse_wan_status

    html = """
    <table>
      <tr><th>Protocol</th><td>DHCP</td></tr>
      <tr><th>Public IP</th><td>*1.2.3.4</td></tr>
      <tr><th>Connected Time</th><td>01:02:03</td></tr>
    </table>
    """
    data = parse_wan_status(html)
    assert data["public_ip"]["value"] == "1.2.3.4"
    assert isinstance(data["connected_time"]["value"], float)
    assert data["connected_time"]["value"] > 0


def test_feature_gating_default_and_wr3000s() -> None:
    """Feature matrix should keep WR3000S exclusions while enabling unknown defaults."""
    from custom_components.cudy_router.features import existing_feature

    assert existing_feature("UNKNOWN MODEL", "wan") is True
    assert existing_feature("WR3000S V1.0", "modem") is False
    assert existing_feature("WR3000S V1.0", "devices") is True
