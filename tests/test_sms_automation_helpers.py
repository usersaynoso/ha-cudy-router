"""Tests for the automation-facing SMS helpers (get_sms, delete_sms, received event)."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from tests.module_loader import load_cudy_module


const = load_cudy_module("const")
load_cudy_module("model_names")
sms = load_cudy_module("sms")

FIXTURES = Path(__file__).resolve().parent / "fixtures"

INBOX_LIST = "admin/network/gcom/sms/smslist?smsbox=rec&iface=4g"
OUTBOX_LIST = "admin/network/gcom/sms/smslist?smsbox=sto&iface=4g"


def _fixture_text(*parts: str) -> str:
    return FIXTURES.joinpath(*parts).read_text(encoding="utf-8")


def _detail_path(cfg: str, smsbox: str = "rec") -> str:
    return f"admin/network/gcom/sms/readsms?iface=4g&cfg={cfg}&smsbox={smsbox}"


def _inbox_with_second_message(read: bool) -> str:
    """Return the inbox fixture with an extra message (cfginbox2) appended."""
    html = _fixture_text("sms", "inbox_list.html")
    row = re.search(r'<tr id="cbi-table-1".*?</tr>', html, re.S).group(0)
    second = (
        row.replace("cbi-table-1", "cbi-table-2")
        .replace("cbid.table.1", "cbid.table.2")
        .replace('data-sid="1"', 'data-sid="2"')
        .replace(">1</p>", ">2</p>")
        .replace("cfginbox1", "cfginbox2")
        .replace("+441234500001", "+441234500002")
        .replace("04/12/26, 08:41:23", "04/12/26, 09:15:00")
        .replace("Reminder: use *new* code [ALPHA]...", "1234 estado")
    )
    if read:
        second = second.replace("icon-unreadsms text-primary", "icon-readsms")
    return html.replace(row, row + "\n" + second)


def _detail_for_second_message() -> str:
    return (
        _fixture_text("sms", "inbox_detail.html")
        .replace("+441234500001", "+441234500002")
        .replace("04/12/26, 08:41:23", "04/12/26, 09:15:00")
        .replace("Reminder: use *new* code [ALPHA].\nBring ID.", "1234 estado")
    )


class _FakeBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def async_fire(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))


class _FakeHass:
    def __init__(self) -> None:
        self.bus = _FakeBus()

    async def async_add_executor_job(self, func, *args):
        return func(*args)


class _FakeRouter:
    def __init__(self, pages: dict[str, str], delete_results: dict[str, tuple[int, str]] | None = None) -> None:
        self.pages = pages
        self.delete_results = delete_results or {}
        self.requests: list[str] = []
        self.deleted: list[str] = []

    def get(self, path: str, silent: bool = False) -> str:
        self.requests.append(path)
        return self.pages.get(path, "")

    def delete_sms(self, cfg: str) -> tuple[int, str]:
        self.deleted.append(cfg)
        return self.delete_results.get(cfg, (302, ""))


class _FakeConfigEntry:
    def __init__(self) -> None:
        self.entry_id = "entry-1"
        self.title = "LT700 Router"
        self.data = {"host": "http://192.168.10.1", "model": "LT500"}
        self.options: dict[str, object] = {}


class _FakeCoordinator:
    def __init__(self, router: _FakeRouter, inbox: int = 1, unread: int = 1) -> None:
        self.api = router
        self.config_entry = _FakeConfigEntry()
        self.refresh_calls = 0
        self.set_counts(inbox, unread)

    def set_counts(self, inbox: int, unread: int) -> None:
        self.data = {
            const.MODULE_SMS: {
                "inbox_count": {"value": inbox},
                "outbox_count": {"value": 1},
                "unread_count": {"value": unread},
            }
        }

    async def async_request_refresh(self) -> None:
        self.refresh_calls += 1


def test_sms_timestamp_to_iso_parses_router_format() -> None:
    assert sms.sms_timestamp_to_iso("04/12/26, 08:41:23") == "2026-04-12T08:41:23"
    assert sms.sms_timestamp_to_iso("2026-11-17 10:20:00") == "2026-11-17T10:20:00"
    assert sms.sms_timestamp_to_iso("not a date") is None
    assert sms.sms_timestamp_to_iso(None) is None


def test_get_sms_returns_full_text_for_inbox() -> None:
    router = _FakeRouter(
        {
            INBOX_LIST: _fixture_text("sms", "inbox_list.html"),
            _detail_path("cfginbox1"): _fixture_text("sms", "inbox_detail.html"),
        }
    )

    result = asyncio.run(sms.async_get_sms_messages(_FakeHass(), _FakeCoordinator(router)))

    assert result["entry_id"] == "entry-1"
    assert result["count"] == 1
    assert result["messages"] == [
        {
            "entry_id": "entry-1",
            "folder": "inbox",
            "cfg": "cfginbox1",
            "phone": "+441234500001",
            "text": "Reminder: use *new* code [ALPHA].\nBring ID.",
            "timestamp": "04/12/26, 08:41:23",
            "received_at": "2026-04-12T08:41:23",
            "read": False,
            "index": 1,
        }
    ]
    assert router.requests == [INBOX_LIST, _detail_path("cfginbox1")]


def test_get_sms_unread_only_skips_detail_pages_of_read_messages() -> None:
    router = _FakeRouter(
        {
            INBOX_LIST: _inbox_with_second_message(read=True),
            _detail_path("cfginbox1"): _fixture_text("sms", "inbox_detail.html"),
            _detail_path("cfginbox2"): _detail_for_second_message(),
        }
    )

    result = asyncio.run(
        sms.async_get_sms_messages(_FakeHass(), _FakeCoordinator(router), "all", True)
    )

    assert [message["cfg"] for message in result["messages"]] == ["cfginbox1"]
    # The read message's detail page and the outbox are never fetched.
    assert router.requests == [INBOX_LIST, _detail_path("cfginbox1")]


def test_get_sms_all_reads_both_mailboxes() -> None:
    router = _FakeRouter(
        {
            INBOX_LIST: _fixture_text("sms", "inbox_list.html"),
            OUTBOX_LIST: _fixture_text("sms", "outbox_list.html"),
            _detail_path("cfginbox1"): _fixture_text("sms", "inbox_detail.html"),
            _detail_path("cfgoutbox1", "sto"): _fixture_text("sms", "outbox_detail.html"),
        }
    )

    result = asyncio.run(sms.async_get_sms_messages(_FakeHass(), _FakeCoordinator(router), "all"))

    assert [(m["folder"], m["cfg"]) for m in result["messages"]] == [
        ("inbox", "cfginbox1"),
        ("outbox", "cfgoutbox1"),
    ]
    assert result["messages"][1]["text"] == "Confirmed | back gate at 18:00."


def test_get_sms_raises_when_mailbox_is_unreadable() -> None:
    router = _FakeRouter({INBOX_LIST: ""})

    with pytest.raises(sms.SmsUnavailableError):
        asyncio.run(sms.async_get_sms_messages(_FakeHass(), _FakeCoordinator(router)))


def test_get_sms_rejects_unknown_folder() -> None:
    with pytest.raises(ValueError):
        asyncio.run(
            sms.async_get_sms_messages(_FakeHass(), _FakeCoordinator(_FakeRouter({})), "spam")
        )


def test_delete_sms_deletes_each_once_and_refreshes_once() -> None:
    router = _FakeRouter({}, delete_results={"cfgbad": (500, "Delete failed")})
    coordinator = _FakeCoordinator(router)

    result = asyncio.run(
        sms.async_delete_sms_messages(
            _FakeHass(),
            coordinator,
            ["cfginbox1", "cfginbox1", "cfgbad", "../evil"],
        )
    )

    assert router.deleted == ["cfginbox1", "cfgbad"]
    assert result == {
        "deleted": ["cfginbox1"],
        "failed": [
            {"cfg": "cfgbad", "message": "Delete failed"},
            {"cfg": "../evil", "message": "Invalid SMS cfg id."},
        ],
    }
    assert coordinator.refresh_calls == 1


def test_delete_sms_does_not_refresh_when_nothing_was_deleted() -> None:
    coordinator = _FakeCoordinator(_FakeRouter({}))

    result = asyncio.run(sms.async_delete_sms_messages(_FakeHass(), coordinator, ["bad id"]))

    assert result["deleted"] == []
    assert coordinator.refresh_calls == 0


def test_received_tracker_seeds_silently_then_fires_for_new_messages() -> None:
    router = _FakeRouter(
        {
            INBOX_LIST: _fixture_text("sms", "inbox_list.html"),
            _detail_path("cfginbox2"): _detail_for_second_message(),
        }
    )
    coordinator = _FakeCoordinator(router, inbox=1, unread=1)
    hass = _FakeHass()
    tracker = sms.SmsReceivedTracker(hass, coordinator)

    # First read only records what is already in the inbox.
    assert tracker.needs_check() is True
    assert asyncio.run(tracker.async_check()) == []
    assert hass.bus.events == []

    # Same counts on the next poll: no router traffic at all.
    router.requests.clear()
    assert tracker.needs_check() is False
    assert asyncio.run(tracker.async_check()) == []
    assert router.requests == []

    # A new message arrives.
    router.pages[INBOX_LIST] = _inbox_with_second_message(read=False)
    coordinator.set_counts(inbox=2, unread=2)
    fired = asyncio.run(tracker.async_check())

    assert hass.bus.events == [
        (
            const.EVENT_SMS_RECEIVED,
            {
                "entry_id": "entry-1",
                "folder": "inbox",
                "cfg": "cfginbox2",
                "phone": "+441234500002",
                "text": "1234 estado",
                "timestamp": "04/12/26, 09:15:00",
                "received_at": "2026-04-12T09:15:00",
                "read": False,
                "index": 2,
            },
        )
    ]
    assert fired == [hass.bus.events[0][1]]
    # Only the new message's detail page is fetched.
    assert router.requests == [INBOX_LIST, _detail_path("cfginbox2")]


def test_received_tracker_retries_when_inbox_list_fails() -> None:
    router = _FakeRouter({INBOX_LIST: _fixture_text("sms", "inbox_list.html")})
    coordinator = _FakeCoordinator(router, inbox=1, unread=1)
    hass = _FakeHass()
    tracker = sms.SmsReceivedTracker(hass, coordinator)
    asyncio.run(tracker.async_check())

    router.pages[INBOX_LIST] = ""
    coordinator.set_counts(inbox=2, unread=2)
    assert asyncio.run(tracker.async_check()) == []
    # Counts were not recorded, so the next poll tries again.
    assert tracker.needs_check() is True

    router.pages[INBOX_LIST] = _inbox_with_second_message(read=False)
    router.pages[_detail_path("cfginbox2")] = _detail_for_second_message()
    assert [event["cfg"] for event in asyncio.run(tracker.async_check())] == ["cfginbox2"]


def test_received_tracker_ignores_deleted_messages() -> None:
    router = _FakeRouter({INBOX_LIST: _inbox_with_second_message(read=False)})
    coordinator = _FakeCoordinator(router, inbox=2, unread=2)
    hass = _FakeHass()
    tracker = sms.SmsReceivedTracker(hass, coordinator)
    asyncio.run(tracker.async_check())

    router.pages[INBOX_LIST] = _fixture_text("sms", "inbox_list.html")
    coordinator.set_counts(inbox=1, unread=1)

    assert asyncio.run(tracker.async_check()) == []
    assert hass.bus.events == []
