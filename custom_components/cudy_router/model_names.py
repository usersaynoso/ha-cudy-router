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


def base_model_name(model_name: str | None) -> str:
    """Return a stable model family name without the trailing hardware version."""
    normalized = normalize_model_name(model_name)
    if not normalized:
        return ""

    return re.sub(r"\s+V\d+(?:\.\d+)?$", "", normalized, flags=re.IGNORECASE)


def family_model_name(model_name: str | None) -> str:
    """Return the leading model family token when firmware adds a marketing suffix."""
    base_name = base_model_name(model_name)
    if not base_name:
        return ""
    if base_name.lower().endswith("-outdoor"):
        return base_name

    match = re.match(r"^[A-Z]+[0-9]+[A-Z0-9.]*", base_name, flags=re.IGNORECASE)
    return match.group(0) if match else base_name


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
    base_name = base_model_name(normalized)
    if base_name and base_name not in candidates:
        candidates.append(base_name)

    family_name = family_model_name(normalized)
    if family_name and family_name not in candidates:
        candidates.append(family_name)

    alias = _MODEL_ALIASES.get(normalized)
    if alias and alias not in candidates:
        candidates.append(alias)

    base_alias = _MODEL_ALIASES.get(base_name)
    if base_alias and base_alias not in candidates:
        candidates.append(base_alias)

    family_alias = _MODEL_ALIASES.get(family_name)
    if family_alias and family_alias not in candidates:
        candidates.append(family_alias)

    for variant in tuple(candidates):
        compact = variant.replace(" ", "")
        if compact not in candidates:
            candidates.append(compact)

        compact_without_dash = compact.replace("-", "")
        if compact_without_dash not in candidates:
            candidates.append(compact_without_dash)

    return tuple(candidates)
