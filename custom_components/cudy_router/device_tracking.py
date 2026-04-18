"""Pure helpers for client selection, matching, and picker options."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DeviceListOption = list[str] | tuple[str, ...] | set[str] | str | None


def normalize_device_identifier(value: str | None) -> str:
    """Normalize a user/device identifier for matching."""
    return (value or "").strip().lower()


def normalize_mac(value: str | None) -> str:
    """Normalize MAC values for matching and unique IDs."""
    normalized = normalize_device_identifier(value)
    return normalized.replace(":", "").replace("-", "")


def format_mac(value: str | None) -> str | None:
    """Return a normalized MAC in colon-separated uppercase form."""
    normalized = normalize_mac(value)
    if len(normalized) != 12:
        return None

    return ":".join(normalized[index : index + 2] for index in range(0, 12, 2)).upper()


def configured_device_values(raw_value: DeviceListOption) -> list[str]:
    """Return cleaned configured device values from legacy or picker options."""
    if raw_value is None:
        return []

    if isinstance(raw_value, str):
        raw_items = raw_value.split(",")
    else:
        raw_items = raw_value

    selected_values: list[str] = []
    seen_values: set[str] = set()
    for item in raw_items:
        cleaned_value = str(item).strip()
        if not cleaned_value:
            continue

        canonical_value = format_mac(cleaned_value) or cleaned_value
        dedupe_key = normalize_device_identifier(canonical_value)
        if dedupe_key in seen_values:
            continue

        seen_values.add(dedupe_key)
        selected_values.append(canonical_value)

    return selected_values


def configured_device_ids(raw_value: DeviceListOption) -> set[str]:
    """Return configured device identifiers from the legacy string or picker values."""
    selected = {
        normalize_device_identifier(item)
        for item in configured_device_values(raw_value)
        if normalize_device_identifier(item)
    }

    selected.update(
        normalize_mac(item)
        for item in configured_device_values(raw_value)
        if normalize_mac(item)
    )
    return selected


def is_selected_device(device: dict[str, Any], selected_ids: set[str]) -> bool:
    """Check whether a device should be tracked."""
    if not selected_ids:
        return False

    device_identifiers = {
        normalize_device_identifier(device.get("hostname")),
        normalize_device_identifier(device.get("ip")),
        normalize_device_identifier(device.get("mac")),
        normalize_mac(device.get("mac")),
    }
    return any(identifier in selected_ids for identifier in device_identifiers if identifier)


def configured_tracked_macs(raw_value: list[str] | tuple[str, ...] | set[str] | str | None) -> set[str]:
    """Return normalized MACs from tracker-specific option values."""
    if raw_value is None:
        return set()

    if isinstance(raw_value, str):
        raw_items = raw_value.split(",")
    else:
        raw_items = raw_value

    return {
        normalized_mac
        for item in raw_items
        if (normalized_mac := normalize_mac(str(item))) and len(normalized_mac) == 12
    }


def connected_device_lookup(devices: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return connected devices keyed by normalized MAC."""
    lookup: dict[str, dict[str, Any]] = {}
    for device in devices:
        normalized_mac = normalize_mac(device.get("mac"))
        if len(normalized_mac) != 12 or normalized_mac in lookup:
            continue
        lookup[normalized_mac] = device
    return lookup


def manual_selected_connected_devices(
    connected_devices: list[dict[str, Any]],
    device_list: DeviceListOption,
) -> list[dict[str, Any]]:
    """Return connected devices that match the manual device list."""
    selected_ids = configured_device_ids(device_list)
    return [
        device
        for device in connected_devices
        if normalize_mac(device.get("mac"))
        and is_selected_device(device, selected_ids)
    ]


def manual_allowed_client_macs(
    *,
    connected_devices: list[dict[str, Any]],
    device_list: DeviceListOption,
    known_clients: Mapping[str, Mapping[str, Any]] | None = None,
) -> set[str]:
    """Return MACs that should remain for manual connected-device selections."""
    selected_ids = configured_device_ids(device_list)
    allowed_macs = {
        normalized_mac
        for item in configured_device_values(device_list)
        if len(normalized_mac := normalize_mac(item)) == 12
    }

    if selected_ids:
        allowed_macs.update(
            normalize_mac(device.get("mac"))
            for device in connected_devices
            if len(normalize_mac(device.get("mac"))) == 12
            and is_selected_device(device, selected_ids)
        )

    if known_clients and selected_ids:
        for normalized_mac, client in known_clients.items():
            client_identifiers = {
                normalize_device_identifier(str(client.get("name")) if client.get("name") is not None else None),
                normalize_device_identifier(str(client.get("mac")) if client.get("mac") is not None else None),
                normalize_mac(str(client.get("mac")) if client.get("mac") is not None else None),
                normalize_device_identifier(format_mac(normalized_mac)),
                normalize_mac(normalized_mac),
            }
            if any(identifier in selected_ids for identifier in client_identifiers if identifier):
                allowed_macs.add(normalized_mac)

    return {normalized_mac for normalized_mac in allowed_macs if len(normalized_mac) == 12}


