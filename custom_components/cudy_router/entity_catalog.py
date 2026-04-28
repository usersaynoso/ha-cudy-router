"""Entity catalog helpers for Cudy Router diagnostics."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from homeassistant.const import CONF_MODEL

from .const import (
    DOMAIN,
    MODULE_DEVICES,
    MODULE_MESH,
    MODULE_MODEM,
    MODULE_WAN,
    MODULE_WAN_INTERFACES,
    OPTIONS_AUTO_ADD_CONNECTED_DEVICES,
    OPTIONS_AUTO_ADD_DEVICE_TRACKERS,
    OPTIONS_DEVICELIST,
    OPTIONS_TRACKED_DEVICE_MACS,
    SECTION_DEVICE_LIST,
)
from .device_info import known_client_devices, known_tracker_clients
from .device_tracking import (
    build_client_seed_device,
    build_tracker_seed_device,
    configured_tracked_macs,
    connected_device_lookup,
    format_mac,
    manual_allowed_client_macs,
    normalize_mac,
    tracker_allowed_macs,
)
from .features import existing_feature, module_available
from .select import ROUTER_SELECTS
from .sensor_descriptions import (
    DEVICE_CONNECTION_TYPE_SENSOR,
    DEVICE_IP_SENSOR,
    DEVICE_ONLINE_TIME_SENSOR,
    DEVICE_SIGNAL_DETAILS_SENSOR,
    MESH_DEVICE_BACKHAUL_SENSOR,
    MESH_DEVICE_CONNECTED_SENSOR,
    MESH_DEVICE_FIRMWARE_SENSOR,
    MESH_DEVICE_HARDWARE_SENSOR,
    MESH_DEVICE_IP_SENSOR,
    MESH_DEVICE_MAC_SENSOR,
    MESH_DEVICE_MODEL_SENSOR,
    MESH_DEVICE_NAME_SENSOR,
    MESH_DEVICE_STATUS_SENSOR,
    NETWORK_SENSOR,
    SENSOR_TYPES,
    SIGNAL_SENSOR,
    WAN_INTERFACE_SENSOR_TYPES,
    CudyRouterSensorEntityDescription,
)
from .switch import ROUTER_SETTING_SWITCHES

ValueTransform = Callable[[str, Any], Any]

_WAN_DUPLICATE_MODEM_KEYS = {
    "connected_time",
    "public_ip",
    "session_upload",
    "session_download",
    "wan_ip",
}
_WAN_REMOVED_SENSOR_KEYS = {"mac_address"}
_CLIENT_SENSOR_DESCRIPTIONS = (
    DEVICE_IP_SENSOR,
    DEVICE_CONNECTION_TYPE_SENSOR,
    DEVICE_SIGNAL_DETAILS_SENSOR,
    DEVICE_ONLINE_TIME_SENSOR,
)
_MESH_SENSOR_DESCRIPTIONS = (
    MESH_DEVICE_NAME_SENSOR,
    MESH_DEVICE_MODEL_SENSOR,
    MESH_DEVICE_MAC_SENSOR,
    MESH_DEVICE_FIRMWARE_SENSOR,
    MESH_DEVICE_STATUS_SENSOR,
    MESH_DEVICE_IP_SENSOR,
    MESH_DEVICE_CONNECTED_SENSOR,
    MESH_DEVICE_HARDWARE_SENSOR,
    MESH_DEVICE_BACKHAUL_SENSOR,
)
_CLIENT_SWITCH_FEATURES = (
    ("internet", "Internet access"),
    ("dnsfilter", "DNS filter"),
    ("vpn", "VPN"),
)


def _identity_value(_key: str, value: Any) -> Any:
    """Return an unmodified value."""
    return value


def _registry_entries(hass: Any, config_entry: Any) -> list[Any]:
    """Return entity registry entries belonging to this config entry."""
    try:
        from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
    except ImportError:
        return []

    entity_registry = async_get_entity_registry(hass)
    entities = getattr(entity_registry, "entities", {})
    config_entry_id = getattr(config_entry, "entry_id", None)
    entry_prefix = f"{config_entry_id}-" if config_entry_id else ""
    entries: list[Any] = []
    for entity_entry in list(entities.values()):
        unique_id = getattr(entity_entry, "unique_id", "") or ""
        platform = getattr(entity_entry, "platform", None)
        entity_config_entry_id = getattr(entity_entry, "config_entry_id", None)
        if (
            entity_config_entry_id != config_entry_id
            and platform != DOMAIN
            and not str(unique_id).startswith(entry_prefix)
        ):
            continue
        entries.append(entity_entry)
    return entries


def _registry_index(hass: Any, config_entry: Any) -> dict[str, dict[str, Any]]:
    """Return redaction-ready registry metadata keyed by unique ID."""
    entries: dict[str, dict[str, Any]] = {}
    for entity_entry in _registry_entries(hass, config_entry):
        unique_id = str(getattr(entity_entry, "unique_id", "") or "")
        if not unique_id:
            continue
        entries[unique_id] = {
            "entity_id": getattr(entity_entry, "entity_id", None),
            "domain": getattr(entity_entry, "domain", None),
            "platform": getattr(entity_entry, "platform", None),
            "unique_id": unique_id,
            "disabled_by": str(getattr(entity_entry, "disabled_by", None))
            if getattr(entity_entry, "disabled_by", None) is not None
            else None,
            "entity_category": str(getattr(entity_entry, "entity_category", None))
            if getattr(entity_entry, "entity_category", None) is not None
            else None,
        }
    return entries


def _value_present(value: Any) -> bool:
    """Return whether an entity state value is meaningful."""
    return value not in (None, "")


def _entry_value(module_data: Mapping[str, Any], key: str) -> Any:
    """Return the nested Home Assistant state value for a coordinator entry."""
    entry = module_data.get(key)
    if isinstance(entry, Mapping):
        return entry.get("value")
    return None


def _status_for_data(
    *,
    device_model: str,
    module: str,
    key: str | None,
    data: dict[str, Any],
    value: Any = None,
    value_known: bool = False,
) -> tuple[str, str | None]:
    """Return catalog status and blocked reason for a module/key."""
    if not module_available(device_model, module, data):
        return "blocked", "unsupported_model"

    module_data = data.get(module)
    if not isinstance(module_data, Mapping):
        return "blocked", "missing_page"

    if key is None:
        return "available", None

    if key not in module_data:
        return "blocked", "missing_value"

    candidate_value = value if value_known else _entry_value(module_data, key)
    if not _value_present(candidate_value):
        return "blocked", "empty_value"

    return "available", None


def _candidate(
    *,
    registry: dict[str, dict[str, Any]],
    seen_unique_ids: set[str],
    domain: str,
    unique_id: str | None,
    platform: str,
    name: str,
    module: str | None = None,
    key: str | None = None,
    device_scope: str = "router",
    source: str = "definition",
    status: str = "available",
    reason: str | None = None,
    sample_value: Any = None,
) -> dict[str, Any]:
    """Build a normalized entity catalog row."""
    registry_entry = registry.get(unique_id or "")
    if unique_id:
        seen_unique_ids.add(unique_id)
    if registry_entry is not None and status != "blocked":
        status = "created"

    entry = {
        "domain": domain,
        "platform": platform,
        "unique_id": unique_id,
        "entity_id": registry_entry.get("entity_id") if registry_entry else None,
        "name": name,
        "module": module,
        "key": key,
        "device_scope": device_scope,
        "source": source,
        "status": status,
        "reason": reason,
        "created": registry_entry is not None,
    }
    if sample_value is not None:
        entry["sample_value"] = sample_value
    if registry_entry:
        entry["disabled_by"] = registry_entry.get("disabled_by")
        entry["entity_category"] = registry_entry.get("entity_category")
    return entry


def _module_data(data: dict[str, Any], module: str) -> Mapping[str, Any]:
    """Return module data as a mapping."""
    module_data = data.get(module, {})
    return module_data if isinstance(module_data, Mapping) else {}


def _router_sensor_candidates(
    *,
    config_entry: Any,
    device_model: str,
    data: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    seen_unique_ids: set[str],
    transform_value: ValueTransform,
) -> list[dict[str, Any]]:
    """Return router-level sensor catalog entries."""
    candidates: list[dict[str, Any]] = []
    descriptions: list[CudyRouterSensorEntityDescription] = list(SENSOR_TYPES.values())
    descriptions.extend([SIGNAL_SENSOR, NETWORK_SENSOR])
    entry_id = getattr(config_entry, "entry_id", "")

    for description in descriptions:
        module = description.module
        key = description.key
        module_data = _module_data(data, module)
        value = _entry_value(module_data, key)
        if module == MODULE_WAN and (
            key in _WAN_REMOVED_SENSOR_KEYS
            or (key in _WAN_DUPLICATE_MODEM_KEYS and MODULE_MODEM in data)
        ):
            status, reason = "blocked", "superseded"
        else:
            status, reason = _status_for_data(
                device_model=device_model,
                module=module,
                key=key,
                data=data,
                value=value,
                value_known=True,
            )

        candidates.append(
            _candidate(
                registry=registry,
                seen_unique_ids=seen_unique_ids,
                domain="sensor",
                platform=DOMAIN,
                unique_id=f"{entry_id}-{module}-{key}",
                name=description.name_suffix,
                module=module,
                key=key,
                source="coordinator_data" if status != "blocked" else "definition",
                status=status,
                reason=reason,
                sample_value=transform_value(key, value) if _value_present(value) else None,
            )
        )

    return candidates


def _wan_interface_candidates(
    *,
    config_entry: Any,
    device_model: str,
    data: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    seen_unique_ids: set[str],
    transform_value: ValueTransform,
) -> list[dict[str, Any]]:
    """Return per-WAN interface sensor catalog entries."""
    entry_id = getattr(config_entry, "entry_id", "")
    wan_interfaces = _module_data(data, MODULE_WAN_INTERFACES)
    if not wan_interfaces:
        status, reason = _status_for_data(
            device_model=device_model,
            module=MODULE_WAN_INTERFACES,
            key=None,
            data=data,
        )
        if status == "blocked":
            return [
                _candidate(
                    registry=registry,
                    seen_unique_ids=seen_unique_ids,
                    domain="sensor",
                    platform=DOMAIN,
                    unique_id=None,
                    name="WAN interface sensors",
                    module=MODULE_WAN_INTERFACES,
                    device_scope="router",
                    status=status,
                    reason=reason,
                )
            ]
        return []

    candidates: list[dict[str, Any]] = []
    for interface_key, interface_data in sorted(wan_interfaces.items()):
        if not isinstance(interface_key, str) or not isinstance(interface_data, Mapping):
            continue
        for description in WAN_INTERFACE_SENSOR_TYPES:
            value = _entry_value(interface_data, description.key)
            status = "available" if _value_present(value) else "blocked"
            reason = None if status == "available" else "empty_value"
            candidates.append(
                _candidate(
                    registry=registry,
                    seen_unique_ids=seen_unique_ids,
                    domain="sensor",
                    platform=DOMAIN,
                    unique_id=f"{entry_id}-{MODULE_WAN_INTERFACES}-{interface_key}-{description.key}",
                    name=f"{interface_key.upper()} {description.name_suffix}",
                    module=MODULE_WAN_INTERFACES,
                    key=description.key,
                    device_scope="router",
                    source="coordinator_data",
                    status=status,
                    reason=reason,
                    sample_value=transform_value(description.key, value)
                    if _value_present(value)
                    else None,
                )
            )
    return candidates


def _connected_devices(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return parsed connected client devices."""
    devices = _module_data(data, MODULE_DEVICES).get(SECTION_DEVICE_LIST, [])
    return [device for device in devices if isinstance(device, dict)]


