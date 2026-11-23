"""Router.send_sms: single-step and two-step (store, then sendsms) firmware."""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs

from tests.module_loader import load_cudy_module


router_module = load_cudy_module("router")

PHONE = "+34600111222"
TEXT = "Hola ñ"
PHONE_HEX = PHONE.encode("utf-16-be").hex().upper()
TEXT_HEX = TEXT.encode("utf-16-be").hex().upper()

URLENCODED_FORM = """
<form method="post" action="/cgi-bin/luci/admin/network/gcom/sms/smsnew">
  <input type="hidden" name="token" value="tok" />
  <input name="cbid.smsnew.1.phone" />
</form>
"""

LT450_FORM = """
<form method="post" enctype="multipart/form-data" action="/cgi-bin/luci/admin/network/gcom/sms/smsnew?nomodal=&iface=4g">
  <input type="hidden" name="token" value="tok" />
  <input type="hidden" name="timeclock" value="" />
  <input name="cbid.smsnew.1.phone" />
</form>
"""


def _response(text: str = "", status_code: int = 200, location: str | None = None) -> SimpleNamespace:
    headers = {"Location": location} if location else {}
    return SimpleNamespace(text=text, status_code=status_code, headers=headers)


def _setup(monkeypatch, form_html: str, post_response: SimpleNamespace):
    router = router_module.CudyRouter(None, "https://192.168.10.1", "user", "password")
    calls: dict[str, list] = {"post": [], "request": []}

    def fake_get(path: str, **kwargs):
        assert path == "admin/network/gcom/sms/smsnew?nomodal=&iface=4g"
        return _response(form_html)

    def fake_post(path: str, **kwargs):
        calls["post"].append((path, kwargs))
        return post_response

    def fake_request(method: str, url: str, **kwargs):
        calls["request"].append((method, url, kwargs))
        return _response("OK")

    monkeypatch.setattr(router, "_luci_get", fake_get)
    monkeypatch.setattr(router, "_luci_post", fake_post)
    monkeypatch.setattr(router, "_request", fake_request)
    return router, calls


def test_single_step_firmware_sends_on_post_only(monkeypatch) -> None:
    """Firmware that sends on POST must not get a second (duplicate) send."""
    router, calls = _setup(monkeypatch, URLENCODED_FORM, _response("Sent", 200))

    assert router.send_sms(PHONE, TEXT) == (200, "Sent")

    assert len(calls["post"]) == 1
    _, kwargs = calls["post"][0]
    payload = parse_qs(kwargs["data"], keep_blank_values=True)
    assert payload["timeclock"] == ["0"]
    assert payload["cbid.smsnew.1.phone"] == [PHONE]
    assert kwargs["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert calls["request"] == []


def test_redirect_to_other_page_is_not_followed(monkeypatch) -> None:
    router, calls = _setup(
        monkeypatch,
        URLENCODED_FORM,
        _response("", 302, location="/cgi-bin/luci/admin/network/gcom/sms"),
    )

    assert router.send_sms(PHONE, TEXT)[0] == 302
    assert calls["request"] == []


def test_lt450_follows_sendsms_redirect_once(monkeypatch) -> None:
    """LT450 stores on POST and redirects to sendsms, which actually sends."""
    location = (
        f"https://192.168.10.1/cgi-bin/luci/admin/network/gcom/sms/sendsms"
        f"?iface=4g&phone={PHONE_HEX}&content={TEXT_HEX}"
    )
    router, calls = _setup(monkeypatch, LT450_FORM, _response("", 302, location=location))

    assert router.send_sms(PHONE, TEXT) == (200, "OK")

    _, kwargs = calls["post"][0]
    assert "data" not in kwargs or kwargs.get("data") is None
    fields = {key: value[1] for key, value in kwargs["files"].items()}
    assert fields["timeclock"] == ""
    assert fields["cbid.smsnew.1.content"] == TEXT
    assert "Content-Type" not in kwargs["headers"]

    assert len(calls["request"]) == 1
    method, url, request_kwargs = calls["request"][0]
    assert method == "GET"
    assert url == (
        "https://192.168.10.1/cgi-bin/luci/admin/network/gcom/sms/sendsms"
        f"?iface=4g&phone={PHONE_HEX}&content={TEXT_HEX}"
    )
    assert request_kwargs["retries"] == 0
    assert request_kwargs["reauth_on_403"] is False


def test_lt450_script_flow_builds_hex_sendsms_request(monkeypatch) -> None:
    """When the POST response triggers sendsms from script, build the same GET."""
    body = "<script>location.href='/cgi-bin/luci/admin/network/gcom/sms/sendsms?iface=4g&phone='+p</script>"
    router, calls = _setup(monkeypatch, LT450_FORM, _response(body, 200))

    assert router.send_sms(PHONE, TEXT) == (200, "OK")

    assert len(calls["request"]) == 1
    _, url, request_kwargs = calls["request"][0]
    assert url.endswith(
        f"admin/network/gcom/sms/sendsms?iface=4g&phone={PHONE_HEX}&content={TEXT_HEX}"
    )
    assert request_kwargs["retries"] == 0


def test_sendsms_failure_is_reported(monkeypatch) -> None:
    location = "/cgi-bin/luci/admin/network/gcom/sms/sendsms?iface=4g&phone=00&content=00"
    router, calls = _setup(monkeypatch, LT450_FORM, _response("", 302, location=location))
    monkeypatch.setattr(router, "_request", lambda *args, **kwargs: None)

    status, message = router.send_sms(PHONE, TEXT)

    assert status == 0
    assert "did not confirm" in message


def test_hex_encoding_matches_web_ui() -> None:
    assert router_module._encode_sms_hex("+1") == "002B0031"
    assert router_module._encode_sms_hex("é") == "00E9"
