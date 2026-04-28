#!/usr/bin/env python3
"""Crawl Cudy's public emulator catalog for capability-map maintenance."""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import re
import sys
import types
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "custom_components" / "cudy_router"


def _ensure_package_stub(name: str, path: Path) -> None:
    """Install a package stub without importing the integration package."""
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = module


def _load_cudy_module(module_name: str) -> Any:
    """Load a Cudy helper module without executing custom_components init."""
    _ensure_package_stub("custom_components", ROOT / "custom_components")
    _ensure_package_stub("custom_components.cudy_router", PACKAGE_ROOT)
    qualified_name = f"custom_components.cudy_router.{module_name}"
    module_path = PACKAGE_ROOT / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(qualified_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)
    return module


const = _load_cudy_module("const")
_load_cudy_module("model_names")
features = _load_cudy_module("features")
model_feature_set = features.model_feature_set

DEFAULT_BASE_URL = "https://support.cudy.com/"

_EMULATOR_LINK_RE = re.compile(r"/emulator/([^/?#]+)/?$", re.IGNORECASE)
_LUCI_PATH_RE = re.compile(
    r"['\"](?:https?://[^'\"]+)?/?emulator/[^'\"]+/cgi-bin/luci/([^'\"]+?)['\"]",
    re.IGNORECASE,
)
_HW_RE = re.compile(r"\bHW:\s*([^|<]+)", re.IGNORECASE)
_FW_RE = re.compile(r"\bFW:\s*([^|<]+)", re.IGNORECASE)

_PATH_MODULE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (const.MODULE_MODEM, ("admin/network/gcom/status", "admin/network/gcom/iface")),
    (const.MODULE_CELLULAR_SETTINGS, ("admin/network/gcom/config",)),
    (const.MODULE_DATA_USAGE, ("admin/network/gcom/statistics",)),
    (const.MODULE_SMS, ("admin/network/gcom/sms",)),
    (const.MODULE_DEVICES, ("admin/network/devices",)),
    (const.MODULE_SYSTEM, ("admin/system/status", "admin/status/overview", "admin/system/system")),
    (const.MODULE_WIFI_2G, ("admin/network/wireless", "admin/setup?active=wireless")),
    (const.MODULE_WIFI_5G, ("admin/network/wireless", "admin/setup?active=wireless")),
    (const.MODULE_WIRELESS_SETTINGS, ("admin/network/wireless/config", "admin/setup?active=wireless")),
    (const.MODULE_LAN, ("admin/network/lan",)),
    (const.MODULE_DHCP, ("admin/services/dhcp",)),
    (const.MODULE_VPN, ("admin/network/vpn", "admin/setup?active=vpn")),
    (const.MODULE_VPN_SETTINGS, ("admin/network/vpn/config", "admin/setup?active=vpn")),
    (const.MODULE_WAN, ("admin/network/wan", "admin/setup?active=wan")),
    (const.MODULE_LOAD_BALANCING, ("admin/network/mwan3",)),
    (const.MODULE_WAN_INTERFACES, ("admin/network/mwan3",)),
    (const.MODULE_MESH, ("admin/network/mesh", "admin/easymesh")),
    (const.MODULE_AUTO_UPDATE_SETTINGS, ("admin/system/autoupgrade", "admin/setup?active=autoupgrade")),
)


