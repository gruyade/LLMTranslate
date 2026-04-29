"""自動監視サービス - QTimerベースの定期キャプチャと画像差分検出"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject, QTimer, Signal

from .async_worker import AsyncTranslationWorker
from .capture import capture_region, images_differ, ocr_analyze
from .config import ConfigManager
from .i18n import tr
from .logger import get_logger

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

logger = get_logger("monitor")


class MonitorService(QObject):
    """
    自動監視モード: 一定間隔でキャプチャし、変化があれば翻訳を実行する。

    Signals
    -------
    translation_started     : 翻訳開始を通知
    translation_chunk(str)  : ストリーミングチャンクを通知
    translation_done(str)   : 翻訳完了（全文）を通知
    translation_error(str)  : エラーメッセージを通知
    translation_cancelled   : キャンセル完了を通知
    status_changed(bool)    : 監視ON/OFFの状態変化を通知
    """

    translation_started = Signal()
    translation_chunk = Signal(str)
    translation_done = Signal(str)
    translation_error = Signal(str)
    translation_cancelled = Signal()
    status_changed = Signal(bool)
    font_size_detected = Signal(float)

    def __init__(self, config: ConfigManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._worker = AsyncTranslationWorker(config)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._running = False
        self._translating = False
        self._is_paused = False
        self._detect_font_size = False
        self._last_image_b64: str = ""
        self._get_region: Callable[[], tuple[int, int, int, int]] | None = None
        self._hide_widget: QWidget | None = None
        self._pre_capture_cb: Callable[[], None] | None = None
        self._post_capture_cb: Callable[[], None] | None = None

        # ワーカーのシグナルを中継
        self._worker.translation_started.connect(self.translation_started)
        self._worker.chunk_received.connect(self.translation_chunk)
        self._worker.translation_done.connect(self._on_worker_done)
        self._worker.translation_error.connect(self._on_worker_error)
        self._worker.translation_cancelled.connect(self._on_worker_cancelled)

    # ------------------------------------------------------------------
    # 設定
    # ------------------------------------------------------------------

    def set_region_provider(
        self,
        provider: Callable[[], tuple[int, int, int, int]],
    ) -> None:
        """キャプチャ領域を返すコールバックを設定 (x, y, width, height)"""
        self._get_region = provider

    def set_hide_widget(self, widget: "QWidget") -> None:
        """キャプチャ時に一時非表示にするウィジェット（枠線映り込み防止）"""
        self._hide_widget = widget

    def set_pre_capture_callback(self, cb: Callable[[], None] | None) -> None:
        self._pre_capture_cb = cb

    def set_post_capture_callback(self, cb: Callable[[], None] | None) -> None:
        self._post_capture_cb = cb

    def set_detect_font_size(self, enabled: bool) -> None:
        self._detect_font_size = enabled

    def reload_config(self) -> None:
        """設定変更後にクライアントを再生成"""
        self._worker.reload_client()
        if self._running:
            self._restart_timer()

    # ------------------------------------------------------------------
    # ワーカースレッド管理
    # ------------------------------------------------------------------

    def start_worker(self) -> None:
        """ワーカースレッドを起動"""
        self._worker.start_loop()

    def stop_worker(self) -> None:
        """ワーカースレッドを停止"""
        self._worker.stop_loop()

    def cancel_translation(self) -> None:
        """進行中の翻訳をキャンセル"""
        self._worker.cancel_translation()

    # ------------------------------------------------------------------
    # 開始・停止
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._last_image_b64 = ""
        self._restart_timer()
        interval_sec = self._config.get_monitor_config().get("interval", 2.0)
        logger.info("自動監視を開始: interval=%.1fs", interval_sec)
        self.status_changed.emit(True)

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._timer.stop()
        logger.info("自動監視を停止")
        self.status_changed.emit(False)

    def toggle(self) -> bool:
        """監視ON/OFFを切り替え、新しい状態を返す"""
        if self._running:
            self.stop()
        else:
            self.start()
        return self._running

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # 手動翻訳（単発実行）
    # ------------------------------------------------------------------

    def translate_once(self) -> None:
        """手動モードで1回だけ翻訳を実行"""
        if self._translating:
            return
        self._do_translate(force=True)

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------

    def _restart_timer(self) -> None:
        interval_sec = self._config.get_monitor_config().get("interval", 2.0)
        interval_ms = max(500, int(interval_sec * 1000))
        self._timer.start(interval_ms)

    def _on_tick(self) -> None:
        if self._translating or self._is_paused:
            return
        self._do_translate(force=False)

    def set_paused(self, paused: bool):
        self._is_paused = paused

    def _do_translate(self, force: bool) -> None:
        if self._get_region is None:
            return

        if self._worker.is_busy:
            return

        try:
            x, y, w, h = self._get_region()
            # キャプチャ前コールバック
            if self._pre_capture_cb:
                self._pre_capture_cb()
            
            try:
                # 点滅防止のため hide_widget（オーバーレイの透過操作）を渡さない
                image_b64 = capture_region(x, y, w, h, hide_widget=None)
            finally:
                # キャプチャ後コールバック
                if self._post_capture_cb:
                    self._post_capture_cb()
        except Exception as e:
            logger.error("キャプチャ中にエラー: %s", e)
            self.translation_error.emit(tr("error.capture", error=str(e)))
            return

        threshold = self._config.get_monitor_config().get("change_threshold", 0.05)
        if not force and not images_differ(self._last_image_b64, image_b64, threshold):
            logger.debug("画像差分なし。スキップします")
            return

        logger.debug("画像差分を検出。翻訳を実行します")

        # RapidOCR によるテキスト有無チェック + フォントサイズ検出（常時実行）
        has_text, font_size_pt = ocr_analyze(image_b64)
        if not has_text:
            logger.debug("OCR事前チェック: テキストなし。スキップします")
            return
        if self._detect_font_size and font_size_pt:
            self.font_size_detected.emit(font_size_pt)

        self._last_image_b64 = image_b64
        self._translating = True
        self._worker.submit_translation(image_b64)

    def _on_worker_done(self, full_text: str) -> None:
        self._translating = False
        self.translation_done.emit(full_text)

    def _on_worker_error(self, message: str) -> None:
        self._translating = False
        self.translation_error.emit(tr("error.translation", error=message))

    def _on_worker_cancelled(self) -> None:
        self._translating = False
        self.translation_cancelled.emit()
