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


def test_bs4_compat_injects_missing_deprecation_module(monkeypatch) -> None:
    """A broken bs4 install missing bs4._deprecation should still import."""
    for module_name in (
        "custom_components.cudy_router.bs4_compat",
        "bs4",
        "bs4._deprecation",
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
            raise ModuleNotFoundError("No module named 'bs4._deprecation'", name="bs4._deprecation")
        return fake_bs4

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    module = load_cudy_module("bs4_compat")

    assert module.BeautifulSoup is fake_bs4.BeautifulSoup
    deprecation_module = sys.modules["bs4._deprecation"]
    assert hasattr(deprecation_module, "_deprecated")
    assert hasattr(deprecation_module, "_deprecated_alias")


def test_bs4_compat_repairs_missing_top_level_public_exports(monkeypatch) -> None:
    """Broken bs4 installs missing top-level aliases should be repaired after import."""
    for module_name in (
        "custom_components.cudy_router.bs4_compat",
        "bs4",
        "bs4.element",
        "bs4.filter",
        "bs4.css",
        "bs4.dammit",
        "bs4.exceptions",
    ):
        sys.modules.pop(module_name, None)

    class FakeBS4(types.ModuleType):
        BeautifulSoup = object()

    fake_bs4 = FakeBS4("bs4")
    fake_element = types.SimpleNamespace(
        Tag=object(),
        Comment=object(),
        Declaration=object(),
        ProcessingInstruction=object(),
        ResultSet=object(),
        Script=object(),
        Stylesheet=object(),
        TemplateString=object(),
        CData=object(),
        Doctype=object(),
    )
    fake_filter = types.SimpleNamespace(ElementFilter=object())
    fake_css = types.SimpleNamespace(CSS=object())
    fake_dammit = types.SimpleNamespace(UnicodeDammit=object())
    fake_exceptions = types.SimpleNamespace(
        FeatureNotFound=object(),
        ParserRejectedMarkup=object(),
        StopParsing=object(),
    )

    def fake_import_module(name: str, package: str | None = None):
        assert package is None
        modules = {
            "bs4": fake_bs4,
            "bs4.element": fake_element,
            "bs4.filter": fake_filter,
            "bs4.css": fake_css,
            "bs4.dammit": fake_dammit,
            "bs4.exceptions": fake_exceptions,
        }
        if name in modules:
            return modules[name]
        return importlib.__import__(name)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    module = load_cudy_module("bs4_compat")

    assert module.BeautifulSoup is fake_bs4.BeautifulSoup
    assert fake_bs4.Tag is fake_element.Tag
    assert fake_bs4.ResultSet is fake_element.ResultSet
    assert fake_bs4.CSS is fake_css.CSS
    assert fake_bs4.UnicodeDammit is fake_dammit.UnicodeDammit
    assert fake_bs4.FeatureNotFound is fake_exceptions.FeatureNotFound


def test_bs4_compat_adds_dynamic_getattr_fallback_for_missing_exports(monkeypatch) -> None:
    """Missing bs4 aliases should still resolve later through module __getattr__."""
    for module_name in (
        "custom_components.cudy_router.bs4_compat",
        "bs4",
        "bs4.element",
    ):
        sys.modules.pop(module_name, None)

    class FakeBS4(types.ModuleType):
        BeautifulSoup = object()

    fake_bs4 = FakeBS4("bs4")
    fake_element = types.SimpleNamespace(Tag=object())
    import_calls: list[str] = []

    def fake_import_module(name: str, package: str | None = None):
        assert package is None
        import_calls.append(name)
        if name == "bs4":
            return fake_bs4
        if name == "bs4.element":
            return fake_element
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    load_cudy_module("bs4_compat")

    delattr(fake_bs4, "Tag")

    assert fake_bs4.__getattr__("Tag") is fake_element.Tag
    assert fake_bs4.Tag is fake_element.Tag
    assert "bs4.element" in import_calls


def test_bs4_compat_repairs_stale_soupsieve_bs4_reference(monkeypatch) -> None:
    """A stale soupsieve import should use the repaired bs4 module."""
    patched_modules = (
        "custom_components.cudy_router.bs4_compat",
        "bs4",
        "bs4.element",
        "bs4.filter",
        "bs4.css",
        "bs4.dammit",
        "bs4.exceptions",
        "soupsieve",
        "soupsieve.css_match",
    )
    for module_name in patched_modules:
        sys.modules.pop(module_name, None)

    class FakeBS4(types.ModuleType):
        BeautifulSoup = object()

    stale_bs4 = types.ModuleType("bs4")
    fake_bs4 = FakeBS4("bs4")
    fake_element = types.SimpleNamespace(
        Tag=object(),
        Comment=object(),
        Declaration=object(),
        ProcessingInstruction=object(),
        ResultSet=object(),
        Script=object(),
        Stylesheet=object(),
        TemplateString=object(),
        CData=object(),
        Doctype=object(),
    )
    fake_filter = types.SimpleNamespace(ElementFilter=object())
    fake_css = types.SimpleNamespace(CSS=object())
    fake_dammit = types.SimpleNamespace(UnicodeDammit=object())
    fake_exceptions = types.SimpleNamespace(
        FeatureNotFound=object(),
        ParserRejectedMarkup=object(),
        StopParsing=object(),
    )
    stale_soupsieve = types.ModuleType("soupsieve.css_match")
    stale_soupsieve.bs4 = stale_bs4
    sys.modules["soupsieve.css_match"] = stale_soupsieve

    def fake_import_module(name: str, package: str | None = None):
        assert package is None
        modules = {
            "bs4": fake_bs4,
            "bs4.element": fake_element,
            "bs4.filter": fake_filter,
            "bs4.css": fake_css,
            "bs4.dammit": fake_dammit,
            "bs4.exceptions": fake_exceptions,
        }
        if name in modules:
            return modules[name]
        return importlib.__import__(name)

    try:
        monkeypatch.setattr(importlib, "import_module", fake_import_module)

        load_cudy_module("bs4_compat")

        assert stale_soupsieve.bs4 is fake_bs4
        assert stale_soupsieve.bs4.Tag is fake_element.Tag
    finally:
        for module_name in patched_modules:
            sys.modules.pop(module_name, None)
