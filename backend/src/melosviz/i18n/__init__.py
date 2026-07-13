"""Thin catalog-based i18n for CLI help strings (en / es scaffold).

Override with ``MELOSVIZ_LOCALE=es``. Falls back to English for missing keys.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

Locale = Literal["en", "es"]

_LOCALES_DIR = Path(__file__).resolve().parent / "locales"
_SUPPORTED: tuple[Locale, ...] = ("en", "es")
_cache: dict[Locale, dict[str, str]] = {}
_current: Locale | None = None


def _load(locale: Locale) -> dict[str, str]:
    if locale not in _cache:
        path = _LOCALES_DIR / f"{locale}.json"
        _cache[locale] = json.loads(path.read_text(encoding="utf-8"))
    return _cache[locale]


def detect_locale() -> Locale:
    raw = (os.environ.get("MELOSVIZ_LOCALE") or "en").strip().lower()
    if raw.startswith("es"):
        return "es"
    return "en"


def set_locale(locale: Locale) -> None:
    global _current
    _current = locale if locale in _SUPPORTED else "en"


def get_locale() -> Locale:
    global _current
    if _current is None:
        _current = detect_locale()
    return _current


def t(key: str, fallback: str | None = None) -> str:
    """Look up *key* in the active catalog; fall back to en, then *fallback*/key."""
    locale = get_locale()
    catalog = _load(locale)
    if key in catalog:
        return catalog[key]
    if locale != "en":
        en = _load("en")
        if key in en:
            return en[key]
    return fallback if fallback is not None else key


__all__ = [
    "Locale",
    "detect_locale",
    "get_locale",
    "set_locale",
    "t",
]
