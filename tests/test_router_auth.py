"""Authentication flow coverage for browser-style Cudy logins."""

from __future__ import annotations

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