class _LinkParser(HTMLParser):
    """Collect links and text from an HTML document."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        self._current_href = attrs_dict.get("href")
        self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current_href is None:
            return
        self.links.append(
            {
                "href": html.unescape(self._current_href),
                "label": " ".join("".join(self._current_text).split()),
            }
        )
        self._current_href = None
        self._current_text = []


def parse_catalog(html_text: str) -> list[dict[str, str]]:
    """Extract emulator model links from the support catalog page."""
    parser = _LinkParser()
    parser.feed(html_text)
    models: dict[str, dict[str, str]] = {}
    for link in parser.links:
        match = _EMULATOR_LINK_RE.search(link["href"])
        if not match:
            continue
        slug = urllib.parse.unquote(match.group(1))
        models.setdefault(
            slug,
            {
                "model": slug,
                "label": link["label"] or slug,
                "path": f"/emulator/{slug}/",
            },
        )
    return [models[key] for key in sorted(models)]


def extract_luci_paths(html_text: str) -> list[str]:
    """Extract LuCI paths referenced by an emulator page."""
    paths: set[str] = set()
    for match in _LUCI_PATH_RE.finditer(html_text):
        path = html.unescape(match.group(1)).strip()
        if path:
            paths.add(path)
    return sorted(paths)


def extract_metadata(html_text: str) -> dict[str, str | None]:
    """Extract hardware and firmware metadata from an emulator page."""
    hw_match = _HW_RE.search(html_text)
    fw_match = _FW_RE.search(html_text)
    return {
        "hardware": " ".join(hw_match.group(1).split()) if hw_match else None,
        "firmware": " ".join(fw_match.group(1).split()) if fw_match else None,
    }


def infer_modules_from_paths(paths: list[str]) -> list[str]:
    """Infer integration module families from referenced LuCI paths."""
    modules: set[str] = set()
    for path in paths:
        normalized_path = path.lower()
        for module, markers in _PATH_MODULE_RULES:
            if any(marker.lower() in normalized_path for marker in markers):
                modules.add(module)
    return sorted(modules)


def _fetch_text(url: str, timeout: int) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "ha-cudy-router-catalog/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def crawl_catalog(
    *,
    base_url: str = DEFAULT_BASE_URL,
    limit: int | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    """Fetch the emulator catalog and summarize visible module families."""
    base_url = base_url.rstrip("/") + "/"
    catalog_html = _fetch_text(base_url, timeout)
    models = parse_catalog(catalog_html)
    if limit is not None:
        models = models[:limit]

    results: list[dict[str, Any]] = []
    for model in models:
        root_url = urllib.parse.urljoin(base_url, model["path"].lstrip("/"))
        panel_url = urllib.parse.urljoin(root_url, "cgi-bin/luci/admin/panel")
        root_html = _fetch_text(root_url, timeout)
        panel_html = _fetch_text(panel_url, timeout)
        paths = extract_luci_paths(root_html) + extract_luci_paths(panel_html)
        paths = sorted(set(paths))
        inferred_modules = infer_modules_from_paths(paths)
        mapped_modules = sorted(model_feature_set(model["model"]))
        results.append(
            {
                **model,
                **extract_metadata(root_html + panel_html),
                "paths": paths,
                "inferred_modules": inferred_modules,
                "mapped_modules": mapped_modules,
                "missing_from_map": sorted(set(inferred_modules) - set(mapped_modules)),
                "mapped_not_visible": sorted(set(mapped_modules) - set(inferred_modules)),
            }
        )

    return {
        "source": base_url,
        "model_count": len(results),
        "models": results,
    }


def _format_markdown(report: dict[str, Any]) -> str:
    """Format a crawl report as Markdown."""
    lines = [
        "# Cudy Emulator Catalog",
        "",
        f"Source: {report['source']}",
        f"Models checked: {report['model_count']}",
        "",
        "| Model | Firmware | Inferred modules | Missing from map |",
        "| --- | --- | --- | --- |",
    ]
    for model in report["models"]:
        lines.append(
            "| {model} | {firmware} | {modules} | {missing} |".format(
                model=model["label"],
                firmware=model.get("firmware") or "",
                modules=", ".join(model["inferred_modules"]),
                missing=", ".join(model["missing_from_map"]),
            )
        )
    return "\n".join(lines)


def main() -> int:
    """Run the crawler CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()

    report = crawl_catalog(
        base_url=args.base_url,
        limit=args.limit,
        timeout=args.timeout,
    )
    if args.format == "markdown":
        print(_format_markdown(report))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
