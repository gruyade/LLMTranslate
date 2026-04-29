"""オーバーレイ枠線ウィンドウ - 透過背景に枠線のみ描画、ドラッグ移動・リサイズ対応"""

from __future__ import annotations

import sys
from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QCursor, QFont
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QScrollArea, QLabel

from ..core.i18n import tr

if TYPE_CHECKING:
    from PySide6.QtGui import QMouseEvent, QPaintEvent, QResizeEvent

# リサイズハンドルの当たり判定サイズ（px）- マージン内に収まるサイズ
HANDLE_SIZE = 5
# 最小ウィンドウサイズ（フレーム内側）
MIN_SIZE = QSize(80, 60)
NO_TEXT_PATTERN = "[No text detected]"

# フレーム右側のボタンパネル幅（ボタン3個を縦並び）
_BTN_PANEL_W = 28
# ボタンサイズ
_BTN_SIZE = 20
# グラブハンドルの幅・高さ
_GRAB_W = 30
_GRAB_H = 6
# ハンドルをフレーム外側に表示するためのマージン（px）
_HANDLE_MARGIN = 5


def _apply_dwm_no_border(hwnd: int) -> None:
    """Windows DWM の角丸枠線を除去する（Win32 API 呼び出し）"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import Structure, c_int, byref, windll

        class MARGINS(Structure):
            _fields_ = [
                ("cxLeftWidth", c_int),
                ("cxRightWidth", c_int),
                ("cyTopHeight", c_int),
                ("cyBottomHeight", c_int),
            ]

        # 非クライアント領域をクライアント領域に拡張（枠線を消す）
        margins = MARGINS(-1, -1, -1, -1)
        windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, byref(margins))

        # 角丸を無効化（DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_DONOTROUND = 1）
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_DONOTROUND = ctypes.c_int(1)
        windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            byref(DWMWCP_DONOTROUND),
            ctypes.sizeof(DWMWCP_DONOTROUND),
        )
    except Exception:
        pass  # DWM API が使えない環境では無視


def _apply_wda_exclude_from_capture(hwnd: int) -> None:
    """スクリーンキャプチャからウィンドウを除外する（Win32 WDA_EXCLUDEFROMCAPTURE）"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # WDA_EXCLUDEFROMCAPTURE = 0x11（Windows 10 build 19041以降）
        WDA_EXCLUDEFROMCAPTURE = 0x11
        ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
    except Exception:
        pass


_LABEL_STYLE_NORMAL = "color: white; padding: 4px; background: transparent;"
_LABEL_STYLE_ERROR = "color: #ff8888; padding: 4px; background: transparent;"


