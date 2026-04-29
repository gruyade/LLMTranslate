"""アプリケーションメインクラス - タスクトレイ・コンポーネント間の接続"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QObject, Signal, Slot
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter, QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QSystemTrayIcon,
    QWidget,
)

from .core.capture import warmup_ocr_engine
from .core.config import ConfigManager
from .ui.overlay_window import _BTN_PANEL_W, _HANDLE_MARGIN
from .core.logger import get_logger
from .core.monitor import MonitorService
from .core.i18n import tr
from .ui.overlay_window import OverlayWindow
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

    # フォールバック: プログラムで生成
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
    アプリケーション全体を管理するクラス。
    QApplicationは呼び出し元で生成済みであること。
    """

    def __init__(self, config: ConfigManager) -> None:
        self._config = config
        self._settings_dialog: SettingsDialog | None = None
        self._translating = False
        self._font_size_signal_connected = False

        logger.info("LLMTranslateApp 起動")

        # コンポーネント初期化
        self._init_overlay()
        self._init_result_window()
        self._init_monitor()
        self._init_tray()
        self._init_shortcuts()

        # 初期状態の反映
        overlay_cfg = self._config.get_overlay()
        if overlay_cfg.get("visible", True):
            self._overlay.show()

        if self._config.get_auto_monitor():
            self._monitor.start()
            self._overlay.set_auto_mode(True)
        else:
            self._overlay.set_auto_mode(False)

        # 初期表示モードの反映
        self._apply_display_mode()

        # RapidOCR エンジンをバックグラウンドでウォームアップ（初回翻訳の遅延を解消）
        threading.Thread(target=warmup_ocr_engine, daemon=True).start()

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
        self._overlay.is_operating_changed.connect(self._on_overlay_operating_changed)
        self._overlay.mode_toggle_requested.connect(self._toggle_monitor)
        self._overlay.translate_requested.connect(self._trigger_translation)
        self._overlay.settings_requested.connect(self._open_settings)
        self._overlay.view_mode_toggle_requested.connect(self._toggle_display_mode)

    def _init_result_window(self) -> None:
        display = self._config.get_display()
        self._result = ResultWindow(
            opacity=display.get("result_opacity", 0.9),
            font_size=display.get("font_size", 14),
            result_width=display.get("result_width", 350),
        )

    def _init_monitor(self) -> None:
        self._monitor = MonitorService(self._config)
        self._monitor.set_region_provider(self._overlay.get_capture_region)
        self._monitor.set_hide_widget(self._overlay)
        
        # シグナル接続
        self._monitor.translation_started.connect(self._on_translation_started)
        self._monitor.translation_chunk.connect(self._on_translation_chunk)
        self._monitor.translation_done.connect(self._on_translation_done)
        self._monitor.translation_error.connect(self._on_translation_error)
        self._monitor.translation_cancelled.connect(self._on_translation_cancelled)
        self._monitor.status_changed.connect(self._on_monitor_status_changed)
        
        # ワーカースレッド起動
        self._monitor.start_worker()

    def _init_tray(self) -> None:
        self._tray = QSystemTrayIcon(_create_tray_icon())
        self._tray.setToolTip("LLMTranslate")
        self._tray.activated.connect(self._on_tray_activated)
        self._build_tray_menu()
        self._tray.show()

    def _init_shortcuts(self) -> None:
        """グローバルショートカット（アプリウィンドウにフォーカスがなくても動作しない点に注意）"""
        # オーバーレイウィンドウにショートカットを設定
        sc_translate = QShortcut(QKeySequence("Ctrl+Shift+T"), self._overlay)
        sc_translate.setContext(Qt.ApplicationShortcut)
        sc_translate.activated.connect(self._trigger_translation)

        sc_toggle_overlay = QShortcut(QKeySequence("Ctrl+Shift+H"), self._overlay)
        sc_toggle_overlay.setContext(Qt.ApplicationShortcut)
        sc_toggle_overlay.activated.connect(self._toggle_overlay)

        sc_toggle_monitor = QShortcut(QKeySequence("Ctrl+Shift+M"), self._overlay)
        sc_toggle_monitor.setContext(Qt.ApplicationShortcut)
        sc_toggle_monitor.activated.connect(self._toggle_monitor)

    # ------------------------------------------------------------------
    # トレイメニュー構築
    # ------------------------------------------------------------------

    def _build_tray_menu(self) -> None:
        menu = QMenu()

        # 翻訳を実行
        self._action_translate = QAction(f"{tr('menu.translate')} (Ctrl+Shift+T)")
        self._action_translate.triggered.connect(self._trigger_translation)
        menu.addAction(self._action_translate)

        menu.addSeparator()

        # 自動監視モード
        self._action_monitor = QAction(tr("menu.auto_monitor"))
        self._action_monitor.setCheckable(True)
        self._action_monitor.setChecked(self._config.get_auto_monitor())
        self._action_monitor.triggered.connect(self._toggle_monitor)
        menu.addAction(self._action_monitor)

        menu.addSeparator()

        # 枠線の表示/非表示
        self._action_overlay = QAction(f"{tr('menu.show_overlay')} (Ctrl+Shift+H)")
        self._action_overlay.setCheckable(True)
        self._action_overlay.setChecked(self._config.get_overlay().get("visible", True))
        self._action_overlay.triggered.connect(self._toggle_overlay)
        menu.addAction(self._action_overlay)

        # 設定
        self._action_settings = QAction(tr("menu.settings"))
        self._action_settings.triggered.connect(self._open_settings)
        menu.addAction(self._action_settings)

        menu.addSeparator()

        # 終了
        self._action_quit = QAction(tr("menu.quit"))
        self._action_quit.triggered.connect(self._quit)
        menu.addAction(self._action_quit)

        self._tray.setContextMenu(menu)

    # ------------------------------------------------------------------
    # シグナルハンドラ
    # ------------------------------------------------------------------

    def _on_overlay_operating_changed(self, operating: bool) -> None:
        self._monitor.set_paused(operating)

    def _on_region_changed(self, x: int, y: int, w: int, h: int) -> None:
        """オーバーレイ枠が移動・リサイズされたとき"""
        # 結果ウィンドウの位置を更新
        overlay_rect = self._overlay.geometry()
        self._result.reposition(overlay_rect)
        # 設定に保存（ボタンパネル幅・マージンを除いたフレーム幅を保存）
        geo = self._overlay.geometry()
        m = _HANDLE_MARGIN
        self._config.set_overlay(
            geo.x() + m, geo.y() + m,
            geo.width() - _BTN_PANEL_W - m * 2,
            geo.height() - m * 2,
            self._overlay.isVisible()
        )

    def _get_display_mode(self) -> str:
        return self._config.get_display().get("result_display_mode", "bubble_window")

    def _on_translation_started(self) -> None:
        """翻訳開始"""
        self._translating = True
        self._action_translate.setEnabled(True) # キャンセル用に有効化
        self._overlay.set_translating(True)
        
        if self._get_display_mode() == "inline_overlay":
            widget = self._overlay.get_inline_widget()
            if widget:
                widget.start_new_translation()
        else:
            self._result.start_new_translation()
            self._result.reposition(self._overlay.geometry())

    def _on_translation_chunk(self, chunk: str) -> None:
        """ストリーミングチャンクを受信"""
        if self._get_display_mode() == "inline_overlay":
            widget = self._overlay.get_inline_widget()
            if widget:
                widget.append_chunk(chunk)
        else:
            self._result.append_chunk(chunk)

    def _on_translation_done(self, full_text: str) -> None:
        """翻訳完了"""
        self._translating = False
        self._action_translate.setEnabled(True)
        self._overlay.set_translating(False)
        
        if self._get_display_mode() == "inline_overlay":
            widget = self._overlay.get_inline_widget()
            if widget:
                widget.finish_translation()
        else:
            self._result.finish_translation()

    def _on_translation_error(self, message: str) -> None:
        """翻訳エラー"""
        self._translating = False
        self._action_translate.setEnabled(True)
        self._overlay.set_translating(False)
        logger.warning("翻訳エラー: %s", message)
        
        if self._get_display_mode() == "inline_overlay":
            widget = self._overlay.get_inline_widget()
            if widget:
                widget.show_error(message)
        else:
            self._result.show_error(message)

    def _on_translation_cancelled(self) -> None:
        """翻訳キャンセル"""
        self._translating = False
        self._action_translate.setEnabled(True)
        self._overlay.set_translating(False)
        # キャンセル時はバブルにその旨を表示
        msg = f"\n[{tr('result.cancelled') if hasattr(tr, 'result.cancelled') else 'Cancelled'}]"
        if self._get_display_mode() == "inline_overlay":
            widget = self._overlay.get_inline_widget()
            if widget:
                widget.append_chunk(msg)
                widget.finish_translation()
        else:
            self._result.append_chunk(msg)
            self._result.finish_translation()

    def _on_monitor_status_changed(self, running: bool) -> None:
        self._action_monitor.setChecked(running)
        self._config.set_auto_monitor(running)
        self._overlay.set_auto_mode(running)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self._toggle_overlay()

    # ------------------------------------------------------------------
    # アクション
    # ------------------------------------------------------------------

    def _trigger_translation(self) -> None:
        """手動翻訳を実行（翻訳中ならキャンセル）"""
        if self._translating:
            self._monitor.cancel_translation()
            return
        
        self._translating = True
        self._action_translate.setEnabled(True) # キャンセル可能にするため
        self._monitor.translate_once()

    def _toggle_overlay(self) -> None:
        if self._overlay.isVisible():
            self._overlay.hide()
            self._action_overlay.setChecked(False)
        else:
            self._overlay.show()
            self._action_overlay.setChecked(True)
        geo = self._overlay.geometry()
        m = _HANDLE_MARGIN
        self._config.set_overlay(
            geo.x() + m, geo.y() + m,
            geo.width() - _BTN_PANEL_W - m * 2,
            geo.height() - m * 2,
            self._overlay.isVisible()
        )

    def _toggle_monitor(self) -> None:
        running = self._monitor.toggle()
        self._action_monitor.setChecked(running)

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
        """設定が適用されたときにUIを更新"""
        display = self._config.get_display()

        # オーバーレイ枠線の更新
        self._overlay.set_border_color(display.get("border_color", "#FF0000"))
        self._overlay.set_border_width(display.get("border_width", 2))

        # 表示モードの反映
        self._apply_display_mode()

        # 結果ウィンドウの更新
        self._result.set_opacity(display.get("result_opacity", 0.9))
        self._result.set_font_size(display.get("font_size", 14))
        self._result.set_result_width(display.get("result_width", 350))

        # 監視サービスの設定再読み込み
        self._monitor.reload_config()

        # 自動監視が有効な場合はタイマーを再起動
        if self._monitor.is_running:
            self._monitor.stop()
            self._monitor.start()

    def _apply_display_mode(self) -> None:
        """現在の設定に基づいて表示モードを適用する"""
        display = self._config.get_display()
        mode = display.get("result_display_mode", "bubble_window")
        is_inline = mode == "inline_overlay"

        if is_inline:
            self._overlay.enable_inline_result(
                font_size=display.get("font_size", 14),
                opacity=display.get("inline_opacity", 0.7),
                max_height_ratio=display.get("inline_max_height_ratio", 0.4),
            )
            # インラインモード時は別ウィンドウを隠す
            self._result.hide()

            # フォントサイズ検出を有効化
            self._monitor.set_detect_font_size(True)
            # 重複接続を防ぐ（フラグで管理）
            if not self._font_size_signal_connected:
                self._monitor.font_size_detected.connect(self._on_font_size_detected)
                self._font_size_signal_connected = True
        else:
            self._overlay.disable_inline_result()
            self._monitor.set_detect_font_size(False)
            if self._font_size_signal_connected:
                self._monitor.font_size_detected.disconnect(self._on_font_size_detected)
                self._font_size_signal_connected = False

        self._overlay.set_inline_mode(is_inline)

    def _toggle_display_mode(self) -> None:
        """オーバーレイボタンから表示モードを切り替える"""
        display = self._config.get_display()
        current = display.get("result_display_mode", "bubble_window")
        new_mode = "bubble_window" if current == "inline_overlay" else "inline_overlay"

        # アクティブプリセットの display.result_display_mode を更新して保存
        name = self._config.get_active_preset_name()
        preset = self._config.get_active_preset()
        preset["display"]["result_display_mode"] = new_mode
        self._config.save_preset(name, preset)

        self._apply_display_mode()

    def _on_font_size_detected(self, pt: float) -> None:
        """検出されたフォントサイズを適用する"""
        widget = self._overlay.get_inline_widget()
        if widget:
            # 最小8pt, 最大72ptに制限
            clamped_pt = max(8, min(72, int(pt)))
            widget.set_font_size(clamped_pt)

    def _quit(self) -> None:
        """アプリケーションを終了"""
        logger.info("アプリケーション終了")
        # 終了前に設定を保存（ボタンパネル幅・マージンを除いたフレーム幅を保存）
        geo = self._overlay.geometry()
        m = _HANDLE_MARGIN
        self._config.set_overlay(
            geo.x() + m, geo.y() + m,
            geo.width() - _BTN_PANEL_W - m * 2,
            geo.height() - m * 2,
            self._overlay.isVisible()
        )
        self._monitor.stop()
        self._monitor.stop_worker()  # ワーカースレッド停止
        self._tray.hide()
        QApplication.quit()
