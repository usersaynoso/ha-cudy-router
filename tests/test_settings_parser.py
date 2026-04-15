"""Parser coverage for configurable router settings pages."""

from __future__ import annotations

from tests.module_loader import load_cudy_module


parser = load_cudy_module("parser")
parser_settings = load_cudy_module("parser_settings")


def test_parse_devices_extracts_client_access_flags_from_modern_rows() -> None:
    """Modern device rows should capture internet, DNS filter, and VPN states."""
    html = """
    <table class="table">
      <tbody>
        <tr id="cbi-table-1">
          <td>1</td>
          <td><p class="hidden-xs">Home Assistant <span>wifi</span></p></td>
          <td>ignore</td>
          <td>ignore</td>
          <td><p class="hidden-xs">192.168.10.55 <span>AA:BB:CC:DD:EE:FF</span></p></td>
          <td><p class="hidden-xs">Up: 1 Mbps Down: 8 Mbps</p></td>
          <td><p class="hidden-xs">-58 dBm</p></td>
          <td><p class="hidden-xs">00:21:46</p></td>
          <td>
            <input type="hidden" name="cbid.table.1.internet" value="0" />
          </td>
          <td>
            <input type="hidden" name="cbid.table.1.dnsfilter" value="1" />
          </td>
          <td>
            <input type="hidden" name="cbid.table.1.vpn" value="0" />
          </td>
        </tr>
      </tbody>
    </table>
    """

    parsed = parser.parse_devices(html, "")
    device = parsed["device_list"][0]

    assert device["internet"] is False
    assert device["dnsfilter"] is True
    assert device["vpn"] is False
    assert device["connection_type"] == "wifi"
    assert device["signal"] == "-58 dBm"
    assert device["online_time"] == "00:21:46"


def test_parse_devices_merges_legacy_and_modern_views_for_same_row() -> None:
    """Legacy div parsing must not discard richer modern row fields."""
    html = """
    <table class="table table-striped">
      <tbody>
        <tr id="cbi-table-1">
          <td class="hidden-xs"><div id="cbi-table-1-idx"><p class="visible-xs">1</p></div></td>
          <td class="hidden-xs">
            <div id="cbi-table-1-hostname">
              <p class="visible-xs">Living-Room<br /><span class="text-primary">5G WiFi</span></p>
            </div>
          </td>
          <td class="visible-xs">
            <div id="cbi-table-1-hostnamexs">
              <p class="visible-xs">Living-Room<br />192.168.10.14</p>
            </div>
          </td>
          <td class="hidden-xs"><div id="cbi-table-1-icon"></div></td>
          <td class="hidden-xs">
            <div id="cbi-table-1-ipmac">
              <p class="visible-xs">192.168.10.14<br />8C:26:AA:DB:27:A4</p>
            </div>
          </td>
          <td class="hidden-xs">
            <div id="cbi-table-1-speed">
              <p class="visible-xs"><i></i> 0.00 Kbps<br /><i></i> 0.00 Kbps</p>
            </div>
          </td>
          <td class="hidden-xs"><div id="cbi-table-1-signal"><p class="visible-xs">-71 dBm</p></div></td>
          <td class="hidden-xs"><div id="cbi-table-1-online"><p class="visible-xs">1 Day 12:48:01</p></div></td>
          <td>
            <div id="cbi-table-1-internet">
              <input type="hidden" value="1" name="cbi.cbe.table.1.internet" />
              <input type="hidden" id="cbid.table.1.internet" name="cbid.table.1.internet" value="1" />
            </div>
          </td>
          <td>
            <div id="cbi-table-1-dnsfilter">
              <input type="hidden" value="0" name="cbi.cbe.table.1.dnsfilter" />
              <input type="hidden" id="cbid.table.1.dnsfilter" name="cbid.table.1.dnsfilter" value="0" />
            </div>
          </td>
        </tr>
      </tbody>
    </table>
    """

    parsed = parser.parse_devices(html, "")
    device = parsed["device_list"][0]

    assert len(parsed["device_list"]) == 1
    assert device["hostname"] == "Living-Room"
    assert device["connection_type"] == "5G WiFi"
    assert device["signal"] == "-71 dBm"
    assert device["online_time"] == "1 Day 12:48:01"
    assert device["internet"] is True
    assert device["dnsfilter"] is False


def test_parse_cellular_settings_reads_current_values_and_options() -> None:
    """Cellular parser should normalize key APN settings."""
    html = """
    <form>
      <input type="hidden" name="cbid.network.4g.disabled" value="0" />
      <input type="hidden" name="cbid.network.4g.roaming" value="1" />
      <select name="cbid.network.4g.simslot">
        <option value="0">Auto</option>
        <option value="1" selected="selected">1</option>
        <option value="2">2</option>
      </select>
      <select name="cbid.network.4g.service">
        <option value="lte">4G only</option>
        <option value="5g">5G-SA only</option>
        <option value="5gnsa_lte" selected="selected">5G-NSA</option>
        <option value="all">Auto</option>
      </select>
      <select name="cbid.network.4g.search">
        <option value="auto" selected="selected">Auto</option>
        <option value="manual">Manual</option>
      </select>
      <select name="cbid.network.4g.isp">
        <option value="custom">Custom</option>
        <option value="vodafone" selected="selected">Vodafone</option>
      </select>
      <select name="cbid.network.4g.pdptype">
        <option value="ip" selected="selected">IPv4</option>
        <option value="ipv4v6">IPv4/IPv6</option>
      </select>
    </form>
    """

    parsed = parser_settings.parse_cellular_settings(html)

    assert parsed["enabled"]["value"] is True
    assert parsed["data_roaming"]["value"] is True
    assert parsed["sim_slot"]["value"] == "1"
    assert parsed["sim_slot"]["options"]["1"] == "Sim 1"
    assert parsed["network_mode"]["value"] == "5gnsa_lte"
    assert parsed["network_mode"]["options"]["5gnsa_lte"] == "5G-NSA"
    assert parsed["network_search"]["value"] == "auto"
    assert parsed["apn_profile"]["value"] == "vodafone"
    assert parsed["pdp_type"]["value"] == "ip"


