"""Tests for model normalization helpers."""

from __future__ import annotations

from tests.module_loader import load_cudy_module


model_names = load_cudy_module("model_names")


def test_normalize_model_name_collapses_spacing() -> None:
    """Model normalization should clean spacing without overfitting."""
    assert model_names.normalize_model_name("  WR1300E   V2.0  ") == "WR1300E V2.0"
    assert model_names.normalize_model_name("LT700 - Outdoor") == "LT700-Outdoor"


def test_resolve_model_name_applies_known_aliases() -> None:
    """Known alternate hardware strings should map to stable model names."""
    assert model_names.resolve_model_name("LT300 V3.0") == "LT300V3"
    assert model_names.resolve_model_name("WR1300 V4.0") == "WR1300V4.0"
    assert model_names.resolve_model_name(None) == "default"


def test_base_model_name_strips_hardware_revision_suffix() -> None:
    """Capability matching should be able to use the family model name."""
    assert model_names.base_model_name("WR11000 V1.0") == "WR11000"
    assert model_names.base_model_name("LT700-Outdoor V1.0") == "LT700-Outdoor"
    assert model_names.base_model_name("LT300V3") == "LT300V3"


def test_family_model_name_strips_marketing_suffixes_without_breaking_outdoor_models() -> None:
    """Model family extraction should retain real family names for suffixed variants."""
    assert model_names.family_model_name("R700-UK") == "R700"
    assert model_names.family_model_name("R700 AX3000") == "R700"
    assert model_names.family_model_name("LT700-Outdoor V1.0") == "LT700-Outdoor"


def test_iter_model_name_candidates_includes_alias_and_compact_forms() -> None:
    """Feature matching should be able to try normalized model variants."""
    candidates = model_names.iter_model_name_candidates("WR1300E V2.0")

    assert "WR1300E" in candidates
    assert "WR1300E V2.0" in candidates
    assert "WR1300EV2" in candidates
    assert "WR1300EV2.0" in candidates


def test_iter_model_name_candidates_includes_family_name_for_suffixed_models() -> None:
    """Feature matching should fall back to the base family for regional/marketing suffixes."""
    candidates = model_names.iter_model_name_candidates("R700 AX3000")

    assert "R700 AX3000" in candidates
    assert "R700" in candidates