def eligible_manual_picker_devices(connected_devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return live devices that should appear in the manual connected-device picker."""
    return [
        device
        for device in connected_devices
        if len(normalize_mac(device.get("mac"))) == 12
    ]


def eligible_tracker_picker_devices(
    *,
    auto_add_connected_devices: bool,
    connected_devices: list[dict[str, Any]],
    device_list: DeviceListOption,
) -> list[dict[str, Any]]:
    """Return live devices that should appear in the tracker picker."""
    if auto_add_connected_devices:
        return eligible_manual_picker_devices(connected_devices)

    manual_devices = manual_selected_connected_devices(connected_devices, device_list)
    if manual_devices:
        return manual_devices

    return eligible_manual_picker_devices(connected_devices)


def next_options_flow_step(
    *,
    auto_add_connected_devices: bool,
    auto_add_device_trackers: bool,
    after_manual_devices: bool = False,
) -> str | None:
    """Return the next options-flow step for the current toggle combination."""
    if not after_manual_devices and not auto_add_connected_devices:
        return "manual_devices"

    if auto_add_device_trackers:
        return None

    return "trackers"


def tracker_option_label(name: str | None, normalized_mac: str) -> str:
    """Build a readable label for a tracker selection option."""
    formatted_mac = format_mac(normalized_mac) or normalized_mac.upper()
    cleaned_name = (name or "").strip()
    if cleaned_name and cleaned_name.lower() != formatted_mac.lower():
        return f"{cleaned_name} ({formatted_mac})"
    return formatted_mac


def tracker_picker_options(
    connected_devices: list[dict[str, Any]],
    known_trackers: Mapping[str, str | None],
) -> list[dict[str, str]]:
    """Return tracker-picker options from live clients and known trackers."""
    options_by_mac: dict[str, str] = {}

    for normalized_mac, name in known_trackers.items():
        if len(normalized_mac) != 12:
            continue
        options_by_mac[normalized_mac] = tracker_option_label(name, normalized_mac)

    for device in connected_devices:
        normalized_mac = normalize_mac(device.get("mac"))
        if len(normalized_mac) != 12:
            continue
        options_by_mac[normalized_mac] = tracker_option_label(
            device.get("hostname"),
            normalized_mac,
        )

    return [
        {"value": normalized_mac, "label": label}
        for normalized_mac, label in sorted(
            options_by_mac.items(),
            key=lambda item: (item[1].lower(), item[0]),
        )
    ]


def tracker_allowed_macs(
    *,
    auto_add_device_trackers: bool,
    connected_devices: list[dict[str, Any]],
    tracked_device_macs: set[str],
    legacy_tracked_macs: set[str] | None = None,
    tracker_options_configured: bool,
) -> set[str]:
    """Return normalized MACs that should keep tracker entities."""
    allowed_macs = set(tracked_device_macs)

    if auto_add_device_trackers:
        allowed_macs.update(connected_device_lookup(connected_devices))

    if not tracker_options_configured and legacy_tracked_macs:
        allowed_macs.update(legacy_tracked_macs)

    return allowed_macs


def build_tracker_seed_device(
    normalized_mac: str,
    connected_devices: Mapping[str, dict[str, Any]],
    known_name: str | None = None,
) -> dict[str, Any]:
    """Return a connected-device payload suitable for tracker bootstrap."""
    return build_client_seed_device(
        normalized_mac,
        connected_devices,
        known_name,
    )


def build_client_seed_device(
    normalized_mac: str,
    connected_devices: Mapping[str, dict[str, Any]],
    known_name: str | None = None,
) -> dict[str, Any]:
    """Return a connected-device payload suitable for tracker bootstrap."""
    if normalized_mac in connected_devices:
        return connected_devices[normalized_mac]

    formatted_mac = format_mac(normalized_mac) or normalized_mac.upper()
    return {
        "hostname": known_name or formatted_mac,
        "mac": formatted_mac,
    }
