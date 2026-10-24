"""Runtime coverage for the main-router LuCI reboot workflow."""

from __future__ import annotations

from types import SimpleNamespace

from tests.module_loader import load_cudy_module


router_module = load_cudy_module("router")


def _response(status_code: int, location: str = "") -> SimpleNamespace:
    return SimpleNamespace(status_code=status_code, headers={"Location": location}, text="")


def test_reboot_uses_cudys_empty_multipart_action_and_apply_workflow(monkeypatch) -> None:
    """The real Cudy UI posts directly to reboot/reboot, not a CBI form."""
    api = router_module.CudyRouter(None, "http://192.168.10.1", "user", "password")
    calls: list[tuple[str, str, object]] = []

    def fake_post(path: str, **kwargs):
        calls.append(("POST", path, kwargs))
        return _response(302, "/cgi-bin/luci/admin/system/reboot")

    def fake_get(path: str, **kwargs):
        calls.append(("GET", path, kwargs))
        return _response(200)

    monkeypatch.setattr(api, "_luci_post", fake_post)
    monkeypatch.setattr(api, "_luci_get", fake_get)

    assert api.reboot_router() == (200, "Router reboot initiated")
    assert [(method, path) for method, path, _ in calls] == [
        ("POST", "admin/system/reboot/reboot"),
        ("GET", "admin/system/reboot"),
        ("GET", "admin/system/reboot/apply"),
    ]
    request = calls[0][2]
    assert request["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert request["headers"]["Origin"] == "http://192.168.10.1"
    assert request["data"].endswith(b"--\r\n")


def test_reboot_rejects_a_redirect_to_an_unrelated_page(monkeypatch) -> None:
    """Do not claim success unless the reboot action gave its expected redirect."""
    api = router_module.CudyRouter(None, "http://192.168.10.1", "user", "password")
    monkeypatch.setattr(api, "_luci_post", lambda *_args, **_kwargs: _response(302, "/cgi-bin/luci/admin/panel"))

    status, message = api.reboot_router()

    assert status == 0
    assert "Unexpected redirect" in message
