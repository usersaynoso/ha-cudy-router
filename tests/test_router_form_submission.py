"""Router form submission behavior."""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs

from tests.module_loader import load_cudy_module


router_module = load_cudy_module("router")


def _response(text: str, status_code: int = 200) -> SimpleNamespace:
    return SimpleNamespace(text=text, status_code=status_code, ok=(200 <= status_code < 300))


def test_submit_form_executes_embedded_apply_workflow(monkeypatch) -> None:
    """LuCI save/apply responses should trigger the follow-up service restart."""
    router = router_module.CudyRouter(None, "https://192.168.10.1", "user", "password")
    monkeypatch.setattr(router_module.time, "time", lambda: 1_700_000_000)
    monkeypatch.setattr(router_module.time, "sleep", lambda _: None)

    fetched_paths: list[str] = []
    posted_requests: list[tuple[str, dict[str, list[str]], str]] = []

    form_html = """
    <form action="/cgi-bin/luci/admin/network/gcom/config/apn">
      <input type="hidden" name="token" value="page-token" />
      <input type="hidden" name="timeclock" value="" />
      <input type="hidden" name="cbi.submit" value="1" />
      <input type="hidden" name="cbid.network.4g.disabled" value="0" />
      <button type="submit" name="cbi.apply">Save &amp; Apply</button>
    </form>
    """
    apply_html = """
    <script type="text/javascript">
    $.post('/cgi-bin/luci/admin/servicectl/restart/gcom', { token: 'apply-token' },
        function() {
            $.get('/cgi-bin/luci/admin/servicectl/status', function(data) {
                if( data == 'finish' ) {}
            });
        }
    );
    </script>
    """

    def fake_get(path: str, **kwargs):
        fetched_paths.append(path)
        if path == "admin/network/gcom/config/apn":
            return _response(form_html)
        if path == "admin/servicectl/status":
            return _response("finish")
        raise AssertionError(f"Unexpected GET path: {path}")

    def fake_post(path: str, **kwargs):
        payload = parse_qs(kwargs["data"], keep_blank_values=True)
        posted_requests.append((path, payload, kwargs["headers"]["Referer"]))
        if path == "admin/network/gcom/config/apn":
            return _response(apply_html)
        if path == "admin/servicectl/restart/gcom":
            return _response("ok")
        raise AssertionError(f"Unexpected POST path: {path}")

    monkeypatch.setattr(router, "_luci_get", fake_get)
    monkeypatch.setattr(router, "_luci_post", fake_post)

    result = router._submit_form(
        "admin/network/gcom/config/apn",
        {"cbid.network.4g.disabled": "1"},
        referer="https://192.168.10.1/cgi-bin/luci/admin/network/gcom/config",
    )

    assert result == (200, "Configuration applied.")
    assert fetched_paths == [
        "admin/network/gcom/config/apn",
        "admin/servicectl/status",
    ]
    assert [path for path, _, _ in posted_requests] == [
        "admin/network/gcom/config/apn",
        "admin/servicectl/restart/gcom",
    ]

    form_post = posted_requests[0][1]
    assert form_post["cbid.network.4g.disabled"] == ["1"]
    assert form_post["timeclock"] == ["1700000000"]
    assert form_post["cbi.apply"] == [""]

    apply_post = posted_requests[1][1]
    assert apply_post == {"token": ["apply-token"]}


def test_set_device_access_supports_vpn_toggle(monkeypatch) -> None:
    """Per-device access toggles should support the VPN control exposed by R700."""
    router = router_module.CudyRouter(None, "https://192.168.10.1", "user", "password")

    page_html = """
    <form class="form-horizontal" role="form" method="post">
      <input type="hidden" name="token" value="page-token" />
      <table class="table table-striped">
        <tbody>
          <tr id="cbi-table-1">
            <td>NICK</td>
            <td>192.168.10.20</td>
            <td>74:86:E2:10:22:61</td>
            <td>
              <input type="hidden" name="cbi.cbe.table.1.vpn" value="1" />
              <input type="hidden" id="cbid.table.1.vpn" name="cbid.table.1.vpn" value="1" />
              <i class="fa fa-toggle-on" onclick="cbi_switch_toggle(this, true, '/cgi-bin/luci/admin/network/devices/vpn?macaddr=74:86:E2:10:22:61&hostname=NICK&internet=1&vpn=1')"></i>
            </td>
          </tr>
        </tbody>
      </table>
    </form>
    """
    posted: list[tuple[str, dict[str, str], str]] = []

    monkeypatch.setattr(
        router,
        "get",
        lambda path, silent=False: page_html if path == "admin/network/devices/devlist?detail=1" else "",
    )

    def fake_post(path: str, **kwargs):
        posted.append((path, kwargs["data"], kwargs["headers"]["Referer"]))
        return _response("ok")

    monkeypatch.setattr(router, "_luci_post", fake_post)

    result = router.set_device_access(
        {"mac": "74:86:E2:10:22:61"},
        "vpn",
        False,
    )

    assert result == (200, "ok")
    assert posted == [
        (
            "admin/network/devices/vpn?macaddr=74:86:E2:10:22:61&hostname=NICK&internet=1&vpn=1",
            {
                "token": "page-token",
                "cbi.submit": "1",
                "cbi.toggle": "1",
                "cbi.cbe.table.1.vpn": "1",
                "cbid.table.1.vpn": "0",
            },
            "https://192.168.10.1/cgi-bin/luci/admin/network/devices/devlist",
        )
    ]
