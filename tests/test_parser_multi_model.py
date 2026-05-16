"""Functional parser tests using representative multi-model fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.module_loader import load_cudy_module


const = load_cudy_module("const")
load_cudy_module("model_names")
parser = load_cudy_module("parser")
parser_network = load_cudy_module("parser_network")
parser_settings = load_cudy_module("parser_settings")


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture_text(*parts: str) -> str:
    return (FIXTURES.joinpath(*parts)).read_text(encoding="utf-8")


def test_parse_devices_supports_legacy_device_layout() -> None:
    """Legacy device rows should still produce device metrics and details."""
    parsed = parser.parse_devices(
        _fixture_text("devices", "legacy_devices.html"),
        "AA:BB:CC:DD:EE:01",
    )

    assert parsed["device_count"]["value"] == 2
    assert len(parsed[const.SECTION_DEVICE_LIST]) == 2
    assert parsed["top_downloader_hostname"]["value"] == "Office Laptop"
    assert parsed[const.SECTION_DETAILED]["AA:BB:CC:DD:EE:01"]["ip"] == "192.168.10.20"


def test_parse_devices_supports_modern_device_layout() -> None:
    """Newer Cudy connected-device tables should also be parsed."""
    parsed = parser.parse_devices(
        _fixture_text("devices", "modern_devices.html"),
        "tablet",
    )

    assert parsed["device_count"]["value"] == 2
    assert len(parsed[const.SECTION_DEVICE_LIST]) == 2
    assert parsed["top_downloader_hostname"]["value"] == "Gaming PC"
    assert parsed[const.SECTION_DETAILED]["tablet"]["mac"] == "AA:BB:CC:DD:EE:31"


def test_parse_system_status_supports_alternate_labels() -> None:
    """System parser should handle label variants seen on other Cudy models."""
    parsed = parser.parse_system_status(_fixture_text("system", "system_alt_labels.html"))

    assert parsed["firmware_version"]["value"] == "2.3.4-beta1"
    assert parsed["local_time"]["value"] == "2026-03-26 12:15:00"
    assert parsed["uptime"]["value"] == pytest.approx(97276.0)
    assert parsed["cpu_usage"]["value"] == 18.5
    assert parsed["ram_usage"]["value"] == 50.0


def test_parse_sms_status_and_inbox_rows_from_p5_layout() -> None:
    """SMS parsing should extract counts and inbox row metadata from the P5 layout."""
    status = parser.parse_sms_status(_fixture_text("sms", "status.html"))
    inbox_messages = parser.parse_sms_list(_fixture_text("sms", "inbox_list.html"), "rec")

    assert status["inbox_count"]["value"] == 1
    assert status["outbox_count"]["value"] == 1
    assert status["unread_count"]["value"] == 1
    assert inbox_messages is not None
    assert len(inbox_messages) == 1
    assert inbox_messages[0]["folder"] == "inbox"
    assert inbox_messages[0]["index"] == 1
    assert inbox_messages[0]["phone"] == "+441234500001"
    assert inbox_messages[0]["timestamp"] == "04/12/26, 08:41:23"
    assert inbox_messages[0]["cfg"] == "cfginbox1"
    assert inbox_messages[0]["read"] is False


def test_parse_sms_outbox_rows_and_detail_modal() -> None:
    """SMS parsing should extract outbox metadata and full detail text."""
    outbox_messages = parser.parse_sms_list(_fixture_text("sms", "outbox_list.html"), "sto")
    outbox_detail = parser.parse_sms_detail(_fixture_text("sms", "outbox_detail.html"))

    assert outbox_messages is not None
    assert len(outbox_messages) == 1
    assert outbox_messages[0]["folder"] == "outbox"
    assert outbox_messages[0]["preview"] == "Confirmed | back gate..."
    assert outbox_messages[0]["cfg"] == "cfgoutbox1"
    assert outbox_messages[0]["read"] is None
    assert outbox_detail == {
        "direction": "To",
        "phone": "+441234500002",
        "timestamp": "04/12/26, 08:55:00",
        "text": "Confirmed | back gate at 18:00.",
    }


def test_parse_sms_inbox_detail_modal() -> None:
    """SMS detail parsing should preserve the full inbox message body."""
    inbox_detail = parser.parse_sms_detail(_fixture_text("sms", "inbox_detail.html"))

    assert inbox_detail == {
        "direction": "From",
        "phone": "+441234500001",
        "timestamp": "04/12/26, 08:41:23",
        "text": "Reminder: use *new* code [ALPHA].\nBring ID.",
    }


def test_parse_wan_status_supports_alternate_labels() -> None:
    """WAN parser should accept common alternate field names."""
    parsed = parser_network.parse_wan_status(_fixture_text("wan", "wan_alt_labels.html"))

    assert parsed["protocol"]["value"] == "DHCP"
    assert parsed["mac_address"]["value"] == "AA:BB:CC:DD:EE:FF"
    assert parsed["public_ip"]["value"] == "203.0.113.10"
    assert parsed["wan_ip"]["value"] == "100.64.0.2"
    assert parsed["subnet_mask"]["value"] == "255.255.255.0"
    assert parsed["gateway"]["value"] == "100.64.0.1"
    assert parsed["dns"]["value"] == "1.1.1.1"
    assert parsed["session_upload"]["value"] == 51.6
    assert parsed["session_download"]["value"] == 368.07


def test_parse_wan_status_reads_wr3000s_detail_fixture() -> None:
    """WAN parser should read the WR3000S detail table reported in diagnostics."""
    parsed = parser_network.parse_wan_status(_fixture_text("wan", "wan_wr3000s_detail.html"))

    assert round(parsed["connected_time"]["value"]) == 6153152
    assert parsed["public_ip"]["value"] == "203.0.113.35"
    assert parsed["wan_ip"]["value"] == "198.51.100.36"
    assert parsed["session_upload"]["value"] == 1077145.6
    assert parsed["session_download"]["value"] == 2502942.72


def test_parse_arp_status_counts_br_lan_entries() -> None:
    """ARP parsing should count only the requested interface rows."""
    parsed = parser_network.parse_arp_status(_fixture_text("devices", "r700_arp_status.html"), "br-lan")

    assert parsed["arp_br_lan_count"]["value"] == 3


def test_parse_arp_status_matches_annotated_interface_cells() -> None:
    """ARP parsing should tolerate newer interface cells that include extra text."""
    parsed = parser_network.parse_arp_status(
        """
        <table class="table">
          <tbody>
            <tr id="cbi-table-1">
              <td>1</td>
              <td>192.168.10.140</td>
              <td>AA:BB:CC:DD:EE:FF</td>
              <td>Host</td>
              <td><p class="form-control-static">br-lan (bridge)</p></td>
            </tr>
            <tr id="cbi-table-2">
              <td>2</td>
              <td>192.168.0.10</td>
              <td>AA:BB:CC:DD:EE:00</td>
              <td>WAN</td>
              <td><p class="form-control-static">eth1.3</p></td>
            </tr>
          </tbody>
        </table>
        """,
        "br-lan",
    )

    assert parsed["arp_br_lan_count"]["value"] == 1


def test_parse_lan_settings_reads_subnet_mask_from_config_page() -> None:
    """LAN config parsing should expose the router subnet mask."""
    parsed = parser_settings.parse_lan_settings(_fixture_text("lan", "lan_config_subnet.html"))

    assert parsed["ip_address"]["value"] == "192.168.10.1"
    assert parsed["subnet_mask"]["value"] == "255.255.255.0"


def test_parse_lan_status_reads_byte_counters() -> None:
    """LAN status parsing should expose explicit RX/TX byte counters."""
    parsed = parser.parse_lan_status(_fixture_text("lan", "lan_status_bytes.html"))

    assert parsed["bytes_received"]["value"] == int(1.5 * 1024**3)
    assert parsed["bytes_sent"]["value"] == 512 * 1024**2


def test_parse_wan_settings_reads_protocol_and_subnet_mask_from_config_page() -> None:
    """WAN config parsing should keep the selected protocol and configured mask."""
    parsed = parser_settings.parse_wan_settings(_fixture_text("wan", "wan_config_subnet.html"))

    assert parsed["protocol"]["value"] == "dhcp"
    assert parsed["subnet_mask"]["value"] == "255.255.255.0"


def test_parse_wan_status_reads_byte_counters() -> None:
    """WAN status parsing should expose explicit receive/transmit byte counters."""
    parsed = parser_network.parse_wan_status(_fixture_text("wan", "wan_status_bytes.html"))

    assert parsed["bytes_received"]["value"] == 2 * 1024**3
    assert parsed["bytes_sent"]["value"] == 256 * 1024**2


def test_parse_wan_status_reads_bytes_rx_tx_label_variants() -> None:
    """WAN byte parsing should handle newer TX/RX label wording."""
    parsed = parser_network.parse_wan_status(
        """
        <table class="table">
          <tbody>
            <tr><td>Protocol</td><td>DHCP</td></tr>
            <tr><td>Bytes RX</td><td>1.5 GiB</td></tr>
            <tr><td>Bytes TX</td><td>512 MiB</td></tr>
          </tbody>
        </table>
        """
    )

    assert parsed["bytes_received"]["value"] == int(1.5 * 1024**3)
    assert parsed["bytes_sent"]["value"] == 512 * 1024**2


def test_parse_wan_status_reads_combined_rx_tx_byte_counter() -> None:
    """WAN byte parsing should split combined receive/transmit counters."""
    parsed = parser_network.parse_wan_status(
        """
        <table class="table">
          <tbody>
            <tr><td>RX / TX Bytes</td><td>2 GB / 128 MB</td></tr>
          </tbody>
        </table>
        """
    )

    assert parsed["bytes_received"]["value"] == 2 * 1024**3
    assert parsed["bytes_sent"]["value"] == 128 * 1024**2


def test_parse_wisp_status_reads_lt300_host_network_panel() -> None:
    """WISP status parsing should extract LT300 host-network panel fields."""
    parsed = parser_network.parse_wisp_status(
        """
        <div class="panel panel-primary">
          <div class="panel-heading"><h3 class="panel-title">Host Network</h3></div>
          <table class="table">
            <thead>
              <tr><th>Status</th><th>Connected</th><th><i class="fa fa-check"></i></th></tr>
            </thead>
            <tbody>
              <tr><td><p class="visible-xs">SSID</p></td><td><p class="visible-xs">Cudy-Office-Guest</p></td></tr>
              <tr><td><p class="visible-xs">Public IP</p></td><td><p class="visible-xs">203.0.113.77</p></td></tr>
              <tr><td><p class="visible-xs">Signal</p></td><td><p class="visible-xs">65 dB</p></td></tr>
            </tbody>
          </table>
        </div>
        """
    )

    assert parsed["status"]["value"] == "Connected"
    assert parsed["status"]["attributes"]["raw_status"] == "Connected"
    assert parsed["ssid"]["value"] == "Cudy-Office-Guest"
    assert parsed["public_ip"]["value"] == "203.0.113.77"
    assert parsed["signal"]["value"] == 65


def test_parse_wisp_data_reads_json_status_payload() -> None:
    """WISP JSON parsing should normalize status, protocol, and radio fields."""
    parsed = parser_network.parse_wisp_data(
        """
        {"wds":"success","ssid":"Cudy-Office-Guest","up":true,
         "public_ip":"203.0.113.78",
         "bssid":"80:AF:CA:5F:AA:C6","hidden":0,"proto":"dhcp",
         "txpower":-1,"channel":5,"htbw":"ht40","maxsta":0,
         "isolate":0,"quality":62}
        """
    )

    assert parsed["status"]["value"] == "Connected"
    assert parsed["status"]["attributes"] == {"raw_status": "success", "up": True}
    assert parsed["ssid"]["value"] == "Cudy-Office-Guest"
    assert parsed["bssid"]["value"] == "80:AF:CA:5F:AA:C6"
    assert parsed["public_ip"]["value"] == "203.0.113.78"
    assert parsed["quality"]["value"] == 62
    assert parsed["channel"]["value"] == 5
    assert parsed["channel_width"]["value"] == "40 MHz"
    assert parsed["protocol"]["value"] == "DHCP"
    assert parsed["transmit_power"]["value"] == -1
    assert parsed["hidden"]["value"] is False
    assert parsed["isolate"]["value"] is False
    assert parsed["up"]["value"] is True


def test_parse_vpn_status_reads_r700_pptp_fields() -> None:
    """R700 VPN status parsing should expose the PPTP protocol and tunnel IP."""
    parsed = parser_network.parse_vpn_status(_fixture_text("vpn", "vpn_r700_status.html"))

    assert parsed["protocol"]["value"] == "PPTP Client"
    assert parsed["tunnel_ip"]["value"] == "192.168.2.20"
    assert parsed["vpn_clients"]["value"] is None


def test_parse_vpn_status_reads_connected_client_count() -> None:
    """VPN parsing should read connected-client counts from alternate status labels."""
    parsed = parser_network.parse_vpn_status(_fixture_text("vpn", "vpn_connected_clients.html"))

    assert parsed["protocol"]["value"] == "WireGuard"
    assert parsed["vpn_clients"]["value"] == 1
    assert parsed["tunnel_ip"]["value"] == "10.8.0.2"


def test_parse_vpn_status_reads_zero_device_count() -> None:
    """VPN parsing should preserve explicit zero connected-device counts."""
    parsed = parser_network.parse_vpn_status(
        _fixture_text("vpn", "vpn_wr3000s_openvpn_server_zero.html")
    )

    assert parsed["protocol"]["value"] == "OpenVPN Server"
    assert parsed["vpn_clients"]["value"] == 0


def test_parse_vpn_status_reads_additional_client_count_labels() -> None:
    """VPN count parsing should accept newer active-client labels."""
    parsed = parser_network.parse_vpn_status(
        """
        <table class="table">
          <tbody>
            <tr><td>Protocol</td><td>OpenVPN Server</td></tr>
            <tr><td>Active Clients</td><td>3 clients</td></tr>
          </tbody>
        </table>
        """
    )

    assert parsed["vpn_clients"]["value"] == 3


def test_parse_vpn_status_reads_singular_vpn_client_count_labels() -> None:
    """VPN count parsing should accept singular VPN client labels."""
    parsed = parser_network.parse_vpn_status(
        """
        <table class="table">
          <tbody>
            <tr><td>Protocol</td><td>WireGuard Client</td></tr>
            <tr><td>VPN Client</td><td>1</td></tr>
          </tbody>
        </table>
        """
    )
    alternate = parser_network.parse_vpn_status(
        """
        <table class="table">
          <tbody>
            <tr><td>VPN Client(s)</td><td>2 clients</td></tr>
          </tbody>
        </table>
        """
    )

    assert parsed["vpn_clients"]["value"] == 1
    assert alternate["vpn_clients"]["value"] == 2


def test_parse_vpn_status_counts_connected_client_table_rows() -> None:
    """VPN count parsing should count client rows when no summary count is present."""
    parsed = parser_network.parse_vpn_status(
        """
        <table class="table">
          <thead>
            <tr>
              <th>Common Name</th>
              <th>Real Address</th>
              <th>Virtual Address</th>
              <th>Bytes Received</th>
              <th>Bytes Sent</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>phone</td>
              <td>198.51.100.10:51820</td>
              <td>10.8.0.2</td>
              <td>2 MB</td>
              <td>1 MB</td>
            </tr>
            <tr>
              <td>laptop</td>
              <td>198.51.100.20:51820</td>
              <td>10.8.0.3</td>
              <td>4 MB</td>
              <td>2 MB</td>
            </tr>
          </tbody>
        </table>
        """
    )

    assert parsed["vpn_clients"]["value"] == 2


def test_parse_load_balancing_status_reads_r700_interfaces() -> None:
    """R700 load-balancing status parsing should expose interface health."""
    parsed = parser_network.parse_load_balancing_status(_fixture_text("load_balancing", "r700_status.html"))

    assert set(parsed) == {"wan1_status", "wan4_status"}
    assert parsed["wan1_status"]["value"] == "Online"
    assert parsed["wan4_status"]["value"] == "Online"


def test_parse_load_balancing_status_supports_middle_wan_interfaces() -> None:
    """Load-balancing parsing should support WAN2/WAN3 without inventing other sensors."""
    parsed = parser_network.parse_load_balancing_status(_fixture_text("load_balancing", "r700_status_wan2_wan3.html"))

    assert set(parsed) == {"wan2_status", "wan3_status"}
    assert parsed["wan2_status"]["value"] == "Online"
    assert parsed["wan3_status"]["value"] == "Offline"


def test_parse_load_balancing_status_supports_protocol_annotated_interfaces() -> None:
    """Protocol text in the interface column should not hide a WAN3 status row."""
    parsed = parser_network.parse_load_balancing_status(
        _fixture_text("load_balancing", "r700_status_protocol_labels.html")
    )

    assert set(parsed) == {"wan1_status", "wan3_status"}
    assert parsed["wan1_status"]["value"] == "Online"
    assert parsed["wan3_status"]["value"] == "Online"


def test_get_sim_value_returns_none_when_status_icon_is_missing() -> None:
    """Missing SIM markup should not emit an invalid enum sensor state."""
    assert parser.get_sim_value("<html><body><p>No SIM icon</p></body></html>") is None


def test_get_signal_strength_returns_none_when_rssi_is_missing() -> None:
    """Missing RSSI should not emit a string sentinel into numeric signal handling."""
    assert parser.get_signal_strength(None) is None
