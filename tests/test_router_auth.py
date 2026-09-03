"""Authentication flow coverage for browser-style Cudy logins."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from types import SimpleNamespace
from urllib.parse import parse_qs

from tests.module_loader import load_cudy_module


router_module = load_cudy_module("router")


def _response(
    text: str,
    status_code: int = 200,
    *,
    headers: dict[str, str] | None = None,
    url: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        status_code=status_code,
        ok=(200 <= status_code < 300),
        headers=headers or {},
        url=url,
    )


def _requests_cookie_jar():
    return router_module.requests.cookies.RequestsCookieJar()


def test_request_logs_slow_router_endpoint_with_redacted_query(
    monkeypatch,
    caplog,
) -> None:
    """Slow router requests should identify the endpoint without leaking client data."""
    router = router_module.CudyRouter(None, "http://192.168.10.1", "admin", "demo")

    class FakeSession:
        def __init__(self) -> None:
            self.cookies = _requests_cookie_jar()

        def request(self, **kwargs):
            return _response("ok", url=kwargs["url"])

    monkeypatch.setattr(router, "_get_session", lambda: FakeSession())
    elapsed_times = iter([100.0, 112.5])
    monkeypatch.setattr(router_module.time, "monotonic", lambda: next(elapsed_times))

    caplog.set_level(logging.WARNING, logger=router_module._LOGGER.name)

    response = router._request(
        "GET",
        "http://192.168.10.1/cgi-bin/luci/admin/network/mesh/client/devstatus?embedded=&client=80AFCAF259A1&hostname=LivingRoom",
        timeout=15,
        headers={},
        silent=True,
    )

    assert response is not None
    assert "Slow router request: GET /cgi-bin/luci/admin/network/mesh/client/devstatus" in caplog.text
    assert "client=%3Credacted%3E" in caplog.text
    assert "hostname=%3Credacted%3E" in caplog.text
    assert "80AFCAF259A1" not in caplog.text
    assert "LivingRoom" not in caplog.text


def test_authenticate_new_discovers_root_login_form_and_posts_browser_payload(
    monkeypatch,
) -> None:
    """WR1200-style routers should use the root login form and browser payload."""
    router = router_module.CudyRouter(None, "http://192.168.10.1", "admin", "demo")
    session = SimpleNamespace(cookies=_requests_cookie_jar())
    monkeypatch.setattr(router, "_get_session", lambda: session)
    monkeypatch.setattr(router_module.time, "time", lambda: 1_700_000_000)

    login_html = """
    <html>
      <body>
        <form method="post" action="/cgi-bin/luci/">
          <input type="hidden" name="_csrf" value="csrf-token" />
          <input type="hidden" name="token" value="page-token" />
          <input type="hidden" name="salt" value="page-salt" />
          <input type="hidden" name="luci_username" value="admin" />
          <input type="hidden" name="luci_password" value="" />
          <select name="luci_language">
            <option value="auto" selected="selected">Auto (English)</option>
            <option value="en">English</option>
          </select>
          <input type="password" id="luci_password2" />
        </form>
        <footer><span>HW: WR1200 V2.0</span></footer>
      </body>
    </html>
    """

    calls: list[tuple[str, str]] = []

    def fake_request(method: str, url: str, **kwargs):
        calls.append((method, url))
        if method == "GET":
            assert url == "http://192.168.10.1/"
            assert kwargs["allow_redirects"] is True
            return _response(login_html, url=url)

        if method == "POST":
            assert url == "http://192.168.10.1/cgi-bin/luci/"
            assert kwargs["allow_redirects"] is True
            payload = parse_qs(kwargs["data"], keep_blank_values=True)
            assert payload["_csrf"] == ["csrf-token"]
            assert payload["token"] == ["page-token"]
            assert payload["salt"] == ["page-salt"]
            assert payload["luci_username"] == ["admin"]
            assert payload["luci_language"] == ["auto"]
            assert payload["timeclock"] == ["1700000000"]
            assert payload["zonename"][0]
            assert payload["luci_password"] == [
                router_module._compute_luci_password("demo", "page-salt", "page-token")
            ]
            session.cookies.set("sysauth", "cookie-value")
            return _response("ok", url="http://192.168.10.1/cgi-bin/luci/admin/panel")

        raise AssertionError(f"Unexpected request: {method} {url}")

    monkeypatch.setattr(router, "_request", fake_request)

    assert router._authenticate_new() is True
    assert router.auth_cookie == "cookie-value"
    assert calls == [
        ("GET", "http://192.168.10.1/"),
        ("POST", "http://192.168.10.1/cgi-bin/luci/"),
    ]


def test_get_model_falls_back_to_luci_login_page_when_root_has_no_form(monkeypatch) -> None:
    """Model discovery should retry /cgi-bin/luci/ when the root page is only a redirect stub."""
    router = router_module.CudyRouter(None, "http://192.168.10.1", "admin", "demo")
    session = SimpleNamespace(cookies=_requests_cookie_jar())
    monkeypatch.setattr(router, "_get_session", lambda: session)

    redirect_stub = """
    <html>
      <head>
        <meta http-equiv="refresh" content="0; URL=cgi-bin/luci/" />
      </head>
    </html>
    """
    login_html = """
    <html>
      <body>
        <form method="post" action="/cgi-bin/luci/">
          <input type="hidden" name="token" value="page-token" />
          <input type="hidden" name="salt" value="page-salt" />
          <input type="hidden" name="luci_password" value="" />
          <input type="password" id="luci_password2" />
        </form>
        <footer><span>HW: P5 V1.1</span></footer>
      </body>
    </html>
    """

    calls: list[tuple[str, str, bool]] = []

    def fake_request(method: str, url: str, **kwargs):
        calls.append((method, url, kwargs["allow_redirects"]))
        if method != "GET":
            raise AssertionError(f"Unexpected method: {method}")
        if url == "http://192.168.10.1/":
            return _response(redirect_stub, url=url)
        if url == "http://192.168.10.1/cgi-bin/luci/":
            return _response(login_html, url=url)
        raise AssertionError(f"Unexpected GET URL: {url}")

    monkeypatch.setattr(router, "_request", fake_request)

    assert router.get_model() == "P5 V1.1"
    assert calls == [
        ("GET", "http://192.168.10.1/", True),
        ("GET", "http://192.168.10.1/cgi-bin/luci/", True),
    ]


def test_authenticate_new_accepts_authenticated_panel_without_cookie(monkeypatch) -> None:
    """Routers that finalize auth after a redirect should pass via panel verification."""
    router = router_module.CudyRouter(None, "http://192.168.10.1", "admin", "demo")
    session = SimpleNamespace(cookies=_requests_cookie_jar())
    monkeypatch.setattr(router, "_get_session", lambda: session)
    monkeypatch.setattr(router_module.time, "time", lambda: 1_700_000_000)

    login_html = """
    <html>
      <body>
        <form method="post" action="/cgi-bin/luci/">
          <input type="hidden" name="token" value="page-token" />
          <input type="hidden" name="salt" value="page-salt" />
          <input type="hidden" name="luci_password" value="" />
          <select name="luci_language">
            <option value="en" selected="selected">English</option>
          </select>
          <input type="password" id="luci_password2" />
        </form>
      </body>
    </html>
    """
    panel_html = "<html><body><h1>Advanced Settings</h1></body></html>"

    calls: list[tuple[str, str]] = []

    def fake_request(method: str, url: str, **kwargs):
        calls.append((method, url))
        if method == "GET" and url == "http://192.168.10.1/":
            return _response(login_html, url=url)
        if method == "POST" and url == "http://192.168.10.1/cgi-bin/luci/":
            return _response("", status_code=200, url="http://192.168.10.1/cgi-bin/luci/admin/panel")
        if method == "GET" and url == "http://192.168.10.1/cgi-bin/luci/admin/panel":
            assert kwargs["allow_redirects"] is True
            return _response(panel_html, url=url)
        raise AssertionError(f"Unexpected request: {method} {url}")

    monkeypatch.setattr(router, "_request", fake_request)

    assert router._authenticate_new() is True
    assert router.auth_cookie is None
    assert calls == [
        ("GET", "http://192.168.10.1/"),
        ("POST", "http://192.168.10.1/cgi-bin/luci/"),
        ("GET", "http://192.168.10.1/cgi-bin/luci/admin/panel"),
    ]


def test_authenticate_new_falls_back_from_https_to_http_and_accepts_http_cookie(
    monkeypatch,
) -> None:
    """Routers stored as https should still authenticate when the login form only works over http."""
    router = router_module.CudyRouter(None, "192.168.10.1", "admin", "demo")
    session = SimpleNamespace(cookies=_requests_cookie_jar())
    monkeypatch.setattr(router, "_get_session", lambda: session)
    monkeypatch.setattr(router_module.time, "time", lambda: 1_700_000_000)

    login_html = """
    <html>
      <body>
        <form method="post" action="/cgi-bin/luci/">
          <input type="hidden" name="token" value="page-token" />
          <input type="hidden" name="salt" value="page-salt" />
          <input type="hidden" name="luci_password" value="" />
          <select name="luci_language">
            <option value="en" selected="selected">English</option>
          </select>
          <input type="password" id="luci_password2" />
        </form>
      </body>
    </html>
    """

    calls: list[tuple[str, str]] = []

    def fake_absolute_request(method: str, url: str, **kwargs):
        calls.append((method, url))
        if method == "GET" and url in {
            "https://192.168.10.1/",
            "https://192.168.10.1/cgi-bin/luci/",
        }:
            return None
        if method == "GET" and url == "http://192.168.10.1/":
            return _response(login_html, url=url)
        if method == "POST" and url == "http://192.168.10.1/cgi-bin/luci/":
            session.cookies.set("sysauth_http", "cookie-value")
            return _response("ok", url="http://192.168.10.1/cgi-bin/luci/admin/panel")
        raise AssertionError(f"Unexpected request: {method} {url}")

    monkeypatch.setattr(router, "_absolute_request", fake_absolute_request)

    assert router._authenticate_new() is True
    assert router.base_url == "http://192.168.10.1"
    assert router.auth_cookie_name == "sysauth_http"
    assert router.auth_cookie == "cookie-value"
    assert calls == [
        ("GET", "https://192.168.10.1/"),
        ("GET", "https://192.168.10.1/cgi-bin/luci/"),
        ("GET", "http://192.168.10.1/"),
        ("POST", "http://192.168.10.1/cgi-bin/luci/"),
    ]


def test_extract_session_auth_cookie_accepts_sysauth_http_header() -> None:
    """Legacy/new auth should accept LuCI's newer scheme-specific cookie names."""
    router = router_module.CudyRouter(None, "http://192.168.10.1", "admin", "demo")
    session = SimpleNamespace(cookies=_requests_cookie_jar())
    response = _response(
        "",
        headers={"set-cookie": "sysauth_http=http-cookie; path=/cgi-bin/luci/; HttpOnly"},
        url="http://192.168.10.1/cgi-bin/luci/",
    )

    # Use the helper against an empty session so the response header parsing path is exercised.
    router._session = session

    assert router._extract_session_auth_cookie(response) is True
    assert router.auth_cookie_name == "sysauth_http"
    assert router.auth_cookie == "http-cookie"


