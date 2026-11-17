"""On-demand SMS helpers for the Cudy Router integration."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .const import DOMAIN, EVENT_SMS_RECEIVED, MODULE_SMS, OPTIONS_SHOW_SMS_PANEL_IN_SIDEBAR
from .features import supports_sms_feature
from .parser import parse_sms_detail, parse_sms_list, parse_sms_status

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


SMS_STATUS_PATH = "admin/network/gcom/sms/status"
SMS_PANEL_URL_PATH = "cudy-router-sms"
SMS_PANEL_COMPONENT_NAME = "cudy-router-sms-panel"
SMS_PANEL_STATIC_URL = "/cudy_router_static/cudy-router-sms-panel.js"
SMS_PANEL_STATIC_FILE = "frontend/cudy-router-sms-panel.js"

_SMSBOX_TO_FOLDER = {
    "rec": "inbox",
    "sto": "outbox",
}
_FOLDER_TO_SMSBOX = {folder: smsbox for smsbox, folder in _SMSBOX_TO_FOLDER.items()}

SMS_FOLDER_ALL = "all"
SMS_FOLDERS = (*_FOLDER_TO_SMSBOX, SMS_FOLDER_ALL)

# The router lists messages as e.g. "04/12/26, 08:41:23" (month/day/year).
_SMS_TIMESTAMP_FORMATS = (
    "%m/%d/%y, %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
)
_SMS_CFG_RE = re.compile(r"^cfg[0-9A-Za-z_]+$")


class SmsUnavailableError(RuntimeError):
    """Raised when the router does not return a readable SMS mailbox."""


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
    include: Callable[[dict[str, Any]], bool] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Fetch and enrich one SMS mailbox.

    ``include`` filters the list rows before their detail pages are fetched, so
    callers that only want some messages do not pay for the others.
    """
    list_html = await hass.async_add_executor_job(router.get, _sms_list_path(smsbox), True)
    messages = parse_sms_list(list_html, smsbox)
    if messages is None:
        return [], False

    if include is not None:
        messages = [message for message in messages if include(message)]

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


def interpret_delete_sms_result(status_code: int, response_text: str) -> dict[str, Any]:
    """Normalize the router's delete-SMS response."""
    snippet = (response_text or "").strip()
    normalized = snippet.lower()
    success = (
        200 <= status_code < 400
        and "error" not in normalized
        and "failed" not in normalized
    )
    return {
        "success": success,
        "status_code": status_code,
        "message": (
            "SMS deleted."
            if success
            else (snippet or "The router did not confirm deletion.")
        ),
    }


async def async_delete_sms_message(
    hass: HomeAssistant,
    coordinator: Any,
    cfg: str,
) -> dict[str, Any]:
    """Delete an SMS by cfg and refresh the coordinator if accepted."""
    status_code, response_text = await hass.async_add_executor_job(
        coordinator.api.delete_sms,
        cfg,
    )
    result = interpret_delete_sms_result(status_code, response_text)
    if result["success"]:
        await coordinator.async_request_refresh()
    return result


