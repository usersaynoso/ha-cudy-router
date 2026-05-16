"""Static wiring checks for the added settings platforms."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = ROOT / "custom_components" / "cudy_router" / "__init__.py"
ROUTER_DATA_PATH = ROOT / "custom_components" / "cudy_router" / "router_data.py"
ROUTER_PATH = ROOT / "custom_components" / "cudy_router" / "router.py"
SELECT_PATH = ROOT / "custom_components" / "cudy_router" / "select.py"
SWITCH_PATH = ROOT / "custom_components" / "cudy_router" / "switch.py"
SENSOR_PATH = ROOT / "custom_components" / "cudy_router" / "sensor.py"
COORDINATOR_PATH = ROOT / "custom_components" / "cudy_router" / "coordinator.py"


def test_platform_registration_includes_selects() -> None:
    """The integration should register the new select platform."""
    source = INIT_PATH.read_text(encoding="utf-8")

    assert "Platform.SELECT" in source


def test_router_data_collects_configuration_modules() -> None:
    """Coordinator refreshes should include the new settings pages."""
    source = ROUTER_DATA_PATH.read_text(encoding="utf-8")

    assert '"admin/network/gcom/config/apn"' in source
    assert '"admin/network/wireless/config/combo"' in source
    assert '"admin/network/vpn/config"' in source
    assert '"admin/network/vpn/wireguard/status?detail="' in source
    assert '"admin/network/vpn/pptp/status?detail="' in source
    assert '"admin/network/vpn/status?detail="' in source
    assert '"admin/network/mwan3/status?detail="' in source
    assert '"admin/system/status/arp"' in source
    assert '"admin/system/autoupgrade"' in source
    assert '"admin/setup"' in source
    assert '"admin/network/wireless/wds/status"' in source
    assert '"admin/network/wireless/wds/data"' in source
    assert '"admin/network/wireless/wds/config/nomodal/wisp"' in source
    assert "existing_feature(device_model, MODULE_WIRELESS_SETTINGS)" in source
    assert "existing_feature(device_model, MODULE_AUTO_UPDATE_SETTINGS)" in source


def test_router_client_exposes_setting_mutators() -> None:
    """Router API should provide mutators for the new entity types."""
    source = ROUTER_PATH.read_text(encoding="utf-8")

    for method_name in (
        "set_cellular_setting",
        "set_wireless_setting",
        "set_smart_connect",
        "set_vpn_setting",
        "set_auto_update_setting",
        "set_wisp_setting",
        "set_device_access",
    ):
        assert f"def {method_name}" in source
    assert '"cbi.toggle"' in source
    assert "cbid.table" in source
    assert "_find_state_form_field_name_by_suffix" in source
    assert '"admin/network/wireless/wds/config/nomodal/wisp"' in source
    assert '"admin/setup"' in source
    assert '"auto_upgrade"' in source


def test_switch_and_select_platforms_cover_router_settings() -> None:
    """Router setting switches and selects should be defined in their platforms."""
    switch_source = SWITCH_PATH.read_text(encoding="utf-8")
    select_source = SELECT_PATH.read_text(encoding="utf-8")

    assert "ROUTER_SETTING_SWITCHES" in switch_source
    assert "CudyClientFeatureSwitch" in switch_source
    assert '"site_to_site"' in switch_source
    assert '("vpn", "VPN", "mdi:vpn")' in switch_source
    assert "module_available(device_model, MODULE_MESH, coordinator.data)" in switch_source
    assert 'mesh_data.get("main_router_led_status") is not None' in switch_source
    assert 'entity_registry.async_get_entity_id("switch", DOMAIN, unique_id)' in switch_source
    assert "entity_registry.async_remove(entity_id)" in switch_source
    assert "_remove_router_setting_entity" in switch_source
    assert "MODULE_WISP" in switch_source
    assert '"WISP enabled"' in switch_source
    assert "ROUTER_SELECTS" in select_source
    assert "CudyRouterSettingSelect" in select_source
    assert '"network_search"' in select_source
    assert '"apn_profile"' in select_source
    assert 'async_get_entity_registry' in select_source
    assert 'entity_registry.async_get_entity_id("select", DOMAIN, unique_id)' in select_source
    assert "entity_registry.async_remove(entity_id)" in select_source


def test_router_vpn_entities_include_r700_status_fields() -> None:
    """VPN entity wiring should cover the R700 PPTP status page fields."""
    router_data_source = ROUTER_DATA_PATH.read_text(encoding="utf-8")
    switch_source = SWITCH_PATH.read_text(encoding="utf-8")
    sensor_descriptions_source = (ROOT / "custom_components" / "cudy_router" / "sensor_descriptions.py").read_text(
        encoding="utf-8"
    )

    assert '"admin/network/vpn/wireguard/status?detail="' in router_data_source
    assert '"admin/network/vpn/openvpns/status?status="' in router_data_source
    assert '"admin/network/vpn/pptp/status?detail="' in router_data_source
    assert '"admin/network/vpn/status?detail="' in router_data_source
    assert '"tunnel_ip"' in router_data_source
    assert '"VPN tunnel IP"' in sensor_descriptions_source
    assert '("vpn", "VPN", "mdi:vpn")' in switch_source


def test_router_load_balancing_entities_include_r700_status_fields() -> None:
    """Load-balancing entity wiring should cover the R700 dashboard status page."""
    router_data_source = ROUTER_DATA_PATH.read_text(encoding="utf-8")
    parser_network_source = (ROOT / "custom_components" / "cudy_router" / "parser_network.py").read_text(
        encoding="utf-8"
    )
    sensor_descriptions_source = (ROOT / "custom_components" / "cudy_router" / "sensor_descriptions.py").read_text(
        encoding="utf-8"
    )

    assert '"admin/network/mwan3/status?detail="' in router_data_source
    assert "range(1, 5)" in parser_network_source
    assert "_LOAD_BALANCING_INTERFACE_RE" in parser_network_source
    assert '"Load balancing WAN1"' in sensor_descriptions_source
    assert '"Load balancing WAN2"' in sensor_descriptions_source
    assert '"Load balancing WAN3"' in sensor_descriptions_source
    assert '"Load balancing WAN4"' in sensor_descriptions_source


def test_router_device_and_interface_stats_include_r700_specific_sensors() -> None:
    """R700-specific ARP and byte counters should be wired into the integration."""
    router_data_source = ROUTER_DATA_PATH.read_text(encoding="utf-8")
    sensor_descriptions_source = (ROOT / "custom_components" / "cudy_router" / "sensor_descriptions.py").read_text(
        encoding="utf-8"
    )
    parser_network_source = (ROOT / "custom_components" / "cudy_router" / "parser_network.py").read_text(
        encoding="utf-8"
    )

    assert '"admin/system/status/arp"' in router_data_source
    assert '"admin/network/lan/status?detail=1"' in router_data_source
    assert '"admin/network/wan/status?detail=1&iface={iface_name}"' in router_data_source
    assert '"wanb"' in router_data_source
    assert '"wanc"' in router_data_source
    assert "interface.replace('-', '_')" in parser_network_source
    assert '"bytes_received"' in parser_network_source
    assert '"LAN ARP entries"' in sensor_descriptions_source
    assert '"WAN bytes received"' in sensor_descriptions_source
    assert 'name_suffix="Bytes received"' in sensor_descriptions_source


def test_sensor_platform_adds_connected_client_and_mesh_detail_sensors() -> None:
    """Sensors should expose the new live client and mesh metadata fields."""
    source = SENSOR_PATH.read_text(encoding="utf-8")

    assert "CudyRouterConnectedDeviceSensor" in source
    assert "DEVICE_IP_SENSOR" in source
    assert "DEVICE_CONNECTION_TYPE_SENSOR" in source
    assert "DEVICE_SIGNAL_DETAILS_SENSOR" in source
    assert "DEVICE_ONLINE_TIME_SENSOR" in source
    assert "MESH_DEVICE_HARDWARE_SENSOR" in source
    assert "MESH_DEVICE_BACKHAUL_SENSOR" in source


def test_coordinator_timeout_covers_expanded_refresh_surface() -> None:
    """The coordinator timeout should allow the expanded page set to refresh."""
    source = COORDINATOR_PATH.read_text(encoding="utf-8")

    assert "REQUEST_TIMEOUT = 90" in source