def test_authenticate_new_uses_dynamic_luci_challenge_without_inline_salt_or_token(
    monkeypatch,
) -> None:
    """New LuCI forms should request a challenge and submit an RSA-encrypted proof."""
    router = router_module.CudyRouter(None, "http://192.168.10.1", "admin", "demo")
    session = SimpleNamespace(cookies=_requests_cookie_jar())
    monkeypatch.setattr(router, "_get_session", lambda: session)
    monkeypatch.setattr(router_module.time, "time", lambda: 1_700_000_000)

    login_html = """
    <form method="post" action="/cgi-bin/luci/">
      <input type="hidden" name="_csrf" value="csrf-token" />
      <input type="hidden" name="luci_username" value="admin" />
      <input type="hidden" name="luci_password" value="" />
      <input type="password" id="luci_password2" />
    </form>
    """
    challenge = {
        "key": base64.b64encode(b"synthetic-public-key").decode(),
        "nonce": "nonce-value",
        "salt": "salt-value",
        "kdfiter": 0,
        "cipher": "RSA",
        "encode": "base64",
    }
    encrypted_inputs: list[bytes] = []

    class FakePublicKey:
        def encrypt(self, value, algorithm):
            encrypted_inputs.append(value)
            assert isinstance(algorithm, router_module.padding.OAEP)
            return b"encrypted-proof"

    monkeypatch.setattr(
        router_module.serialization,
        "load_pem_public_key",
        lambda value: FakePublicKey(),
    )

    def fake_absolute_request(method: str, url: str, **kwargs):
        if method == "GET":
            return _response(login_html, url=url)
        if url.endswith("/admin/login"):
            assert kwargs["headers"]["X-Requested-With"] == "XMLHttpRequest"
            assert parse_qs(kwargs["data"]) == {"username": ["admin"]}
            return _response(json.dumps(challenge), url=url)
        if method == "POST" and url.endswith("/cgi-bin/luci/"):
            payload = parse_qs(kwargs["data"], keep_blank_values=True)
            assert payload["_csrf"] == ["csrf-token"]
            assert payload["luci_username"] == ["admin"]
            assert payload["luci_password"] == [base64.b64encode(b"encrypted-proof").decode()]
            assert payload["timeclock"] == ["1700000000"]
            session.cookies.set("sysauth", "cookie-value")
            return _response("ok", url=url)
        raise AssertionError(f"Unexpected request: {method} {url}")

    monkeypatch.setattr(router, "_absolute_request", fake_absolute_request)

    assert router._authenticate_new() is True
    password_hash = hashlib.sha256(b"demosalt-value").hexdigest()
    assert encrypted_inputs == [
        hashlib.sha256(f"{password_hash}nonce-value".encode()).hexdigest().encode()
    ]
    assert router.auth_cookie == "cookie-value"


