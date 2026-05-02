"""アプリケーションサービス層 - GUI非依存のビジネスロジック"""

from __future__ import annotations

import threading
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

from .capture import warmup_ocr_engine
from .config import ConfigManager
from .i18n import tr
from .logger import get_logger
from .monitor import MonitorService

logger = get_logger("app_service")


class AppService(QObject):
    """
    翻訳フロー制御・監視モード管理・設定反映などのビジネスロジックを集約。
    GUI（OverlayWindow, ResultWindow等）には依存しない。

    Signals
    -------
    translation_started      : 翻訳開始
    translation_chunk(str)   : ストリーミングチャンク受信
    translation_done(str)    : 翻訳完了（全文）
    translation_error(str)   : 翻訳エラー
    translation_cancelled    : 翻訳キャンセル
    monitor_status_changed(bool) : 監視ON/OFF状態変化
    display_mode_changed(str)    : 表示モード変更 ("bubble_window" or "inline_overlay")
    font_size_detected(float)    : フォントサイズ検出
    settings_changed             : 設定変更（UIへの反映トリガー）
    """

    translation_started = Signal()
    translation_chunk = Signal(str)
    translation_done = Signal(str)
    translation_error = Signal(str)
    translation_cancelled = Signal()
    monitor_status_changed = Signal(bool)
    display_mode_changed = Signal(str)
    font_size_detected = Signal(float)
    settings_changed = Signal()

    def __init__(self, config: ConfigManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._translating = False
        self._font_size_signal_connected = False

        # MonitorService 生成
        self._monitor = MonitorService(config)

        # MonitorService のシグナルを中継
        self._monitor.translation_started.connect(self._on_translation_started)
        self._monitor.translation_chunk.connect(self._on_translation_chunk)
        self._monitor.translation_done.connect(self._on_translation_done)
        self._monitor.translation_error.connect(self._on_translation_error)
        self._monitor.translation_cancelled.connect(self._on_translation_cancelled)
        self._monitor.status_changed.connect(self._on_monitor_status_changed)

        logger.info("AppService 初期化完了")

    # ------------------------------------------------------------------
    # プロパティ
    # ------------------------------------------------------------------

    @property
    def config(self) -> ConfigManager:
        return self._config

    @property
    def monitor(self) -> MonitorService:
        return self._monitor

    @property
    def is_translating(self) -> bool:
        return self._translating

    # ------------------------------------------------------------------
    # ライフサイクル
    # ------------------------------------------------------------------

    def start(self) -> None:
        """サービスを開始（ワーカースレッド起動・OCRウォームアップ）"""
        self._monitor.start_worker()
        threading.Thread(target=warmup_ocr_engine, daemon=True).start()

        # 自動監視が有効なら開始
        if self._config.get_auto_monitor():
            self._monitor.start()

        # 表示モードに応じたフォントサイズ検出の設定
        self._apply_font_size_detection()

    def shutdown(self) -> None:
        """サービスを停止"""
        logger.info("AppService シャットダウン")
        self._monitor.stop()
        self._monitor.stop_worker()

    # ------------------------------------------------------------------
    # 翻訳操作
    # ------------------------------------------------------------------

    def trigger_translation(self) -> None:
        """手動翻訳を実行（翻訳中ならキャンセル）"""
        if self._translating:
            self._monitor.cancel_translation()
            return

        self._translating = True
        self._monitor.translate_once()

    def cancel_translation(self) -> None:
        """進行中の翻訳をキャンセル"""
        self._monitor.cancel_translation()

    # ------------------------------------------------------------------
    # 監視モード操作
    # ------------------------------------------------------------------

    def toggle_monitor(self) -> bool:
        """監視ON/OFFを切り替え、新しい状態を返す"""
        return self._monitor.toggle()

    def set_monitor_paused(self, paused: bool) -> None:
        """監視を一時停止/再開"""
        self._monitor.set_paused(paused)

    # ------------------------------------------------------------------
    # キャプチャ領域
    # ------------------------------------------------------------------

    def set_region_provider(
        self,
        provider: Callable[[], tuple[int, int, int, int]],
    ) -> None:
        """キャプチャ領域を返すコールバックを設定"""
        self._monitor.set_region_provider(provider)

    def invalidate_font_size_cache(self) -> None:
        """フォントサイズキャッシュを無効化（領域リサイズ時に呼ぶ）"""
        self._monitor.invalidate_font_size_cache()

    # ------------------------------------------------------------------
    # 表示モード操作
    # ------------------------------------------------------------------

    def get_display_mode(self) -> str:
        """現在の表示モードを返す"""
        return self._config.get_display().get("result_display_mode", "bubble_window")

    def toggle_display_mode(self) -> str:
        """表示モードを切り替え、新しいモードを返す"""
        current = self.get_display_mode()
        new_mode = "bubble_window" if current == "inline_overlay" else "inline_overlay"

        name = self._config.get_active_preset_name()
        preset = self._config.get_active_preset()
        preset["display"]["result_display_mode"] = new_mode
        self._config.save_preset(name, preset)

        self._apply_font_size_detection()
        self.display_mode_changed.emit(new_mode)
        return new_mode

    # ------------------------------------------------------------------
    # 設定反映
    # ------------------------------------------------------------------

    def apply_settings(self) -> None:
        """設定変更を各コンポーネントに反映"""
        # 監視サービスの設定再読み込み
        self._monitor.reload_config()

        # 自動監視が有効な場合はタイマーを再起動
        if self._monitor.is_running:
            self._monitor.stop()
            self._monitor.start()

        # フォントサイズ検出の設定
        self._apply_font_size_detection()

        # UIへの反映トリガー
        self.settings_changed.emit()

    def get_display_config(self) -> dict[str, Any]:
        """現在の表示設定を返す"""
        return self._config.get_display()

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------

    def _apply_font_size_detection(self) -> None:
        """表示モードに応じてフォントサイズ検出を有効/無効化"""
        is_inline = self.get_display_mode() == "inline_overlay"

        if is_inline:
            self._monitor.set_detect_font_size(True)
            if not self._font_size_signal_connected:
                self._monitor.font_size_detected.connect(self.font_size_detected)
                self._font_size_signal_connected = True
        else:
            self._monitor.set_detect_font_size(False)
            if self._font_size_signal_connected:
                self._monitor.font_size_detected.disconnect(self.font_size_detected)
                self._font_size_signal_connected = False

    # ------------------------------------------------------------------
    # MonitorService シグナルハンドラ
    # ------------------------------------------------------------------

    def _on_translation_started(self) -> None:
        self._translating = True
        self.translation_started.emit()

    def _on_translation_chunk(self, chunk: str) -> None:
        self.translation_chunk.emit(chunk)

    def _on_translation_done(self, full_text: str) -> None:
        self._translating = False
        self.translation_done.emit(full_text)

    def _on_translation_error(self, message: str) -> None:
        self._translating = False
        self.translation_error.emit(message)

    def _on_translation_cancelled(self) -> None:
        self._translating = False
        self.translation_cancelled.emit()

    def _on_monitor_status_changed(self, running: bool) -> None:
        self._config.set_auto_monitor(running)
        self.monitor_status_changed.emit(running)
