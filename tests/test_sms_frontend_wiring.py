"""Static wiring checks for the SMS panel implementation."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_PATH = ROOT / "custom_components" / "cudy_router" / "frontend.py"
PANEL_JS_PATH = ROOT / "custom_components" / "cudy_router" / "frontend" / "cudy-router-sms-panel.js"
INIT_PATH = ROOT / "custom_components" / "cudy_router" / "__init__.py"
SENSOR_PATH = ROOT / "custom_components" / "cudy_router" / "sensor.py"
SENSOR_DESCRIPTIONS_PATH = ROOT / "custom_components" / "cudy_router" / "sensor_descriptions.py"
CONFIG_FLOW_PATH = ROOT / "custom_components" / "cudy_router" / "config_flow.py"
STRINGS_PATH = ROOT / "custom_components" / "cudy_router" / "strings.json"
TRANSLATIONS_PATH = ROOT / "custom_components" / "cudy_router" / "translations" / "en.json"


def test_frontend_module_registers_panel_and_websocket_commands() -> None:
    """The integration should ship admin-only frontend wiring for SMS."""
    source = FRONTEND_PATH.read_text(encoding="utf-8")

    assert "async_register_built_in_panel" in source
    assert "async_remove_panel" in source
    assert "StaticPathConfig" in source
    assert '"cudy_router/sms/list_entries"' in source
    assert '"cudy_router/sms/get_messages"' in source
    assert '"cudy_router/sms/send"' in source
    assert "@websocket_api.require_admin" in source
    assert 'sidebar_title="Cudy SMS"' in source
    assert 'frontend_url_path=SMS_PANEL_URL_PATH' in source
    assert "show_in_sidebar=show_in_sidebar" in source
    assert "update=runtime[\"panel_registered\"]" in source
    assert '"embed_iframe": False' in source
    assert 'panel_path.stat().st_mtime_ns' in source
    assert '"module_url": f"{SMS_PANEL_STATIC_URL}?v={panel_version}"' in source
    assert 'f"{SMS_PANEL_STATIC_URL}?v={panel_version}"' in source


def test_frontend_panel_bundle_exists_and_supports_compose_flow() -> None:
    """The shipped panel bundle should include inbox/outbox browsing and compose actions."""
    source = PANEL_JS_PATH.read_text(encoding="utf-8")

    assert 'customElements.define("cudy-router-sms-panel"' in source
    assert 'type: "cudy_router/sms/get_messages"' in source
    assert 'type: "cudy_router/sms/send"' in source
    assert "Reply" in source
    assert "Send SMS" in source
    assert "Inbox" in source
    assert "Outbox" in source
    assert "--paper-font-common-base_-_font-family" in source
    assert "--sms-panel-card-background" in source
    assert "--sms-panel-border-strong" in source
    assert "--sms-panel-accent-deep" in source
    assert "linear-gradient(" in source
    assert ".primary:disabled" in source
    assert "text-shadow:" in source
    assert "pane-header" in source
    assert "hero-grid" in source
    assert "composer-actions" in source
    assert "list-body" in source
    assert "phone-field" in source
    assert "--sms-panel-control-outline" in source
    assert "--sms-panel-control-background" in source
    assert "0 0 0 1px var(--sms-panel-control-outline)" in source
    assert "toolbar-button" in source
    assert "message-item.active" in source
    assert "appearance: none;" in source
    assert "min-width: 104px;" in source


def test_init_refreshes_frontend_and_sensor_cleans_up_removed_sms_entity() -> None:
    """Runtime wiring should refresh the panel state and remove the retired sensor entity."""
    init_source = INIT_PATH.read_text(encoding="utf-8")
    sensor_source = SENSOR_PATH.read_text(encoding="utf-8")
    descriptions_source = SENSOR_DESCRIPTIONS_PATH.read_text(encoding="utf-8")

    assert "async_refresh_frontend" in init_source
    assert '_remove_sensor_by_unique_id(f"{config_entry.entry_id}-sms-messages")' in sensor_source
    assert "SMS messages" not in descriptions_source


def test_sms_sidebar_option_is_declared_only_in_options_resources() -> None:
    """The SMS sidebar visibility option should be wired into the options flow and translations."""
    config_flow_source = CONFIG_FLOW_PATH.read_text(encoding="utf-8")
    strings_source = STRINGS_PATH.read_text(encoding="utf-8")
    translations_source = TRANSLATIONS_PATH.read_text(encoding="utf-8")

    assert "OPTIONS_SHOW_SMS_PANEL_IN_SIDEBAR" in config_flow_source
    assert "show_sms_panel_in_sidebar" in strings_source
    assert "Show Cudy SMS in sidebar" in strings_source
    assert "keep the SMS page available only by direct URL" in strings_source
    assert "show_sms_panel_in_sidebar" in translations_source
