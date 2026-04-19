"""Frontend panel and websocket wiring for Cudy SMS."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import frontend as ha_frontend
from homeassistant.components import websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .sms import (
    SMS_PANEL_COMPONENT_NAME,
    SMS_PANEL_STATIC_FILE,
    SMS_PANEL_STATIC_URL,
    SMS_PANEL_URL_PATH,
    async_fetch_sms_data,
    async_send_sms_message,
    coordinator_shows_sms_panel_in_sidebar,
    coordinator_supports_sms,
    sms_capable_coordinators,
    sms_entry_payload,
)

_RUNTIME_KEY = f"{DOMAIN}_frontend"


def _runtime_state(hass: HomeAssistant) -> dict[str, bool]:
    """Return mutable runtime state for frontend helpers."""
    return hass.data.setdefault(
        _RUNTIME_KEY,
        {
            "panel_registered": False,
            "static_registered": False,
            "websocket_registered": False,
        },
    )


def _coordinator_for_entry_id(hass: HomeAssistant, entry_id: str) -> Any | None:
    """Return the loaded coordinator for an entry id."""
    return hass.data.get(DOMAIN, {}).get(entry_id)


async def _async_register_static_path(hass: HomeAssistant) -> None:
    """Register the panel JavaScript bundle."""
    runtime = _runtime_state(hass)
    if runtime["static_registered"]:
        return

    panel_path = Path(__file__).parent / SMS_PANEL_STATIC_FILE
    await hass.http.async_register_static_paths(
        [StaticPathConfig(SMS_PANEL_STATIC_URL, str(panel_path), False)]
    )
    runtime["static_registered"] = True


def _register_panel(hass: HomeAssistant, *, show_in_sidebar: bool) -> None:
    """Register or update the sidebar panel."""
    runtime = _runtime_state(hass)
    panel_path = Path(__file__).parent / SMS_PANEL_STATIC_FILE
    panel_version = panel_path.stat().st_mtime_ns

    ha_frontend.async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="Cudy SMS",
        sidebar_icon="mdi:message-text",
        frontend_url_path=SMS_PANEL_URL_PATH,
        config={
            "_panel_custom": {
                "name": SMS_PANEL_COMPONENT_NAME,
                "embed_iframe": False,
                "trust_external": False,
                "module_url": f"{SMS_PANEL_STATIC_URL}?v={panel_version}",
            }
        },
        require_admin=True,
        show_in_sidebar=show_in_sidebar,
        update=runtime["panel_registered"],
    )
    runtime["panel_registered"] = True


def _remove_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar panel if it is no longer needed."""
    runtime = _runtime_state(hass)
    if not runtime["panel_registered"]:
        return

    ha_frontend.async_remove_panel(hass, SMS_PANEL_URL_PATH, warn_if_unknown=False)
    runtime["panel_registered"] = False


def _register_websocket_commands(hass: HomeAssistant) -> None:
    """Register websocket handlers once."""
    runtime = _runtime_state(hass)
    if runtime["websocket_registered"]:
        return

    websocket_api.async_register_command(hass, websocket_list_sms_entries)
    websocket_api.async_register_command(hass, websocket_get_sms_messages)
    websocket_api.async_register_command(hass, websocket_send_sms)
    runtime["websocket_registered"] = True


async def async_refresh_frontend(hass: HomeAssistant) -> None:
    """Ensure the SMS panel matches the currently loaded entries."""
    coordinators = sms_capable_coordinators(hass)
    if coordinators:
        await _async_register_static_path(hass)
        _register_websocket_commands(hass)
        _register_panel(
            hass,
            show_in_sidebar=any(
                coordinator_shows_sms_panel_in_sidebar(coordinator)
                for coordinator in coordinators
            ),
        )
        return

    _remove_panel(hass)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "cudy_router/sms/list_entries",
    }
)
@websocket_api.require_admin
def websocket_list_sms_entries(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """List SMS-capable Cudy entries."""
    entries = [sms_entry_payload(coordinator) for coordinator in sms_capable_coordinators(hass)]
    connection.send_result(msg["id"], {"entries": entries})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "cudy_router/sms/get_messages",
        vol.Required("entry_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_get_sms_messages(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the latest SMS messages for one router."""
    coordinator = _coordinator_for_entry_id(hass, msg["entry_id"])
    if coordinator is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Unknown Cudy Router entry.")
        return
    if not coordinator_supports_sms(coordinator):
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_SUPPORTED,
            "The selected router does not support SMS.",
        )
        return

    connection.send_result(msg["id"], await async_fetch_sms_data(hass, coordinator))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "cudy_router/sms/send",
        vol.Required("entry_id"): str,
        vol.Required("phone_number"): str,
        vol.Required("message"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_send_sms(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Send an SMS via the selected router."""
    coordinator = _coordinator_for_entry_id(hass, msg["entry_id"])
    if coordinator is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Unknown Cudy Router entry.")
        return
    if not coordinator_supports_sms(coordinator):
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_SUPPORTED,
            "The selected router does not support SMS.",
        )
        return

    result = await async_send_sms_message(
        hass,
        coordinator,
        msg["phone_number"],
        msg["message"],
    )
    if not result["success"]:
        raise HomeAssistantError(result["message"])

    connection.send_result(msg["id"], result)
