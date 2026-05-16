"""Model capability mapping for the Cudy router integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

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
    MODULE_WAN_INTERFACES,
    MODULE_WIRELESS_SETTINGS,
    MODULE_WISP,
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
    WIRED_ROUTER_BASE_FEATURES | frozenset({MODULE_LOAD_BALANCING, MODULE_WAN_INTERFACES})
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
CELLULAR_LEGACY_SMS_FEATURES: Final[FeatureSet] = (
    CELLULAR_LEGACY_FEATURES | frozenset({MODULE_SMS})
)
CELLULAR_LEGACY_SMS_AUTO_UPDATE_FEATURES: Final[FeatureSet] = (
    CELLULAR_LEGACY_AUTO_UPDATE_FEATURES | frozenset({MODULE_SMS})
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
WISP_FEATURES: Final[FeatureSet] = frozenset({MODULE_WISP})

# The emulator-backed device list provided for this integration maps cleanly onto
# a small set of firmware capability profiles. Unknown models still fall back to
# a permissive profile so existing user setups do not lose entities.
MODEL_FEATURES: Final[dict[str, FeatureSet]] = {
    "default": CELLULAR_SMS_MESH_FEATURES,
    "P5": CELLULAR_SMS_MESH_FEATURES,
    "P4": CELLULAR_SMS_MESH_FEATURES,
    "P2": CELLULAR_SMS_MESH_FEATURES | WISP_FEATURES,
    "WR11000": ROUTER_MESH_FEATURES,
    "WR6500": ROUTER_AUTO_UPDATE_FEATURES,
    "WR3600H": ROUTER_AUTO_UPDATE_FEATURES,
    "TR3000": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "TR1200": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "WR3000E": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "WR3000EV2": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "WR3000": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "WR3000V2": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "WR3000S": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "WR3000P": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "WR1500": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "WR1300": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "WR1300V4.0": ROUTER_MESH_FEATURES,
    "WR1300E": ROUTER_BASE_FEATURES | WISP_FEATURES,
    "WR1300EV2": ROUTER_BASE_FEATURES | WISP_FEATURES,
    "WR1300S": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "WR1200": ROUTER_BASE_FEATURES | WISP_FEATURES,
    "WR1200E": ROUTER_BASE_FEATURES | WISP_FEATURES,
    "WR300": ROUTER_LEGACY_MESH_FEATURES | WISP_FEATURES,
    "WR300S": ROUTER_LEGACY_MESH_FEATURES | WISP_FEATURES,
    "R700": WIRED_MULTI_WAN_ROUTER_AUTO_UPDATE_FEATURES,
    "LT15E": CELLULAR_SMS_MESH_FEATURES | WISP_FEATURES,
    "LT18": CELLULAR_SMS_MESH_FEATURES | WISP_FEATURES,
    "LT700E": CELLULAR_SMS_MESH_FEATURES | WISP_FEATURES,
    "LT700V": CELLULAR_SMS_MESH_FEATURES | WISP_FEATURES,
    "LT500": CELLULAR_SMS_MESH_FEATURES | WISP_FEATURES,
    "LT500E": CELLULAR_SMS_MESH_FEATURES | WISP_FEATURES,
    "LT500-Outdoor": CELLULAR_SMS_MESH_FEATURES | WISP_FEATURES,
    "LT400": CELLULAR_LEGACY_SMS_FEATURES | WISP_FEATURES,
    "LT400E": CELLULAR_LEGACY_SMS_FEATURES | WISP_FEATURES,
    "LT400V": CELLULAR_LEGACY_SMS_FEATURES | WISP_FEATURES,
    "LT300": CELLULAR_LEGACY_SMS_AUTO_UPDATE_FEATURES | WISP_FEATURES,
    "LT300V2": CELLULAR_LEGACY_SMS_AUTO_UPDATE_FEATURES | WISP_FEATURES,
    "LT300V3": CELLULAR_LEGACY_SMS_AUTO_UPDATE_FEATURES | WISP_FEATURES,
    "LT700-Outdoor": CELLULAR_SMS_MESH_FEATURES | WISP_FEATURES,
    "LT400-Outdoor": CELLULAR_LEGACY_SMS_FEATURES | WISP_FEATURES,
    "IR02": CELLULAR_SMS_MESH_FEATURES | WISP_FEATURES,
    "IR04": CELLULAR_SMS_MESH_FEATURES | WISP_FEATURES,
    "M11000": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "M3000": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "M3000S": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "M1800": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "M1500": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "M1300": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "M1200": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "X6": ROUTER_MESH_FEATURES | WISP_FEATURES,
    "RE3600": EXTENDER_AUTO_UPDATE_FEATURES | WISP_FEATURES,
    "RE3000": EXTENDER_AUTO_UPDATE_FEATURES | WISP_FEATURES,
    "RE1800": EXTENDER_AUTO_UPDATE_FEATURES | WISP_FEATURES,
    "RE1500": EXTENDER_AUTO_UPDATE_FEATURES | WISP_FEATURES,
    "RE1200": EXTENDER_AUTO_UPDATE_FEATURES | WISP_FEATURES,
    "RE1200-Outdoor": EXTENDER_BASE_FEATURES | WISP_FEATURES,
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


def supports_sms_feature(
    device_model: str | None,
    data: dict[str, Any] | None = None,
) -> bool:
    """Return whether SMS is supported by model mapping or detected runtime data."""
    return known_feature(device_model, MODULE_SMS) or (
        isinstance(data, dict) and MODULE_SMS in data
    )


def has_live_module_data(module_data: Any) -> bool:
    """Return whether parsed module data contains a real non-empty value."""
    if isinstance(module_data, Mapping):
        for value in module_data.values():
            if has_live_module_data(value):
                return True
        return False
    if isinstance(module_data, list | tuple | set):
        return any(has_live_module_data(value) for value in module_data)
    return module_data not in (None, "")


def module_available(
    device_model: str | None,
    module: str,
    data: dict[str, Any] | None = None,
) -> bool:
    """Return whether a module is supported by model mapping or live parsed data."""
    if existing_feature(device_model or "default", module):
        return True
    if not isinstance(data, dict) or module not in data:
        return False
    return has_live_module_data(data.get(module))


def existing_feature(device_model: str, key_entity: str, model_entity: str = "") -> bool:
    """Check if a feature is supported for a specific device model."""
    del model_entity
    return key_entity in model_feature_set(device_model)
