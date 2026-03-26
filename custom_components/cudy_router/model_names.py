"""Helpers for normalizing and matching Cudy model names."""

from __future__ import annotations

import re

_MODEL_ALIASES: dict[str, str] = {
    "LT300 V3.0": "LT300V3",
    "WR1300E V2.0": "WR1300EV2",
    "WR1300 V4.0": "WR1300V4.0",
}


def normalize_model_name(model_name: str | None) -> str:
    """Normalize spacing and common formatting in a Cudy model string."""
    if not model_name:
        return ""

    normalized = model_name.strip()
    normalized = re.sub(r"\s*-\s*Outdoor\s*$", "-Outdoor", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+Outdoor\s*$", "-Outdoor", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def resolve_model_name(model_name: str | None, default: str = "default") -> str:
    """Map model aliases to a stable value while remaining permissive."""
    normalized = normalize_model_name(model_name)
    if not normalized:
        return default

    return _MODEL_ALIASES.get(normalized, normalized)


def iter_model_name_candidates(model_name: str | None) -> tuple[str, ...]:
    """Return likely variants for matching model-specific feature flags."""
    normalized = normalize_model_name(model_name)
    if not normalized:
        return ("default",)

    candidates: list[str] = [normalized]

    alias = _MODEL_ALIASES.get(normalized)
    if alias and alias not in candidates:
        candidates.append(alias)

    compact = normalized.replace(" ", "")
    if compact not in candidates:
        candidates.append(compact)

    compact_without_dash = compact.replace("-", "")
    if compact_without_dash not in candidates:
        candidates.append(compact_without_dash)

    return tuple(candidates)
