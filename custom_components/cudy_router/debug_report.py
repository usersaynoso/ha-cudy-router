"""Debug reporting helpers for Cudy router compatibility issues."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .bs4_compat import BeautifulSoup
from .const import DOMAIN
from .entity_catalog import build_entity_catalog
from .parser import (
    parse_data_usage,
    parse_devices,
    parse_devices_status,
    parse_lan_status,
    parse_mesh_devices,
    parse_modem_info,
    parse_sms_status,
    parse_system_status,
    parse_tables,
    parse_wifi_status,
)
from .parser_network import (
    parse_arp_status,
    parse_dhcp_status,
    parse_load_balancing_status,
    parse_vpn_status,
    parse_wan_status,
)
from .parser_settings import (
    parse_auto_update_settings,
    parse_cellular_settings,
    parse_lan_settings,
    parse_vpn_settings,
    parse_wan_settings,
    parse_wireless_settings,
)
from .router_data import (
    _LOAD_BALANCING_STATUS_PATHS,
    _VPN_STATUS_PATHS,
    _wan_status_paths,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_DEBUG_HTML_CHARS = 3000

_WAN_DEBUG_IFACES: tuple[str, ...] = (
    "wan",
    "wan1",
    "wan2",
    "wan3",
    "wan4",
    "wanb",
    "wanc",
    "wand",
)
_WAN_CONFIG_PATH_FORMATS: tuple[str, ...] = (
    "admin/network/wan/config/detail?nomodal=&iface={iface_name}",
    "admin/network/wan/config?nomodal=&iface={iface_name}",
    "admin/network/wan/iface/{iface_name}",
    "admin/network/wan/iface/{iface_name}/status",
    "admin/network/wan/iface/{iface_name}/config",
)
_VPN_DEBUG_EXTRA_PATHS: tuple[str, ...] = (
    "admin/network/vpn/wireguard/status",
    "admin/network/vpn/wireguard/status?status=",
    "admin/network/vpn/openvpns/status",
    "admin/network/vpn/openvpns/status?detail=",
    "admin/network/vpn/openvpnc/status",
    "admin/network/vpn/openvpnc/status?detail=",
    "admin/network/vpn/pptp/status?status=",
    "admin/network/vpn/pptp/status?detail=1",
    "admin/network/vpn/status?status=",
    "admin/network/vpn/status?detail=1",
)
_MODULE_DEBUG_PATHS: dict[str, tuple[str, ...]] = {
    "system": (
        "admin/system/status",
        "admin/status/overview",
        "admin/system/system",
        "admin/panel",
    ),
    "devices": (
        "admin/network/devices/devlist?detail=1",
        "admin/network/devices/status?detail=1",
        "admin/system/status/arp",
    ),
    "modem": (
        "admin/network/gcom/status",
        "admin/network/gcom/status?detail=1&iface=4g",
    ),
    "data_usage": ("admin/network/gcom/statistics?iface=4g",),
    "sms": ("admin/network/gcom/sms/status",),
    "wifi": (
        "admin/network/wireless/status?iface=wlan00",
        "admin/network/wireless/status?iface=wlan10",
    ),
    "lan": (
        "admin/network/lan/status?detail=1",
        "admin/network/lan/status",
        "admin/network/lan/config?nomodal=",
        "admin/network/lan/config/detail?nomodal=",
    ),
    "dhcp": ("admin/services/dhcp/status?detail=1",),
    "mesh": (
        "admin/network/mesh/status",
        "admin/network/mesh",
        "admin/network/mesh/topology",
        "admin/network/mesh/nodes",
        "admin/easymesh/status",
        "admin/easymesh",
        "admin/network/mesh/clients?clients=all",
    ),
    "settings": (
        "admin/network/gcom/config/apn",
        "admin/network/wireless/config/combo",
        "admin/network/wireless/config/combine",
        "admin/network/wireless/config/uncombine",
        "admin/network/vpn/config",
        "admin/system/autoupgrade",
        "admin/setup",
    ),
}

_MAC_RE = re.compile(r"\b(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b")
_COMPACT_MAC_RE = re.compile(r"(?<![0-9a-fA-F])(?:[0-9a-fA-F]{12})(?![0-9a-fA-F])")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6_RE = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{0,4}\b")
_INPUT_SECRET_RE = re.compile(
    r"(?is)(<input\b(?=[^>]*\b(?:name|id)=['\"][^'\"]*"
    r"(?:sysauth|token|csrf|salt|pass|pwd)[^'\"]*['\"])[^>]*\bvalue=['\"])([^'\"]*)(['\"])",
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(sysauth(?:_http|_https)?|token|csrf|_csrf|salt|password|passwd|pwd|"
    r"session(?:id)?|cookie|auth)\b\s*=\s*(['\"]?)([^&;\s'\"<>]+)\2",
)
_HTML_NAME_VALUE_RE = re.compile(
    r"(?is)(>\s*(?:Host(?:name)?|Device Name|Client Name|Common Name|User(?:name| Name)|"
    r"SSID)\s*<[^>]*>\s*<[^>]+[^>]*>)([^<]+)",
)
_SECRET_KEY_RE = re.compile(
    r"(password|passwd|pwd|token|csrf|salt|sysauth|cookie|session[_-]?id|secret|auth)",
    re.IGNORECASE,
)
_NAME_KEY_RE = re.compile(
    r"^(host|hostname|host_name|username|user_name|client_name|device_name|common_name|ssid|name)$",
    re.IGNORECASE,
)
_NAME_LABEL_RE = re.compile(
    r"^(host\s*name|hostname|device\s*name|client\s*name|common\s*name|user\s*name|username|ssid)$",
    re.IGNORECASE,
)


class Redactor:
    """Redact sensitive values while keeping report structure readable."""

    def __init__(self) -> None:
        """Initialize placeholder tracking."""
        self._replacements: dict[tuple[str, str], str] = {}
        self._counts: dict[str, int] = {}

    def _placeholder(self, kind: str, raw_value: str) -> str:
        """Return a stable placeholder for a sensitive value."""
        key = (kind, raw_value)
        if key not in self._replacements:
            self._counts[kind] = self._counts.get(kind, 0) + 1
            self._replacements[key] = f"<{kind}_{self._counts[kind]}>"
        return self._replacements[key]

    def text(self, value: Any) -> Any:
        """Redact sensitive tokens from a text value."""
        if not isinstance(value, str):
            return value

        redacted = _INPUT_SECRET_RE.sub(r"\1<REDACTED>\3", value)
        redacted = _SECRET_ASSIGNMENT_RE.sub(
            lambda match: f"{match.group(1)}={match.group(2)}<REDACTED>{match.group(2)}",
            redacted,
        )
        redacted = _HTML_NAME_VALUE_RE.sub(
            lambda match: f"{match.group(1)}{self._placeholder('NAME', match.group(2).strip())}",
            redacted,
        )
        redacted = _MAC_RE.sub(lambda match: self._placeholder("MAC", match.group(0)), redacted)
        redacted = _COMPACT_MAC_RE.sub(lambda match: self._placeholder("MAC", match.group(0)), redacted)
        redacted = _IPV4_RE.sub(lambda match: self._placeholder("IP", match.group(0)), redacted)
        redacted = _IPV6_RE.sub(
            lambda match: self._placeholder("IPV6", match.group(0))
            if "::" in match.group(0) or match.group(0).count(":") >= 4
            else match.group(0),
            redacted,
        )
        return redacted

    def keyed_value(self, key: Any, value: Any) -> Any:
        """Redact a value using its field label or key as extra context."""
        key_text = str(key)
        if _SECRET_KEY_RE.search(key_text):
            return "<REDACTED>"
        if _NAME_KEY_RE.search(key_text):
            if value in (None, ""):
                return value
            return self._placeholder("NAME", str(value))
        return self.data(value)

    def table_value(self, label: Any, value: Any) -> Any:
        """Redact a table value using its label as context."""
        label_text = str(label).strip()
        if _SECRET_KEY_RE.search(label_text):
            return "<REDACTED>"
        if _NAME_LABEL_RE.search(label_text):
            if value in (None, ""):
                return value
            return self._placeholder("NAME", str(value))
        return self.text(value)

    def data(self, value: Any) -> Any:
        """Return a JSON-safe redacted copy of a nested value."""
        if isinstance(value, Mapping):
            return {str(key): self.keyed_value(key, nested_value) for key, nested_value in value.items()}
        if isinstance(value, list):
            return [self.data(item) for item in value]
        if isinstance(value, tuple):
            return [self.data(item) for item in value]
        if isinstance(value, set):
            return sorted(self.data(item) for item in value)
        return self.text(_json_safe(value))


def redact_text(value: str) -> str:
    """Redact sensitive values in text using a fresh redactor."""
    return Redactor().text(value)


def wan_debug_paths() -> list[str]:
    """Return the WAN and load-balancing endpoint matrix used by diagnostics."""
    paths: list[str] = list(_LOAD_BALANCING_STATUS_PATHS)
    for iface_name in _WAN_DEBUG_IFACES:
        paths.extend(_wan_status_paths(iface_name))
        paths.extend(path.format(iface_name=iface_name) for path in _WAN_CONFIG_PATH_FORMATS)
    return _unique(paths)


def vpn_debug_paths() -> list[str]:
    """Return the VPN endpoint matrix used by diagnostics."""
    return _unique([*_VPN_STATUS_PATHS, *_VPN_DEBUG_EXTRA_PATHS])


def module_debug_paths() -> dict[str, list[str]]:
    """Return non-WAN/VPN module endpoint paths used by diagnostics."""
    return {group: _unique(paths) for group, paths in _MODULE_DEBUG_PATHS.items()}


def _unique(values: list[str] | tuple[str, ...]) -> list[str]:
    """Return values in order without duplicates."""
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _json_safe(value: Any) -> Any:
    """Return a JSON-safe primitive representation."""
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _manifest_version() -> str:
    """Return the installed integration version from manifest.json."""
    try:
        manifest = json.loads(Path(__file__).with_name("manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unknown"
    version = manifest.get("version")
    return str(version) if version else "unknown"


def _config_entry_summary(config_entry: Any, redactor: Redactor) -> dict[str, Any]:
    """Return a Home Assistant-safe config entry summary."""
    return {
        "entry_id": getattr(config_entry, "entry_id", None),
        "title": redactor.keyed_value("name", getattr(config_entry, "title", None)),
        "version": getattr(config_entry, "version", None),
        "domain": getattr(config_entry, "domain", DOMAIN),
        "data": redactor.data(getattr(config_entry, "data", {})),
        "options": redactor.data(getattr(config_entry, "options", {})),
    }


def _entity_registry_entries(hass: Any, config_entry: Any, redactor: Redactor) -> list[dict[str, Any]]:
    """Return entity registry entries for the config entry."""
    try:
        from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
    except ImportError:
        return []

    entity_registry = async_get_entity_registry(hass)
    entities = getattr(entity_registry, "entities", {})
    config_entry_id = getattr(config_entry, "entry_id", None)
    entry_prefix = f"{config_entry_id}-" if config_entry_id else ""
    entries: list[dict[str, Any]] = []

    for entity_entry in list(entities.values()):
        unique_id = getattr(entity_entry, "unique_id", "") or ""
        platform = getattr(entity_entry, "platform", None)
        entity_config_entry_id = getattr(entity_entry, "config_entry_id", None)
        if (
            entity_config_entry_id != config_entry_id
            and platform != DOMAIN
            and not str(unique_id).startswith(entry_prefix)
        ):
            continue

        entries.append(
            {
                "entity_id": getattr(entity_entry, "entity_id", None),
                "domain": getattr(entity_entry, "domain", None),
                "platform": platform,
                "unique_id": redactor.text(unique_id),
                "disabled_by": _json_safe(getattr(entity_entry, "disabled_by", None)),
                "entity_category": _json_safe(getattr(entity_entry, "entity_category", None)),
            }
        )

    return sorted(entries, key=lambda entry: str(entry.get("entity_id") or ""))


def _page_outline(html: str) -> dict[str, Any]:
    """Return title and heading text from an HTML response."""
    if not html:
        return {"title": None, "headings": []}

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    headings = [
        " ".join(element.stripped_strings)
        for element in soup.select(".panel-title, .panel-heading, h1, h2, h3, h4, legend")
    ]
    return {
        "title": title,
        "headings": [heading for heading in headings if heading][:20],
    }


def _redacted_table_data(html: str, redactor: Redactor) -> dict[str, Any]:
    """Return redacted table label/value data."""
    return {
        redactor.text(str(label)): redactor.table_value(label, value)
        for label, value in parse_tables(html).items()
    }


def _parser_output(path: str, html: str, redactor: Redactor) -> dict[str, Any]:
    """Return redacted parser output for a probed endpoint."""
    if not html:
        return {}

    try:
        if path == "admin/network/devices/devlist?detail=1":
            return redactor.data(parse_devices(html, None))
        if path == "admin/network/devices/status?detail=1":
            return redactor.data(parse_devices_status(html))
        if path == "admin/system/status/arp":
            return redactor.data(parse_arp_status(html, "br-lan"))
        if path.startswith("admin/network/gcom/status"):
            return redactor.data(parse_modem_info(html))
        if path == "admin/network/gcom/statistics?iface=4g":
            return redactor.data(parse_data_usage(html))
        if path == "admin/network/gcom/sms/status":
            return redactor.data(parse_sms_status(html) or {})
        if path.startswith("admin/network/wireless/status"):
            return redactor.data(parse_wifi_status(html))
        if path.startswith("admin/network/lan/status"):
            return redactor.data(parse_lan_status(html))
        if path.startswith("admin/network/lan/config"):
            return redactor.data(parse_lan_settings(html))
        if path == "admin/services/dhcp/status?detail=1":
            return redactor.data(parse_dhcp_status(html))
        if path.startswith("admin/network/mesh") or path.startswith("admin/easymesh"):
            return redactor.data(parse_mesh_devices(html))
        if path == "admin/network/gcom/config/apn":
            return redactor.data(parse_cellular_settings(html))
        if path.startswith("admin/network/wireless/config"):
            return redactor.data(parse_wireless_settings(html, "", ""))
        if path == "admin/network/vpn/config":
            return redactor.data(parse_vpn_settings(html))
        if path in {"admin/system/autoupgrade", "admin/setup"}:
            auto_update_settings = parse_auto_update_settings(html)
            if auto_update_settings:
                return redactor.data(auto_update_settings)
        if path in {"admin/system/status", "admin/status/overview", "admin/system/system", "admin/panel"}:
            return redactor.data(parse_system_status(html))
        if "admin/network/mwan3/" in path:
            return redactor.data(parse_load_balancing_status(html))
        if path.startswith("admin/network/vpn"):
            return redactor.data(parse_vpn_status(html))
        if "admin/network/wan/config" in path:
            return redactor.data(parse_wan_settings(html))
        if "admin/network/wan/" in path:
            return redactor.data(parse_wan_status(html))
    except Exception as err:  # pragma: no cover - defensive diagnostics path
        return {"error": str(err)}
    return {}


async def _async_probe_path(
    hass: Any,
    api: Any,
    path: str,
    redactor: Redactor,
    *,
    include_html: bool,
    max_html_chars: int,
) -> dict[str, Any]:
    """Fetch and summarize a debug endpoint."""
    if hasattr(api, "debug_get"):
        result = await hass.async_add_executor_job(api.debug_get, path)
    else:
        text = await hass.async_add_executor_job(api.get, path, True)
        result = {
            "path": path,
            "status_code": None,
            "ok": bool(text),
            "url": path,
            "text": text or "",
        }

    text = result.get("text") or ""
    outline = _page_outline(text)
    probe: dict[str, Any] = {
        "path": path,
        "url": redactor.text(result.get("url")),
        "status_code": result.get("status_code"),
        "ok": bool(result.get("ok")),
        "response_length": len(text),
        "title": redactor.text(outline["title"]),
        "headings": redactor.data(outline["headings"]),
        "table_data": _redacted_table_data(text, redactor),
        "parser_output": _parser_output(path, text, redactor),
    }
    if include_html:
        probe["html_excerpt"] = redactor.text(text[: max(0, max_html_chars)])
    return probe


async def async_build_debug_payload(
    hass: Any,
    coordinator: Any,
    *,
    include_html: bool = True,
    max_html_chars: int = DEFAULT_DEBUG_HTML_CHARS,
) -> dict[str, Any]:
    """Build a redacted debug payload for diagnostics and service responses."""
    redactor = Redactor()
    config_entry = coordinator.config_entry
    wan_paths = wan_debug_paths()
    vpn_paths = vpn_debug_paths()
    extra_paths = module_debug_paths()

    payload: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "integration": {
            "domain": DOMAIN,
            "version": _manifest_version(),
            "configured_model": getattr(config_entry, "data", {}).get("model"),
        },
        "config_entry": _config_entry_summary(config_entry, redactor),
        "coordinator": {
            "modules": list(getattr(coordinator, "data", {}) or {}),
            "data": redactor.data(getattr(coordinator, "data", {}) or {}),
        },
        "entity_registry": _entity_registry_entries(hass, config_entry, redactor),
        "entity_catalog": redactor.data(
            build_entity_catalog(
                hass,
                config_entry,
                coordinator,
                value_transform=redactor.keyed_value,
            )
        ),
        "endpoint_matrix": {
            **extra_paths,
            "load_balancing": list(_LOAD_BALANCING_STATUS_PATHS),
            "wan": wan_paths,
            "vpn": vpn_paths,
        },
        "probes": {
            **{group: [] for group in extra_paths},
            "load_balancing": [],
            "wan": [],
            "vpn": [],
        },
    }

    api = coordinator.api
    for group, paths in extra_paths.items():
        for path in paths:
            payload["probes"][group].append(
                await _async_probe_path(
                    hass,
                    api,
                    path,
                    redactor,
                    include_html=include_html,
                    max_html_chars=max_html_chars,
                )
            )
    for path in _LOAD_BALANCING_STATUS_PATHS:
        payload["probes"]["load_balancing"].append(
            await _async_probe_path(
                hass,
                api,
                path,
                redactor,
                include_html=include_html,
                max_html_chars=max_html_chars,
            )
        )
    for path in [path for path in wan_paths if path not in _LOAD_BALANCING_STATUS_PATHS]:
        payload["probes"]["wan"].append(
            await _async_probe_path(
                hass,
                api,
                path,
                redactor,
                include_html=include_html,
                max_html_chars=max_html_chars,
            )
        )
    for path in vpn_paths:
        payload["probes"]["vpn"].append(
            await _async_probe_path(
                hass,
                api,
                path,
                redactor,
                include_html=include_html,
                max_html_chars=max_html_chars,
            )
        )

    return payload


def format_debug_report(payload: dict[str, Any]) -> str:
    """Format a debug payload as GitHub-friendly Markdown."""
    integration = payload.get("integration", {})
    config_entry = payload.get("config_entry", {})
    coordinator = payload.get("coordinator", {})
    json_payload = json.dumps(payload, indent=2, sort_keys=True)
    return (
        "# Cudy Router Debug Report\n\n"
        f"- Generated: {payload.get('generated_at')}\n"
        f"- Integration version: {integration.get('version')}\n"
        f"- Configured model: {integration.get('configured_model')}\n"
        f"- Config entry: {config_entry.get('entry_id')}\n"
        f"- Coordinator modules: {', '.join(coordinator.get('modules', []))}\n\n"
        "Paste this whole report into the GitHub issue. It is redacted, but it keeps the entity "
        "catalog, table labels, WAN numbers, VPN counts, and page shapes needed to fix parser "
        "differences.\n\n"
        "```json\n"
        f"{json_payload}\n"
        "```\n"
    )


async def async_generate_debug_report(
    hass: Any,
    coordinator: Any,
    *,
    include_html: bool = True,
    max_html_chars: int = DEFAULT_DEBUG_HTML_CHARS,
) -> str:
    """Build a Markdown debug report."""
    payload = await async_build_debug_payload(
        hass,
        coordinator,
        include_html=include_html,
        max_html_chars=max_html_chars,
    )
    return format_debug_report(payload)


def log_debug_report(report: str) -> None:
    """Write a report to Home Assistant logs with easy-to-find markers."""
    _LOGGER.warning(
        "CUDY_ROUTER_DEBUG_REPORT_START\n%s\nCUDY_ROUTER_DEBUG_REPORT_END",
        report,
    )
