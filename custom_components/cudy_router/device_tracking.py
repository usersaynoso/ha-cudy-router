"""Pure helpers for device tracker selection and matching."""

from __future__ import annotations

from typing import Any


def normalize_device_identifier(value: str | None) -> str:
    """Normalize a user/device identifier for matching."""
    return (value or "").strip().lower()


def normalize_mac(value: str | None) -> str:
    """Normalize MAC values for matching and unique IDs."""
    normalized = normalize_device_identifier(value)
    return normalized.replace(":", "").replace("-", "")


def configured_device_ids(raw_value: str | None) -> set[str]:
    """Return configured device identifiers from the options string."""
    if not raw_value:
        return set()

    selected = {
        normalize_device_identifier(item)
        for item in raw_value.split(",")
        if normalize_device_identifier(item)
    }

    selected.update(normalize_mac(item) for item in raw_value.split(",") if normalize_mac(item))
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
