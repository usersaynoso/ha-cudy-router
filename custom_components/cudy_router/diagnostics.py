"""Diagnostics support for the Cudy Router integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .debug_report import DEFAULT_DEBUG_HTML_CHARS, async_build_debug_payload


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    return await async_build_debug_payload(
        hass,
        coordinator,
        include_html=True,
        max_html_chars=DEFAULT_DEBUG_HTML_CHARS,
    )