class InlineResultWidget(QWidget):
    """
    キャプチャ除外フラグ付きトップレベルウィンドウとして動作する半透明翻訳パネル。
    OverlayWindow の位置に追従して表示する。スクロール対応。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        # トップレベルウィンドウとして生成（parent は追従用に保持するが Qt 親にしない）
        super().__init__(None)
        self._overlay_parent = parent
        self._opacity = 0.7
        self._font_size = 14
        self._max_height_ratio = 0.4
        self._current_buffer = ""

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._build_ui()
        self.hide()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # キャプチャから除外（映り込み・ちらつき防止）
        _apply_wda_exclude_from_capture(int(self.winId()))

    def _build_ui(self) -> None:
        self.setObjectName("inline_result")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setAlignment(Qt.AlignTop)
        self._scroll.setStyleSheet(
            "QScrollArea { background: rgba(0, 0, 0, 160); border: none; border-radius: 4px; }"
        )

        self._content_label = QLabel()
        self._content_label.setWordWrap(True)
        self._content_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._content_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._content_label.setStyleSheet("color: white; padding: 4px; background: transparent;")
        self._update_font()

        self._scroll.setWidget(self._content_label)
        layout.addWidget(self._scroll)

    def _update_font(self) -> None:
        font = QFont()
        font.setPointSize(self._font_size)
        self._content_label.setFont(font)

    def set_font_size(self, size: int) -> None:
        self._font_size = size
        self._update_font()

    def set_opacity(self, opacity: float) -> None:
        self._opacity = opacity
        alpha = int(opacity * 255)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: rgba(0, 0, 0, {alpha}); border: none; border-radius: 4px; }}"
        )

    def set_max_height_ratio(self, ratio: float) -> None:
        self._max_height_ratio = ratio

    def start_new_translation(self) -> None:
        self._current_buffer = ""
        self._content_label.setText("")
        # エラー後の赤文字をリセット
        self._content_label.setStyleSheet(_LABEL_STYLE_NORMAL)
        self.show()

    def append_chunk(self, chunk: str) -> None:
        self._current_buffer += chunk
        stripped = self._current_buffer.strip()
        if stripped == NO_TEXT_PATTERN:
            self.hide()
            return
        if not self.isVisible():
            self.show()
        self._content_label.setText(self._current_buffer)
        self._scroll.verticalScrollBar().setValue(self._scroll.verticalScrollBar().maximum())

    def finish_translation(self) -> None:
        text = self._current_buffer.strip()
        if not text or text == NO_TEXT_PATTERN:
            self.hide()

    def show_error(self, message: str) -> None:
        self.show()
        self._content_label.setText(f"⚠ {message}")
        self._content_label.setStyleSheet(_LABEL_STYLE_ERROR)

    def clear(self) -> None:
        self._current_buffer = ""
        self._content_label.setText("")
        self.hide()


class ResizeEdge(Enum):
    NONE = auto()
    TOP = auto()
    BOTTOM = auto()
    LEFT = auto()
    RIGHT = auto()
    TOP_LEFT = auto()
    TOP_RIGHT = auto()
    BOTTOM_LEFT = auto()
    BOTTOM_RIGHT = auto()
    MOVE_HANDLE = auto()
    MODE_BTN = auto()
    EXEC_BTN = auto()
    SETTINGS_BTN = auto()
    VIEW_MODE_BTN = auto()


_EDGE_CURSORS: dict[ResizeEdge, Qt.CursorShape] = {
    ResizeEdge.TOP: Qt.SizeVerCursor,
    ResizeEdge.BOTTOM: Qt.SizeVerCursor,
    ResizeEdge.LEFT: Qt.SizeHorCursor,
    ResizeEdge.RIGHT: Qt.SizeHorCursor,
    ResizeEdge.TOP_LEFT: Qt.SizeFDiagCursor,
    ResizeEdge.TOP_RIGHT: Qt.SizeBDiagCursor,
    ResizeEdge.BOTTOM_LEFT: Qt.SizeBDiagCursor,
    ResizeEdge.BOTTOM_RIGHT: Qt.SizeFDiagCursor,
    ResizeEdge.MOVE_HANDLE: Qt.SizeAllCursor,
    ResizeEdge.MODE_BTN: Qt.PointingHandCursor,
    ResizeEdge.EXEC_BTN: Qt.PointingHandCursor,
    ResizeEdge.SETTINGS_BTN: Qt.PointingHandCursor,
    ResizeEdge.VIEW_MODE_BTN: Qt.PointingHandCursor,
    ResizeEdge.NONE: Qt.ArrowCursor,
}


class OverlayWindow(QWidget):
    """
    完全透過ウィンドウに枠線のみ描画するオーバーレイ。
    ボタンはフレーム右外側に縦並び配置。
    グラブハンドルはフレーム枠線の外側（_HANDLE_MARGIN 領域）に表示。
    """

    region_changed = Signal(int, int, int, int)
    is_operating_changed = Signal(bool)
    mode_toggle_requested = Signal()
    translate_requested = Signal()
    settings_requested = Signal()
    view_mode_toggle_requested = Signal()

    def __init__(
        self,
        x: int = 100,
        y: int = 100,
        width: int = 400,
        height: int = 300,
        border_color: str = "#FF0000",
        border_width: int = 2,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._border_color = QColor(border_color)
        self._border_width = border_width
        self._auto_mode = False
        self._is_operating = False
        self._is_translating = False
        self._inline_mode = False
        self._inline_widget: InlineResultWidget | None = None

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        # ウィンドウサイズ = フレーム幅 + ボタンパネル幅 + 左右マージン + 上下マージン
        m = _HANDLE_MARGIN
        self.setGeometry(
            x - m,
            y - m,
            width + _BTN_PANEL_W + m * 2,
            height + m * 2,
        )

        self._drag_start: QPoint | None = None
        self._drag_origin: QPoint | None = None
        self._resize_edge = ResizeEdge.NONE
        self._resize_start_pos: QPoint | None = None
        self._resize_start_rect: QRect | None = None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # ウィンドウが表示された後に DWM 枠線を除去
        _apply_dwm_no_border(int(self.winId()))

    def set_auto_mode(self, enabled: bool):
        self._auto_mode = enabled
        self.update()

    def set_inline_mode(self, enabled: bool) -> None:
        """表示モードボタンの表示状態を更新（inline_overlay=True, bubble_window=False）"""
        self._inline_mode = enabled
        self.update()

    def set_translating(self, translating: bool):
        self._is_translating = translating
        self.update()

    # ------------------------------------------------------------------
    # 外観設定
    # ------------------------------------------------------------------

    def set_border_color(self, color: str) -> None:
        self._border_color = QColor(color)
        self.update()

    def set_border_width(self, width: int) -> None:
        self._border_width = max(1, width)
        self.update()

    # ------------------------------------------------------------------
    # インライン表示
    # ------------------------------------------------------------------

    def enable_inline_result(self, font_size: int, opacity: float, max_height_ratio: float) -> None:
        if self._inline_widget is None:
            self._inline_widget = InlineResultWidget(self)

        self._inline_widget.set_font_size(font_size)
        self._inline_widget.set_opacity(opacity)
        self._inline_widget.set_max_height_ratio(max_height_ratio)
        self._update_inline_geometry()
        if self._is_translating:
            self._inline_widget.show()

    def disable_inline_result(self) -> None:
        if self._inline_widget:
            self._inline_widget.hide()

    def get_inline_widget(self) -> InlineResultWidget | None:
        return self._inline_widget

    def _update_inline_geometry(self) -> None:
        """InlineResultWidget をフレーム内側のスクリーン座標に配置（トップレベルウィンドウのため）"""
        if self._inline_widget is None:
            return

        m = _HANDLE_MARGIN
        bw = self._border_width
        geo = self.geometry()
        frame_w = geo.width() - _BTN_PANEL_W - m * 2
        # スクリーン座標で配置
        sx = geo.x() + m + bw
        sy = geo.y() + m + bw
        sw = frame_w - bw * 2
        sh = geo.height() - m * 2 - bw * 2
        if sh < 10:
            sh = 10
        self._inline_widget.setGeometry(sx, sy, sw, sh)

    # ------------------------------------------------------------------
    # キャプチャ領域の取得
    # ------------------------------------------------------------------

    def get_capture_region(self) -> tuple[int, int, int, int]:
        """フレーム内側のキャプチャ領域（ボタンパネル・マージンを除く）"""
        geo = self.geometry()
        m = _HANDLE_MARGIN
        bw = self._border_width
        frame_w = geo.width() - _BTN_PANEL_W - m * 2
        return (
            geo.x() + m + bw,
            geo.y() + m + bw,
            max(1, frame_w - bw * 2),
            max(1, geo.height() - m * 2 - bw * 2),
        )

    # ------------------------------------------------------------------
    # 描画
    # ------------------------------------------------------------------

    def paintEvent(self, event: "QPaintEvent") -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w, h = self.width(), self.height()
        m = _HANDLE_MARGIN
        # フレーム部分の幅（マージン・ボタンパネルを除く）
        frame_w = w - _BTN_PANEL_W - m * 2
        frame_h = h - m * 2

        # フレーム枠線（4辺描画）
        pen = QPen(self._border_color, self._border_width)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        half = self._border_width / 2

        # 左辺
        painter.drawLine(
            int(m + half), int(m + half),
            int(m + half), int(m + frame_h - half),
        )
        # 上辺
        painter.drawLine(
            int(m + half), int(m + half),
            int(m + frame_w - half), int(m + half),
        )
        # 下辺
        painter.drawLine(
            int(m + half), int(m + frame_h - half),
            int(m + frame_w - half), int(m + frame_h - half),
        )
        # 右辺（ボタンパネルとの境界線）
        painter.drawLine(
            int(m + frame_w - half), int(m + half),
            int(m + frame_w - half), int(m + frame_h - half),
        )

        # グラブハンドル（上辺中央、フレーム枠線の外側）
        handle_color = QColor(self._border_color)
        handle_color.setAlpha(200)
        painter.setBrush(handle_color)
        painter.setPen(Qt.NoPen)
        gh_x = m + (frame_w - _GRAB_W) // 2
        painter.drawRect(gh_x, m - _GRAB_H, _GRAB_W, _GRAB_H)

        # ボタンパネル（フレーム右外側に縦並び、上寄せ）
        btn_x = m + frame_w + (_BTN_PANEL_W - _BTN_SIZE) // 2
        btn_gap = 4
        btn_start_y = m + 8  # 上寄せ（固定マージン8px）

        # 設定ボタン
        settings_btn_rect = QRect(btn_x, btn_start_y, _BTN_SIZE, _BTN_SIZE)
        painter.setBrush(QColor("#607D8B"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(settings_btn_rect)
        painter.setPen(Qt.white)
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(settings_btn_rect, Qt.AlignCenter, "⚙")

        # 翻訳実行ボタン
        exec_btn_rect = QRect(btn_x, btn_start_y + _BTN_SIZE + btn_gap, _BTN_SIZE, _BTN_SIZE)
        if self._is_translating:
            painter.setBrush(QColor("#F44336"))
        else:
            painter.setBrush(QColor("#4CAF50"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(exec_btn_rect)
        painter.setPen(Qt.white)
        painter.drawText(exec_btn_rect, Qt.AlignCenter, "■" if self._is_translating else "▶")

        # モード切替ボタン
        mode_btn_rect = QRect(btn_x, btn_start_y + (_BTN_SIZE + btn_gap) * 2, _BTN_SIZE, _BTN_SIZE)
        if self._auto_mode:
            painter.setBrush(QColor("#2196F3"))
        else:
            painter.setBrush(QColor("#757575"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(mode_btn_rect)
        painter.setPen(Qt.white)
        painter.drawText(mode_btn_rect, Qt.AlignCenter, tr("overlay.mode.auto") if self._auto_mode else tr("overlay.mode.manual"))

        # 表示モード切替ボタン（インライン ↔ 別ウィンドウ）
        view_mode_btn_rect = QRect(btn_x, btn_start_y + (_BTN_SIZE + btn_gap) * 3, _BTN_SIZE, _BTN_SIZE)
        if self._inline_mode:
            painter.setBrush(QColor("#9C27B0"))
        else:
            painter.setBrush(QColor("#455A64"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(view_mode_btn_rect)
        painter.setPen(Qt.white)
        # インライン時は「□」（別ウィンドウへ切替）、別ウィンドウ時は「▣」（インラインへ切替）
        painter.drawText(view_mode_btn_rect, Qt.AlignCenter, "□" if self._inline_mode else "▣")

        # リサイズハンドル（四隅）- ボタン描画の後に描画して最前面に表示
        # 右側ハンドルは赤枠右辺の外側（ボタンパネル上に重ねて描画）
        hs = HANDLE_SIZE  # = _HANDLE_MARGIN = 5
        handle_color2 = QColor(self._border_color)
        handle_color2.setAlpha(200)
        painter.setBrush(handle_color2)
        painter.setPen(Qt.NoPen)
        corners = [
            QRect(m - hs, m - hs, hs, hs),                          # 左上
            QRect(m + frame_w, m - hs, hs, hs),                     # 右上（赤枠右辺外側）
            QRect(m - hs, m + frame_h, hs, hs),                     # 左下
            QRect(m + frame_w, m + frame_h, hs, hs),                # 右下（赤枠右辺外側）
        ]
        for corner in corners:
            painter.drawRect(corner)

    # ------------------------------------------------------------------
    # マウスイベント
    # ------------------------------------------------------------------

    def _btn_rects(self) -> tuple[QRect, QRect, QRect, QRect]:
        """設定・実行・モード・表示モードボタンの QRect を返す"""
        w, h = self.width(), self.height()
        m = _HANDLE_MARGIN
        frame_w = w - _BTN_PANEL_W - m * 2
        btn_x = m + frame_w + (_BTN_PANEL_W - _BTN_SIZE) // 2
        btn_gap = 4
        btn_start_y = m + 8  # 上寄せ
        settings = QRect(btn_x, btn_start_y, _BTN_SIZE, _BTN_SIZE)
        exec_ = QRect(btn_x, btn_start_y + _BTN_SIZE + btn_gap, _BTN_SIZE, _BTN_SIZE)
        mode = QRect(btn_x, btn_start_y + (_BTN_SIZE + btn_gap) * 2, _BTN_SIZE, _BTN_SIZE)
        view_mode = QRect(btn_x, btn_start_y + (_BTN_SIZE + btn_gap) * 3, _BTN_SIZE, _BTN_SIZE)
        return settings, exec_, mode, view_mode

    def _hit_test(self, pos: QPoint) -> ResizeEdge:
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        m = _HANDLE_MARGIN
        frame_w = w - _BTN_PANEL_W - m * 2
        frame_h = h - m * 2
        hs = HANDLE_SIZE
        bw = max(self._border_width + 4, hs)

        # グラブハンドル判定（フレーム上辺の外側マージン領域）- 最優先
        gh_x = m + (frame_w - _GRAB_W) // 2
        if y < m and y >= m - _GRAB_H - 4 and gh_x <= x <= gh_x + _GRAB_W:
            return ResizeEdge.MOVE_HANDLE

        # 四隅ハンドル判定（フレーム外側マージン領域）- ボタン判定より優先
        # 右側ハンドルは赤枠右辺外側（m + frame_w の位置）
        on_left_handle = x < m
        on_right_handle = m + frame_w <= x < m + frame_w + hs
        on_top_handle = y < m
        on_bottom_handle = m + frame_h <= y < m + frame_h + hs

        if on_top_handle and on_left_handle:
            return ResizeEdge.TOP_LEFT
        if on_top_handle and on_right_handle:
            return ResizeEdge.TOP_RIGHT
        if on_bottom_handle and on_left_handle:
            return ResizeEdge.BOTTOM_LEFT
        if on_bottom_handle and on_right_handle:
            return ResizeEdge.BOTTOM_RIGHT

        # ボタン判定
        settings_rect, exec_rect, mode_rect, view_mode_rect = self._btn_rects()
        if settings_rect.contains(pos):
            return ResizeEdge.SETTINGS_BTN
        if exec_rect.contains(pos):
            return ResizeEdge.EXEC_BTN
        if mode_rect.contains(pos):
            return ResizeEdge.MODE_BTN
        if view_mode_rect.contains(pos):
            return ResizeEdge.VIEW_MODE_BTN

        # ボタンパネル領域（ボタン以外）はNONE
        if x >= m + frame_w:
            return ResizeEdge.NONE

        # フレーム枠線上のリサイズ判定
        on_left = x < m + bw
        on_right = x > m + frame_w - bw
        on_top = y < m + bw
        on_bottom = y > m + frame_h - bw

        if on_top and on_left:
            return ResizeEdge.TOP_LEFT
        if on_top and on_right:
            return ResizeEdge.TOP_RIGHT
        if on_bottom and on_left:
            return ResizeEdge.BOTTOM_LEFT
        if on_bottom and on_right:
            return ResizeEdge.BOTTOM_RIGHT
        if on_top:
            return ResizeEdge.TOP
        if on_bottom:
            return ResizeEdge.BOTTOM
        if on_left:
            return ResizeEdge.LEFT
        if on_right:
            return ResizeEdge.RIGHT

        return ResizeEdge.NONE

    def mousePressEvent(self, event: "QMouseEvent") -> None:
        if event.button() != Qt.LeftButton:
            return

        edge = self._hit_test(event.position().toPoint())
        if edge == ResizeEdge.NONE:
            return

        if edge == ResizeEdge.MODE_BTN:
            self.mode_toggle_requested.emit()
            return
        if edge == ResizeEdge.EXEC_BTN:
            self.translate_requested.emit()
            return
        if edge == ResizeEdge.SETTINGS_BTN:
            self.settings_requested.emit()
            return
        if edge == ResizeEdge.VIEW_MODE_BTN:
            self.view_mode_toggle_requested.emit()
            return

        self._set_operating(True)

        if edge == ResizeEdge.MOVE_HANDLE:
            self._drag_start = event.globalPosition().toPoint()
            self._drag_origin = self.pos()
            self._resize_edge = ResizeEdge.NONE
        else:
            self._resize_edge = edge
            self._resize_start_pos = event.globalPosition().toPoint()
            self._resize_start_rect = self.geometry()
            self._drag_start = None

    def mouseMoveEvent(self, event: "QMouseEvent") -> None:
        if not (event.buttons() & Qt.LeftButton):
            edge = self._hit_test(event.position().toPoint())
            self.setCursor(QCursor(_EDGE_CURSORS.get(edge, Qt.ArrowCursor)))
            return

        global_pos = event.globalPosition().toPoint()

        if self._drag_start is not None and self._drag_origin is not None:
            delta = global_pos - self._drag_start
            self.move(self._drag_origin + delta)
            return

        if self._resize_edge != ResizeEdge.NONE and self._resize_start_pos is not None:
            self._do_resize(global_pos)

    def mouseReleaseEvent(self, event: "QMouseEvent") -> None:
        self._drag_start = None
        self._drag_origin = None
        self._resize_edge = ResizeEdge.NONE
        self._resize_start_pos = None
        self._resize_start_rect = None
        self._set_operating(False)
        self._emit_region_changed()

    def _set_operating(self, operating: bool):
        if self._is_operating != operating:
            self._is_operating = operating
            self.is_operating_changed.emit(operating)

    def _do_resize(self, global_pos: QPoint) -> None:
        if self._resize_start_rect is None or self._resize_start_pos is None:
            return

        delta = global_pos - self._resize_start_pos
        dx, dy = delta.x(), delta.y()
        r = QRect(self._resize_start_rect)
        edge = self._resize_edge
        m = _HANDLE_MARGIN

        if edge in (ResizeEdge.LEFT, ResizeEdge.TOP_LEFT, ResizeEdge.BOTTOM_LEFT):
            r.setLeft(r.left() + dx)
        if edge in (ResizeEdge.RIGHT, ResizeEdge.TOP_RIGHT, ResizeEdge.BOTTOM_RIGHT):
            r.setRight(r.right() + dx)
        if edge in (ResizeEdge.TOP, ResizeEdge.TOP_LEFT, ResizeEdge.TOP_RIGHT):
            r.setTop(r.top() + dy)
        if edge in (ResizeEdge.BOTTOM, ResizeEdge.BOTTOM_LEFT, ResizeEdge.BOTTOM_RIGHT):
            r.setBottom(r.bottom() + dy)

        min_w = MIN_SIZE.width() + _BTN_PANEL_W + m * 2
        min_h = MIN_SIZE.height() + m * 2
        if r.width() < min_w:
            if edge in (ResizeEdge.LEFT, ResizeEdge.TOP_LEFT, ResizeEdge.BOTTOM_LEFT):
                r.setLeft(r.right() - min_w)
            else:
                r.setRight(r.left() + min_w)
        if r.height() < min_h:
            if edge in (ResizeEdge.TOP, ResizeEdge.TOP_LEFT, ResizeEdge.TOP_RIGHT):
                r.setTop(r.bottom() - min_h)
            else:
                r.setBottom(r.top() + min_h)

        self.setGeometry(r)

    def _emit_region_changed(self) -> None:
        x, y, w, h = self.get_capture_region()
        self.region_changed.emit(x, y, w, h)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._update_inline_geometry()
        self._emit_region_changed()

    def resizeEvent(self, event: "QResizeEvent") -> None:
        super().resizeEvent(event)
        self._update_inline_geometry()
        self._emit_region_changed()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        # オーバーレイ非表示時にインラインウィジェットも隠す
        if self._inline_widget:
            self._inline_widget.hide()

    def closeEvent(self, event) -> None:
        # オーバーレイ終了時にインラインウィジェットも閉じる
        if self._inline_widget:
            self._inline_widget.close()
        super().closeEvent(event)
