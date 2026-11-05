"""Every shipped translation must cover the same keys as English."""

from __future__ import annotations

import json
import re
from pathlib import Path

TRANSLATIONS_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "cudy_router" / "translations"


def _flatten(payload: dict, prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in payload.items():
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{prefix}{key}."))
        else:
            flat[f"{prefix}{key}"] = value
    return flat


def test_french_translation_ships() -> None:
    """French was contributed in issue #40."""
    assert (TRANSLATIONS_DIR / "fr.json").is_file()


def test_translations_match_english_keys_and_placeholders() -> None:
    english = _flatten(json.loads((TRANSLATIONS_DIR / "en.json").read_text(encoding="utf-8")))
    for path in TRANSLATIONS_DIR.glob("*.json"):
        if path.name == "en.json":
            continue
        translated = _flatten(json.loads(path.read_text(encoding="utf-8")))
        assert set(translated) == set(english), path.name
        for key, text in english.items():
            assert set(re.findall(r"\{\w+\}", text)) == set(re.findall(r"\{\w+\}", translated[key])), (path.name, key)
