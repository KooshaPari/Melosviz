"""Tests for melosviz.i18n catalog loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from melosviz.i18n import detect_locale, get_locale, set_locale, t

_LOCALES_DIR = Path(__file__).resolve().parents[1] / "src" / "melosviz" / "i18n" / "locales"


def _load_catalog(locale: str) -> dict[str, str]:
    return json.loads((_LOCALES_DIR / f"{locale}.json").read_text(encoding="utf-8"))


class TestCatalogParity:
    def test_en_and_es_share_keys(self) -> None:
        en = _load_catalog("en")
        es = _load_catalog("es")
        assert set(en) == set(es), f"key mismatch: en-only={set(en)-set(es)} es-only={set(es)-set(en)}"


class TestTranslate:
    def test_spanish_subcommand_help(self) -> None:
        set_locale("es")
        assert "Analizar" in t("cli.analyze.help")

    def test_format_interpolation(self) -> None:
        set_locale("en")
        msg = t("cli.error.file_not_found", cmd="analyze", path="/tmp/x.wav")
        assert "analyze" in msg
        assert "/tmp/x.wav" in msg

    def test_unknown_key_returns_key(self) -> None:
        set_locale("en")
        assert t("totally.missing.key") == "totally.missing.key"

    def test_explicit_fallback(self) -> None:
        set_locale("en")
        assert t("totally.missing.key", fallback="fb") == "fb"

    def test_detect_locale_es_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MELOSVIZ_LOCALE", "es-MX")
        set_locale(detect_locale())
        assert get_locale() == "es"
