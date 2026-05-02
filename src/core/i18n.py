"""多言語対応モジュール - シングルトンI18nManagerによる翻訳キー管理"""

from __future__ import annotations

import importlib
from typing import Any

from PySide6.QtCore import QLocale

# サポート対象言語
SUPPORTED_LANGUAGES = {
    "en": "English",
    "ja": "日本語",
    "fr": "Français",
    "de": "Deutsch",
    "th": "ไทย",
    "zh_CN": "中文（简体）",
    "zh_TW": "中文（繁體）",
    "pt_BR": "Português - Brasil",
    "es_419": "Español - Latinoamérica",
    "ko": "한국어",
}

# ロケール名から言語コードへのマッピング
LOCALE_MAP = {
    "ja": "ja",
    "fr": "fr",
    "de": "de",
    "th": "th",
    "zh_CN": "zh_CN",
    "zh_Hans": "zh_CN",
    "zh_TW": "zh_TW",
    "zh_Hant": "zh_TW",
    "pt": "pt_BR",
    "es": "es_419",
    "ko": "ko",
}


class I18nManager:
    """多言語対応マネージャー（シングルトン）"""

    _instance: I18nManager | None = None

    def __new__(cls) -> I18nManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._current_lang = "en"
        self._translations: dict[str, str] = {}
        self._fallback_translations: dict[str, str] = {}
        self._initialized = True

    @classmethod
    def reset(cls) -> None:
        """シングルトンインスタンスをリセットする（テスト用）"""
        cls._instance = None

    def setup(self, lang_code: str | None = None) -> None:
        """言語を設定し、翻訳ファイルを読み込む"""
        if not lang_code:
            # OSのロケールから自動検出
            locale_name = QLocale.system().name()  # e.g. "ja_JP"
            base_lang = locale_name.split("_")[0]  # e.g. "ja"

            # マッピングを試みる
            lang_code = LOCALE_MAP.get(locale_name, LOCALE_MAP.get(base_lang, "en"))

        self._current_lang = lang_code if lang_code in SUPPORTED_LANGUAGES else "en"

        # 翻訳の読み込み
        self._translations = self._load_translation(self._current_lang)

        # 英語をフォールバックとして常に読み込む
        if self._current_lang != "en":
            self._fallback_translations = self._load_translation("en")
        else:
            self._fallback_translations = self._translations

    def _load_translation(self, lang_code: str) -> dict[str, str]:
        try:
            module = importlib.import_module(f".translations.{lang_code}", package="src.core")
            return getattr(module, "TRANSLATIONS", {})
        except (ImportError, AttributeError):
            return {}

    def tr(self, key: str, **kwargs: Any) -> str:
        """指定されたキーの翻訳を返す。なければキー自体を返す"""
        text = self._translations.get(key, self._fallback_translations.get(key, key))
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                pass
        return text

    @property
    def current_lang(self) -> str:
        return self._current_lang


# ------------------------------------------------------------------
# シングルトンインスタンスとショートカット関数
# ------------------------------------------------------------------

_manager = I18nManager()


def setup_i18n(lang_code: str | None = None) -> None:
    _manager.setup(lang_code)


def tr(key: str, **kwargs: Any) -> str:
    return _manager.tr(key, **kwargs)


def get_current_lang() -> str:
    return _manager.current_lang
