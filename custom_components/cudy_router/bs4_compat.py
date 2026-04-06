"""Compatibility wrapper for importing BeautifulSoup in Home Assistant."""

from __future__ import annotations

import importlib
import sys
import types


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


def _load_beautiful_soup():
    """Import BeautifulSoup, repairing broken bs4 installs if necessary."""
    try:
        return importlib.import_module("bs4").BeautifulSoup
    except ModuleNotFoundError as err:
        if err.name != "bs4._warnings":
            raise

    for module_name in tuple(sys.modules):
        if module_name == "bs4" or module_name.startswith("bs4."):
            sys.modules.pop(module_name, None)
    _install_bs4_warnings_shim()
    return importlib.import_module("bs4").BeautifulSoup


BeautifulSoup = _load_beautiful_soup()

