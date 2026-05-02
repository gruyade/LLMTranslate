"""アプリケーションGUI層 - AppServiceとUIコンポーネントの接続"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter, QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QSystemTrayIcon,
)

from .core.app_service import AppService
from .core.config import ConfigManager
from .core.i18n import tr
from .core.logger import get_logger
from .ui.overlay_window import OverlayWindow, _BTN_PANEL_W, _HANDLE_MARGIN
from .ui.result_window import ResultWindow
from .ui.settings_dialog import SettingsDialog

logger = get_logger("app")


def _get_resource_path(filename: str) -> Path:
    """リソースファイルのパスを返す（PyInstaller対応）"""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent / "resources"
    return base / filename


def _create_tray_icon() -> QIcon:
    """タスクトレイアイコンを生成（PNGがなければプログラムで生成）"""
    icon_path = _get_resource_path("icon.png")
    if icon_path.exists():
        return QIcon(str(icon_path))

    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#2196F3"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(2, 2, 28, 28, 6, 6)
    painter.setPen(QColor("white"))
    font = painter.font()
    font.setPointSize(14)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "T")
    painter.end()
    return QIcon(pixmap)


class LLMTranslateApp:
    """
    GUI層: UIコンポーネントの組み立てとAppServiceへのシグナル接続。
    ビジネスロジックはAppServiceに委譲する。
    """

    def __init__(self, config: ConfigManager) -> None:
        self._config = config
        self._settings_dialog: SettingsDialog | None = None

        # オーバーレイ位置保存のデバウンスタイマー
        self._save_overlay_timer = QTimer()
        self._save_overlay_timer.setSingleShot(True)
        self._save_overlay_timer.setInterval(500)
        self._save_overlay_timer.timeout.connect(self._save_overlay_state)

        logger.info("LLMTranslateApp 起動")

        # サービス層の初期化
        self._service = AppService(config)

        # UIコンポーネント初期化
        self._init_overlay()
        self._init_result_window()
        self._init_tray()
        self._init_shortcuts()

        # サービス層にキャプチャ領域プロバイダーを設定
        self._service.set_region_provider(self._overlay.get_capture_region)

        # サービス層のシグナルをUIに接続
        self._connect_service_signals()

        # サービス開始（ワーカースレッド起動・OCRウォームアップ）
        self._service.start()

        # 初期状態の反映
        overlay_cfg = self._config.get_overlay()
        if overlay_cfg.get("visible", True):
            self._overlay.show()

        self._overlay.set_auto_mode(self._config.get_auto_monitor())

        # 初期表示モードの反映
        self._apply_display_mode()

    # ------------------------------------------------------------------
    # 初期化
    # ------------------------------------------------------------------

    def _init_overlay(self) -> None:
        cfg = self._config.get_overlay()
        display = self._config.get_display()
        self._overlay = OverlayWindow(
            x=cfg.get("x", 100),
            y=cfg.get("y", 100),
            width=cfg.get("width", 400),
            height=cfg.get("height", 300),
            border_color=display.get("border_color", "#FF0000"),
            border_width=display.get("border_width", 2),
        )
        self._overlay.region_changed.connect(self._on_region_changed)
        self._overlay.is_operating_changed.connect(self._service.set_monitor_paused)
        self._overlay.mode_toggle_requested.connect(self._on_toggle_monitor)
        self._overlay.translate_requested.connect(self._service.trigger_translation)
        self._overlay.settings_requested.connect(self._open_settings)
        self._overlay.view_mode_toggle_requested.connect(self._on_toggle_display_mode)

    def _init_result_window(self) -> None:
        display = self._config.get_display()
        self._result = ResultWindow(
            opacity=display.get("result_opacity", 0.9),
            font_size=display.get("font_size", 14),
            result_width=display.get("result_width", 350),
        )

    def _init_tray(self) -> None:
        self._tray = QSystemTrayIcon(_create_tray_icon())
        self._tray.setToolTip("LLMTranslate")
        self._tray.activated.connect(self._on_tray_activated)
        self._build_tray_menu()
        self._tray.show()

    def _init_shortcuts(self) -> None:
        """グローバルショートカット"""
        sc_translate = QShortcut(QKeySequence("Ctrl+Shift+T"), self._overlay)
        sc_translate.setContext(Qt.ApplicationShortcut)
        sc_translate.activated.connect(self._service.trigger_translation)

        sc_toggle_overlay = QShortcut(QKeySequence("Ctrl+Shift+H"), self._overlay)
        sc_toggle_overlay.setContext(Qt.ApplicationShortcut)
        sc_toggle_overlay.activated.connect(self._toggle_overlay)

        sc_toggle_monitor = QShortcut(QKeySequence("Ctrl+Shift+M"), self._overlay)
        sc_toggle_monitor.setContext(Qt.ApplicationShortcut)
        sc_toggle_monitor.activated.connect(self._on_toggle_monitor)

    def _connect_service_signals(self) -> None:
        """AppServiceのシグナルをUIコンポーネントに接続"""
        s = self._service

        s.translation_started.connect(self._on_translation_started)
        s.translation_chunk.connect(self._on_translation_chunk)
        s.translation_done.connect(self._on_translation_done)
        s.translation_error.connect(self._on_translation_error)
        s.translation_cancelled.connect(self._on_translation_cancelled)
        s.monitor_status_changed.connect(self._on_monitor_status_changed)
        s.display_mode_changed.connect(self._apply_display_mode)
        s.font_size_detected.connect(self._on_font_size_detected)
        s.settings_changed.connect(self._on_settings_changed)

    # ------------------------------------------------------------------
    # トレイメニュー構築
    # ------------------------------------------------------------------

    def _build_tray_menu(self) -> None:
        menu = QMenu()

        self._action_translate = QAction(f"{tr('menu.translate')} (Ctrl+Shift+T)")
        self._action_translate.triggered.connect(self._service.trigger_translation)
        menu.addAction(self._action_translate)

        menu.addSeparator()

        self._action_monitor = QAction(tr("menu.auto_monitor"))
        self._action_monitor.setCheckable(True)
        self._action_monitor.setChecked(self._config.get_auto_monitor())
        self._action_monitor.triggered.connect(self._on_toggle_monitor)
        menu.addAction(self._action_monitor)

        menu.addSeparator()

        self._action_overlay = QAction(f"{tr('menu.show_overlay')} (Ctrl+Shift+H)")
        self._action_overlay.setCheckable(True)
        self._action_overlay.setChecked(self._config.get_overlay().get("visible", True))
        self._action_overlay.triggered.connect(self._toggle_overlay)
        menu.addAction(self._action_overlay)

        self._action_settings = QAction(tr("menu.settings"))
        self._action_settings.triggered.connect(self._open_settings)
        menu.addAction(self._action_settings)

        menu.addSeparator()

        self._action_quit = QAction(tr("menu.quit"))
        self._action_quit.triggered.connect(self._quit)
        menu.addAction(self._action_quit)

        self._tray.setContextMenu(menu)

    # ------------------------------------------------------------------
    # UI イベントハンドラ（GUI固有の処理）
    # ------------------------------------------------------------------

    def _on_region_changed(self, x: int, y: int, w: int, h: int) -> None:
        """オーバーレイ枠が移動・リサイズされたとき"""
        overlay_rect = self._overlay.geometry()
        self._result.reposition(overlay_rect)
        self._save_overlay_timer.start()
        # 領域変更時にフォントサイズキャッシュを無効化（次回 OCR で再検出）
        self._service.invalidate_font_size_cache()

    def _save_overlay_state(self) -> None:
        """オーバーレイ位置・サイズを設定ファイルに保存"""
        geo = self._overlay.geometry()
        m = _HANDLE_MARGIN
        self._config.set_overlay(
            geo.x() + m, geo.y() + m,
            geo.width() - _BTN_PANEL_W - m * 2,
            geo.height() - m * 2,
            self._overlay.isVisible()
        )

    def _on_translation_started(self) -> None:
        self._action_translate.setEnabled(True)
        self._overlay.set_translating(True)
        self._result.start_new_translation()
        self._result.reposition(self._overlay.geometry())

        if self._service.get_display_mode() == "inline_overlay":
            widget = self._overlay.get_inline_widget()
            if widget:
                widget.start_new_translation()

    def _on_translation_chunk(self, chunk: str) -> None:
        self._result.append_chunk(chunk)

        if self._service.get_display_mode() == "inline_overlay":
            widget = self._overlay.get_inline_widget()
            if widget:
                widget.append_chunk(chunk)

    def _on_translation_done(self, full_text: str) -> None:
        self._action_translate.setEnabled(True)
        self._overlay.set_translating(False)
        self._result.finish_translation()

        if self._service.get_display_mode() == "inline_overlay":
            widget = self._overlay.get_inline_widget()
            if widget:
                widget.finish_translation()

    def _on_translation_error(self, message: str) -> None:
        self._action_translate.setEnabled(True)
        self._overlay.set_translating(False)
        logger.warning("翻訳エラー: %s", message)
        self._result.show_error(message)

        if self._service.get_display_mode() == "inline_overlay":
            widget = self._overlay.get_inline_widget()
            if widget:
                widget.show_error(message)

    def _on_translation_cancelled(self) -> None:
        self._action_translate.setEnabled(True)
        self._overlay.set_translating(False)
        msg = f"\n[{tr('result.cancelled')}]"
        self._result.append_chunk(msg)
        self._result.finish_translation()

        if self._service.get_display_mode() == "inline_overlay":
            widget = self._overlay.get_inline_widget()
            if widget:
                widget.append_chunk(msg)
                widget.finish_translation()

    def _on_monitor_status_changed(self, running: bool) -> None:
        self._action_monitor.setChecked(running)
        self._overlay.set_auto_mode(running)

    def _on_toggle_monitor(self) -> None:
        running = self._service.toggle_monitor()
        self._action_monitor.setChecked(running)

    def _on_toggle_display_mode(self) -> None:
        self._service.toggle_display_mode()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self._toggle_overlay()

    def _toggle_overlay(self) -> None:
        if self._overlay.isVisible():
            self._overlay.hide()
            self._action_overlay.setChecked(False)
        else:
            self._overlay.show()
            self._action_overlay.setChecked(True)
        self._save_overlay_timer.stop()
        self._save_overlay_state()

    def _open_settings(self) -> None:
        logger.debug("設定画面を表示")
        if self._settings_dialog is not None and self._settings_dialog.isVisible():
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return

        self._settings_dialog = SettingsDialog(self._config)
        self._settings_dialog.settings_applied.connect(self._on_settings_applied)
        self._settings_dialog.show()

    def _on_settings_applied(self) -> None:
        """設定ダイアログから適用されたとき"""
        self._service.apply_settings()

    def _on_settings_changed(self) -> None:
        """AppServiceから設定変更通知を受けたとき、UIを更新"""
        display = self._config.get_display()

        self._overlay.set_border_color(display.get("border_color", "#FF0000"))
        self._overlay.set_border_width(display.get("border_width", 2))

        self._result.set_opacity(display.get("result_opacity", 0.9))
        self._result.set_font_size(display.get("font_size", 14))
        self._result.set_result_width(display.get("result_width", 350))

        self._apply_display_mode()

    def _apply_display_mode(self, mode: str | None = None) -> None:
        """表示モードをUIに反映"""
        if mode is None:
            mode = self._service.get_display_mode()
        display = self._config.get_display()
        is_inline = mode == "inline_overlay"

        if is_inline:
            self._overlay.enable_inline_result(
                font_size=display.get("font_size", 14),
                opacity=display.get("inline_opacity", 0.7),
                max_height_ratio=display.get("inline_max_height_ratio", 0.4),
            )
            self._result.set_background_mode(True)
            latest = self._result.get_latest_text()
            if latest:
                widget = self._overlay.get_inline_widget()
                if widget:
                    widget.start_new_translation()
                    widget.append_chunk(latest)
                    widget.finish_translation()
        else:
            self._overlay.disable_inline_result()
            self._result.set_background_mode(False)
            self._result.show_if_has_history()

        self._overlay.set_inline_mode(is_inline)

    def _on_font_size_detected(self, pt: float) -> None:
        widget = self._overlay.get_inline_widget()
        if widget:
            clamped_pt = max(8, min(72, int(pt)))
            widget.set_font_size(clamped_pt)

    def _quit(self) -> None:
        """アプリケーションを終了"""
        logger.info("アプリケーション終了")
        self._save_overlay_timer.stop()
        self._save_overlay_state()
        self._service.shutdown()
        self._tray.hide()
        QApplication.quit()
