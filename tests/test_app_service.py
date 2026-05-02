"""AppService のテスト"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.app_service import AppService
from src.core.config import ConfigManager, DEFAULT_PRESET


@pytest.fixture
def config(tmp_path: Path, monkeypatch) -> ConfigManager:
    """テスト用 ConfigManager"""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr("src.core.config._get_config_path", lambda: config_file)
    monkeypatch.setattr("src.core.logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("src.core.logger.LOG_FILE", tmp_path / "logs" / "test.log")
    return ConfigManager()


@pytest.fixture
def service(config: ConfigManager) -> AppService:
    """テスト用 AppService（ワーカースレッドは起動しない）"""
    svc = AppService(config)
    yield svc
    # テスト後にクリーンアップ
    try:
        svc.shutdown()
    except Exception:
        pass


# ------------------------------------------------------------------
# 初期化
# ------------------------------------------------------------------


def test_service_init(service: AppService):
    """AppServiceが正常に初期化されること"""
    assert service.config is not None
    assert service.monitor is not None
    assert service.is_translating is False


# ------------------------------------------------------------------
# 翻訳操作
# ------------------------------------------------------------------


def test_trigger_translation_starts_translation(service: AppService):
    """trigger_translationがMonitorService.translate_onceを呼ぶこと"""
    with patch.object(service.monitor, "translate_once") as mock_translate:
        service.trigger_translation()
        mock_translate.assert_called_once()


def test_trigger_translation_cancels_when_translating(service: AppService):
    """翻訳中にtrigger_translationを呼ぶとキャンセルされること"""
    service._translating = True
    with patch.object(service.monitor, "cancel_translation") as mock_cancel:
        service.trigger_translation()
        mock_cancel.assert_called_once()


def test_cancel_translation(service: AppService):
    """cancel_translationがMonitorServiceに委譲されること"""
    with patch.object(service.monitor, "cancel_translation") as mock_cancel:
        service.cancel_translation()
        mock_cancel.assert_called_once()


# ------------------------------------------------------------------
# 監視モード操作
# ------------------------------------------------------------------


def test_toggle_monitor(service: AppService):
    """toggle_monitorがMonitorService.toggleを呼ぶこと"""
    with patch.object(service.monitor, "toggle", return_value=True) as mock_toggle:
        result = service.toggle_monitor()
        mock_toggle.assert_called_once()
        assert result is True


def test_set_monitor_paused(service: AppService):
    """set_monitor_pausedがMonitorServiceに委譲されること"""
    with patch.object(service.monitor, "set_paused") as mock_paused:
        service.set_monitor_paused(True)
        mock_paused.assert_called_once_with(True)


# ------------------------------------------------------------------
# 表示モード操作
# ------------------------------------------------------------------


def test_get_display_mode_default(service: AppService):
    """デフォルトの表示モードがbubble_windowであること"""
    assert service.get_display_mode() == "bubble_window"


def test_toggle_display_mode(service: AppService):
    """toggle_display_modeがモードを切り替えること"""
    assert service.get_display_mode() == "bubble_window"

    # シグナル発火を確認
    signal_received = []
    service.display_mode_changed.connect(lambda mode: signal_received.append(mode))

    new_mode = service.toggle_display_mode()
    assert new_mode == "inline_overlay"
    assert service.get_display_mode() == "inline_overlay"
    assert signal_received == ["inline_overlay"]

    # もう一度切り替え
    new_mode = service.toggle_display_mode()
    assert new_mode == "bubble_window"
    assert signal_received == ["inline_overlay", "bubble_window"]


# ------------------------------------------------------------------
# 設定反映
# ------------------------------------------------------------------


def test_apply_settings_emits_signal(service: AppService):
    """apply_settingsがsettings_changedシグナルを発火すること"""
    signal_received = []
    service.settings_changed.connect(lambda: signal_received.append(True))

    service.apply_settings()
    assert len(signal_received) == 1


def test_get_display_config(service: AppService):
    """get_display_configが表示設定を返すこと"""
    display = service.get_display_config()
    assert "border_color" in display
    assert "font_size" in display


# ------------------------------------------------------------------
# 翻訳シグナル中継
# ------------------------------------------------------------------


def test_translation_started_signal(service: AppService):
    """翻訳開始シグナルが中継されること"""
    signal_received = []
    service.translation_started.connect(lambda: signal_received.append(True))

    service._on_translation_started()
    assert service.is_translating is True
    assert len(signal_received) == 1


def test_translation_chunk_signal(service: AppService):
    """翻訳チャンクシグナルが中継されること"""
    chunks = []
    service.translation_chunk.connect(lambda c: chunks.append(c))

    service._on_translation_chunk("Hello")
    service._on_translation_chunk(" World")
    assert chunks == ["Hello", " World"]


def test_translation_done_signal(service: AppService):
    """翻訳完了シグナルが中継されること"""
    results = []
    service.translation_done.connect(lambda t: results.append(t))

    service._translating = True
    service._on_translation_done("完了テキスト")
    assert service.is_translating is False
    assert results == ["完了テキスト"]


def test_translation_error_signal(service: AppService):
    """翻訳エラーシグナルが中継されること"""
    errors = []
    service.translation_error.connect(lambda e: errors.append(e))

    service._translating = True
    service._on_translation_error("接続エラー")
    assert service.is_translating is False
    assert errors == ["接続エラー"]


def test_translation_cancelled_signal(service: AppService):
    """翻訳キャンセルシグナルが中継されること"""
    cancelled = []
    service.translation_cancelled.connect(lambda: cancelled.append(True))

    service._translating = True
    service._on_translation_cancelled()
    assert service.is_translating is False
    assert len(cancelled) == 1


def test_monitor_status_changed_signal(service: AppService, config: ConfigManager):
    """監視状態変更シグナルが中継され、設定に保存されること"""
    statuses = []
    service.monitor_status_changed.connect(lambda s: statuses.append(s))

    service._on_monitor_status_changed(True)
    assert statuses == [True]
    assert config.get_auto_monitor() is True

    service._on_monitor_status_changed(False)
    assert statuses == [True, False]
    assert config.get_auto_monitor() is False


# ------------------------------------------------------------------
# キャプチャ領域
# ------------------------------------------------------------------


def test_set_region_provider(service: AppService):
    """set_region_providerがMonitorServiceに委譲されること"""
    provider = lambda: (0, 0, 100, 100)
    with patch.object(service.monitor, "set_region_provider") as mock_set:
        service.set_region_provider(provider)
        mock_set.assert_called_once_with(provider)
