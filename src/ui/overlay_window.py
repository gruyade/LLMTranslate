"""オーバーレイ枠線ウィンドウ - 透過背景に枠線のみ描画、ドラッグ移動・リサイズ対応"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QPainter, QPen, QCursor, QFont, QFontMetrics,
    QLinearGradient,
)
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QScrollArea, QLabel

from ..core.i18n import tr
from ..core.platform import apply_wda_exclude_from_capture

if TYPE_CHECKING:
    from PySide6.QtGui import QMouseEvent, QPaintEvent, QResizeEvent

# リサイズハンドルの当たり判定サイズ（px）- マージン内に収まるサイズ
HANDLE_SIZE = 5
# 最小ウィンドウサイズ（フレーム内側）
MIN_SIZE = QSize(80, 60)
NO_TEXT_PATTERN = "[No text detected]"

# フレーム右側のボタンパネル幅（ボタン4個を縦並び）
_BTN_PANEL_W = 28
# ボタンサイズ
_BTN_SIZE = 20
# グラブハンドルの幅・高さ
_GRAB_W = 36
_GRAB_H = 5
# ウィンドウ端のクリック余白（px）
_HANDLE_MARGIN = 5
# ホバー拡大時のサイズ
_GRAB_W_EXPANDED = 60
_GRAB_H_EXPANDED = 10
_RESIZE_SIZE_EXPANDED = 10
# ホバー検出距離（px）
_HOVER_DISTANCE = 30


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
        # DWM 角丸を無効化（Windows 11 のウィンドウ角丸を除去）
        _apply_dwm_no_border(int(self.winId()))
        # キャプチャから除外（映り込み・ちらつき防止）
        apply_wda_exclude_from_capture(int(self.winId()))

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
            "QScrollArea { background: rgba(0, 0, 0, 160); border: none; }"
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
            f"QScrollArea {{ background: rgba(0, 0, 0, {alpha}); border: none; }}"
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


# ---------------------------------------------------------------------------
# AutoHideController — UI要素の自動非表示を制御するコントローラ
# ---------------------------------------------------------------------------


@dataclass
class _FadeState:
    """各UI要素のフェード状態"""

    current_opacity: float = 1.0
    target_opacity: float = 1.0
    velocity: float = 0.0


class AutoHideController:
    """UI要素の自動非表示を制御するコントローラ

    マウス位置に基づいて全UI要素（ボタンパネル・グラブハンドル・リサイズハンドル）の
    不透明度を一括管理し、フェードアニメーションで滑らかに表示/非表示を切り替える。
    """

    # タイミング定数
    FADE_DURATION_MS: int = 150
    FADE_OUT_DELAY_MS: int = 800
    INITIAL_SHOW_MS: int = 1000
    TICK_INTERVAL_MS: int = 16

    def __init__(self, overlay: "OverlayWindow") -> None:
        self._overlay = overlay

        # 全UI要素の統一フェード状態
        self._fade = _FadeState()

        # 内部フラグ
        self._is_operating: bool = False
        self._is_initial_show: bool = False
        self._mouse_inside: bool = False

        # アニメーションティックタイマー（≈60fps）
        self._fade_timer = QTimer()
        self._fade_timer.setInterval(self.TICK_INTERVAL_MS)
        self._fade_timer.timeout.connect(self._on_fade_tick)

        # マウス離脱後のフェードアウト遅延タイマー
        self._fade_out_delay_timer = QTimer()
        self._fade_out_delay_timer.setSingleShot(True)
        self._fade_out_delay_timer.setInterval(self.FADE_OUT_DELAY_MS)
        self._fade_out_delay_timer.timeout.connect(self._on_fade_out_delay)

        # 初期表示維持タイマー（1s singleShot）
        self._initial_show_timer = QTimer()
        self._initial_show_timer.setSingleShot(True)
        self._initial_show_timer.setInterval(self.INITIAL_SHOW_MS)
        self._initial_show_timer.timeout.connect(self._on_initial_show_end)

    # ------------------------------------------------------------------
    # 公開プロパティ
    # ------------------------------------------------------------------

    @property
    def opacity(self) -> float:
        """全UI要素の現在の不透明度 (0.0〜1.0)"""
        return self._fade.current_opacity

    # 後方互換プロパティ（描画コードから参照）
    @property
    def btn_opacity(self) -> float:
        return self._fade.current_opacity

    @property
    def grab_handle_opacity(self) -> float:
        return self._fade.current_opacity

    def resize_handle_opacity(self, corner_index: int) -> float:
        return self._fade.current_opacity

    # ------------------------------------------------------------------
    # Hover Zone 判定
    # ------------------------------------------------------------------

    def update_mouse_position(self, local_pos: QPoint) -> None:
        """マウス位置を受け取り、Hover Zone 判定を行う

        操作中・初期表示中は全要素を表示状態に維持する。
        フレーム枠線・ボタンパネル付近にマウスがあれば全UI要素を表示する。
        """
        if self._is_operating or self._is_initial_show:
            return

        w = self._overlay.width()
        h = self._overlay.height()
        m = _HANDLE_MARGIN
        frame_w = w - _BTN_PANEL_W - m * 2
        frame_h = h - m * 2
        mx, my = local_pos.x(), local_pos.y()

        # フレーム枠線からの距離で判定（内側・外側両方）
        band = _HOVER_DISTANCE

        # フレーム矩形を band だけ膨らませた領域（ボタンパネル含む）
        in_expanded = (
            m - band <= mx <= m + frame_w + _BTN_PANEL_W + band
            and m - band <= my <= m + frame_h + band
        )

        # フレーム矩形を band だけ縮めた領域（完全に内側の深い部分）
        in_inner = (
            m + band <= mx <= m + frame_w - band
            and m + band <= my <= m + frame_h - band
        )

        # 枠線付近 = 膨張領域内 かつ 内側深部でない
        # または ボタンパネル領域内
        in_border_band = in_expanded and not in_inner
        in_btn_panel = (
            m + frame_w - 10 <= mx <= m + frame_w + _BTN_PANEL_W + 10
            and m - 10 <= my <= m + frame_h + 10
        )

        self._fade.target_opacity = 1.0 if (in_border_band or in_btn_panel) else 0.0
        self._ensure_fade_timer()

    # ------------------------------------------------------------------
    # フェードアニメーション
    # ------------------------------------------------------------------

    def _on_fade_tick(self) -> None:
        """フェード状態を目標値に向けて補間する"""
        step = self.TICK_INTERVAL_MS / self.FADE_DURATION_MS
        state = self._fade

        if abs(state.current_opacity - state.target_opacity) < 0.001:
            if state.current_opacity != state.target_opacity:
                state.current_opacity = state.target_opacity
                self._overlay.update()
            self._fade_timer.stop()
            return

        if state.target_opacity > state.current_opacity:
            state.current_opacity = min(
                state.target_opacity,
                state.current_opacity + step,
            )
        else:
            state.current_opacity = max(
                state.target_opacity,
                state.current_opacity - step,
            )
        state.current_opacity = max(0.0, min(1.0, state.current_opacity))
        self._overlay.update()

    def _ensure_fade_timer(self) -> None:
        """目標と現在値に差がある場合にタイマーを開始する"""
        if abs(self._fade.current_opacity - self._fade.target_opacity) > 0.001:
            if not self._fade_timer.isActive():
                self._fade_timer.start()

    # ------------------------------------------------------------------
    # マウス入退出
    # ------------------------------------------------------------------

    def on_mouse_enter(self) -> None:
        """マウスがウィンドウ内に入った時の処理"""
        self._mouse_inside = True
        self._fade_out_delay_timer.stop()

    def on_mouse_leave(self) -> None:
        """マウスがウィンドウ外に出た時の処理"""
        self._mouse_inside = False
        if self._is_operating or self._is_initial_show:
            return
        # 全要素のターゲットを 0 にセットし、遅延後にフェードアウト開始
        self._fade_out_delay_timer.start()

    def _on_fade_out_delay(self) -> None:
        """フェードアウト遅延タイマー発火 — 非表示ターゲットに設定"""
        if self._is_operating or self._is_initial_show or self._mouse_inside:
            return
        self._fade.target_opacity = 0.0
        self._ensure_fade_timer()

    # ------------------------------------------------------------------
    # 強制表示・操作中制御
    # ------------------------------------------------------------------

    def force_visible(self) -> None:
        """全要素を即座に不透明度 1.0 に設定する"""
        self._fade.current_opacity = 1.0
        self._fade.target_opacity = 1.0
        self._fade_timer.stop()
        self._overlay.update()

    def set_operating(self, operating: bool) -> None:
        """ドラッグ/リサイズ操作中フラグの設定

        操作中は全要素を表示状態に維持する。
        """
        self._is_operating = operating
        if operating:
            self.force_visible()

    def on_show_or_reposition(self) -> None:
        """ウィンドウ表示/移動時に1秒間表示を維持する"""
        self._is_initial_show = True
        self.force_visible()
        self._initial_show_timer.start()

    def _on_initial_show_end(self) -> None:
        """初期表示維持タイマー発火 — 自動非表示を有効化"""
        self._is_initial_show = False
        if not self._mouse_inside:
            self._on_fade_out_delay()


# ---------------------------------------------------------------------------
# HoverExpander — ハンドルのホバー拡大アニメーションを管理
# ---------------------------------------------------------------------------


@dataclass
class _ScaleState:
    """サイズ補間状態"""

    current: float = 0.0   # 現在の補間値 (0.0=default, 1.0=expanded)
    target: float = 0.0    # 目標補間値
    velocity: float = 0.0  # 変化速度 (per tick)


def _ease_out(t: float) -> float:
    """ease-out 補間: 自然な減速感を実現

    入力 t は [0.0, 1.0] の線形補間値。
    出力は [0.0, 1.0] の ease-out 補間値。
    """
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 2


class HoverExpander:
    """ハンドルのホバー拡大アニメーションを管理

    マウス位置と各ハンドル中心の距離に基づいて拡大/縮小ターゲットを設定し、
    ease-out 補間で滑らかにサイズを変化させる。
    """

    # タイミング定数
    EXPAND_DURATION_MS: int = 100
    TICK_INTERVAL_MS: int = 16

    # グラブハンドルのサイズ範囲
    GRAB_DEFAULT: tuple[int, int] = (_GRAB_W, _GRAB_H)
    GRAB_EXPANDED: tuple[int, int] = (_GRAB_W_EXPANDED, _GRAB_H_EXPANDED)

    # リサイズハンドルのサイズ範囲
    RESIZE_DEFAULT: int = HANDLE_SIZE
    RESIZE_EXPANDED: int = _RESIZE_SIZE_EXPANDED

    def __init__(self, overlay: "OverlayWindow") -> None:
        self._overlay = overlay
        # グラブハンドルの拡大率
        self._grab_scale = _ScaleState()
        # リサイズハンドル×4 の拡大率
        self._resize_scales: list[_ScaleState] = [_ScaleState() for _ in range(4)]

        # アニメーションティックタイマー
        self._anim_timer = QTimer()
        self._anim_timer.setInterval(self.TICK_INTERVAL_MS)
        self._anim_timer.timeout.connect(self._on_anim_tick)

    # ------------------------------------------------------------------
    # マウス位置に基づくホバー判定
    # ------------------------------------------------------------------

    def update_mouse_position(self, local_pos: QPoint, frame_rect: QRect) -> None:
        """マウス位置に基づいてホバー状態を更新

        各ハンドル中心とマウス位置の距離を計算し、
        _HOVER_DISTANCE 以内なら拡大ターゲットを 1.0 に設定する。
        """
        mx, my = local_pos.x(), local_pos.y()

        # --- グラブハンドル ---
        # 中心: フレーム上辺の中央
        grab_cx = frame_rect.x() + frame_rect.width() / 2.0
        grab_cy = float(frame_rect.y())
        grab_dist = math.hypot(mx - grab_cx, my - grab_cy)
        self._grab_scale.target = 1.0 if grab_dist <= _HOVER_DISTANCE else 0.0

        # --- リサイズハンドル ---
        # 中心: フレームの 4 コーナー
        fx = frame_rect.x()
        fy = frame_rect.y()
        fw = frame_rect.width()
        fh = frame_rect.height()
        corner_centers = [
            (float(fx), float(fy)),              # TL
            (float(fx + fw), float(fy)),         # TR
            (float(fx), float(fy + fh)),         # BL
            (float(fx + fw), float(fy + fh)),    # BR
        ]
        for i, (cx, cy) in enumerate(corner_centers):
            dist = math.hypot(mx - cx, my - cy)
            self._resize_scales[i].target = 1.0 if dist <= _HOVER_DISTANCE else 0.0

        self._ensure_anim_timer()

    # ------------------------------------------------------------------
    # アニメーションティック
    # ------------------------------------------------------------------

    def _on_anim_tick(self) -> None:
        """各スケール状態を目標値に向けて補間する"""
        step = self.TICK_INTERVAL_MS / self.EXPAND_DURATION_MS

        changed = False
        all_done = True
        for state in self._all_scale_states():
            if abs(state.current - state.target) < 0.001:
                if state.current != state.target:
                    state.current = state.target
                    changed = True
                continue

            all_done = False
            if state.target > state.current:
                state.current = min(state.target, state.current + step)
            else:
                state.current = max(state.target, state.current - step)
            # クランプ
            state.current = max(0.0, min(1.0, state.current))
            changed = True

        if changed:
            self._overlay.update()

        if all_done:
            self._anim_timer.stop()

    def _all_scale_states(self) -> list[_ScaleState]:
        """全スケール状態のリストを返す"""
        return [self._grab_scale, *self._resize_scales]

    def _ensure_anim_timer(self) -> None:
        """目標と現在値に差がある場合にタイマーを開始する"""
        for state in self._all_scale_states():
            if abs(state.current - state.target) > 0.001:
                if not self._anim_timer.isActive():
                    self._anim_timer.start()
                return

    # ------------------------------------------------------------------
    # 公開プロパティ
    # ------------------------------------------------------------------

    @property
    def grab_width(self) -> float:
        """現在のグラブハンドル幅（ease-out 補間値）"""
        t = _ease_out(self._grab_scale.current)
        return _GRAB_W + (_GRAB_W_EXPANDED - _GRAB_W) * t

    @property
    def grab_height(self) -> float:
        """現在のグラブハンドル高さ（ease-out 補間値）"""
        t = _ease_out(self._grab_scale.current)
        return _GRAB_H + (_GRAB_H_EXPANDED - _GRAB_H) * t

    def resize_handle_size(self, corner_index: int) -> float:
        """指定コーナーのリサイズハンドルサイズ（ease-out 補間値）

        corner_index: 0=TL, 1=TR, 2=BL, 3=BR
        不正なインデックスの場合は HANDLE_SIZE を返す。
        """
        if 0 <= corner_index < 4:
            t = _ease_out(self._resize_scales[corner_index].current)
            return HANDLE_SIZE + (_RESIZE_SIZE_EXPANDED - HANDLE_SIZE) * t
        return float(HANDLE_SIZE)

    @property
    def needs_repaint(self) -> bool:
        """アニメーション中で再描画が必要かどうか"""
        for state in self._all_scale_states():
            if abs(state.current - state.target) > 0.001:
                return True
        return False


class OverlayWindow(QWidget):
    """
    完全透過ウィンドウに枠線のみ描画するオーバーレイ。
    ボタンはフレーム右外側に縦並び配置。
    グラブハンドル・リサイズハンドルはフレーム内側に表示。
    WDA_EXCLUDEFROMCAPTURE でキャプチャから除外済み。
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

        # 自動非表示・ホバー拡大コントローラ
        self._auto_hide = AutoHideController(self)
        self._hover_expander = HoverExpander(self)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # ウィンドウが表示された後に DWM 枠線を除去
        _apply_dwm_no_border(int(self.winId()))
        # キャプチャから除外（ハンドル等がキャプチャに映り込むのを防止）
        apply_wda_exclude_from_capture(int(self.winId()))
        # 初期表示時に1秒間UI要素を表示維持
        self._auto_hide.on_show_or_reposition()

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

        # グラブハンドル（上辺中央、フレーム内側）- 角丸ピル型
        grab_opacity = self._auto_hide.grab_handle_opacity
        if grab_opacity > 0.01:
            gw = self._hover_expander.grab_width
            gh = self._hover_expander.grab_height
            handle_color = QColor(self._border_color)
            handle_color.setAlpha(int(180 * grab_opacity))
            painter.setBrush(handle_color)
            painter.setPen(Qt.NoPen)
            gh_x = m + (frame_w - gw) / 2.0
            gh_y = m + self._border_width + 2  # フレーム内側に配置
            painter.drawRoundedRect(QRectF(gh_x, gh_y, gw, gh), 2, 2)

        # ボタンパネル（フレーム右外側に縦並び、上寄せ）
        btn_opacity = self._auto_hide.btn_opacity
        if btn_opacity > 0.01:
            painter.setOpacity(btn_opacity)
            btn_x = m + frame_w + (_BTN_PANEL_W - _BTN_SIZE) // 2
            btn_gap = 4
            btn_start_y = m + 6

            # --- ボタン描画ヘルパー ---
            def _draw_btn(rect: QRect, base_color: QColor, text: str, font_size: int = 9) -> None:
                """角丸四角ボタンを描画し、テキストを正確にセンタリング"""
                cx = rect.center().x()
                cy = rect.center().y()
                radius = 4  # 角丸半径

                # 上→下のリニアグラデーション
                grad = QLinearGradient(rect.x(), rect.y(), rect.x(), rect.y() + rect.height())
                lighter = QColor(base_color)
                lighter.setRed(min(255, lighter.red() + 30))
                lighter.setGreen(min(255, lighter.green() + 30))
                lighter.setBlue(min(255, lighter.blue() + 30))
                grad.setColorAt(0.0, lighter)
                grad.setColorAt(1.0, base_color)
                painter.setBrush(grad)

                # 微細な明るい縁取り
                border_pen = QPen(QColor(255, 255, 255, 40), 1)
                painter.setPen(border_pen)
                painter.drawRoundedRect(rect, radius, radius)

                # テキスト描画（フォントメトリクスで正確にセンタリング）
                f = QFont("Segoe UI Symbol", font_size)
                f.setBold(True)
                painter.setFont(f)
                painter.setPen(QColor(255, 255, 255, 240))
                fm = QFontMetrics(f)
                tw = fm.horizontalAdvance(text)
                th = fm.ascent()
                tx = cx - tw // 2
                ty = cy + (th - fm.descent()) // 2
                painter.drawText(tx, ty, text)

            # 設定ボタン
            settings_btn_rect = QRect(btn_x, btn_start_y, _BTN_SIZE, _BTN_SIZE)
            _draw_btn(settings_btn_rect, QColor("#546E7A"), "⚙", 11)

            # 翻訳実行ボタン
            exec_btn_rect = QRect(btn_x, btn_start_y + _BTN_SIZE + btn_gap, _BTN_SIZE, _BTN_SIZE)
            exec_color = QColor("#E53935") if self._is_translating else QColor("#43A047")
            exec_text = "■" if self._is_translating else "▶"
            _draw_btn(exec_btn_rect, exec_color, exec_text, 10)

            # モード切替ボタン
            mode_btn_rect = QRect(btn_x, btn_start_y + (_BTN_SIZE + btn_gap) * 2, _BTN_SIZE, _BTN_SIZE)
            mode_color = QColor("#1E88E5") if self._auto_mode else QColor("#616161")
            mode_text = tr("overlay.mode.auto") if self._auto_mode else tr("overlay.mode.manual")
            _draw_btn(mode_btn_rect, mode_color, mode_text, 10)

            # 表示モード切替ボタン（インライン ↔ 別ウィンドウ）
            view_mode_btn_rect = QRect(btn_x, btn_start_y + (_BTN_SIZE + btn_gap) * 3, _BTN_SIZE, _BTN_SIZE)
            view_color = QColor("#8E24AA") if self._inline_mode else QColor("#37474F")
            view_text = "□" if self._inline_mode else "▣"
            _draw_btn(view_mode_btn_rect, view_color, view_text, 10)

            painter.setOpacity(1.0)

        # リサイズハンドル（四隅）- 角丸ドット（不透明度 + 動的サイズ適用）
        # 各コーナーからフレーム内側方向にオフセットして描画
        corner_positions = [
            (m, m),                     # TL: 左上
            (m + frame_w, m),           # TR: 右上
            (m, m + frame_h),           # BL: 左下
            (m + frame_w, m + frame_h), # BR: 右下
        ]
        # (dx, dy): コーナー基点からの描画オフセット方向
        # TL→右下方向, TR→左下方向, BL→右上方向, BR→左上方向
        corner_offsets = [
            (0, 0),       # TL: cx, cy を左上として右下に描画
            (-1, 0),      # TR: cx-hs, cy を左上として左下に描画
            (0, -1),      # BL: cx, cy-hs を左上として右上に描画
            (-1, -1),     # BR: cx-hs, cy-hs を左上として左上に描画
        ]
        for i, ((cx, cy), (ox, oy)) in enumerate(zip(corner_positions, corner_offsets)):
            r_opacity = self._auto_hide.resize_handle_opacity(i)
            if r_opacity < 0.01:
                continue
            hs = self._hover_expander.resize_handle_size(i)
            handle_color2 = QColor(self._border_color)
            handle_color2.setAlpha(int(180 * r_opacity))
            painter.setBrush(handle_color2)
            painter.setPen(Qt.NoPen)
            rx = cx + ox * hs
            ry = cy + oy * hs
            painter.drawRoundedRect(QRectF(rx, ry, hs, hs), 1, 1)

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
        btn_start_y = m + 6
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
        bw = max(self._border_width + 4, HANDLE_SIZE)

        # グラブハンドル判定（フレーム内側）- 最優先
        # ホバー拡大時の動的サイズを使用
        gw = self._hover_expander.grab_width
        gh = self._hover_expander.grab_height
        gh_x = m + (frame_w - gw) / 2.0
        gh_y = m + self._border_width + 2  # 描画位置と一致
        if gh_y <= y <= gh_y + gh + 4 and gh_x <= x <= gh_x + gw:
            return ResizeEdge.MOVE_HANDLE

        # 四隅ハンドル判定（フレーム内側）- ボタン判定より優先
        # ホバー拡大時の動的サイズを使用
        corner_positions = [
            (m, m),                     # TL
            (m + frame_w, m),           # TR
            (m, m + frame_h),           # BL
            (m + frame_w, m + frame_h), # BR
        ]
        corner_edges = [
            ResizeEdge.TOP_LEFT,
            ResizeEdge.TOP_RIGHT,
            ResizeEdge.BOTTOM_LEFT,
            ResizeEdge.BOTTOM_RIGHT,
        ]
        # 描画と同じオフセット方向でヒットテスト
        corner_offsets = [
            (0, 0),       # TL: 右下方向
            (-1, 0),      # TR: 左下方向
            (0, -1),      # BL: 右上方向
            (-1, -1),     # BR: 左上方向
        ]
        for i, ((cx, cy), edge, (ox, oy)) in enumerate(
            zip(corner_positions, corner_edges, corner_offsets)
        ):
            hs = self._hover_expander.resize_handle_size(i)
            rx = cx + ox * hs
            ry = cy + oy * hs
            if rx <= x < rx + hs and ry <= y < ry + hs:
                return edge

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
        pos = event.position().toPoint()

        # コントローラにマウス位置を通知
        m = _HANDLE_MARGIN
        frame_w = self.width() - _BTN_PANEL_W - m * 2
        frame_h = self.height() - m * 2
        frame_rect = QRect(m, m, frame_w, frame_h)
        self._auto_hide.update_mouse_position(pos)
        self._hover_expander.update_mouse_position(pos, frame_rect)

        if not (event.buttons() & Qt.LeftButton):
            edge = self._hit_test(pos)
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
            self._auto_hide.set_operating(operating)

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
        # ウィンドウ移動時に1秒間UI要素を表示維持
        self._auto_hide.on_show_or_reposition()

    def resizeEvent(self, event: "QResizeEvent") -> None:
        super().resizeEvent(event)
        self._update_inline_geometry()
        self._emit_region_changed()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        # オーバーレイ非表示時にインラインウィジェットも隠す
        if self._inline_widget:
            self._inline_widget.hide()

    def enterEvent(self, event) -> None:
        """マウスがウィンドウ内に入った時の処理"""
        super().enterEvent(event)
        self._auto_hide.on_mouse_enter()

    def leaveEvent(self, event) -> None:
        """マウスがウィンドウ外に出た時の処理"""
        super().leaveEvent(event)
        self._auto_hide.on_mouse_leave()

    def closeEvent(self, event) -> None:
        # オーバーレイ終了時にインラインウィジェットも閉じる
        if self._inline_widget:
            self._inline_widget.close()
        super().closeEvent(event)
