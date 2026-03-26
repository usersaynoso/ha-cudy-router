"""Static checks for README coverage of major user-facing features."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"


def test_readme_documents_new_settings_entities() -> None:
    """README should describe the recently added writable settings entities."""
    source = README_PATH.read_text(encoding="utf-8")

    assert "SIM slot" in source
    assert "Data roaming" in source
    assert "Network search" in source
    assert "APN profile" in source
    assert "VPN site-to-site" in source
    assert "Auto update time" in source
    assert "internet access switch" in source.lower()
    assert "DNS filter switch" in source
    assert "WiFi 2.4G hidden network" in source
    assert "WiFi 5G separate clients" in source


def test_readme_documents_connected_device_auto_add_option() -> None:
    """README should explain the new automatic client-device toggle."""
    source = README_PATH.read_text(encoding="utf-8")

    assert "Automatically Add Connected Devices" in source
    assert "Manually Add Connected Devices" in source
    assert "currently connected device reported by the router" in source
    assert "device_tracker" in source
    assert "MAC addresses, hostnames, and IP addresses" in source


def test_readme_covers_device_model_and_services() -> None:
    """README should document the current HA device split and service surface."""
    source = README_PATH.read_text(encoding="utf-8")

    assert "Main Router" in source
    assert "Mesh Nodes" in source
    assert "Connected Client Devices" in source
    assert "cudy_router.reboot_router" in source
    assert "cudy_router.restart_5g_connection" in source
    assert "cudy_router.switch_5g_band" in source
    assert "cudy_router.send_sms" in source
    assert "cudy_router.send_at_command" in source


def test_readme_lists_emulator_backed_compatibility_models() -> None:
    """README should clearly mark the emulator-backed models as compatible-but-untested."""
    source = README_PATH.read_text(encoding="utf-8")

    assert "Only the **Cudy P5** has been tested on real hardware so far." in source
    assert "mapped but have **not** been tested on real hardware yet" in source
    assert "WR11000" in source
    assert "LT500" in source
    assert "M3000" in source
    assert "RE1200-Outdoor" in source


def test_readme_documents_hacs_custom_repository_install() -> None:
    """README should include explicit HACS custom repository steps."""
    source = README_PATH.read_text(encoding="utf-8")

    assert "Custom repositories" in source
    assert "https://github.com/usersaynoso/ha-cudy-router" in source
    assert "Integration repository" in source or "**Integration** repository" in source
