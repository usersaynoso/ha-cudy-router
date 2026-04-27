"""Tests for Cudy Router debug report helpers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from tests.module_loader import load_cudy_module


debug_report = load_cudy_module("debug_report")


class _FakeHass:
    async def async_add_executor_job(self, func, *args):
        return func(*args)


class _FakeApi:
    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages
        self.requests: list[str] = []

    def debug_get(self, path: str) -> dict[str, object]:
        self.requests.append(path)
        text = self._pages.get(path, "")
        return {
            "path": path,
            "status_code": 200 if text else 404,
            "ok": bool(text),
            "url": f"https://192.168.10.1/cgi-bin/luci/{path}",
            "text": text,
        }


def test_debug_report_redaction_keeps_wan_counts_and_protocols() -> None:
    """Sensitive values should be removed without hiding useful status shape."""
    redacted = debug_report.redact_text(
        """
        Cookie: sysauth=abcdef123456; token="very-secret"
        <table><tr><td>Hostname</td><td>Chris-iPhone</td></tr></table>
        WAN3 PPTP Connected Clients 1 192.168.10.42 AA:BB:CC:DD:EE:FF
        """
    )

    assert "abcdef123456" not in redacted
    assert "very-secret" not in redacted
    assert "Chris-iPhone" not in redacted
    assert "192.168.10.42" not in redacted
    assert "AA:BB:CC:DD:EE:FF" not in redacted
    assert "WAN3" in redacted
    assert "PPTP" in redacted
    assert "Connected Clients 1" in redacted


def test_debug_report_endpoint_matrix_includes_r700_wan_and_vpn_variants() -> None:
    """The diagnostic matrix should probe the known R700 WAN and VPN variants."""
    wan_paths = debug_report.wan_debug_paths()
    vpn_paths = debug_report.vpn_debug_paths()

    assert "admin/network/mwan3/status?detail=" in wan_paths
    assert "admin/network/wan/status?detail=1&iface=wan" in wan_paths
    assert "admin/network/wan/status?detail=1&iface=wan3" in wan_paths
    assert "admin/network/wan/status?detail=1&iface=wanc" in wan_paths
    assert "admin/network/wan/config/detail?nomodal=&iface=wan4" in wan_paths
    assert "admin/network/wan/iface/wand/config" in wan_paths
    assert "admin/network/vpn/wireguard/status?detail=" in vpn_paths
    assert "admin/network/vpn/openvpns/status?status=" in vpn_paths
    assert "admin/network/vpn/openvpnc/status?detail=" in vpn_paths
    assert "admin/network/vpn/pptp/status?status=" in vpn_paths


def test_debug_report_payload_probes_and_redacts_router_pages() -> None:
    """Debug payloads should include transport details, parser output, and redacted HTML."""
    pages = {
        "admin/network/mwan3/status?detail=": """
        <table><tr><td>WAN3 (DHCP)</td><td>Online</td></tr></table>
        """,
        "admin/network/wan/status?detail=1&iface=wan3": """
        <h3 class="panel-title">WAN3</h3>
        <table>
          <tr><td>Protocol</td><td>DHCP</td></tr>
          <tr><td>IP Address</td><td>192.168.10.42</td></tr>
          <tr><td>Bytes RX</td><td>512 MB</td></tr>
          <tr><td>Bytes TX</td><td>64 MB</td></tr>
        </table>
        """,
        "admin/network/vpn/status?detail=": """
        <table><tr><td>Connected Clients</td><td>1 client</td></tr></table>
        """,
    }
    config_entry = SimpleNamespace(
        entry_id="entry123",
        title="Office Router",
        version=3,
        domain="cudy_router",
        data={"host": "192.168.10.1", "username": "admin", "password": "secret", "model": "R700"},
        options={},
    )
    coordinator = SimpleNamespace(
        config_entry=config_entry,
        api=_FakeApi(pages),
        data={"wan_interfaces": {"wan3": {"wan_ip": {"value": "192.168.10.42"}}}},
    )

    payload = asyncio.run(
        debug_report.async_build_debug_payload(
            _FakeHass(),
            coordinator,
            include_html=True,
            max_html_chars=2000,
        )
    )

    wan3_probe = next(
        probe
        for probe in payload["probes"]["wan"]
        if probe["path"] == "admin/network/wan/status?detail=1&iface=wan3"
    )
    vpn_probe = next(
        probe
        for probe in payload["probes"]["vpn"]
        if probe["path"] == "admin/network/vpn/status?detail="
    )

    assert payload["config_entry"]["data"]["password"] == "<REDACTED>"
    assert "192.168.10.42" not in wan3_probe["html_excerpt"]
    assert wan3_probe["headings"] == ["WAN3"]
    assert wan3_probe["table_data"]["IP Address"].startswith("<IP_")
    assert wan3_probe["parser_output"]["protocol"]["value"] == "DHCP"
    assert wan3_probe["parser_output"]["bytes_received"]["value"] == 512 * 1024**2
    assert vpn_probe["parser_output"]["vpn_clients"]["value"] == 1
