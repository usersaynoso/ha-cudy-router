"""Helpers for consistent Home Assistant device registry metadata."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_MODEL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    async_get as async_get_device_registry,
)
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .const import DOMAIN, MODULE_LAN, MODULE_MESH, MODULE_SYSTEM, MODULE_WAN
from .device_tracking import format_mac, normalize_mac

_CLIENT_ENTITY_DOMAINS = {"sensor", "switch", "device_tracker"}


def _clean_text(value: Any) -> str | None:
    """Return a stripped string or None."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _mac_connection(mac_address: str | None) -> set[tuple[str, str]] | None:
    """Return a normalized MAC connection set for the device registry."""
    normalized = normalize_mac(mac_address)
    if len(normalized) != 12:
        return None

    formatted = ":".join(normalized[i : i + 2] for i in range(0, 12, 2))
    return {(CONNECTION_NETWORK_MAC, formatted)}


def _module_value(data: dict[str, Any], module: str, key: str) -> str | None:
    """Return the plain string value for a module/key pair."""
    entry = data.get(module, {}).get(key)
    if isinstance(entry, dict):
        return _clean_text(entry.get("value"))
    return None


def _entity_domain(entry: Any) -> str | None:
    """Return an entity registry entry domain, falling back to entity_id parsing."""
    domain = _clean_text(getattr(entry, "domain", None))
    if domain:
        return domain

    entity_id = _clean_text(getattr(entry, "entity_id", None))
    if entity_id and "." in entity_id:
        return entity_id.split(".", 1)[0]
    return None


def router_display_name(config_entry: Any, data: dict[str, Any] | None) -> str:
    """Return the best available Home Assistant device name for the main router."""
    mesh_name = _clean_text((data or {}).get(MODULE_MESH, {}).get("main_router_name"))
    if mesh_name:
        return mesh_name

    model = _clean_text(config_entry.data.get(CONF_MODEL))
    if model and model.lower() != "default":
        return model

    return "Cudy Router"


def client_display_name(device: dict[str, Any]) -> str:
    """Return the preferred display name for a connected client."""
    return (
        _clean_text(device.get("hostname"))
        or _clean_text(device.get("mac"))
        or "Connected device"
    )


def mesh_display_name(mesh_name: str | None, mesh_mac: str | None) -> str:
    """Return a clearly distinct display name for a mesh node."""
    raw_name = _clean_text(mesh_name) or _clean_text(mesh_mac) or "Node"
    if raw_name.lower().startswith("mesh "):
        return raw_name
    return f"Mesh {raw_name}"


def _mesh_model_fields(mesh_device: dict[str, Any]) -> tuple[str | None, str | None]:
    """Split the mesh model and hardware version when available."""
    model = _clean_text(mesh_device.get("model"))
    hardware = _clean_text(mesh_device.get("hardware"))
    hw_version = None

    if hardware:
        if model and hardware.lower().startswith(model.lower()):
            remainder = hardware[len(model) :].strip()
            if remainder:
                hw_version = remainder
        elif not model:
            parts = hardware.split(" ", 1)
            model = parts[0]
            if len(parts) > 1:
                hw_version = parts[1].strip() or None

    return model, hw_version


def build_router_device_info(coordinator: Any) -> DeviceInfo:
    """Return registry metadata for the main router device."""
    data = coordinator.data or {}
    info: dict[str, Any] = {
        "identifiers": {(DOMAIN, coordinator.config_entry.entry_id)},
        "manufacturer": "Cudy",
        "name": router_display_name(coordinator.config_entry, data),
    }

    model = _clean_text(coordinator.config_entry.data.get(CONF_MODEL))
    if model and model.lower() != "default":
        info["model"] = model

    sw_version = _module_value(data, MODULE_SYSTEM, "firmware_version")
    if sw_version:
        info["sw_version"] = sw_version

    connections = _mac_connection(
        _module_value(data, MODULE_LAN, "mac_address")
        or _module_value(data, MODULE_WAN, "mac_address")
    )
    if connections:
        info["connections"] = connections

    return DeviceInfo(**info)