def _allowed_client_macs(
    hass: Any,
    config_entry: Any,
    data: dict[str, Any],
) -> tuple[set[str], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Return allowed client MACs and lookup helpers."""
    connected_devices = _connected_devices(data)
    connected_devices_by_mac = connected_device_lookup(connected_devices)
    options = getattr(config_entry, "options", {}) or {}
    if options.get(OPTIONS_AUTO_ADD_CONNECTED_DEVICES, True):
        allowed_client_macs = set(connected_devices_by_mac)
    else:
        allowed_client_macs = manual_allowed_client_macs(
            connected_devices=connected_devices,
            device_list=options.get(OPTIONS_DEVICELIST),
            known_clients=known_client_devices(hass, config_entry),
        )
    return allowed_client_macs, connected_devices_by_mac, connected_devices


def _client_sensor_candidates(
    *,
    hass: Any,
    config_entry: Any,
    data: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    seen_unique_ids: set[str],
    transform_value: ValueTransform,
) -> list[dict[str, Any]]:
    """Return connected-client sensor catalog entries."""
    entry_id = getattr(config_entry, "entry_id", "")
    options = getattr(config_entry, "options", {}) or {}
    auto_add_connected_devices = options.get(OPTIONS_AUTO_ADD_CONNECTED_DEVICES, True)
    allowed_client_macs, connected_devices_by_mac, connected_devices = _allowed_client_macs(
        hass,
        config_entry,
        data,
    )
    known_clients = known_client_devices(hass, config_entry)
    candidates: list[dict[str, Any]] = []

    blocked_macs = set(connected_device_lookup(connected_devices)) - allowed_client_macs
    for normalized_mac in sorted(blocked_macs):
        candidates.append(
            _candidate(
                registry=registry,
                seen_unique_ids=seen_unique_ids,
                domain="sensor",
                platform=DOMAIN,
                unique_id=f"{entry_id}-device-{normalized_mac}-*",
                name="Connected client sensors",
                module=MODULE_DEVICES,
                device_scope="client",
                source="coordinator_data",
                status="blocked",
                reason="disabled_option" if not auto_add_connected_devices else "not_selected",
            )
        )

    for normalized_mac in sorted(allowed_client_macs):
        device = build_client_seed_device(
            normalized_mac,
            connected_devices_by_mac,
            known_clients.get(normalized_mac, {}).get("name"),
        )
        for description in _CLIENT_SENSOR_DESCRIPTIONS:
            value = device.get(description.key)
            candidates.append(
                _candidate(
                    registry=registry,
                    seen_unique_ids=seen_unique_ids,
                    domain="sensor",
                    platform=DOMAIN,
                    unique_id=f"{entry_id}-device-{normalized_mac}-{description.key}",
                    name=description.name_suffix,
                    module=MODULE_DEVICES,
                    key=description.key,
                    device_scope="client",
                    source="coordinator_data",
                    status="available" if _value_present(value) else "blocked",
                    reason=None if _value_present(value) else "empty_value",
                    sample_value=transform_value(description.key, value)
                    if _value_present(value)
                    else None,
                )
            )
    return candidates


def _client_switch_candidates(
    *,
    hass: Any,
    config_entry: Any,
    data: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    seen_unique_ids: set[str],
) -> list[dict[str, Any]]:
    """Return connected-client switch catalog entries."""
    entry_id = getattr(config_entry, "entry_id", "")
    allowed_client_macs, connected_devices_by_mac, _connected = _allowed_client_macs(
        hass,
        config_entry,
        data,
    )
    known_clients = known_client_devices(hass, config_entry)
    candidates: list[dict[str, Any]] = []
    for normalized_mac in sorted(allowed_client_macs):
        current_device = connected_devices_by_mac.get(normalized_mac)
        known_switch_features = set(
            known_clients.get(normalized_mac, {}).get("switch_features", set())
        )
        for feature_key, name in _CLIENT_SWITCH_FEATURES:
            if current_device is not None:
                has_feature = current_device.get(feature_key) is not None
            else:
                has_feature = feature_key in known_switch_features
            candidates.append(
                _candidate(
                    registry=registry,
                    seen_unique_ids=seen_unique_ids,
                    domain="switch",
                    platform=DOMAIN,
                    unique_id=f"{entry_id}-device-{normalized_mac}-{feature_key}",
                    name=name,
                    module=MODULE_DEVICES,
                    key=feature_key,
                    device_scope="client",
                    source="coordinator_data",
                    status="available" if has_feature else "blocked",
                    reason=None if has_feature else "empty_value",
                )
            )
    return candidates


def _tracker_candidates(
    *,
    hass: Any,
    config_entry: Any,
    data: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    seen_unique_ids: set[str],
) -> list[dict[str, Any]]:
    """Return device-tracker catalog entries."""
    options = getattr(config_entry, "options", {}) or {}
    connected_devices = _connected_devices(data)
    connected_devices_by_mac = connected_device_lookup(connected_devices)
    known_trackers = known_tracker_clients(hass, config_entry)
    tracker_options_configured = (
        OPTIONS_AUTO_ADD_DEVICE_TRACKERS in options
        or OPTIONS_TRACKED_DEVICE_MACS in options
    )
    allowed_tracker_macs = tracker_allowed_macs(
        auto_add_device_trackers=options.get(OPTIONS_AUTO_ADD_DEVICE_TRACKERS, False),
        connected_devices=connected_devices,
        tracked_device_macs=configured_tracked_macs(options.get(OPTIONS_TRACKED_DEVICE_MACS)),
        legacy_tracked_macs=set(known_trackers),
        tracker_options_configured=tracker_options_configured,
    )
    candidates: list[dict[str, Any]] = []
    for normalized_mac in sorted(set(connected_devices_by_mac) - allowed_tracker_macs):
        candidates.append(
            _candidate(
                registry=registry,
                seen_unique_ids=seen_unique_ids,
                domain="device_tracker",
                platform=DOMAIN,
                unique_id=format_mac(normalized_mac) or normalized_mac,
                name="Device tracker",
                module=MODULE_DEVICES,
                key="device_tracker",
                device_scope="client",
                source="coordinator_data",
                status="blocked",
                reason="disabled_option",
            )
        )
    for normalized_mac in sorted(allowed_tracker_macs):
        device = build_tracker_seed_device(
            normalized_mac,
            connected_devices_by_mac,
            known_trackers.get(normalized_mac, {}).get("name"),
        )
        candidates.append(
            _candidate(
                registry=registry,
                seen_unique_ids=seen_unique_ids,
                domain="device_tracker",
                platform=DOMAIN,
                unique_id=format_mac(normalized_mac) or normalized_mac,
                name=str(device.get("hostname") or "Device tracker"),
                module=MODULE_DEVICES,
                key="device_tracker",
                device_scope="client",
                source="coordinator_data",
                status="available",
            )
        )
    return candidates


def _mesh_candidates(
    *,
    config_entry: Any,
    device_model: str,
    data: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    seen_unique_ids: set[str],
    transform_value: ValueTransform,
) -> list[dict[str, Any]]:
    """Return mesh-device entity catalog entries."""
    entry_id = getattr(config_entry, "entry_id", "")
    mesh_data = _module_data(data, MODULE_MESH)
    mesh_devices = mesh_data.get("mesh_devices", {})
    if not isinstance(mesh_devices, Mapping):
        mesh_devices = {}
    candidates: list[dict[str, Any]] = []
    if not mesh_devices and not module_available(device_model, MODULE_MESH, data):
        return [
            _candidate(
                registry=registry,
                seen_unique_ids=seen_unique_ids,
                domain="sensor",
                platform=DOMAIN,
                unique_id=None,
                name="Mesh node entities",
                module=MODULE_MESH,
                device_scope="mesh",
                status="blocked",
                reason="unsupported_model",
            )
        ]

    main_led_status = mesh_data.get("main_router_led_status")
    candidates.append(
        _candidate(
            registry=registry,
            seen_unique_ids=seen_unique_ids,
            domain="switch",
            platform=DOMAIN,
            unique_id=f"{entry_id}-main-router-led",
            name="LED",
            module=MODULE_MESH,
            key="main_router_led_status",
            source="coordinator_data",
            status="available" if main_led_status is not None else "blocked",
            reason=None if main_led_status is not None else "empty_value",
            sample_value=transform_value("main_router_led_status", main_led_status)
            if main_led_status is not None
            else None,
        )
    )

    for mesh_mac, mesh_device in sorted(mesh_devices.items()):
        if not isinstance(mesh_device, Mapping):
            continue
        for description in _MESH_SENSOR_DESCRIPTIONS:
            value = mesh_device.get(description.key)
            candidates.append(
                _candidate(
                    registry=registry,
                    seen_unique_ids=seen_unique_ids,
                    domain="sensor",
                    platform=DOMAIN,
                    unique_id=f"{entry_id}-mesh-{mesh_mac}-{description.key}",
                    name=description.name_suffix,
                    module=MODULE_MESH,
                    key=description.key,
                    device_scope="mesh",
                    source="coordinator_data",
                    status="available" if _value_present(value) else "blocked",
                    reason=None if _value_present(value) else "empty_value",
                    sample_value=transform_value(description.key, value)
                    if _value_present(value)
                    else None,
                )
            )
        for domain, suffix, key in (
            ("switch", "LED", "led"),
            ("button", "Reboot", "reboot"),
        ):
            candidates.append(
                _candidate(
                    registry=registry,
                    seen_unique_ids=seen_unique_ids,
                    domain=domain,
                    platform=DOMAIN,
                    unique_id=f"{entry_id}-mesh-{mesh_mac}-{key}",
                    name=suffix,
                    module=MODULE_MESH,
                    key=key,
                    device_scope="mesh",
                    source="coordinator_data",
                    status="available",
                )
            )
    return candidates


def _setting_candidates(
    *,
    config_entry: Any,
    device_model: str,
    data: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    seen_unique_ids: set[str],
    transform_value: ValueTransform,
) -> list[dict[str, Any]]:
    """Return router switch/select setting catalog entries."""
    entry_id = getattr(config_entry, "entry_id", "")
    candidates: list[dict[str, Any]] = []
    for domain, descriptions in (
        ("switch", ROUTER_SETTING_SWITCHES),
        ("select", ROUTER_SELECTS),
    ):
        for description in descriptions:
            module_data = _module_data(data, description.module)
            entry = module_data.get(description.key)
            value = entry.get("value") if isinstance(entry, Mapping) else None
            status, reason = _status_for_data(
                device_model=device_model,
                module=description.module,
                key=description.key,
                data=data,
                value=value,
                value_known=True,
            )
            if status != "blocked" and not isinstance(entry, Mapping):
                status, reason = "blocked", "missing_value"
            candidates.append(
                _candidate(
                    registry=registry,
                    seen_unique_ids=seen_unique_ids,
                    domain=domain,
                    platform=DOMAIN,
                    unique_id=f"{entry_id}-{description.module}-{description.key}",
                    name=description.name_suffix,
                    module=description.module,
                    key=description.key,
                    source="coordinator_data" if status != "blocked" else "definition",
                    status=status,
                    reason=reason,
                    sample_value=transform_value(description.key, value)
                    if _value_present(value)
                    else None,
                )
            )
    return candidates


def _button_candidates(
    *,
    config_entry: Any,
    registry: dict[str, dict[str, Any]],
    seen_unique_ids: set[str],
) -> list[dict[str, Any]]:
    """Return always-available router button catalog entries."""
    return [
        _candidate(
            registry=registry,
            seen_unique_ids=seen_unique_ids,
            domain="button",
            platform=DOMAIN,
            unique_id=f"{getattr(config_entry, 'entry_id', '')}-reboot",
            name="Reboot",
            key="reboot",
            status="available",
        )
    ]


def _registry_only_candidates(
    registry: dict[str, dict[str, Any]],
    seen_unique_ids: set[str],
) -> list[dict[str, Any]]:
    """Return created registry entries not matched by the live catalog."""
    rows: list[dict[str, Any]] = []
    for unique_id, entry in sorted(registry.items(), key=lambda item: item[0]):
        if unique_id in seen_unique_ids:
            continue
        rows.append(
            {
                "domain": entry.get("domain"),
                "platform": entry.get("platform"),
                "unique_id": unique_id,
                "entity_id": entry.get("entity_id"),
                "name": None,
                "module": None,
                "key": None,
                "device_scope": "unknown",
                "source": "entity_registry",
                "status": "created",
                "reason": "registry_only",
                "created": True,
                "disabled_by": entry.get("disabled_by"),
                "entity_category": entry.get("entity_category"),
            }
        )
    return rows


def _summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Return entity catalog summary counts."""
    by_status: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    blocked_reasons: dict[str, int] = {}
    for entry in entries:
        status = str(entry.get("status") or "unknown")
        domain = str(entry.get("domain") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        by_domain[domain] = by_domain.get(domain, 0) + 1
        if status == "blocked":
            reason = str(entry.get("reason") or "unknown")
            blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1
    return {
        "total": len(entries),
        "by_status": dict(sorted(by_status.items())),
        "by_domain": dict(sorted(by_domain.items())),
        "blocked_reasons": dict(sorted(blocked_reasons.items())),
    }


def build_entity_catalog(
    hass: Any,
    config_entry: Any,
    coordinator: Any,
    *,
    value_transform: ValueTransform | None = None,
) -> dict[str, Any]:
    """Return diagnostics data describing created and possible entities."""
    transform_value = value_transform or _identity_value
    data = getattr(coordinator, "data", {}) or {}
    if not isinstance(data, dict):
        data = {}
    device_model = str(getattr(config_entry, "data", {}).get(CONF_MODEL, "default"))
    registry = _registry_index(hass, config_entry)
    seen_unique_ids: set[str] = set()
    entries: list[dict[str, Any]] = []
    entries.extend(
        _router_sensor_candidates(
            config_entry=config_entry,
            device_model=device_model,
            data=data,
            registry=registry,
            seen_unique_ids=seen_unique_ids,
            transform_value=transform_value,
        )
    )
    entries.extend(
        _wan_interface_candidates(
            config_entry=config_entry,
            device_model=device_model,
            data=data,
            registry=registry,
            seen_unique_ids=seen_unique_ids,
            transform_value=transform_value,
        )
    )
    entries.extend(
        _setting_candidates(
            config_entry=config_entry,
            device_model=device_model,
            data=data,
            registry=registry,
            seen_unique_ids=seen_unique_ids,
            transform_value=transform_value,
        )
    )
    entries.extend(
        _button_candidates(
            config_entry=config_entry,
            registry=registry,
            seen_unique_ids=seen_unique_ids,
        )
    )
    entries.extend(
        _client_sensor_candidates(
            hass=hass,
            config_entry=config_entry,
            data=data,
            registry=registry,
            seen_unique_ids=seen_unique_ids,
            transform_value=transform_value,
        )
    )
    entries.extend(
        _client_switch_candidates(
            hass=hass,
            config_entry=config_entry,
            data=data,
            registry=registry,
            seen_unique_ids=seen_unique_ids,
        )
    )
    entries.extend(
        _tracker_candidates(
            hass=hass,
            config_entry=config_entry,
            data=data,
            registry=registry,
            seen_unique_ids=seen_unique_ids,
        )
    )
    entries.extend(
        _mesh_candidates(
            config_entry=config_entry,
            device_model=device_model,
            data=data,
            registry=registry,
            seen_unique_ids=seen_unique_ids,
            transform_value=transform_value,
        )
    )
    entries.extend(_registry_only_candidates(registry, seen_unique_ids))
    entries = sorted(
        entries,
        key=lambda entry: (
            str(entry.get("domain") or ""),
            str(entry.get("device_scope") or ""),
            str(entry.get("module") or ""),
            str(entry.get("key") or ""),
            str(entry.get("unique_id") or ""),
        ),
    )
    return {
        "summary": _summary(entries),
        "entities": entries,
        "model": {
            "configured": device_model,
            "mapped_modules": sorted(
                module
                for module in {
                    entry.get("module")
                    for entry in entries
                    if isinstance(entry.get("module"), str)
                }
                if existing_feature(device_model, str(module))
            ),
            "live_modules": sorted(data),
        },
    }