def test_dynamic_luci_challenge_uses_pbkdf2_when_iterations_are_positive(monkeypatch) -> None:
    """Dynamic LuCI challenges with iterations should derive the password via PBKDF2."""
    router = router_module.CudyRouter(None, "http://192.168.10.1", "admin", "demo")
    form = router_module._LoginFormInfo(
        page_url="http://192.168.10.1/cgi-bin/luci/",
        action_url="http://192.168.10.1/cgi-bin/luci/",
        html="",
        csrf="csrf-token",
        token="",
        salt="",
        language="en",
    )
    challenge = {
        "key": base64.b64encode(b"synthetic-public-key").decode(),
        "nonce": "nonce-value",
        "salt": "00ff",
        "kdfiter": 123,
    }
    kdf_arguments: dict[str, object] = {}
    encrypted_inputs: list[bytes] = []

    class FakeKdf:
        def __init__(self, **kwargs):
            kdf_arguments.update(kwargs)

        def derive(self, password: bytes) -> bytes:
            assert password == b"demo"
            return b"\xab" * 32

    class FakePublicKey:
        def encrypt(self, value, algorithm):
            encrypted_inputs.append(value)
            return b"encrypted-proof"

    monkeypatch.setattr(router_module, "PBKDF2HMAC", FakeKdf)
    monkeypatch.setattr(router_module.serialization, "load_pem_public_key", lambda value: FakePublicKey())
    monkeypatch.setattr(router, "_extract_session_auth_cookie", lambda response: True)

    calls = 0

    def fake_absolute_request(method: str, url: str, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _response(json.dumps(challenge), url=url)
        return _response("ok", url=url)

    monkeypatch.setattr(router, "_absolute_request", fake_absolute_request)

    assert router._authenticate_dynamic_luci(form) is True
    assert kdf_arguments["salt"] == bytes.fromhex("00ff")
    assert kdf_arguments["iterations"] == 123
    password_hash = (b"\xab" * 32).hex()
    assert encrypted_inputs == [
        hashlib.sha256(f"{password_hash}nonce-value".encode()).hexdigest().encode()
    ]
