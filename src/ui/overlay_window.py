"""オーバーレイ枠線ウィンドウ - 透過背景に枠線のみ描画、ドラッグ移動・リサイズ対応"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QCursor
from PySide6.QtWidgets import QApplication, QWidget

from ..core.i18n import tr

if TYPE_CHECKING:
    from PySide6.QtGui import QMouseEvent, QPaintEvent, QResizeEvent

# リサイズハンドルの当たり判定サイズ（px）
HANDLE_SIZE = 10
# 最小ウィンドウサイズ
MIN_SIZE = QSize(80, 60)


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
    ResizeEdge.NONE: Qt.ArrowCursor,
}


class OverlayWindow(QWidget):
    """
    完全透過ウィンドウに枠線のみ描画するオーバーレイ。
    """

    region_changed = Signal(int, int, int, int)
    is_operating_changed = Signal(bool)
    mode_toggle_requested = Signal()
    translate_requested = Signal()
    settings_requested = Signal()

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

        # ウィンドウフラグ設定
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)

        # 初期位置・サイズ
        self.setGeometry(x, y, width, height)

        # ドラッグ・リサイズ状態
        self._drag_start: QPoint | None = None
        self._drag_origin: QPoint | None = None
        self._resize_edge = ResizeEdge.NONE
        self._resize_start_pos: QPoint | None = None
        self._resize_start_rect: QRect | None = None

    def set_auto_mode(self, enabled: bool):
        self._auto_mode = enabled
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
    # キャプチャ領域の取得
    # ------------------------------------------------------------------

    def get_capture_region(self) -> tuple[int, int, int, int]:
        """スクリーン座標でのキャプチャ領域 (x, y, width, height) を返す"""
        geo = self.geometry()
        bw = self._border_width
        return (
            geo.x() + bw,
            geo.y() + bw,
            max(1, geo.width() - bw * 2),
            max(1, geo.height() - bw * 2),
        )

    # ------------------------------------------------------------------
    # 描画
    # ------------------------------------------------------------------

    def paintEvent(self, event: "QPaintEvent") -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        pen = QPen(self._border_color, self._border_width)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        half = self._border_width / 2
        rect = self.rect().adjusted(
            int(half), int(half), -int(half), -int(half)
        )
        painter.drawRect(rect)

        # リサイズハンドル（小さな四角）を四隅に描画
        handle_color = QColor(self._border_color)
        handle_color.setAlpha(200)
        painter.setBrush(handle_color)
        painter.setPen(Qt.NoPen)
        hs = HANDLE_SIZE
        w, h = self.width(), self.height()
        corners = [
            QRect(0, 0, hs, hs),
            QRect(w - hs, 0, hs, hs),
            QRect(0, h - hs, hs, hs),
            QRect(w - hs, h - hs, hs, hs),
        ]
        for corner in corners:
            painter.drawRect(corner)

        # 移動ハンドル（上辺中央のグリップバー）を描画
        gh_w = 60
        gh_h = HANDLE_SIZE
        gh_x = (w - gh_w) // 2
        painter.drawRect(gh_x, 0, gh_w, gh_h)

        # 右上のボタン類
        btn_size = 20
        # モード切替ボタン
        mode_btn_rect = QRect(w - btn_size - 5, 5, btn_size, btn_size)
        if self._auto_mode:
            painter.setBrush(QColor("#2196F3")) # Blue
        else:
            painter.setBrush(QColor("#757575")) # Gray
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(mode_btn_rect)
        painter.setPen(Qt.white)
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(mode_btn_rect, Qt.AlignCenter, tr("overlay.mode.auto") if self._auto_mode else tr("overlay.mode.manual"))

        # 翻訳実行ボタン（常時表示、翻訳中は停止ボタン）
        exec_btn_rect = QRect(w - btn_size*2 - 10, 5, btn_size, btn_size)
        if self._is_translating:
            painter.setBrush(QColor("#F44336")) # Red
        else:
            painter.setBrush(QColor("#4CAF50")) # Green
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(exec_btn_rect)
        painter.setPen(Qt.white)
        painter.drawText(exec_btn_rect, Qt.AlignCenter, "■" if self._is_translating else "▶")

        # 左上の設定ボタン
        settings_btn_rect = QRect(5, 5, btn_size, btn_size)
        painter.setBrush(QColor("#607D8B")) # Blue Grey
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(settings_btn_rect)
        painter.setPen(Qt.white)
        painter.drawText(settings_btn_rect, Qt.AlignCenter, "⚙")

    # ------------------------------------------------------------------
    # マウスイベント
    # ------------------------------------------------------------------

    def _hit_test(self, pos: QPoint) -> ResizeEdge:
        """マウス位置からリサイズエッジを判定"""
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        hs = HANDLE_SIZE
        bw = max(self._border_width + 4, hs)

        btn_size = 20
        # ボタン判定
        if w - btn_size - 5 <= x <= w - 5 and 5 <= y <= 5 + btn_size:
            return ResizeEdge.MODE_BTN
        
        if w - btn_size*2 - 10 <= x <= w - btn_size - 10 and 5 <= y <= 5 + btn_size:
            return ResizeEdge.EXEC_BTN

        if 5 <= x <= 5 + btn_size and 5 <= y <= 5 + btn_size:
            return ResizeEdge.SETTINGS_BTN

        on_left = x < bw
        on_right = x > w - bw
        on_top = y < bw
        on_bottom = y > h - bw

        # 上辺中央の移動ハンドル判定
        gh_w = 60
        if y < hs and (w - gh_w) // 2 <= x <= (w + gh_w) // 2:
            return ResizeEdge.MOVE_HANDLE

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

        if edge in (ResizeEdge.LEFT, ResizeEdge.TOP_LEFT, ResizeEdge.BOTTOM_LEFT):
            r.setLeft(r.left() + dx)
        if edge in (ResizeEdge.RIGHT, ResizeEdge.TOP_RIGHT, ResizeEdge.BOTTOM_RIGHT):
            r.setRight(r.right() + dx)
        if edge in (ResizeEdge.TOP, ResizeEdge.TOP_LEFT, ResizeEdge.TOP_RIGHT):
            r.setTop(r.top() + dy)
        if edge in (ResizeEdge.BOTTOM, ResizeEdge.BOTTOM_LEFT, ResizeEdge.BOTTOM_RIGHT):
            r.setBottom(r.bottom() + dy)

        if r.width() < MIN_SIZE.width():
            if edge in (ResizeEdge.LEFT, ResizeEdge.TOP_LEFT, ResizeEdge.BOTTOM_LEFT):
                r.setLeft(r.right() - MIN_SIZE.width())
            else:
                r.setRight(r.left() + MIN_SIZE.width())
        if r.height() < MIN_SIZE.height():
            if edge in (ResizeEdge.TOP, ResizeEdge.TOP_LEFT, ResizeEdge.TOP_RIGHT):
                r.setTop(r.bottom() - MIN_SIZE.height())
            else:
                r.setBottom(r.top() + MIN_SIZE.height())

        self.setGeometry(r)

    def _emit_region_changed(self) -> None:
        x, y, w, h = self.get_capture_region()
        self.region_changed.emit(x, y, w, h)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._emit_region_changed()

    def resizeEvent(self, event: "QResizeEvent") -> None:
        super().resizeEvent(event)
        self._emit_region_changed()
