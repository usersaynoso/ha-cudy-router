"""Tests for centralized router HTTP request behavior."""

from __future__ import annotations

from dataclasses import dataclass

import requests

from custom_components.cudy_router.router import CudyRouter


class _FakeCookies:
    def set(self, _name: str, _value: str) -> None:
        return


@dataclass
class _FakeResponse:
    status_code: int
    text: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class _FakeSession:
    def __init__(self, events: list[object]) -> None:
        self.events = events
        self.cookies = _FakeCookies()
        self.verify = False
        self.call_count = 0

    def request(self, **_kwargs):  # noqa: ANN003
        self.call_count += 1
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        return event


def test_get_retries_after_timeout() -> None:
    """GET should retry after timeout and eventually return response text."""
    router = CudyRouter(None, "https://router.local", "admin", "password")
    router._session = _FakeSession(
        [
            requests.exceptions.Timeout("timeout"),
            _FakeResponse(status_code=200, text="ok"),
        ]
    )

    assert router.get("admin/panel") == "ok"
    assert router._session.call_count == 2


def test_get_refreshes_auth_after_forbidden() -> None:
    """GET should re-authenticate once after a 403 and retry."""
    router = CudyRouter(None, "https://router.local", "admin", "password")
    router._session = _FakeSession(
        [
            _FakeResponse(status_code=403, text="forbidden"),
            _FakeResponse(status_code=200, text="retried"),
        ]
    )

    auth_calls = {"count": 0}

    def _auth() -> bool:
        auth_calls["count"] += 1
        router.auth_cookie = "cookie-token"
        return True

    router.authenticate = _auth

    assert router.get("admin/network/wan/status") == "retried"
    assert auth_calls["count"] == 1
    assert router._session.call_count == 2
