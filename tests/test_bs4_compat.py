"""Compatibility coverage for BeautifulSoup imports."""

from __future__ import annotations

import importlib
import sys
import types

from tests.module_loader import load_cudy_module


def test_bs4_compat_injects_missing_warnings_module(monkeypatch) -> None:
    """A broken bs4 install missing bs4._warnings should still import."""
    for module_name in (
        "custom_components.cudy_router.bs4_compat",
        "bs4",
        "bs4._warnings",
    ):
        sys.modules.pop(module_name, None)

    fake_bs4 = types.SimpleNamespace(BeautifulSoup=object())
    call_count = 0

    def fake_import_module(name: str, package: str | None = None):
        nonlocal call_count
        assert package is None
        if name != "bs4":
            return importlib.__import__(name)
        call_count += 1
        if call_count == 1:
            raise ModuleNotFoundError("No module named 'bs4._warnings'", name="bs4._warnings")
        return fake_bs4

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    module = load_cudy_module("bs4_compat")

    assert module.BeautifulSoup is fake_bs4.BeautifulSoup
    warnings_module = sys.modules["bs4._warnings"]
    assert hasattr(warnings_module, "GuessedAtParserWarning")
    assert hasattr(warnings_module, "XMLParsedAsHTMLWarning")