def test_parse_wireless_settings_merges_smart_connect_specific_forms() -> None:
    """Wireless parser should expose canonical keys regardless of page variant."""
    combo_html = """
    <form>
      <input type="hidden" name="cbid.wireless.smart.connect" value="0" />
    </form>
    """
    combine_html = "<form></form>"
    uncombine_html = """
    <form>
      <input type="hidden" name="cbid.wireless.wlan00.disabled" value="0" />
      <input type="hidden" name="cbid.wireless.wlan10.disabled" value="1" />
      <input type="hidden" name="cbid.wireless.wlan00.hidden" value="1" />
      <input type="hidden" name="cbid.wireless.wlan10.hidden" value="0" />
      <input type="hidden" name="cbid.wireless.wlan00.isolate" value="0" />
      <input type="hidden" name="cbid.wireless.wlan10.isolate" value="1" />
      <select name="cbid.wireless.wlan00.hwmode">
        <option value="11bgnax" selected="selected">2.4GHz (802.11b+g+n+ax)</option>
      </select>
      <select name="cbid.wireless.wlan00.htbw">
        <option value="auto" selected="selected">Auto</option>
      </select>
      <select name="cbid.wireless.wlan00.channel">
        <option value="0" selected="selected">Auto</option>
        <option value="6">6 (2437 MHz)</option>
      </select>
      <select name="cbid.wireless.wlan00.txpower">
        <option value="100" selected="selected">Maximum</option>
      </select>
      <select name="cbid.wireless.wlan10.hwmode">
        <option value="11anacax" selected="selected">5GHz (802.11a+n+ac+ax)</option>
      </select>
      <select name="cbid.wireless.wlan10.htbw3">
        <option value="ht80" selected="selected">80 MHz</option>
      </select>
      <select name="cbid.wireless.wlan10.channel4">
        <option value="36" selected="selected">36 (5180 MHz)</option>
      </select>
      <select name="cbid.wireless.wlan10.txpower">
        <option value="20" selected="selected">Middle</option>
      </select>
    </form>
    """

    parsed = parser_settings.parse_wireless_settings(combo_html, combine_html, uncombine_html)

    assert parsed["smart_connect"]["value"] is False
    assert parsed["wifi_2g_enabled"]["value"] is True
    assert parsed["wifi_5g_enabled"]["value"] is False
    assert parsed["wifi_2g_hidden"]["value"] is True
    assert parsed["wifi_5g_hidden"]["value"] is False
    assert parsed["wifi_2g_isolate"]["value"] is False
    assert parsed["wifi_5g_isolate"]["value"] is True
    assert parsed["wifi_5g_channel_width"]["value"] == "ht80"
    assert parsed["wifi_5g_channel"]["value"] == "36"


def test_parse_vpn_and_auto_update_settings_extract_controls() -> None:
    """VPN and autoupdate pages should expose current switch/select values."""
    vpn_html = """
    <form>
      <input type="hidden" name="cbid.vpn.config.enabled" value="1" />
      <input type="hidden" name="cbid.vpn.config.s2s" value="1" />
      <select name="cbid.vpn.config._proto">
        <option value="pptp" selected="selected">PPTP Client</option>
      </select>
      <select name="cbid.vpn.config.filter">
        <option value="allow" selected="selected">Allow all devices</option>
      </select>
      <select name="cbid.vpn.config.access">
        <option value="wan" selected="selected">Internet</option>
      </select>
      <select name="cbid.vpn.config.policy">
        <option value="killswitch" selected="selected">VPN kill switch</option>
      </select>
    </form>
    """
    update_html = """
    <form>
      <input type="hidden" name="cbid.upgrade.1.auto_upgrade" value="1" />
      <select name="cbid.upgrade.1.upgrade_time">
        <option value="0">00:00 - 02:00</option>
        <option value="3" selected="selected">03:00 - 05:00</option>
      </select>
    </form>
    """

    vpn = parser_settings.parse_vpn_settings(vpn_html)
    autoupdate = parser_settings.parse_auto_update_settings(update_html)

    assert vpn["enabled"]["value"] is True
    assert vpn["site_to_site"]["value"] is True
    assert vpn["protocol"]["value"] == "pptp"
    assert vpn["default_rule"]["value"] == "allow"
    assert vpn["client_access"]["value"] == "wan"
    assert vpn["vpn_policy"]["value"] == "killswitch"
    assert autoupdate["auto_update"]["value"] is True
    assert autoupdate["update_time"]["value"] == "3"