def build_client_device_info(config_entry: Any, device: dict[str, Any]) -> DeviceInfo:
    """Return registry metadata for a connected client device."""
    normalized_mac = normalize_mac(device.get("mac"))
    info: dict[str, Any] = {
        "identifiers": {(DOMAIN, f"{config_entry.entry_id}-device-{normalized_mac}")},
        "name": client_display_name(device),
        "via_device": (DOMAIN, config_entry.entry_id),
    }

    connections = _mac_connection(device.get("mac"))
    if connections:
        info["connections"] = connections

    return DeviceInfo(**info)


def async_ensure_client_entity_device(
    hass: HomeAssistant,
    config_entry: Any,
    entity_domain: str,
    entity_unique_id: str,
    device: dict[str, Any],
) -> str | None:
    """Ensure a client entity is linked to a device-registry entry."""
    device_info = build_client_device_info(config_entry, device)
    device_registry = async_get_device_registry(hass)
    registry_device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers=device_info["identifiers"],
        connections=device_info.get("connections"),
        name=device_info.get("name"),
        via_device=device_info.get("via_device"),
    )

    entity_registry = async_get_entity_registry(hass)
    entity_id = entity_registry.async_get_entity_id(
        entity_domain,
        DOMAIN,
        entity_unique_id,
    )
    if entity_id is None:
        return registry_device.id

    entry = entity_registry.entities.get(entity_id)
    if entry is None or getattr(entry, "device_id", None) == registry_device.id:
        return registry_device.id

    entity_registry.async_update_entity(entity_id, device_id=registry_device.id)
    return registry_device.id


def build_mesh_device_info(coordinator: Any, mesh_mac: str, mesh_device: dict[str, Any]) -> DeviceInfo:
    """Return registry metadata for a mesh node."""
    model, hw_version = _mesh_model_fields(mesh_device)

    info: dict[str, Any] = {
        "identifiers": {(DOMAIN, f"{coordinator.config_entry.entry_id}-mesh-{mesh_mac}")},
        "manufacturer": "Cudy",
        "name": mesh_display_name(mesh_device.get("name"), mesh_mac),
        "via_device": (DOMAIN, coordinator.config_entry.entry_id),
    }

    connections = _mac_connection(mesh_device.get("mac_address") or mesh_mac)
    if connections:
        info["connections"] = connections
    if model:
        info["model"] = model
    if hw_version:
        info["hw_version"] = hw_version

    sw_version = _clean_text(mesh_device.get("firmware_version"))
    if sw_version:
        info["sw_version"] = sw_version

    return DeviceInfo(**info)


def async_cleanup_stale_mesh_entities(
    hass: HomeAssistant,
    config_entry: Any,
    entity_domain: str,
    active_mesh_macs: set[str],
) -> None:
    """Remove mesh entities for nodes that are no longer reported."""
    entity_registry = async_get_entity_registry(hass)
    prefix = f"{config_entry.entry_id}-mesh-"
    active_prefixes = {
        f"{prefix}{normalize_mac(mesh_mac) if ':' not in mesh_mac and '-' not in mesh_mac else mesh_mac}-"
        for mesh_mac in active_mesh_macs
    }

    for entry in list(entity_registry.entities.values()):
        if entry.platform != DOMAIN or _entity_domain(entry) != entity_domain:
            continue
        if not entry.unique_id.startswith(prefix):
            continue
        if any(entry.unique_id.startswith(active_prefix) for active_prefix in active_prefixes):
            continue
        entity_registry.async_remove(entry.entity_id)


def async_cleanup_stale_client_entities(
    hass: HomeAssistant,
    config_entry: Any,
    entity_domain: str,
    active_client_macs: set[str],
) -> None:
    """Remove client entities for devices that should no longer exist."""
    _async_cleanup_stale_client_entities(
        hass,
        config_entry,
        entity_domain,
        active_client_macs,
    )


