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
from .device_tracking import normalize_mac


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
        if entry.platform != DOMAIN or entry.domain != entity_domain:
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
    entity_registry = async_get_entity_registry(hass)
    device_registry = async_get_device_registry(hass)
    prefix = f"{config_entry.entry_id}-device-"
    active_normalized_macs = {normalize_mac(mac) for mac in active_client_macs if normalize_mac(mac)}

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
        if normalized_mac in active_normalized_macs:
            continue
        device_registry.async_remove_device(device.id)

    for entry in list(entity_registry.entities.values()):
        if entry.platform != DOMAIN or entry.domain != entity_domain:
            continue
        if not entry.unique_id.startswith(prefix):
            continue

        remainder = entry.unique_id[len(prefix) :]
        normalized_mac = remainder.split("-", 1)[0]
        if normalized_mac in active_normalized_macs:
            continue
        entity_registry.async_remove(entry.entity_id)
