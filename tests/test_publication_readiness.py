"""Static checks for HACS and Hassfest publication requirements."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "custom_components" / "cudy_router" / "manifest.json"
HACS_JSON_PATH = ROOT / "hacs.json"
STRINGS_PATH = ROOT / "custom_components" / "cudy_router" / "strings.json"
TRANSLATIONS_PATH = ROOT / "custom_components" / "cudy_router" / "translations" / "en.json"
BRAND_ICON_PATH = ROOT / "custom_components" / "cudy_router" / "brand" / "icon.png"
BRAND_LOGO_PATH = ROOT / "custom_components" / "cudy_router" / "brand" / "logo.png"
HACS_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "validate.yaml"
HASSFEST_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "hassfest.yaml"
RELEASE_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yaml"


def test_manifest_has_required_hacs_fields() -> None:
    """Manifest should satisfy the current HACS integration requirements."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert manifest["domain"] == "cudy_router"
    assert manifest["name"] == "Cudy Router"
    assert manifest["documentation"] == "https://github.com/usersaynoso/ha-cudy-router#readme"
    assert manifest["dependencies"] == ["http"]
    assert manifest["issue_tracker"] == "https://github.com/usersaynoso/ha-cudy-router/issues"
    assert manifest["integration_type"] == "hub"
    assert manifest["requirements"] == [
        "beautifulsoup4==4.14.3",
        "python-dateutil==2.9.0.post0",
    ]
    assert manifest["version"] == "1.3.14"
    assert "image" not in manifest


def test_hacs_json_matches_current_schema() -> None:
    """hacs.json should not include deprecated keys rejected by HACS validation."""
    hacs_json = json.loads(HACS_JSON_PATH.read_text(encoding="utf-8"))

    assert hacs_json["name"] == "Cudy Router"
    assert hacs_json["zip_release"] is False
    assert set(hacs_json) == {"name", "zip_release"}


def test_config_flow_strings_cover_reauth_flow() -> None:
    """Translations should include the reauth flow implemented by config_flow.py."""
    strings = json.loads(STRINGS_PATH.read_text(encoding="utf-8"))
    translations = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))

    assert "reauth_confirm" in strings["config"]["step"]
    assert "reauth_successful" in strings["config"]["abort"]
    assert "reauth_confirm" in translations["config"]["step"]
    assert "reauth_successful" in translations["config"]["abort"]


def test_github_actions_exist_for_hacs_and_hassfest() -> None:
    """The repository should ship the validation workflows HACS expects."""
    hacs_workflow = HACS_WORKFLOW_PATH.read_text(encoding="utf-8")
    hassfest_workflow = HASSFEST_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert 'uses: hacs/action@main' in hacs_workflow
    assert "category: integration" in hacs_workflow
    assert 'uses: actions/checkout@v4' in hassfest_workflow
    assert 'uses: home-assistant/actions/hassfest@master' in hassfest_workflow


def test_release_workflow_creates_github_releases_from_version_tags() -> None:
    """Tag pushes should publish a GitHub release for the shipped version."""
    release_workflow = RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "tags:" in release_workflow
    assert '- "v*"' in release_workflow
    assert "contents: write" in release_workflow
    assert 'uses: actions/checkout@v4' in release_workflow
    assert 'name: Publish GitHub release' in release_workflow
    assert 'release_exists() {' in release_workflow
    assert 'wait_for_release() {' in release_workflow
    assert 'gh release view "$RELEASE_TAG"' in release_workflow
    assert 'gh release create "$RELEASE_TAG"' in release_workflow
    assert "--generate-notes" in release_workflow
    assert "--verify-tag" in release_workflow
    assert "Release.tag_name already exists" in release_workflow
    assert "waiting for visibility" in release_workflow
    assert 'was created concurrently; leaving it unchanged.' in release_workflow
    assert 'Failed to publish release $RELEASE_TAG.' in release_workflow


def test_local_brand_assets_exist() -> None:
    """The integration should ship local brand assets for Home Assistant."""
    assert BRAND_ICON_PATH.is_file()
    assert BRAND_LOGO_PATH.is_file()
