"""i18n モジュールのテスト"""
from __future__ import annotations

import pytest

from src.core.i18n import I18nManager, get_current_lang, setup_i18n, tr


@pytest.fixture(autouse=True)
def reset_i18n():
    """各テスト前にシングルトンをリセット"""
    I18nManager.reset()
    yield
    I18nManager.reset()


# ------------------------------------------------------------------
# setup / 言語選択
# ------------------------------------------------------------------


def test_setup_with_explicit_lang():
    """明示的な言語コード指定で正しく設定されること"""
    setup_i18n("ja")
    assert get_current_lang() == "ja"


def test_setup_with_english():
    """英語指定で正しく設定されること"""
    setup_i18n("en")
    assert get_current_lang() == "en"


def test_setup_unsupported_lang_falls_back_to_en():
    """未サポート言語はenにフォールバックすること"""
    setup_i18n("xx_UNKNOWN")
    assert get_current_lang() == "en"


# ------------------------------------------------------------------
# tr() — 翻訳キー取得
# ------------------------------------------------------------------


def test_tr_returns_english_translation():
    """英語の翻訳キーが正しく返ること"""
    setup_i18n("en")
    result = tr("menu.translate")
    assert result == "Execute Translation"


def test_tr_returns_japanese_translation():
    """日本語の翻訳キーが正しく返ること"""
    setup_i18n("ja")
    result = tr("menu.translate")
    # 日本語翻訳ファイルに定義されている値
    assert result != "menu.translate"
    assert len(result) > 0


def test_tr_unknown_key_returns_key_itself():
    """未定義キーはキー文字列自体を返すこと"""
    setup_i18n("en")
    result = tr("nonexistent.key.here")
    assert result == "nonexistent.key.here"


def test_tr_with_kwargs():
    """パラメータ付き翻訳が正しく展開されること"""
    setup_i18n("en")
    result = tr("msg.save_success", name="test_preset")
    assert "test_preset" in result


def test_tr_with_invalid_kwargs():
    """不正なパラメータでもエラーにならずテキストを返すこと"""
    setup_i18n("en")
    # msg.save_success は {name} を期待するが、別のキーを渡す
    result = tr("msg.save_success", wrong_key="value")
    # format失敗時は元テキストをそのまま返す
    assert isinstance(result, str)
    assert len(result) > 0


def test_tr_fallback_to_english():
    """日本語に未定義のキーは英語にフォールバックすること"""
    setup_i18n("en")
    en_text = tr("menu.quit")

    setup_i18n("ja")
    ja_text = tr("menu.quit")

    # 日本語翻訳が存在するか、英語フォールバックが返る（キー自体は返らない）
    assert ja_text != "menu.quit"
    assert isinstance(ja_text, str)


# ------------------------------------------------------------------
# シングルトン
# ------------------------------------------------------------------


def test_singleton_returns_same_instance():
    """I18nManagerがシングルトンであること"""
    a = I18nManager()
    b = I18nManager()
    assert a is b


def test_reset_creates_new_instance():
    """reset後は新しいインスタンスが生成されること"""
    a = I18nManager()
    I18nManager.reset()
    b = I18nManager()
    assert a is not b


# ------------------------------------------------------------------
# result.cancelled キー — 全言語での存在・非空・命名規則
# ------------------------------------------------------------------

SUPPORTED_LANGUAGES = ["en", "ja", "fr", "de", "th", "zh_CN", "zh_TW", "pt_BR", "es_419", "ko"]


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_result_cancelled_resolves_to_non_empty_string(lang: str):
    """全10言語で result.cancelled が非空文字列に解決されること

    Validates: Requirements 5.1, 5.4
    """
    setup_i18n(lang)
    result = tr("result.cancelled")
    assert isinstance(result, str)
    assert len(result) > 0
    # キー文字列そのものが返っていないこと（未定義フォールバックでない）
    assert result != "result.cancelled"


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_result_cancelled_key_follows_naming_convention(lang: str):
    """result.cancelled が result.* 名前空間に準拠していること

    Validates: Requirements 5.3
    """
    key = "result.cancelled"
    assert key.startswith("result.")
    # キーが実際に翻訳辞書に存在することを確認
    setup_i18n(lang)
    result = tr(key)
    assert result != key, f"Language '{lang}' is missing the '{key}' translation"
