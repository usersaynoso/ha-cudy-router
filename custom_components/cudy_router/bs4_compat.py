"""Compatibility wrapper for importing BeautifulSoup in Home Assistant."""

from __future__ import annotations

import importlib
import functools
import sys
import types
import warnings


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
        if module_name == "bs4" or module_name.startswith("bs4."):
            sys.modules.pop(module_name, None)


def _load_beautiful_soup():
    """Import BeautifulSoup, repairing broken bs4 installs if necessary."""
    installed_shims: set[str] = set()
    for _ in range(3):
        try:
            return importlib.import_module("bs4").BeautifulSoup
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
    return importlib.import_module("bs4").BeautifulSoup


BeautifulSoup = _load_beautiful_soup()