def async_cleanup_stale_tracker_entities(
    hass: HomeAssistant,
    config_entry: Any,
    entity_domain: str,
    allowed_tracker_macs: set[str],
) -> None:
    """Remove tracker entities for clients that are no longer allowed."""
    entity_registry = async_get_entity_registry(hass)
    device_registry = async_get_device_registry(hass)
    prefix = f"{config_entry.entry_id}-device-"
    allowed_normalized_macs = {
        normalize_mac(mac)
        for mac in allowed_tracker_macs
        if normalize_mac(mac)
    }
    canonical_tracker_macs = {
        normalized_mac
        for entry in list(entity_registry.entities.values())
        if entry.platform == DOMAIN
        and _entity_domain(entry) == entity_domain
        and (
            normalized_mac := _normalized_client_mac_from_unique_id(
                prefix,
                getattr(entry, "unique_id", "") or "",
            )
        )
        is not None
        and _uses_tracker_mac_unique_id(getattr(entry, "unique_id", "") or "")
    }

    for entry in list(entity_registry.entities.values()):
        if entry.platform != DOMAIN or _entity_domain(entry) != entity_domain:
            continue
        normalized_mac = _normalized_client_mac_from_unique_id(
            prefix,
            getattr(entry, "unique_id", "") or "",
        )
        if normalized_mac is None:
            continue
        if normalized_mac not in allowed_normalized_macs:
            entity_registry.async_remove(entry.entity_id)
            continue
        if (
            normalized_mac in canonical_tracker_macs
            and not _uses_tracker_mac_unique_id(getattr(entry, "unique_id", "") or "")
        ):
            entity_registry.async_remove(entry.entity_id)
            continue

    remaining_client_macs = {
        normalized_mac
        for entry in list(entity_registry.entities.values())
        if entry.platform == DOMAIN
        and _entity_domain(entry) in _CLIENT_ENTITY_DOMAINS
        and (
            normalized_mac := _normalized_client_mac_from_unique_id(
                prefix,
                getattr(entry, "unique_id", "") or "",
            )
        )
        is not None
    }

    for device in list(device_registry.devices.values()):
        if config_entry.entry_id not in getattr(device, "config_entries", set()):
            continue

        matching_identifier = next(
            (
                identifier
                for domain, identifier in getattr(device, "identifiers", set())
                if domain == DOMAIN and identifier.startswith(prefix)
            ),
            None,
        )
        if matching_identifier is None:
            continue

        normalized_mac = matching_identifier[len(prefix) :]
        if (
            normalized_mac in allowed_normalized_macs
            or normalized_mac in remaining_client_macs
        ):
            continue
        device_registry.async_remove_device(device.id)


