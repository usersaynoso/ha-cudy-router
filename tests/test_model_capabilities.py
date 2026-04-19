"""Tests for the emulator-backed model capability mapping."""

from __future__ import annotations

from tests.module_loader import load_cudy_module


const = load_cudy_module("const")
load_cudy_module("model_names")
features = load_cudy_module("features")


def test_router_capabilities_hide_cellular_modules_on_non_cellular_models() -> None:
    """Standard routers should not expose modem-only module families."""
    assert features.existing_feature("WR6500 V1.0", const.MODULE_MODEM) is False
    assert features.existing_feature("WR6500 V1.0", const.MODULE_CELLULAR_SETTINGS) is False
    assert features.existing_feature("WR6500 V1.0", const.MODULE_SMS) is False
    assert features.existing_feature("WR6500 V1.0", const.MODULE_AUTO_UPDATE_SETTINGS) is True


def test_cellular_capabilities_cover_modem_and_settings_pages() -> None:
    """4G/5G models should keep the modem and APN-related modules enabled."""
    assert features.existing_feature("LT700E V1.0", const.MODULE_MODEM) is True
    assert features.existing_feature("LT700E V1.0", const.MODULE_CELLULAR_SETTINGS) is True
    assert features.existing_feature("LT700E V1.0", const.MODULE_MESH) is True
    assert features.existing_feature("LT700E V1.0", const.MODULE_SMS) is True


def test_sms_capability_list_matches_supported_router_models() -> None:
    """Only the explicit SMS-capable router list should report model-mapped SMS support."""
    for model in (
        "P4 V1.0",
        "P5 V1.0",
        "P2 V1.0",
        "LT15E V1.0",
        "LT700E V1.0",
        "LT500 V1.0",
        "LT400E V1.0",
        "LT300V3",
        "LT700-Outdoor V1.0",
        "LT400-Outdoor V1.0",
        "IR02 V1.0",
    ):
        assert features.known_feature(model, const.MODULE_SMS) is True

    assert features.known_feature("WR6500 V1.0", const.MODULE_SMS) is False
    assert features.existing_feature("WR6500 V1.0", const.MODULE_SMS) is False


def test_mesh_wifi_models_keep_mesh_capabilities_without_sms() -> None:
    """Mesh Wi-Fi models should expose mesh features without inheriting SMS support."""
    for model in ("M11000", "M3000", "M1500", "M1200"):
        assert features.existing_feature(model, const.MODULE_MESH) is True
        assert features.existing_feature(model, const.MODULE_SMS) is False


def test_extender_capabilities_hide_router_only_families() -> None:
    """Extenders should not create WAN, DHCP, VPN, or mesh entities."""
    assert features.existing_feature("RE1500 V1.0", const.MODULE_WAN) is False
    assert features.existing_feature("RE1500 V1.0", const.MODULE_DHCP) is False
    assert features.existing_feature("RE1500 V1.0", const.MODULE_VPN_SETTINGS) is False
    assert features.existing_feature("RE1500 V1.0", const.MODULE_MESH) is False
    assert features.existing_feature("RE1500 V1.0", const.MODULE_WIRELESS_SETTINGS) is True


def test_known_legacy_models_disable_auto_update_when_emulator_lacks_it() -> None:
    """Older firmware variants without an auto-upgrade page should keep it hidden."""
    assert features.existing_feature("WR1300E V1.0", const.MODULE_AUTO_UPDATE_SETTINGS) is False
    assert features.existing_feature("LT400-Outdoor V1.0", const.MODULE_AUTO_UPDATE_SETTINGS) is False


def test_r700_emulator_does_not_expose_mesh_only_features() -> None:
    """R700 should not inherit mesh/LED support from the permissive unknown-model profile."""
    assert features.existing_feature("R700 V1.0", const.MODULE_MESH) is False
    assert features.existing_feature("R700", const.MODULE_WAN) is True
    assert features.existing_feature("R700", const.MODULE_DHCP) is True
    assert features.existing_feature("R700", const.MODULE_LOAD_BALANCING) is True
    assert features.existing_feature("R700", const.MODULE_AUTO_UPDATE_SETTINGS) is True
    assert features.existing_feature("R700", const.MODULE_VPN) is True
    assert features.existing_feature("R700", const.MODULE_VPN_SETTINGS) is True
    assert features.existing_feature("R700", const.MODULE_WIFI_2G) is False
    assert features.existing_feature("R700", const.MODULE_WIFI_5G) is False
    assert features.existing_feature("R700", const.MODULE_WIRELESS_SETTINGS) is False


def test_r700_variants_keep_the_r700_feature_profile() -> None:
    """Regional or marketing suffixes should not fall back to the default profile."""
    assert features.existing_feature("R700-UK", const.MODULE_LOAD_BALANCING) is True
    assert features.existing_feature("R700-UK", const.MODULE_AUTO_UPDATE_SETTINGS) is True
    assert features.existing_feature("R700 AX3000", const.MODULE_LOAD_BALANCING) is True
    assert features.existing_feature("R700 AX3000", const.MODULE_AUTO_UPDATE_SETTINGS) is True


def test_unknown_models_keep_best_effort_default_profile() -> None:
    """Unknown models should still fall back to the permissive compatibility profile."""
    assert features.existing_feature("Some Future Model V1.0", const.MODULE_MODEM) is True
    assert features.existing_feature("Some Future Model V1.0", const.MODULE_WIRELESS_SETTINGS) is True
