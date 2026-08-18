from __future__ import annotations

import string
import ast
import pathlib
import re
import unittest

from mindes_ui.i18n import manager
from mindes_ui.i18n.zh_cn import STRINGS as ZH_CN_STRINGS


def placeholders(value: str) -> set[str]:
    return {
        name
        for _, name, _, _ in string.Formatter().parse(value)
        if name is not None
    }


class TranslationCatalogTests(unittest.TestCase):
    def test_catalog_keys_match(self):
        for language in manager.SUPPORTED_LANGUAGES:
            with self.subTest(language=language):
                self.assertEqual(set(ZH_CN_STRINGS), set(manager.catalog_for(language)))

    def test_format_placeholders_match(self):
        for language in manager.SUPPORTED_LANGUAGES:
            catalog = manager.catalog_for(language)
            mismatches = {
                key: (placeholders(ZH_CN_STRINGS[key]), placeholders(catalog[key]))
                for key in ZH_CN_STRINGS
                if placeholders(ZH_CN_STRINGS[key]) != placeholders(catalog[key])
            }
            with self.subTest(language=language):
                self.assertEqual({}, mismatches)

    def test_missing_non_chinese_entry_falls_back_to_chinese(self):
        key = "common.ready"
        original_language = manager._active_language
        catalog = manager.catalog_for(manager.ENGLISH)
        original_value = catalog.pop(key)
        try:
            manager._active_language = manager.ENGLISH
            self.assertEqual(ZH_CN_STRINGS[key], manager.tr(key))
        finally:
            catalog[key] = original_value
            manager._active_language = original_language

    def test_missing_chinese_entry_returns_key(self):
        key = "common.ready"
        original_language = manager._active_language
        original_value = ZH_CN_STRINGS.pop(key)
        try:
            manager._active_language = manager.SIMPLIFIED_CHINESE
            self.assertEqual(key, manager.tr(key))
        finally:
            ZH_CN_STRINGS[key] = original_value
            manager._active_language = original_language

    def test_first_launch_locale_rules(self):
        self.assertEqual(manager.ENGLISH, manager.system_language("en_US"))
        for locale in ("zh_CN", "zh_TW", "de_DE", "fr_FR", "ja_JP", ""):
            with self.subTest(locale=locale):
                expected = manager.system_language() if not locale else manager.SIMPLIFIED_CHINESE
                self.assertEqual(expected, manager.system_language(locale or None))

    def test_language_registry_order_and_native_names(self):
        self.assertEqual(
            [
                ("en", "English"),
                ("zh_CN", "简体中文"),
                ("zh_TW", "繁體中文"),
                ("de", "Deutsch"),
                ("fr", "Français"),
                ("es", "Español"),
                ("ru", "Русский"),
                ("ko", "한국어"),
                ("ja", "日本語"),
            ],
            [(spec.code, spec.native_name) for spec in manager.LANGUAGE_SPECS],
        )

    def test_generated_catalogs_are_not_baseline_placeholders(self):
        for language in manager.SUPPORTED_LANGUAGES:
            if language in {manager.ENGLISH, manager.SIMPLIFIED_CHINESE}:
                continue
            catalog = manager.catalog_for(language)
            same_as_chinese = sum(
                value == ZH_CN_STRINGS[key] for key, value in catalog.items()
            )
            with self.subTest(language=language):
                self.assertLess(same_as_chinese, len(ZH_CN_STRINGS) // 2)
                self.assertFalse(any("ZXQ" in value.upper() for value in catalog.values()))

    def test_invalid_language_uses_system_default(self):
        self.assertEqual(manager.system_language(), manager.resolve_language("invalid"))

    def test_common_qt_text_entry_points_do_not_use_english_literals(self):
        root = pathlib.Path(__file__).parents[1] / "src" / "mindes_ui"
        constructors = {
            "QPushButton": 0,
            "QLabel": 0,
            "QCheckBox": 0,
            "QGroupBox": 0,
            "QAction": 0,
        }
        methods = {
            "setWindowTitle": 0,
            "addAction": 0,
            "setPlaceholderText": 0,
            "setToolTip": 0,
            "setPlainText": 0,
            "setText": 0,
            "addTab": 1,
            "set_title": 0,
            "set_xlabel": 0,
            "set_ylabel": 0,
            "set_zlabel": 0,
            "SetTitle": 0,
            "SetXTitle": 0,
            "SetYTitle": 0,
            "SetZTitle": 0,
            "getOpenFileName": 1,
            "getOpenFileNames": 1,
            "getSaveFileName": 1,
        }
        technical_allowlist = re.compile(
            r"^(?:x[123]:?|deg x[123]:|[XYZ]:?|P[12] [XYZ]:?|"
            r"0, 0\.2, 0\.5, 1\.0|1\.00|G|G_alpha|G_beta|🔄)$"
        )
        violations = []
        for path in root.rglob("*.py"):
            if "i18n" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = (
                    node.func.id
                    if isinstance(node.func, ast.Name)
                    else node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else ""
                )
                index = constructors.get(name, methods.get(name))
                if index is None or len(node.args) <= index:
                    continue
                value = node.args[index]
                if (
                    isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                    and re.search(r"[A-Za-z]", value.value)
                    and not technical_allowlist.fullmatch(value.value)
                ):
                    violations.append(f"{path.relative_to(root)}:{node.lineno}: {value.value}")
                if name in {"getOpenFileName", "getOpenFileNames", "getSaveFileName"}:
                    for dialog_index in (1, 3):
                        if len(node.args) <= dialog_index:
                            continue
                        dialog_value = node.args[dialog_index]
                        if (
                            isinstance(dialog_value, ast.Constant)
                            and isinstance(dialog_value.value, str)
                            and re.search(r"[A-Za-z]", dialog_value.value)
                        ):
                            violations.append(
                                f"{path.relative_to(root)}:{node.lineno}: {dialog_value.value}"
                            )
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
