from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from PySide6.QtCore import QLibraryInfo, QLocale, QSettings, QTranslator
from PySide6.QtWidgets import QApplication, QComboBox

from .zh_cn import STRINGS as ZH_CN_STRINGS

ENGLISH: Final = "en"
SIMPLIFIED_CHINESE: Final = "zh_CN"
TRADITIONAL_CHINESE: Final = "zh_TW"
GERMAN: Final = "de"
FRENCH: Final = "fr"
SPANISH: Final = "es"
RUSSIAN: Final = "ru"
KOREAN: Final = "ko"
JAPANESE: Final = "ja"
SETTINGS_KEY: Final = "ui/language"


@dataclass(frozen=True)
class LanguageSpec:
    code: str
    native_name: str
    qt_locale: str
    module: str


LANGUAGE_SPECS: Final = (
    LanguageSpec(ENGLISH, "English", "en", "en"),
    LanguageSpec(SIMPLIFIED_CHINESE, "简体中文", "zh_CN", "zh_cn"),
    LanguageSpec(TRADITIONAL_CHINESE, "繁體中文", "zh_TW", "zh_tw"),
    LanguageSpec(GERMAN, "Deutsch", "de", "de"),
    LanguageSpec(FRENCH, "Français", "fr", "fr"),
    LanguageSpec(SPANISH, "Español", "es", "es"),
    LanguageSpec(RUSSIAN, "Русский", "ru", "ru"),
    LanguageSpec(KOREAN, "한국어", "ko", "ko"),
    LanguageSpec(JAPANESE, "日本語", "ja", "ja"),
)
SUPPORTED_LANGUAGES: Final = tuple(spec.code for spec in LANGUAGE_SPECS)
_LANGUAGE_BY_CODE: Final = {spec.code: spec for spec in LANGUAGE_SPECS}

_active_language = SIMPLIFIED_CHINESE
_translators: list[QTranslator] = []


def _settings() -> QSettings:
    return QSettings("MInDes", "MInDes-UI")


def system_language(locale_name: str | None = None) -> str:
    name = (locale_name or QLocale.system().name()).lower()
    return ENGLISH if name.startswith("en") else SIMPLIFIED_CHINESE


def resolve_language(value: object | None = None) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in SUPPORTED_LANGUAGES else system_language()


def preferred_language() -> str:
    return resolve_language(_settings().value(SETTINGS_KEY, "", type=str))


def set_preferred_language(language: str) -> None:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported UI language: {language}")
    settings = _settings()
    settings.setValue(SETTINGS_KEY, language)
    settings.sync()


def active_language() -> str:
    return _active_language


@lru_cache(maxsize=None)
def catalog_for(language: str) -> dict[str, str]:
    spec = _LANGUAGE_BY_CODE.get(language)
    if spec is None:
        return ZH_CN_STRINGS
    module = importlib.import_module(f"{__package__}.{spec.module}")
    return module.STRINGS


def _install_qt_translations(app: QApplication, language: str) -> None:
    global _translators
    for translator in _translators:
        app.removeTranslator(translator)
    _translators = []

    locale = _LANGUAGE_BY_CODE[language].qt_locale
    if language == ENGLISH:
        return
    translations_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for filename in (f"qtbase_{locale}.qm", f"qt_{locale}.qm"):
        translator = QTranslator(app)
        if translator.load(os.path.join(translations_dir, filename)):
            app.installTranslator(translator)
            _translators.append(translator)


def initialize(app: QApplication, language: str | None = None) -> str:
    global _active_language
    requested = language if language is not None else preferred_language()
    _active_language = resolve_language(requested)
    QLocale.setDefault(QLocale(_LANGUAGE_BY_CODE[_active_language].qt_locale))
    _install_qt_translations(app, _active_language)
    return _active_language


def tr(key: str, **params: object) -> str:
    template = catalog_for(_active_language).get(key, ZH_CN_STRINGS.get(key, key))
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, ValueError):
        fallback = ZH_CN_STRINGS.get(key, key)
        try:
            return fallback.format(**params)
        except (KeyError, ValueError):
            return key


def add_combo_items(
    combo: QComboBox, items: list[tuple[str, str]] | tuple[tuple[str, str], ...]
) -> None:
    for label_key, value in items:
        combo.addItem(tr(label_key), value)


def combo_value(combo: QComboBox) -> str:
    value = combo.currentData()
    return str(value) if value is not None else combo.currentText()


def set_combo_value(combo: QComboBox, value: str) -> None:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)
    else:
        combo.setCurrentText(value)
