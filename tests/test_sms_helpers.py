"""Targeted tests for the SMS helper module."""

from __future__ import annotations

import asyncio
from pathlib import Path

from tests.module_loader import load_cudy_module


const = load_cudy_module("const")
load_cudy_module("model_names")
sms = load_cudy_module("sms")

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture_text(*parts: str) -> str:
    return FIXTURES.joinpath(*parts).read_text(encoding="utf-8")


class _FakeHass:
    async def async_add_executor_job(self, func, *args):
        return func(*args)


class _FakeRouter:
    def __init__(self, pages: dict[str, str], send_result: tuple[int, str] = (200, "Sent")) -> None:
        self._pages = pages
        self._send_result = send_result
        self.requests: list[tuple[str, bool]] = []

    def get(self, path: str, silent: bool = False) -> str:
        self.requests.append((path, silent))
        return self._pages.get(path, "")

    def send_sms(self, phone_number: str, message: str) -> tuple[int, str]:
        self.last_send = (phone_number, message)
        return self._send_result


class _FakeConfigEntry:
    def __init__(
        self,
        entry_id: str = "entry-1",
        title: str = "P5 Router",
        model: str = "P5",
    ) -> None:
        self.entry_id = entry_id
        self.title = title
        self.data = {
            "host": "http://192.168.10.1",
            "model": model,
        }
        self.options: dict[str, object] = {}


class _FakeCoordinator:
    def __init__(
        self,
        router: _FakeRouter,
        *,
        model: str = "P5",
        data: dict[str, object] | None = None,
    ) -> None:
        self.api = router
        self.config_entry = _FakeConfigEntry(model=model)
        self.data = data if data is not None else {
            const.MODULE_SMS: {
                "inbox_count": {"value": 1},
                "outbox_count": {"value": 1},
                "unread_count": {"value": 1},
            }
        }
        self.refresh_calls = 0

    async def async_request_refresh(self) -> None:
        self.refresh_calls += 1


def test_async_fetch_sms_data_reads_full_mailboxes_on_demand() -> None:
    """The helper should fetch inbox and outbox bodies only when requested."""
    router = _FakeRouter(
        {
            "admin/network/gcom/sms/status": _fixture_text("sms", "status.html"),
            "admin/network/gcom/sms/smslist?smsbox=rec&iface=4g": _fixture_text("sms", "inbox_list.html"),
            "admin/network/gcom/sms/smslist?smsbox=sto&iface=4g": _fixture_text("sms", "outbox_list.html"),
            "admin/network/gcom/sms/readsms?iface=4g&cfg=cfginbox1&smsbox=rec": _fixture_text(
                "sms",
                "inbox_detail.html",
            ),
            "admin/network/gcom/sms/readsms?iface=4g&cfg=cfgoutbox1&smsbox=sto": _fixture_text(
                "sms",
                "outbox_detail.html",
            ),
        }
    )
    coordinator = _FakeCoordinator(router)

    result = asyncio.run(sms.async_fetch_sms_data(_FakeHass(), coordinator))

    assert result["counts"] == {"inbox": 1, "outbox": 1, "unread": 1}
    assert result["mailboxes"]["inbox"]["available"] is True
    assert result["mailboxes"]["outbox"]["available"] is True
    assert result["mailboxes"]["inbox"]["messages"][0]["text"] == "Reminder: use *new* code [ALPHA].\nBring ID."
    assert result["mailboxes"]["outbox"]["messages"][0]["text"] == "Confirmed | back gate at 18:00."
    assert [path for path, _ in router.requests] == [
        "admin/network/gcom/sms/status",
        "admin/network/gcom/sms/smslist?smsbox=rec&iface=4g",
        "admin/network/gcom/sms/readsms?iface=4g&cfg=cfginbox1&smsbox=rec",
        "admin/network/gcom/sms/smslist?smsbox=sto&iface=4g",
        "admin/network/gcom/sms/readsms?iface=4g&cfg=cfgoutbox1&smsbox=sto",
    ]


def test_async_fetch_sms_data_reports_unavailable_mailboxes() -> None:
    """Blank list pages should surface as unavailable mailboxes, not as entity state."""
    router = _FakeRouter(
        {
            "admin/network/gcom/sms/status": _fixture_text("sms", "status.html"),
            "admin/network/gcom/sms/smslist?smsbox=rec&iface=4g": "",
            "admin/network/gcom/sms/smslist?smsbox=sto&iface=4g": "",
        }
    )
    coordinator = _FakeCoordinator(router)

    result = asyncio.run(sms.async_fetch_sms_data(_FakeHass(), coordinator))

    assert result["counts"] == {"inbox": 1, "outbox": 1, "unread": 1}
    assert result["mailboxes"]["inbox"] == {"available": False, "messages": []}
    assert result["mailboxes"]["outbox"] == {"available": False, "messages": []}


def test_async_send_sms_message_refreshes_on_success() -> None:
    """Successful sends should refresh the coordinator summary data."""
    coordinator = _FakeCoordinator(_FakeRouter({}, send_result=(200, "Queued successfully")))

    result = asyncio.run(
        sms.async_send_sms_message(
            _FakeHass(),
            coordinator,
            "+441234500003",
            "See you soon",
        )
    )

    assert result == {
        "success": True,
        "status_code": 200,
        "message": "Queued successfully",
    }
    assert coordinator.refresh_calls == 1


def test_async_send_sms_message_returns_failure_without_refresh() -> None:
    """Failed sends should keep the coordinator untouched and expose the router error."""
    coordinator = _FakeCoordinator(_FakeRouter({}, send_result=(500, "Send failed")))

    result = asyncio.run(
        sms.async_send_sms_message(
            _FakeHass(),
            coordinator,
            "+441234500004",
            "Status update",
        )
    )

    assert result == {
        "success": False,
        "status_code": 500,
        "message": "Send failed",
    }
    assert coordinator.refresh_calls == 0


def test_sidebar_visibility_defaults_to_enabled_for_sms_entries() -> None:
    """SMS-capable entries should show the panel link unless explicitly disabled."""
    coordinator = _FakeCoordinator(_FakeRouter({}))

    assert sms.coordinator_shows_sms_panel_in_sidebar(coordinator) is True

    coordinator.config_entry.options = {
        const.OPTIONS_SHOW_SMS_PANEL_IN_SIDEBAR: False,
    }

    assert sms.coordinator_shows_sms_panel_in_sidebar(coordinator) is False


def test_coordinator_supports_sms_requires_runtime_signal_for_unknown_models() -> None:
    """Unknown models should not expose SMS purely from the permissive fallback profile."""
    coordinator = _FakeCoordinator(
        _FakeRouter({}),
        model="Some Future Model V1.0",
        data={},
    )

    assert sms.coordinator_supports_sms(coordinator) is False

    coordinator.data = {
        const.MODULE_SMS: {
            "inbox_count": {"value": 0},
            "outbox_count": {"value": 0},
            "unread_count": {"value": 0},
        }
    }

    assert sms.coordinator_supports_sms(coordinator) is True
