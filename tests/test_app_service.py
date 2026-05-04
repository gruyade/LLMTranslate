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


# ------------------------------------------------------------------
# 統合テスト: MonitorService + CaptureExclusionManager
# ------------------------------------------------------------------


class TestMonitorCaptureExclusionIntegration:
    """MonitorService と CaptureExclusionManager の統合テスト

    キャプチャ前後で exclude_all / restore_all が正しく呼ばれることを検証。
    """

    @pytest.fixture
    def monitor(self, config: ConfigManager):
        """テスト用 MonitorService（ワーカースレッドは起動しない）"""
        from src.core.monitor import MonitorService

        svc = MonitorService(config)
        # region provider を設定（有効な領域を返す）
        svc.set_region_provider(lambda: (0, 0, 100, 100))
        return svc

    @pytest.fixture
    def exclusion_mgr(self):
        """テスト用 CaptureExclusionManager（HWND を登録済み）"""
        from src.core.platform import CaptureExclusionManager

        mgr = CaptureExclusionManager()
        mgr.register(1001)
        mgr.register(1002)
        mgr.register(1003)
        return mgr

    def _setup_worker_mock(self, monitor) -> None:
        """_worker を MagicMock に差し替え（is_busy property のモック回避）"""
        mock_worker = MagicMock()
        mock_worker.is_busy = False
        monitor._worker = mock_worker

    def test_pre_capture_calls_exclude_all(
        self, monitor, exclusion_mgr
    ) -> None:
        """pre_capture_cb で exclude_all が呼ばれ、全 HWND に WDA_EXCLUDEFROMCAPTURE が設定される

        **Validates: Requirements 6.1, 7.1**
        """
        from src.core.platform import _WDA_EXCLUDEFROMCAPTURE

        # コールバック接続
        monitor.set_pre_capture_callback(exclusion_mgr.exclude_all)
        monitor.set_post_capture_callback(exclusion_mgr.restore_all)
        self._setup_worker_mock(monitor)

        wda_calls: list[tuple[int, int]] = []

        def track_wda(hwnd: int, affinity: int) -> None:
            wda_calls.append((hwnd, affinity))

        with patch("src.core.platform._set_window_display_affinity", side_effect=track_wda), \
             patch("src.core.monitor.capture_region", return_value="fake_b64"), \
             patch("src.core.monitor.images_differ", return_value=True), \
             patch("src.core.monitor.ocr_analyze", return_value=(True, None)):
            monitor.translate_once()

        # exclude_all で全 HWND に WDA_EXCLUDEFROMCAPTURE が呼ばれたことを検証
        exclude_calls = {
            (h, a) for h, a in wda_calls if a == _WDA_EXCLUDEFROMCAPTURE
        }
        expected = {
            (1001, _WDA_EXCLUDEFROMCAPTURE),
            (1002, _WDA_EXCLUDEFROMCAPTURE),
            (1003, _WDA_EXCLUDEFROMCAPTURE),
        }
        assert exclude_calls == expected

    def test_post_capture_calls_restore_all(
        self, monitor, exclusion_mgr
    ) -> None:
        """post_capture_cb で restore_all が呼ばれ、全 HWND に WDA_NONE が設定される

        **Validates: Requirements 6.2, 7.2**
        """
        from src.core.platform import _WDA_NONE

        monitor.set_pre_capture_callback(exclusion_mgr.exclude_all)
        monitor.set_post_capture_callback(exclusion_mgr.restore_all)
        self._setup_worker_mock(monitor)

        wda_calls: list[tuple[int, int]] = []

        def track_wda(hwnd: int, affinity: int) -> None:
            wda_calls.append((hwnd, affinity))

        with patch("src.core.platform._set_window_display_affinity", side_effect=track_wda), \
             patch("src.core.monitor.capture_region", return_value="fake_b64"), \
             patch("src.core.monitor.images_differ", return_value=True), \
             patch("src.core.monitor.ocr_analyze", return_value=(True, None)):
            monitor.translate_once()

        # restore_all で全 HWND に WDA_NONE が呼ばれたことを検証
        restore_calls = {
            (h, a) for h, a in wda_calls if a == _WDA_NONE
        }
        expected = {
            (1001, _WDA_NONE),
            (1002, _WDA_NONE),
            (1003, _WDA_NONE),
        }
        assert restore_calls == expected

    def test_post_capture_called_on_capture_exception(
        self, monitor, exclusion_mgr
    ) -> None:
        """capture_region 例外時も post_capture_cb（restore_all）が呼ばれる

        **Validates: Requirements 6.3**
        """
        from src.core.platform import _WDA_NONE

        monitor.set_pre_capture_callback(exclusion_mgr.exclude_all)
        monitor.set_post_capture_callback(exclusion_mgr.restore_all)
        self._setup_worker_mock(monitor)

        wda_calls: list[tuple[int, int]] = []

        def track_wda(hwnd: int, affinity: int) -> None:
            wda_calls.append((hwnd, affinity))

        with patch("src.core.platform._set_window_display_affinity", side_effect=track_wda), \
             patch("src.core.monitor.capture_region", side_effect=RuntimeError("capture failed")):
            monitor.translate_once()

        # 例外発生後も restore_all が呼ばれ、全 HWND に WDA_NONE が設定される
        restore_calls = {
            (h, a) for h, a in wda_calls if a == _WDA_NONE
        }
        expected = {
            (1001, _WDA_NONE),
            (1002, _WDA_NONE),
            (1003, _WDA_NONE),
        }
        assert restore_calls == expected

    def test_translate_once_invokes_pre_and_post_callbacks(
        self, monitor, exclusion_mgr
    ) -> None:
        """手動翻訳 translate_once でも pre/post コールバックが両方呼ばれる

        **Validates: Requirements 6.4**
        """
        from src.core.platform import _WDA_EXCLUDEFROMCAPTURE, _WDA_NONE

        monitor.set_pre_capture_callback(exclusion_mgr.exclude_all)
        monitor.set_post_capture_callback(exclusion_mgr.restore_all)

        call_order: list[str] = []
        wda_calls: list[tuple[int, int]] = []

        original_exclude = exclusion_mgr.exclude_all
        original_restore = exclusion_mgr.restore_all

        def tracked_exclude() -> None:
            call_order.append("pre")
            original_exclude()

        def tracked_restore() -> None:
            call_order.append("post")
            original_restore()

        monitor.set_pre_capture_callback(tracked_exclude)
        monitor.set_post_capture_callback(tracked_restore)
        self._setup_worker_mock(monitor)

        def track_wda(hwnd: int, affinity: int) -> None:
            wda_calls.append((hwnd, affinity))

        with patch("src.core.platform._set_window_display_affinity", side_effect=track_wda), \
             patch("src.core.monitor.capture_region", return_value="fake_b64"), \
             patch("src.core.monitor.images_differ", return_value=True), \
             patch("src.core.monitor.ocr_analyze", return_value=(True, None)):
            monitor.translate_once()

        # pre → post の順序で呼ばれたことを検証
        assert call_order == ["pre", "post"]

        # exclude_all と restore_all の両方が全 HWND に対して呼ばれたことを検証
        exclude_calls = {
            (h, a) for h, a in wda_calls if a == _WDA_EXCLUDEFROMCAPTURE
        }
        restore_calls = {
            (h, a) for h, a in wda_calls if a == _WDA_NONE
        }
        assert len(exclude_calls) == 3
        assert len(restore_calls) == 3
