"""Static checks for AGENTS.md operational guidance."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENTS_PATH = ROOT / "AGENTS.md"


def test_agents_documents_home_assistant_deploy_hygiene() -> None:
    """AGENTS should capture the HA deploy rules learned from live testing."""
    source = AGENTS_PATH.read_text(encoding="utf-8")

    assert "changed runtime files on the remote system" in source
    assert "COPYFILE_DISABLE=1" in source
    assert "`._*` AppleDouble files" in source
    assert "may not provide `rsync`" in source
    assert "tar-over-SSH copy staged under `/tmp`" in source
    assert "outside `/config/custom_components`, for example under `/tmp`" in source


def test_agents_documents_r700_status_endpoint_rules() -> None:
    """AGENTS should preserve the R700 endpoint and parsing guidance."""
    source = AGENTS_PATH.read_text(encoding="utf-8")

    assert "`?detail=` or `?detail=1`" in source
    assert "`?details=`" in source
    assert "`wan`, `wanb`, `wanc`, and `wand`" in source
    assert "`WAN3 (DHCP)`" in source
    assert "`WAN1 / PPPoE`" in source
    assert "`Connected`, `Connected Clients`, `Online Clients`, and `Peers`" in source
    assert "do not stop at the first non-empty status page" in source


def test_agents_requires_runtime_tests_for_router_compatibility_changes() -> None:
    """AGENTS should require parser and collect_router_data coverage for compatibility fixes."""
    source = AGENTS_PATH.read_text(encoding="utf-8")

    assert "parser fixture test" in source
    assert "`collect_router_data` test" in source
    assert "Do not rely only on source-string assertions for compatibility changes." in source


def test_agents_requires_post_push_workflow_success_checks() -> None:
    """AGENTS should require checking GitHub workflows after commit-and-push tasks."""
    source = AGENTS_PATH.read_text(encoding="utf-8")

    assert "check the relevant GitHub workflows for the pushed SHA" in source
    assert "do not return until they have completed successfully" in source
    assert "inspect the failed logs, fix the issue" in source
