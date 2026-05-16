"""Helpers to parse configurable router settings pages."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .bs4_compat import BeautifulSoup


def _soup(html: str) -> BeautifulSoup:
    """Return a parsed HTML document."""
    return BeautifulSoup(html or "", "html.parser")


def _normalize_label(label: str) -> str:
    """Normalize option labels for Home Assistant entities."""
    normalized = " ".join(label.split())
    if normalized in {"1", "2"}:
        return f"Sim {normalized}"
    return normalized


def _input_value(soup: BeautifulSoup, field_name: str) -> str | None:
    """Read the first non-empty input value for a form field."""
    for field in soup.find_all("input", attrs={"name": field_name}):
        value = (field.get("value") or "").strip()
        if value:
            return value
    return None


def _field_value(soup: BeautifulSoup, field_name: str) -> str | None:
    """Read the effective field value from a matching input or select."""
    input_value = _input_value(soup, field_name)
    if input_value is not None:
        return input_value

    entry = _select_entry(soup, field_name)
    if entry is None:
        return None

    value = entry.get("value")
    if value in (None, ""):
        return None
    return str(value)


def _field_value_by_suffix(soup: BeautifulSoup, field_name_suffix: str) -> str | None:
    """Read the effective field value from the first field matching a suffix."""
    field_name = _field_name_by_suffix(soup, field_name_suffix)
    if field_name is None:
        return None
    return _field_value(soup, field_name)


def _hidden_bool(
    soup: BeautifulSoup,
    field_name: str,
    *,
    inverted: bool = False,
) -> bool | None:
    """Read a hidden 0/1 switch field."""
    field = soup.find("input", attrs={"name": field_name})
    if field is None:
        return None

    value = field.get("value")
    if value not in {"0", "1"}:
        return None

    enabled = value == "1"
    return not enabled if inverted else enabled


def _field_name_by_suffix(
    soup: BeautifulSoup,
    field_name_suffix: str,
    *,
    tag_names: tuple[str, ...] = ("input", "select"),
) -> str | None:
    """Find the first field name matching a suffix."""
    normalized_suffix = field_name_suffix.strip().lower()
    for tag_name in tag_names:
        for field in soup.find_all(tag_name):
            field_name = (field.get("name") or "").strip()
            if field_name and field_name.lower().endswith(normalized_suffix):
                return field_name
    return None


def _select_entry(
    soup: BeautifulSoup,
    field_name: str,
    *,
    label_transform: Callable[[str], str] | None = None,
) -> dict[str, Any] | None:
    """Read a select field and its options."""
    select = soup.find("select", attrs={"name": field_name})
    if select is None:
        return None

    options: dict[str, str] = {}
    selected_value: str | None = None

    for option in select.find_all("option"):
        value = option.get("value", "")
        label = " ".join(option.stripped_strings)
        if label_transform is not None:
            label = label_transform(label)
        options[value] = label
        if option.has_attr("selected"):
            selected_value = value

    if selected_value is None and options:
        selected_value = next(iter(options))

    return {
        "value": selected_value,
        "options": options,
    }


def _hidden_bool_by_suffix(
    soup: BeautifulSoup,
    field_name_suffix: str,
    *,
    inverted: bool = False,
) -> bool | None:
    """Read a hidden 0/1 switch field by suffix."""
    field_name = _field_name_by_suffix(soup, field_name_suffix, tag_names=("input",))
    if field_name is None:
        return None
    return _hidden_bool(soup, field_name, inverted=inverted)


def _state_field_name_by_suffix(
    soup: BeautifulSoup,
    field_name_suffix: str,
    *,
    tag_names: tuple[str, ...] = ("input", "select"),
) -> str | None:
    """Find a state field by suffix, preferring LuCI cbid fields over widget fields."""
    normalized_suffix = field_name_suffix.strip().lower()
    fallback: str | None = None
    for tag_name in tag_names:
        for field in soup.find_all(tag_name):
            field_name = (field.get("name") or "").strip()
            if not field_name or not field_name.lower().endswith(normalized_suffix):
                continue
            if field_name.startswith("cbid."):
                return field_name
            if fallback is None:
                fallback = field_name
    return fallback


def _select_entry_by_suffix(
    soup: BeautifulSoup,
    field_name_suffix: str,
    *,
    label_transform: Callable[[str], str] | None = None,
) -> dict[str, Any] | None:
    """Read a select field and its options by suffix."""
    field_name = _field_name_by_suffix(soup, field_name_suffix, tag_names=("select",))
    if field_name is None:
        return None
    return _select_entry(soup, field_name, label_transform=label_transform)


def _first_select_entry(
    soup: BeautifulSoup,
    field_names: list[str],
) -> dict[str, Any] | None:
    """Return the first available select field from a list of possible names."""
    for field_name in field_names:
        entry = _select_entry(soup, field_name)
        if entry is not None:
            return entry
    return None


def parse_cellular_settings(input_html: str) -> dict[str, Any]:
    """Parse the cellular/APN settings page."""
    soup = _soup(input_html)

    data: dict[str, Any] = {}

    enabled = _hidden_bool(soup, "cbid.network.4g.disabled", inverted=True)
    if enabled is not None:
        data["enabled"] = {"value": enabled}

    data_roaming = _hidden_bool(soup, "cbid.network.4g.roaming")
    if data_roaming is not None:
        data["data_roaming"] = {"value": data_roaming}

    for key, field_name, transform in (
        ("sim_slot", "cbid.network.4g.simslot", _normalize_label),
        ("network_mode", "cbid.network.4g.service", None),
        ("network_search", "cbid.network.4g.search", None),
        ("pdp_type", "cbid.network.4g.pdptype", None),
        ("apn_profile", "cbid.network.4g.isp", None),
    ):
        entry = _select_entry(soup, field_name, label_transform=transform)
        if entry is not None:
            data[key] = entry

    return data


def parse_vpn_settings(input_html: str) -> dict[str, Any]:
    """Parse the VPN configuration page."""
    soup = _soup(input_html)

    data: dict[str, Any] = {}

    enabled = _hidden_bool(soup, "cbid.vpn.config.enabled")
    if enabled is not None:
        data["enabled"] = {"value": enabled}

    site_to_site = _hidden_bool(soup, "cbid.vpn.config.s2s")
    if site_to_site is not None:
        data["site_to_site"] = {"value": site_to_site}

    for key, field_name in (
        ("protocol", "cbid.vpn.config._proto"),
        ("default_rule", "cbid.vpn.config.filter"),
        ("client_access", "cbid.vpn.config.access"),
        ("vpn_policy", "cbid.vpn.config.policy"),
    ):
        entry = _select_entry(soup, field_name)
        if entry is not None:
            data[key] = entry

    return data


def parse_auto_update_settings(input_html: str) -> dict[str, Any]:
    """Parse the firmware auto-update page."""
    soup = _soup(input_html)

    data: dict[str, Any] = {}

    auto_update = _hidden_bool(soup, "cbid.upgrade.1.auto_upgrade")
    if auto_update is None:
        auto_update = _hidden_bool_by_suffix(soup, "auto_upgrade")
    if auto_update is not None:
        data["auto_update"] = {"value": auto_update}

    update_time = _select_entry(soup, "cbid.upgrade.1.upgrade_time")
    if update_time is None:
        update_time = _select_entry_by_suffix(soup, "upgrade_time")
    if update_time is not None:
        data["update_time"] = update_time

    return data


def parse_lan_settings(input_html: str) -> dict[str, Any]:
    """Parse the LAN configuration page."""
    soup = _soup(input_html)

    data: dict[str, Any] = {}

    for key, field_name in (
        ("ip_address", "cbid.network.lan.ipaddr"),
        ("subnet_mask", "cbid.network.lan.netmask"),
    ):
        value = _field_value(soup, field_name)
        if value in (None, ""):
            suffix = "ipaddr" if key == "ip_address" else "netmask"
            value = _field_value_by_suffix(soup, suffix)
        if value not in (None, ""):
            data[key] = {"value": value}

    return data


def parse_wan_settings(input_html: str) -> dict[str, Any]:
    """Parse WAN configuration details used for status fallbacks."""
    soup = _soup(input_html)

    data: dict[str, Any] = {}

    for key, field_name in (
        ("protocol", "cbid.network.wan.proto"),
        ("subnet_mask", "cbid.network.wan.netmask"),
    ):
        value = _field_value(soup, field_name)
        if value in (None, ""):
            suffix = "proto" if key == "protocol" else "netmask"
            value = _field_value_by_suffix(soup, suffix)
        if value not in (None, ""):
            data[key] = {"value": value}

    return data


def parse_wisp_settings(input_html: str) -> dict[str, Any]:
    """Parse WISP configuration controls exposed by supported firmware."""
    soup = _soup(input_html)

    data: dict[str, Any] = {}

    enabled_field = "cbid.wds-config.1.enabled"
    enabled = _hidden_bool(soup, enabled_field)
    if enabled is None:
        discovered_enabled_field = _state_field_name_by_suffix(
            soup,
            "enabled",
            tag_names=("input",),
        )
        if discovered_enabled_field is not None:
            enabled = _hidden_bool(soup, discovered_enabled_field)
    if enabled is not None:
        data["enabled"] = {"value": enabled}

    for key, suffix in (
        ("hidden", "hidden"),
        ("isolate", "isolate"),
    ):
        field_name = _state_field_name_by_suffix(
            soup,
            suffix,
            tag_names=("input",),
        )
        if field_name is None:
            continue
        value = _hidden_bool(soup, field_name)
        if value is not None:
            data[key] = {"value": value}

    return data


def parse_wireless_settings(
    combo_html: str,
    combine_html: str,
    uncombine_html: str,
) -> dict[str, Any]:
    """Parse the wireless settings pages into canonical settings."""
    combo_soup = _soup(combo_html)
    smart_connect = _hidden_bool(combo_soup, "cbid.wireless.smart.connect")

    data: dict[str, Any] = {}

    if smart_connect is not None:
        data["smart_connect"] = {"value": smart_connect}

    active_soup = _soup(combine_html if smart_connect else uncombine_html)

    if smart_connect:
        enabled = _hidden_bool(active_soup, "cbid.wireless.wlan.disabled", inverted=True)
        hidden = _hidden_bool(active_soup, "cbid.wireless.wlan.hidden")
        isolate = _hidden_bool(active_soup, "cbid.wireless.wlan.isolate")
        band_2g_prefix = "cbid.wireless.wlan.wlan00"
        band_5g_prefix = "cbid.wireless.wlan.wlan10"
    else:
        enabled = None
        hidden = None
        isolate = None
        band_2g_prefix = "cbid.wireless.wlan00"
        band_5g_prefix = "cbid.wireless.wlan10"

    band_2g_enabled = (
        enabled
        if enabled is not None
        else _hidden_bool(active_soup, f"{band_2g_prefix}.disabled", inverted=True)
    )
    band_5g_enabled = (
        enabled
        if enabled is not None
        else _hidden_bool(active_soup, f"{band_5g_prefix}.disabled", inverted=True)
    )
    band_2g_hidden = hidden if hidden is not None else _hidden_bool(active_soup, f"{band_2g_prefix}.hidden")
    band_5g_hidden = hidden if hidden is not None else _hidden_bool(active_soup, f"{band_5g_prefix}.hidden")
    band_2g_isolate = (
        isolate if isolate is not None else _hidden_bool(active_soup, f"{band_2g_prefix}.isolate")
    )
    band_5g_isolate = (
        isolate if isolate is not None else _hidden_bool(active_soup, f"{band_5g_prefix}.isolate")
    )

    for key, value in (
        ("wifi_2g_enabled", band_2g_enabled),
        ("wifi_5g_enabled", band_5g_enabled),
        ("wifi_2g_hidden", band_2g_hidden),
        ("wifi_5g_hidden", band_5g_hidden),
        ("wifi_2g_isolate", band_2g_isolate),
        ("wifi_5g_isolate", band_5g_isolate),
    ):
        if value is not None:
            data[key] = {"value": value}

    for key, entry in (
        ("wifi_2g_mode", _select_entry(active_soup, f"{band_2g_prefix}.hwmode")),
        ("wifi_2g_channel_width", _select_entry(active_soup, f"{band_2g_prefix}.htbw")),
        ("wifi_2g_channel", _select_entry(active_soup, f"{band_2g_prefix}.channel")),
        ("wifi_2g_tx_power", _select_entry(active_soup, f"{band_2g_prefix}.txpower")),
        ("wifi_5g_mode", _select_entry(active_soup, f"{band_5g_prefix}.hwmode")),
        (
            "wifi_5g_channel_width",
            _first_select_entry(
                active_soup,
                [
                    f"{band_5g_prefix}.htbw3",
                    f"{band_5g_prefix}.htbw2",
                    f"{band_5g_prefix}.htbw1",
                ],
            ),
        ),
        (
            "wifi_5g_channel",
            _first_select_entry(
                active_soup,
                [
                    f"{band_5g_prefix}.channel4",
                    f"{band_5g_prefix}.channel3",
                    f"{band_5g_prefix}.channel2",
                    f"{band_5g_prefix}.channel",
                ],
            ),
        ),
        ("wifi_5g_tx_power", _select_entry(active_soup, f"{band_5g_prefix}.txpower")),
    ):
        if entry is not None:
            data[key] = entry

    return data