def known_client_devices(
    hass: HomeAssistant,
    config_entry: Any,
    *,
    entity_domains: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return known client devices from the entity and device registries."""
    entity_registry = async_get_entity_registry(hass)
    device_registry = async_get_device_registry(hass)
    prefix = f"{config_entry.entry_id}-device-"
    known_clients: dict[str, dict[str, Any]] = {}

    for entry in list(entity_registry.entities.values()):
        if entry.platform != DOMAIN:
            continue
        entry_domain = _entity_domain(entry)
        allowed_domains = entity_domains or _CLIENT_ENTITY_DOMAINS
        if entry_domain not in allowed_domains:
            continue

        unique_id = getattr(entry, "unique_id", "") or ""
        normalized_mac = _normalized_client_mac_from_unique_id(prefix, unique_id)
        if normalized_mac is None:
            continue

        device = (
            device_registry.devices.get(entry.device_id)
            if getattr(entry, "device_id", None)
            else None
        )
        client = known_clients.setdefault(
            normalized_mac,
            {
                "mac": format_mac(normalized_mac),
                "name": None,
                "switch_features": set(),
            },
        )
        client["name"] = (
            client.get("name")
            or _clean_text(getattr(device, "name_by_user", None))
            or _clean_text(getattr(device, "name", None))
            or _clean_text(getattr(entry, "name", None))
            or _clean_text(getattr(entry, "original_name", None))
        )

        feature_key = _client_feature_key_from_unique_id(prefix, unique_id)
        if entry_domain == "switch" and feature_key is not None:
            client["switch_features"].add(feature_key)

    for device in list(device_registry.devices.values()):
        if config_entry.entry_id not in getattr(device, "config_entries", set()):
            continue

        matching_identifier = next(
            (
                identifier
                for domain, identifier in getattr(device, "identifiers", set())
                if domain == DOMAIN and identifier.startswith(prefix)
            ),
            None,
        )
        if matching_identifier is None:
            continue

        normalized_mac = matching_identifier[len(prefix) :]
        if len(normalized_mac) != 12:
            continue

        if entity_domains is not None and normalized_mac not in known_clients:
            continue

        client = known_clients.setdefault(
            normalized_mac,
            {
                "mac": format_mac(normalized_mac),
                "name": None,
                "switch_features": set(),
            },
        )
        client["name"] = (
            client.get("name")
            or _clean_text(getattr(device, "name_by_user", None))
            or _clean_text(getattr(device, "name", None))
        )

    return known_clients


def known_tracker_clients(
    hass: HomeAssistant,
    config_entry: Any,
) -> dict[str, dict[str, str | None]]:
    """Return known tracker clients from the entity and device registries."""
    return {
        normalized_mac: {
            "mac": client.get("mac"),
            "name": client.get("name"),
        }
        for normalized_mac, client in known_client_devices(
            hass,
            config_entry,
            entity_domains={"device_tracker"},
        ).items()
    }


def _normalized_client_mac_from_unique_id(prefix: str, unique_id: str) -> str | None:
    """Extract the normalized MAC from a client unique ID."""
    if unique_id.startswith(prefix):
        normalized_mac = unique_id[len(prefix) :].split("-", 1)[0]
        if len(normalized_mac) == 12:
            return normalized_mac

    # Preserve cleanup and picker support for legacy tracker entities that used
    # the client MAC address directly as the unique ID.
    normalized_mac = normalize_mac(unique_id)
    if len(normalized_mac) != 12:
        return None
    return normalized_mac


def _uses_tracker_mac_unique_id(unique_id: str) -> bool:
    """Return whether a tracker unique ID uses the preserved raw-MAC format."""
    normalized_mac = normalize_mac(unique_id)
    if len(normalized_mac) != 12:
        return False
    return unique_id == (format_mac(normalized_mac) or unique_id)


def _client_feature_key_from_unique_id(prefix: str, unique_id: str) -> str | None:
    """Extract the feature key suffix from a client entity unique ID."""
    if not unique_id.startswith(prefix):
        return None

    normalized_mac = _normalized_client_mac_from_unique_id(prefix, unique_id)
    if normalized_mac is None:
        return None

    suffix_prefix = f"{prefix}{normalized_mac}-"
    if not unique_id.startswith(suffix_prefix):
        return None

    feature_key = unique_id[len(suffix_prefix) :]
    return feature_key or None


def _async_cleanup_stale_client_entities(
    hass: HomeAssistant,
    config_entry: Any,
    entity_domain: str,
    kept_client_macs: set[str],
) -> None:
    """Remove client devices and entities that are not in the kept set."""
    entity_registry = async_get_entity_registry(hass)
    device_registry = async_get_device_registry(hass)
    prefix = f"{config_entry.entry_id}-device-"
    kept_normalized_macs = {normalize_mac(mac) for mac in kept_client_macs if normalize_mac(mac)}

    for entry in list(entity_registry.entities.values()):
        if entry.platform != DOMAIN or _entity_domain(entry) != entity_domain:
            continue
        normalized_mac = _normalized_client_mac_from_unique_id(
            prefix,
            getattr(entry, "unique_id", "") or "",
        )
        if normalized_mac is None:
            continue
        if normalized_mac in kept_normalized_macs:
            continue
        entity_registry.async_remove(entry.entity_id)

    remaining_client_macs = {
        normalized_mac
        for entry in list(entity_registry.entities.values())
        if entry.platform == DOMAIN
        and _entity_domain(entry) in _CLIENT_ENTITY_DOMAINS
        and (
            normalized_mac := _normalized_client_mac_from_unique_id(
                prefix,
                getattr(entry, "unique_id", "") or "",
            )
        )
        is not None
    }

    for device in list(device_registry.devices.values()):
        if config_entry.entry_id not in getattr(device, "config_entries", set()):
            continue

        matching_identifier = next(
            (
                identifier
                for domain, identifier in getattr(device, "identifiers", set())
                if domain == DOMAIN and identifier.startswith(prefix)
            ),
            None,
        )
        if matching_identifier is None:
            continue

        normalized_mac = matching_identifier[len(prefix) :]
        if (
            normalized_mac in kept_normalized_macs
            or normalized_mac in remaining_client_macs
        ):
            continue
        device_registry.async_remove_device(device.id)
