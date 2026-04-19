"""Model capability mapping for the Cudy router integration."""

from __future__ import annotations

from typing import Final

from .const import (
    MODULE_AUTO_UPDATE_SETTINGS,
    MODULE_CELLULAR_SETTINGS,
    MODULE_DATA_USAGE,
    MODULE_DEVICES,
    MODULE_DHCP,
    MODULE_LAN,
    MODULE_LOAD_BALANCING,
    MODULE_MESH,
    MODULE_MODEM,
    MODULE_SMS,
    MODULE_SYSTEM,
    MODULE_VPN,
    MODULE_VPN_SETTINGS,
    MODULE_WAN,
    MODULE_WIRELESS_SETTINGS,
    MODULE_WIFI_2G,
    MODULE_WIFI_5G,
)
from .model_names import iter_model_name_candidates

FeatureSet = frozenset[str]


ROUTER_BASE_FEATURES: Final[FeatureSet] = frozenset(
    {
        MODULE_DEVICES,
        MODULE_SYSTEM,
        MODULE_WIFI_2G,
        MODULE_WIFI_5G,
        MODULE_LAN,
        MODULE_VPN,
        MODULE_VPN_SETTINGS,
        MODULE_WAN,
        MODULE_DHCP,
        MODULE_WIRELESS_SETTINGS,
    }
)
WIRED_ROUTER_BASE_FEATURES: Final[FeatureSet] = (
    ROUTER_BASE_FEATURES
    - frozenset(
        {
            MODULE_WIFI_2G,
            MODULE_WIFI_5G,
            MODULE_WIRELESS_SETTINGS,
        }
    )
)
WIRED_MULTI_WAN_ROUTER_FEATURES: Final[FeatureSet] = (
    WIRED_ROUTER_BASE_FEATURES | frozenset({MODULE_LOAD_BALANCING})
)
WIRED_MULTI_WAN_ROUTER_AUTO_UPDATE_FEATURES: Final[FeatureSet] = (
    WIRED_MULTI_WAN_ROUTER_FEATURES | frozenset({MODULE_AUTO_UPDATE_SETTINGS})
)
ROUTER_AUTO_UPDATE_FEATURES: Final[FeatureSet] = (
    ROUTER_BASE_FEATURES | frozenset({MODULE_AUTO_UPDATE_SETTINGS})
)
ROUTER_MESH_FEATURES: Final[FeatureSet] = (
    ROUTER_AUTO_UPDATE_FEATURES | frozenset({MODULE_MESH})
)
ROUTER_LEGACY_MESH_FEATURES: Final[FeatureSet] = (
    ROUTER_BASE_FEATURES | frozenset({MODULE_MESH})
)

CELLULAR_LEGACY_FEATURES: Final[FeatureSet] = (
    ROUTER_BASE_FEATURES
    | frozenset(
        {
            MODULE_MODEM,
            MODULE_DATA_USAGE,
            MODULE_CELLULAR_SETTINGS,
        }
    )
)
CELLULAR_LEGACY_AUTO_UPDATE_FEATURES: Final[FeatureSet] = (
    CELLULAR_LEGACY_FEATURES | frozenset({MODULE_AUTO_UPDATE_SETTINGS})
)
CELLULAR_MESH_FEATURES: Final[FeatureSet] = (
    CELLULAR_LEGACY_AUTO_UPDATE_FEATURES | frozenset({MODULE_MESH})
)
CELLULAR_SMS_MESH_FEATURES: Final[FeatureSet] = (
    CELLULAR_MESH_FEATURES | frozenset({MODULE_SMS})
)

EXTENDER_BASE_FEATURES: Final[FeatureSet] = frozenset(
    {
        MODULE_DEVICES,
        MODULE_SYSTEM,
        MODULE_WIFI_2G,
        MODULE_WIFI_5G,
        MODULE_LAN,
        MODULE_WIRELESS_SETTINGS,
    }
)
EXTENDER_AUTO_UPDATE_FEATURES: Final[FeatureSet] = (
    EXTENDER_BASE_FEATURES | frozenset({MODULE_AUTO_UPDATE_SETTINGS})
)

# The emulator-backed device list provided for this integration maps cleanly onto
# a small set of firmware capability profiles. Unknown models still fall back to
# a permissive profile so existing user setups do not lose entities.
MODEL_FEATURES: Final[dict[str, FeatureSet]] = {
    "default": CELLULAR_SMS_MESH_FEATURES,
    "P5": CELLULAR_SMS_MESH_FEATURES,
    "P2": CELLULAR_MESH_FEATURES,
    "WR11000": ROUTER_MESH_FEATURES,
    "WR6500": ROUTER_AUTO_UPDATE_FEATURES,
    "WR3600H": ROUTER_AUTO_UPDATE_FEATURES,
    "TR3000": ROUTER_MESH_FEATURES,
    "WR3000E": ROUTER_MESH_FEATURES,
    "WR3000": ROUTER_MESH_FEATURES,
    "WR1500": ROUTER_MESH_FEATURES,
    "WR1300V4.0": ROUTER_MESH_FEATURES,
    "WR1300E": ROUTER_BASE_FEATURES,
    "WR1300EV2": ROUTER_BASE_FEATURES,
    "TR1200": ROUTER_MESH_FEATURES,
    "WR1200": ROUTER_BASE_FEATURES,
    "WR300S": ROUTER_LEGACY_MESH_FEATURES,
    "R700": WIRED_MULTI_WAN_ROUTER_AUTO_UPDATE_FEATURES,
    "LT15E": CELLULAR_MESH_FEATURES,
    "LT700E": CELLULAR_MESH_FEATURES,
    "LT500": CELLULAR_SMS_MESH_FEATURES,
    "LT400E": CELLULAR_LEGACY_FEATURES,
    "LT300V3": CELLULAR_LEGACY_AUTO_UPDATE_FEATURES,
    "LT700-Outdoor": CELLULAR_MESH_FEATURES,
    "LT400-Outdoor": CELLULAR_LEGACY_FEATURES,
    "IR02": CELLULAR_MESH_FEATURES,
    "M11000": ROUTER_MESH_FEATURES,
    "M3000": ROUTER_MESH_FEATURES,
    "M1500": ROUTER_MESH_FEATURES,
    "M1200": ROUTER_MESH_FEATURES,
    "RE3600": EXTENDER_AUTO_UPDATE_FEATURES,
    "RE1500": EXTENDER_AUTO_UPDATE_FEATURES,
    "RE1200": EXTENDER_AUTO_UPDATE_FEATURES,
    "RE1200-Outdoor": EXTENDER_BASE_FEATURES,
}


def model_feature_set(device_model: str | None) -> FeatureSet:
    """Return the supported feature set for a model."""
    return _matched_model_feature_set(device_model)[0]


def _matched_model_feature_set(device_model: str | None) -> tuple[FeatureSet, bool]:
    """Return the feature set and whether it came from a known non-default model."""
    for candidate in iter_model_name_candidates(device_model):
        if candidate in MODEL_FEATURES:
            return MODEL_FEATURES[candidate], candidate != "default"
    return MODEL_FEATURES["default"], False


def known_feature(device_model: str | None, key_entity: str) -> bool:
    """Check if a feature is supported by an explicitly mapped model."""
    feature_set, matched_known_model = _matched_model_feature_set(device_model)
    return matched_known_model and key_entity in feature_set


def existing_feature(device_model: str, key_entity: str, model_entity: str = "") -> bool:
    """Check if a feature is supported for a specific device model."""
    del model_entity
    return key_entity in model_feature_set(device_model)
