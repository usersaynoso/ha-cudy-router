"""Static checks for the README user-facing documentation contract."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
HACS_REPOSITORY_URL = (
    "https://my.home-assistant.io/redirect/hacs_repository/"
    "?owner=usersaynoso&repository=ha-cudy-router&category=integration"
)
WIKI_BASE_URL = "https://github.com/usersaynoso/ha-cudy-router/wiki"
WIKI_GUIDE_PAGES = (
    "Installation-and-Setup",
    "First-Run-Checklist",
    "Release-Notes-and-Upgrade-Guide",
    "Supported-Model-Matrix",
    "Supported-Routers-and-Compatibility",
    "Router-Compatibility-Reports",
    "Entities-and-Device-Model",
    "Entity-Naming-and-Finding-Entities",
    "Options-and-Device-Trackers",
    "Connected-Devices-Explained",
    "Services-and-Example-Calls",
    "Common-Automations",
    "Dashboard-Examples",
    "SMS-Panel",
    "Troubleshooting-and-Diagnostics",
    "Troubleshooting-by-Symptom",
    "Error-Messages-and-Repairs",
    "FAQ",
    "Known-Limitations-and-Firmware-Quirks",
    "Network-Setup-Examples",
    "Privacy-and-Security",
    "Updating-Removing-and-Reinstalling",
    "Maintainer-and-Contributor-Guide",
)


def _readme() -> str:
    return README_PATH.read_text(encoding="utf-8")


def test_readme_is_a_concise_landing_page() -> None:
    """README should stay short enough to work as a quick-start page."""
    source = _readme()

    assert source.startswith("# Cudy Router for Home Assistant")
    assert len(source.splitlines()) < 150
    assert "This project is not endorsed, maintained, or supported by Cudy." in source
    assert "## Full Documentation" in source


def test_readme_has_direct_hacs_my_home_assistant_button() -> None:
    """README should offer a one-click HACS repository link."""
    source = _readme()

    assert "https://my.home-assistant.io/badges/hacs_repository.svg" in source
    assert HACS_REPOSITORY_URL in source
    assert "owner=usersaynoso" in source
    assert "repository=ha-cudy-router" in source
    assert "category=integration" in source


def test_readme_documents_hacs_custom_repository_install() -> None:
    """README should include explicit HACS custom repository fallback steps."""
    source = _readme()

    assert "Custom repositories" in source
    assert "https://github.com/usersaynoso/ha-cudy-router" in source
    assert "Integration repository" in source or "**Integration** repository" in source
    assert "Restart Home Assistant" in source


def test_readme_keeps_current_supported_status_warning() -> None:
    """README should keep the real-hardware support status visible."""
    source = _readme()

    assert "Only the **Cudy P5** has been tested on real hardware so far." in source
    assert "model capability map" in source
    assert "have **not** been tested on real hardware yet" in source
    assert f"{WIKI_BASE_URL}/Supported-Routers-and-Compatibility" in source


def test_readme_summarizes_major_user_facing_features() -> None:
    """README should summarize the integration surface without full reference detail."""
    source = _readme()

    assert "sensor`, `switch`, `select`, `button`, and `device_tracker`" in source
    assert "modem/cellular, WAN, LAN, DHCP, VPN, load balancing, Wi-Fi, SMS" in source
    assert "Mesh node support" in source
    assert "Connected client devices" in source
    assert "/cudy-router-sms" in source
    assert "cudy_router.reboot_router" in source
    assert "cudy_router.restart_5g_connection" in source
    assert "cudy_router.switch_5g_band" in source
    assert "cudy_router.send_sms" in source
    assert "cudy_router.send_at_command" in source


def test_readme_links_to_all_wiki_guide_pages() -> None:
    """README should point users to the long-form wiki guide."""
    source = _readme()

    assert WIKI_BASE_URL in source
    for page in WIKI_GUIDE_PAGES:
        assert f"{WIKI_BASE_URL}/{page}" in source


def test_readme_links_directly_to_bug_report_issue_form() -> None:
    """README should send users straight to the diagnostics-aware bug form."""
    source = _readme()

    assert (
        "https://github.com/usersaynoso/ha-cudy-router/issues/new"
        "?template=bug_report.yml"
    ) in source
    assert "attach the Home Assistant diagnostics file" in source
    assert "Settings > Devices & services > Cudy Router" in source
    assert "Download diagnostics" in source
    assert "cudy_router.generate_debug_report" in source
