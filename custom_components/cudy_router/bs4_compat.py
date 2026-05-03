"""Compatibility wrapper for importing BeautifulSoup in Home Assistant."""

from __future__ import annotations

import importlib
import functools
import sys
import types
import warnings
from typing import Any

_BS4_PUBLIC_EXPORTS = {
    "Tag": ("bs4.element", "Tag"),
    "Comment": ("bs4.element", "Comment"),
    "Declaration": ("bs4.element", "Declaration"),
    "ProcessingInstruction": ("bs4.element", "ProcessingInstruction"),
    "ResultSet": ("bs4.element", "ResultSet"),
    "Script": ("bs4.element", "Script"),
    "Stylesheet": ("bs4.element", "Stylesheet"),
    "TemplateString": ("bs4.element", "TemplateString"),
    "CData": ("bs4.element", "CData"),
    "Doctype": ("bs4.element", "Doctype"),
    "ElementFilter": ("bs4.filter", "ElementFilter"),
    "CSS": ("bs4.css", "CSS"),
    "UnicodeDammit": ("bs4.dammit", "UnicodeDammit"),
    "FeatureNotFound": ("bs4.exceptions", "FeatureNotFound"),
    "ParserRejectedMarkup": ("bs4.exceptions", "ParserRejectedMarkup"),
    "StopParsing": ("bs4.exceptions", "StopParsing"),
}


def _install_bs4_warnings_shim() -> None:
    """Provide the internal bs4._warnings module if a broken install lacks it."""
    if "bs4._warnings" in sys.modules:
        return

    module = types.ModuleType("bs4._warnings")

    class GuessedAtParserWarning(UserWarning):
        """Warning used when BeautifulSoup has to guess a parser."""

    class UnusualUsageWarning(UserWarning):
        """Superclass for BeautifulSoup's unusual-usage warnings."""

    class MarkupResemblesLocatorWarning(UnusualUsageWarning):
        """Warning used when markup looks like a URL or filename."""

    class AttributeResemblesVariableWarning(UnusualUsageWarning, SyntaxWarning):
        """Warning used when an attribute name looks like a typo."""

    class XMLParsedAsHTMLWarning(UnusualUsageWarning):
        """Warning used when XML is parsed with an HTML parser."""

    module.GuessedAtParserWarning = GuessedAtParserWarning
    module.UnusualUsageWarning = UnusualUsageWarning
    module.MarkupResemblesLocatorWarning = MarkupResemblesLocatorWarning
    module.AttributeResemblesVariableWarning = AttributeResemblesVariableWarning
    module.XMLParsedAsHTMLWarning = XMLParsedAsHTMLWarning
    sys.modules["bs4._warnings"] = module


def _install_bs4_deprecation_shim() -> None:
    """Provide the internal bs4._deprecation module if a broken install lacks it."""
    if "bs4._deprecation" in sys.modules:
        return

    module = types.ModuleType("bs4._deprecation")

    def _deprecated_alias(old_name: str, new_name: str, version: str):
        @property
        def alias(self):
            warnings.warn(
                f"Access to deprecated property {old_name}. (Replaced by {new_name}) -- Deprecated since version {version}.",
                DeprecationWarning,
                stacklevel=2,
            )
            return getattr(self, new_name)

        @alias.setter
        def alias(self, value):
            warnings.warn(
                f"Write to deprecated property {old_name}. (Replaced by {new_name}) -- Deprecated since version {version}.",
                DeprecationWarning,
                stacklevel=2,
            )
            setattr(self, new_name, value)

        return alias

    def _deprecated_function_alias(old_name: str, new_name: str, version: str):
        def alias(self, *args, **kwargs):
            warnings.warn(
                f"Call to deprecated method {old_name}. (Replaced by {new_name}) -- Deprecated since version {version}.",
                DeprecationWarning,
                stacklevel=2,
            )
            return getattr(self, new_name)(*args, **kwargs)

        return alias

    def _deprecated(replaced_by: str, version: str):
        def deprecate(func):
            @functools.wraps(func)
            def with_warning(*args, **kwargs):
                warnings.warn(
                    f"Call to deprecated method {func.__name__}. (Replaced by {replaced_by}) -- Deprecated since version {version}.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                return func(*args, **kwargs)

            return with_warning

        return deprecate

    module._deprecated_alias = _deprecated_alias
    module._deprecated_function_alias = _deprecated_function_alias
    module._deprecated = _deprecated
    sys.modules["bs4._deprecation"] = module


def _clear_bs4_modules() -> None:
    """Remove any partially imported bs4 modules before retrying."""
    for module_name in tuple(sys.modules):
        if (
            module_name == "bs4"
            or module_name.startswith("bs4.")
            or module_name == "soupsieve"
            or module_name.startswith("soupsieve.")
        ):
            sys.modules.pop(module_name, None)


def _repair_soupsieve_bs4_references(bs4_module: types.ModuleType | Any) -> None:
    """Point any already-loaded soupsieve modules at the repaired bs4 module."""
    for module_name, module in tuple(sys.modules.items()):
        if module_name == "soupsieve" or module_name.startswith("soupsieve."):
            if getattr(module, "bs4", None) is not bs4_module:
                setattr(module, "bs4", bs4_module)


def _repair_bs4_public_api(bs4_module: types.ModuleType | Any) -> types.ModuleType | Any:
    """Restore top-level bs4 exports that some broken installs omit."""
    def _resolve_export(name: str) -> Any:
        module_name, attribute_name = _BS4_PUBLIC_EXPORTS[name]
        module = importlib.import_module(module_name)
        value = getattr(module, attribute_name)
        setattr(bs4_module, name, value)
        return value

    for export_name, (module_name, attribute_name) in _BS4_PUBLIC_EXPORTS.items():
        if hasattr(bs4_module, export_name):
            continue
        try:
            _resolve_export(export_name)
        except (ImportError, AttributeError):
            continue

    def _compat_getattr(name: str) -> Any:
        if name not in _BS4_PUBLIC_EXPORTS:
            raise AttributeError(name)
        return _resolve_export(name)

    if not hasattr(bs4_module, "__getattr__"):
        setattr(bs4_module, "__getattr__", _compat_getattr)

    _repair_soupsieve_bs4_references(bs4_module)
    return bs4_module


def _load_beautiful_soup():
    """Import BeautifulSoup, repairing broken bs4 installs if necessary."""
    installed_shims: set[str] = set()
    for _ in range(3):
        try:
            return _repair_bs4_public_api(importlib.import_module("bs4")).BeautifulSoup
        except ModuleNotFoundError as err:
            if err.name == "bs4._warnings" and err.name not in installed_shims:
                _clear_bs4_modules()
                _install_bs4_warnings_shim()
                installed_shims.add(err.name)
                continue
            if err.name == "bs4._deprecation" and err.name not in installed_shims:
                _clear_bs4_modules()
                _install_bs4_deprecation_shim()
                installed_shims.add(err.name)
                continue
            raise
    return _repair_bs4_public_api(importlib.import_module("bs4")).BeautifulSoup


BeautifulSoup = _load_beautiful_soup()