def sms_timestamp_to_iso(value: Any) -> str | None:
    """Convert a router SMS timestamp to an ISO 8601 string (router local time)."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in _SMS_TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    return None


def sms_message_payload(entry_id: str, message: dict[str, Any]) -> dict[str, Any]:
    """Return the automation-facing shape of one SMS message."""
    return {
        "entry_id": entry_id,
        "folder": message.get("folder"),
        "cfg": message.get("cfg"),
        "phone": message.get("phone"),
        "text": message.get("text") or message.get("preview") or "",
        "timestamp": message.get("timestamp"),
        "received_at": sms_timestamp_to_iso(message.get("timestamp")),
        "read": message.get("read"),
        "index": message.get("index"),
    }


def is_valid_sms_cfg(cfg: Any) -> bool:
    """Return whether a value looks like a router SMS cfg id."""
    return isinstance(cfg, str) and bool(_SMS_CFG_RE.match(cfg))


async def async_get_sms_messages(
    hass: HomeAssistant,
    coordinator: Any,
    folder: str = "inbox",
    unread_only: bool = False,
) -> dict[str, Any]:
    """Return full SMS messages for automations (the ``get_sms`` action)."""
    if folder not in SMS_FOLDERS:
        raise ValueError(f"Unknown SMS folder: {folder}")

    folders = tuple(_FOLDER_TO_SMSBOX) if folder == SMS_FOLDER_ALL else (folder,)
    include = (lambda message: message.get("read") is False) if unread_only else None
    entry_id = coordinator.config_entry.entry_id

    messages: list[dict[str, Any]] = []
    for name in folders:
        smsbox = _FOLDER_TO_SMSBOX[name]
        # Unread state only exists for received messages.
        if unread_only and smsbox != "rec":
            continue
        box_messages, available = await _async_fetch_sms_mailbox(
            coordinator.api,
            hass,
            smsbox,
            include,
        )
        if not available:
            raise SmsUnavailableError(f"Could not read the SMS {name} from the router.")
        messages.extend(sms_message_payload(entry_id, message) for message in box_messages)

    return {
        "entry_id": entry_id,
        "count": len(messages),
        "messages": messages,
    }


async def async_delete_sms_messages(
    hass: HomeAssistant,
    coordinator: Any,
    cfgs: list[str],
) -> dict[str, Any]:
    """Delete several SMS messages and refresh the coordinator once."""
    deleted: list[str] = []
    failed: list[dict[str, str]] = []

    for cfg in dict.fromkeys(cfgs):
        if not is_valid_sms_cfg(cfg):
            failed.append({"cfg": str(cfg), "message": "Invalid SMS cfg id."})
            continue
        status_code, response_text = await hass.async_add_executor_job(
            coordinator.api.delete_sms,
            cfg,
        )
        result = interpret_delete_sms_result(status_code, response_text)
        if result["success"]:
            deleted.append(cfg)
        else:
            failed.append({"cfg": cfg, "message": result["message"]})

    if deleted:
        await coordinator.async_request_refresh()

    return {"deleted": deleted, "failed": failed}


class SmsReceivedTracker:
    """Fire ``cudy_router_sms_received`` when new messages reach the inbox.

    The coordinator only polls SMS counts. When the inbox or unread count
    changes, the tracker reads the inbox list once, compares the message ids
    with the ones it has already seen, and fetches the full text only for the
    new ones. Messages already in the inbox when Home Assistant starts are
    recorded silently, so a restart does not replay old messages.
    """

    def __init__(self, hass: HomeAssistant, coordinator: Any) -> None:
        """Initialize the tracker."""
        self._hass = hass
        self._coordinator = coordinator
        self._known_cfgs: set[str] | None = None
        self._last_counts: tuple[int, int] | None = None
        self._lock = asyncio.Lock()

    def _current_counts(self) -> tuple[int, int]:
        summary = sms_summary_from_data(getattr(self._coordinator, "data", None))
        return summary["inbox"], summary["unread"]

    def needs_check(self) -> bool:
        """Return whether the polled counts changed since the last inbox read."""
        if not coordinator_supports_sms(self._coordinator):
            return False
        return self._current_counts() != self._last_counts

    async def async_check(self) -> list[dict[str, Any]]:
        """Read the inbox if needed and fire one event per new message."""
        if self._lock.locked() or not self.needs_check():
            return []

        async with self._lock:
            counts = self._current_counts()
            router = self._coordinator.api
            list_html = await self._hass.async_add_executor_job(
                router.get,
                _sms_list_path("rec"),
                True,
            )
            messages = parse_sms_list(list_html, "rec")
            if messages is None:
                # Try again on the next poll.
                return []

            current_cfgs = {message["cfg"] for message in messages if message.get("cfg")}
            first_read = self._known_cfgs is None
            known = self._known_cfgs or set()
            new_messages = [] if first_read else [
                message
                for message in messages
                if message.get("cfg") and message["cfg"] not in known
            ]

            entry_id = self._coordinator.config_entry.entry_id
            fired: list[dict[str, Any]] = []
            for message in new_messages:
                detail_html = await self._hass.async_add_executor_job(
                    router.get,
                    _sms_detail_path(message["cfg"], "rec"),
                    True,
                )
                detail = parse_sms_detail(detail_html) or {}
                enriched = dict(message)
                enriched.update(
                    {key: value for key, value in detail.items() if value not in (None, "")}
                )
                payload = sms_message_payload(entry_id, enriched)
                self._hass.bus.async_fire(EVENT_SMS_RECEIVED, payload)
                fired.append(payload)

            if fired:
                _LOGGER.debug("Fired %s for %d new SMS", EVENT_SMS_RECEIVED, len(fired))

            self._known_cfgs = current_cfgs
            self._last_counts = counts
            return fired
