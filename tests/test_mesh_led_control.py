"""Mesh LED control: per-device LED form with a legacy endpoint fallback (PR #41)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from tests.module_loader import load_cudy_module


const = load_cudy_module("const")
router_module = load_cudy_module("router")
switch = load_cudy_module("switch")

LED_FORM_HTML = """
<form>
  <input type="hidden" name="token" value="led-token" />
  <input type="hidden" name="cbi.cbe.leds.1.leds" value="1" />
  <input type="checkbox" name="cbid.leds.1.leds" value="1" checked />
</form>
"""
LEGACY_BATLED_HTML = '<input type="hidden" name="token" value="legacy-token" />'


def _response(text: str = "", status_code: int = 200, headers: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(text=text, status_code=status_code, headers=headers or {})


def _router(monkeypatch, get_responses: dict, post_response):
    router = router_module.CudyRouter(None, "https://192.168.10.1", "user", "password")
    router.auth_cookie = "cookie"
    gets: list[str] = []
    posts: list[tuple[str, dict]] = []

    def fake_get(path: str, **kwargs):
        gets.append(path)
        return get_responses.get(path.split("?", 1)[0])

    def fake_post(path: str, **kwargs):
        posts.append((path, kwargs))
        return post_response

    monkeypatch.setattr(router, "_luci_get", fake_get)
    monkeypatch.setattr(router, "_luci_post", fake_post)
    return router, gets, posts


def test_mesh_led_uses_per_device_form_and_follows_apply_redirect(monkeypatch) -> None:
    router, gets, posts = _router(
        monkeypatch,
        {"admin/network/mesh/leds": _response(LED_FORM_HTML), "admin/network/mesh/apply": _response("ok")},
        _response(
            status_code=302,
            headers={"Location": "/cgi-bin/luci/admin/network/mesh/apply?command=leds&client=AABBCCDDEE01"},
        ),
    )

    status, _message = router.set_mesh_led("aa:bb:cc:dd:ee:01", False)

    assert status == 200
    assert posts[0][0] == "admin/network/mesh/leds?embedded=1&client=AABBCCDDEE01"
    assert posts[0][1]["data"] == {
        "token": "led-token",
        "cbi.submit": "1",
        "cbi.cbe.leds.1.leds": "1",
        "cbid.leds.1.leds": "0",
        "cbi.apply": "1",
    }
    assert gets[-1] == "admin/network/mesh/apply?command=leds&client=AABBCCDDEE01"


def test_main_router_led_falls_back_to_legacy_endpoint_without_led_form(monkeypatch) -> None:
    router, _gets, posts = _router(
        monkeypatch,
        {
            "admin/network/mesh/leds": _response("Not Found", status_code=404),
            "admin/network/mesh/batled": _response(LEGACY_BATLED_HTML),
        },
        _response(""),
    )

    status, _message = router.set_main_router_led(True)

    assert status == 200
    assert posts[0][0] == "admin/network/mesh/ledctl/000000000000"
    assert posts[0][1]["files"]["cbid.table.1.ledstatus"] == (None, "1")


def test_main_router_led_switch_is_created_without_reported_led_status(monkeypatch) -> None:
    config_entry = SimpleNamespace(
        entry_id="entry123",
        data={"model": "WR3000S V1.0"},
        options={},
        title="WR3000S",
        async_on_unload=lambda unload: None,
    )
    coordinator = SimpleNamespace(
        api=SimpleNamespace(),
        config_entry=config_entry,
        data={const.MODULE_MESH: {"mesh_devices": {}}},
        async_add_listener=lambda listener: (lambda: None),
    )
    hass = SimpleNamespace(data={const.DOMAIN: {"entry123": coordinator}})
    registry = SimpleNamespace(entities={}, async_get_entity_id=lambda *args: None, async_remove=lambda entity_id: None)
    added = []

    monkeypatch.setattr(switch, "async_get_entity_registry", lambda hass: registry)
    monkeypatch.setattr(switch, "async_cleanup_stale_mesh_entities", lambda *args: None)

    asyncio.run(switch.async_setup_entry(hass, config_entry, lambda entities: added.extend(entities)))

    assert "entry123-main-router-led" in {entity.unique_id for entity in added}
