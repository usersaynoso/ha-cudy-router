"""On-demand SMS helpers for the Cudy Router integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .const import DOMAIN, MODULE_SMS, OPTIONS_SHOW_SMS_PANEL_IN_SIDEBAR
from .features import supports_sms_feature
from .parser import parse_sms_detail, parse_sms_list, parse_sms_status

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


SMS_STATUS_PATH = "admin/network/gcom/sms/status"
SMS_PANEL_URL_PATH = "cudy-router-sms"
SMS_PANEL_COMPONENT_NAME = "cudy-router-sms-panel"
SMS_PANEL_STATIC_URL = "/cudy_router_static/cudy-router-sms-panel.js"
SMS_PANEL_STATIC_FILE = "frontend/cudy-router-sms-panel.js"

_SMSBOX_TO_FOLDER = {
    "rec": "inbox",
    "sto": "outbox",
}


def _sms_list_path(smsbox: str) -> str:
    """Return the LuCI path for an inbox or outbox listing."""
    return f"admin/network/gcom/sms/smslist?smsbox={smsbox}&iface=4g"


def _sms_detail_path(cfg: str, smsbox: str) -> str:
    """Return the LuCI path for an SMS detail modal."""
    return f"admin/network/gcom/sms/readsms?iface=4g&cfg={cfg}&smsbox={smsbox}"


def coordinator_supports_sms(coordinator: Any) -> bool:
    """Return whether the coordinator's model supports SMS."""
    return supports_sms_feature(
        coordinator.config_entry.data.get("model"),
        getattr(coordinator, "data", None),
    )


def coordinator_shows_sms_panel_in_sidebar(coordinator: Any) -> bool:
    """Return whether the entry wants the SMS panel link in the sidebar."""
    if not coordinator_supports_sms(coordinator):
        return False
    return coordinator.config_entry.options.get(OPTIONS_SHOW_SMS_PANEL_IN_SIDEBAR, True)


def sms_capable_coordinators(hass: HomeAssistant) -> list[Any]:
    """Return loaded coordinators that support SMS."""
    coordinators = hass.data.get(DOMAIN, {})
    return [
        coordinator
        for coordinator in coordinators.values()
        if hasattr(coordinator, "config_entry") and coordinator_supports_sms(coordinator)
    ]


def sms_summary_from_data(data: dict[str, Any] | None) -> dict[str, int]:
    """Extract SMS summary counts from coordinator data."""
    sms_data = (data or {}).get(MODULE_SMS, {})
    return {
        "inbox": int(sms_data.get("inbox_count", {}).get("value") or 0),
        "outbox": int(sms_data.get("outbox_count", {}).get("value") or 0),
        "unread": int(sms_data.get("unread_count", {}).get("value") or 0),
    }


def sms_entry_payload(coordinator: Any) -> dict[str, Any]:
    """Return a frontend-friendly description of an SMS-capable entry."""
    config_entry = coordinator.config_entry
    return {
        "entry_id": config_entry.entry_id,
        "title": config_entry.title or config_entry.data.get("host") or config_entry.entry_id,
        "host": config_entry.data.get("host"),
        "model": config_entry.data.get("model", "default"),
        "counts": sms_summary_from_data(getattr(coordinator, "data", None)),
    }


async def _async_fetch_sms_mailbox(
    router: Any,
    hass: HomeAssistant,
    smsbox: str,
) -> tuple[list[dict[str, Any]], bool]:
    """Fetch and enrich one SMS mailbox."""
    list_html = await hass.async_add_executor_job(router.get, _sms_list_path(smsbox), True)
    messages = parse_sms_list(list_html, smsbox)
    if messages is None:
        return [], False

    detailed_messages: list[dict[str, Any]] = []
    for message in messages:
        cfg = message.get("cfg")
        if not cfg:
            return [], False

        detail_html = await hass.async_add_executor_job(router.get, _sms_detail_path(cfg, smsbox), True)
        detail = parse_sms_detail(detail_html)
        if detail is None:
            return [], False

        enriched_message = dict(message)
        enriched_message.update(
            {
                key: value
                for key, value in detail.items()
                if value not in (None, "")
            }
        )
        detailed_messages.append(enriched_message)

    return detailed_messages, True


async def async_fetch_sms_data(
    hass: HomeAssistant,
    coordinator: Any,
) -> dict[str, Any]:
    """Fetch the latest SMS counts and message bodies for one coordinator."""
    router = coordinator.api
    status_html = await hass.async_add_executor_job(router.get, SMS_STATUS_PATH)
    summary = parse_sms_status(status_html)
    if summary is None:
        raise RuntimeError("The selected router does not support SMS.")
    inbox_messages, inbox_available = await _async_fetch_sms_mailbox(router, hass, "rec")
    outbox_messages, outbox_available = await _async_fetch_sms_mailbox(router, hass, "sto")

    return {
        "entry": sms_entry_payload(coordinator),
        "counts": {
            "inbox": int(summary.get("inbox_count", {}).get("value") or 0),
            "outbox": int(summary.get("outbox_count", {}).get("value") or 0),
            "unread": int(summary.get("unread_count", {}).get("value") or 0),
        },
        "mailboxes": {
            _SMSBOX_TO_FOLDER["rec"]: {
                "available": inbox_available,
                "messages": inbox_messages,
            },
            _SMSBOX_TO_FOLDER["sto"]: {
                "available": outbox_available,
                "messages": outbox_messages,
            },
        },
    }


def interpret_send_sms_result(status_code: int, response_text: str) -> dict[str, Any]:
    """Normalize the router's send-SMS response."""
    snippet = (response_text or "").strip()
    normalized = snippet.lower()
    success = (
        200 <= status_code < 400
        and "error" not in normalized
        and "failed" not in normalized
    )

    message = snippet or (
        "SMS sent."
        if success
        else "The router did not confirm the SMS send request."
    )

    return {
        "success": success,
        "status_code": status_code,
        "message": message,
    }


async def async_send_sms_message(
    hass: HomeAssistant,
    coordinator: Any,
    phone_number: str,
    message: str,
) -> dict[str, Any]:
    """Send an SMS and refresh the coordinator if the router accepts it."""
    status_code, response_text = await hass.async_add_executor_job(
        coordinator.api.send_sms,
        phone_number,
        message,
    )
    result = interpret_send_sms_result(status_code, response_text)
    if result["success"]:
        await coordinator.async_request_refresh()
    return result
