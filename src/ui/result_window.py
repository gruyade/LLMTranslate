"""翻訳結果表示ウィンドウ - バブルUI、履歴表示、リサイズ・移動対応"""

from __future__ import annotations

from datetime import datetime
from PySide6.QtCore import Qt, QRect, QPoint, QSize, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QCursor
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QHBoxLayout,
    QFrame,
)

from ..core.i18n import tr
from ..core.platform import apply_wda_exclude_from_capture

# リサイズハンドルの当たり判定サイズ（px）
HANDLE_SIZE = 8
MIN_WIN_SIZE = QSize(250, 200)
NO_TEXT_PATTERN = "[No text detected]"

class BubbleWidget(QFrame):
    """個別の翻訳結果を表示するバブル"""
    def __init__(self, text: str, font_size: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "BubbleWidget {"
            "  background-color: rgba(60, 60, 60, 180);"
            "  border: 1px solid rgba(255, 255, 255, 40);"
            "  border-radius: 10px;"
            "  margin: 2px;"
            "}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # タイムスタンプ
        time_str = datetime.now().strftime("%H:%M:%S")
        self._time_label = QLabel(time_str)
        self._time_label.setStyleSheet("color: rgba(255, 255, 255, 100); font-size: 9px;")
        layout.addWidget(self._time_label)

        # テキスト
        self._text_label = QLabel(text)
        self._text_label.setWordWrap(True)
        self._text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        font = QFont()
        font.setPointSize(font_size)
        self._text_label.setFont(font)
        self._text_label.setStyleSheet("color: white; background: transparent;")
        layout.addWidget(self._text_label)

        # 操作ボタン（コピー・削除）
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        copy_btn = QPushButton("📋")
        copy_btn.setFixedSize(24, 24)
        copy_btn.setToolTip(tr("result.copy"))
        copy_btn.setStyleSheet("QPushButton { background: transparent; border: none; font-size: 14px; color: #aaa; } QPushButton:hover { color: white; }")
        copy_btn.clicked.connect(self._copy_text)
        btn_layout.addWidget(copy_btn)

        del_btn = QPushButton("🗑")
        del_btn.setFixedSize(24, 24)
        del_btn.setToolTip(tr("result.delete"))
        del_btn.setStyleSheet("QPushButton { background: transparent; border: none; font-size: 14px; color: #aaa; } QPushButton:hover { color: #ff5555; }")
        del_btn.clicked.connect(self.deleteLater)
        btn_layout.addWidget(del_btn)
        
        layout.addLayout(btn_layout)

    def _copy_text(self):
        QApplication.clipboard().setText(self._text_label.text())

    def get_text(self) -> str:
        return self._text_label.text()

    def append_text(self, chunk: str):
        self._text_label.setText(self._text_label.text() + chunk)

class ResultWindow(QWidget):
    """
    翻訳結果を履歴（バブルUI）で表示するウィンドウ。
    ドラッグ移動、リサイズに対応。
    """
    def __init__(
        self,
        opacity: float = 0.9,
        font_size: int = 14,
        result_width: int = 350,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._opacity = opacity
        self._font_size = font_size
        self._result_width = result_width
        self._is_dragging = False
        self._drag_pos = QPoint()
        self._resize_edge = Qt.Edge(0)
        # ユーザーが意図的に上にスクロールしたかどうかのフラグ
        self._user_scrolled_up = False
        # バックグラウンドモード: データは蓄積するが表示しない
        self._background_mode = False

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowOpacity(opacity)
        self.setMouseTracking(True)

        self._build_ui()
        self.resize(result_width, 400)
        self.hide()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        apply_wda_exclude_from_capture(int(self.winId()))

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(HANDLE_SIZE, HANDLE_SIZE, HANDLE_SIZE, HANDLE_SIZE)

        # メインコンテナ
        self._container = QFrame()
        self._container.setObjectName("container")
        self._container.setStyleSheet(
            "#container {"
            "  background-color: rgba(25, 25, 25, 230);"
            "  border: 1px solid rgba(255, 255, 255, 60);"
            "  border-radius: 8px;"
            "}"
        )
        outer.addWidget(self._container)

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        # ヘッダー（移動用ハンドル兼用）
        header = QFrame()
        header.setFixedHeight(24)
        header.setStyleSheet("background: rgba(255, 255, 255, 10); border-top-left-radius: 7px; border-top-right-radius: 7px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(8, 0, 4, 0)
        
        title = QLabel(tr("result.history"))
        title.setStyleSheet("color: rgba(255, 255, 255, 150); font-size: 11px; font-weight: bold;")
        h_layout.addWidget(title)
        
        h_layout.addStretch()

        clear_btn = QPushButton("🗑")
        clear_btn.setFixedSize(20, 20)
        clear_btn.setToolTip(tr("result.clear_history"))
        clear_btn.setStyleSheet("QPushButton { color: #aaa; background: transparent; border: none; font-size: 14px; } QPushButton:hover { color: white; }")
        clear_btn.clicked.connect(self.clear_history)
        h_layout.addWidget(clear_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("QPushButton { color: #aaa; background: transparent; border: none; font-size: 12px; } QPushButton:hover { color: #ff5555; }")
        close_btn.clicked.connect(self.hide)
        h_layout.addWidget(close_btn)

        layout.addWidget(header)
        self._header = header

        # 履歴エリア
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        
        self._history_widget = QWidget()
        self._history_widget.setStyleSheet("background: transparent;")
        self._history_layout = QVBoxLayout(self._history_widget)
        self._history_layout.setContentsMargins(4, 4, 4, 4)
        self._history_layout.setSpacing(8)
        self._history_layout.addStretch()
        
        self._scroll.setWidget(self._history_widget)
        layout.addWidget(self._scroll)

        # スクロールバーの手動操作を検出してフラグを更新
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_value_changed)

        self._current_bubble: BubbleWidget | None = None
        self._current_buffer = ""

    # ------------------------------------------------------------------
    # 翻訳操作
    # ------------------------------------------------------------------

    def _on_scroll_value_changed(self, value: int) -> None:
        """スクロールバーの値変化を監視し、最下部かどうかを追跡する"""
        bar = self._scroll.verticalScrollBar()
        # 最下部付近（10px以内）なら自動スクロール許可、それ以外はユーザーが上にいる
        self._user_scrolled_up = value < bar.maximum() - 10

    def start_new_translation(self):
        """翻訳プロセス開始 - バブル生成は遅延"""
        self._current_buffer = ""
        self._current_bubble = None

    def _create_bubble(self, text: str):
        """バブルを生成してレイアウトに追加"""
        self._current_bubble = BubbleWidget(text, self._font_size)
        self._history_layout.insertWidget(
            self._history_layout.count() - 1, self._current_bubble
        )
        self.show_and_scroll_to_bottom()

    def append_chunk(self, chunk: str):
        self._current_buffer += chunk
        if self._current_bubble:
            self._current_bubble.append_text(chunk)
            self.show_and_scroll_to_bottom()
        else:
            # バブル未作成時はパターン判定
            # バッファが [No text detected] のプレフィックスに一致する間はバブル生成を保留
            stripped = self._current_buffer.strip()
            if stripped and not NO_TEXT_PATTERN.startswith(stripped):
                self._create_bubble(self._current_buffer)

    def finish_translation(self):
        text = self._current_buffer.strip()
        if self._current_bubble:
            # バブル作成済みの場合: テキスト全体が [No text detected] と完全一致するなら削除
            if not text or text == NO_TEXT_PATTERN:
                self._current_bubble.deleteLater()
        else:
            # バブル未作成かつ有効なテキストがあれば作成
            # テキスト全体が [No text detected] と完全一致する場合は作成しない
            if text and text != NO_TEXT_PATTERN:
                self._create_bubble(text)
        
        self._current_bubble = None
        self._current_buffer = ""

    def show_error(self, message: str):
        error_bubble = BubbleWidget(f"⚠ {message}", self._font_size)
        error_bubble.setStyleSheet(error_bubble.styleSheet().replace("rgba(60, 60, 60, 180)", "rgba(100, 30, 30, 180)"))
        self._history_layout.insertWidget(self._history_layout.count() - 1, error_bubble)
        if not self._background_mode:
            self.show_and_scroll_to_bottom()

    def clear_history(self):
        # Stretch以外のウィジェットを削除
        while self._history_layout.count() > 1:
            item = self._history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._current_bubble = None

    def set_background_mode(self, enabled: bool) -> None:
        """バックグラウンドモード切替。Trueの時はデータを蓄積するが表示しない。"""
        self._background_mode = enabled
        if enabled:
            self.hide()

    def show_if_has_history(self) -> None:
        """履歴バブルが1件以上あれば即座に表示して最下部にスクロールする。"""
        # _history_layout は末尾に Stretch を持つため count() > 1 で履歴あり
        if self._history_layout.count() > 1:
            self.show()
            from PySide6.QtCore import QTimer
            def _scroll():
                bar = self._scroll.verticalScrollBar()
                bar.setValue(bar.maximum())
            QTimer.singleShot(50, _scroll)

    def get_latest_text(self) -> str:
        """最新バブルのテキストを返す。履歴がなければ空文字。"""
        # _history_layout: [bubble0, bubble1, ..., Stretch]
        # Stretch は末尾なので count()-2 が最新バブルのインデックス
        count = self._history_layout.count()
        if count < 2:
            return ""
        item = self._history_layout.itemAt(count - 2)
        if item and isinstance(item.widget(), BubbleWidget):
            return item.widget().get_text()
        return ""

    def show_and_scroll_to_bottom(self):
        if not self._background_mode and not self.isVisible():
            self.show()
        # タイマーなしだとサイズ反映前にスクロールしてしまうため
        from PySide6.QtCore import QTimer
        def _maybe_scroll():
            # ユーザーが意図的に上にスクロールしている場合は位置を固定する
            if not self._user_scrolled_up:
                bar = self._scroll.verticalScrollBar()
                bar.setValue(bar.maximum())
        QTimer.singleShot(50, _maybe_scroll)

    # ------------------------------------------------------------------
    # 移動・リサイズ
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # ヘッダー内なら移動
            if self._header.geometry().contains(self._container.mapFrom(self, event.position().toPoint())):
                self._is_dragging = True
                self._drag_pos = event.globalPosition().toPoint() - self.pos()
            else:
                # 端の方ならリサイズ（簡易実装）
                pos = event.position().toPoint()
                bw = HANDLE_SIZE + 10
                if pos.x() > self.width() - bw and pos.y() > self.height() - bw:
                    self._resize_edge = Qt.BottomEdge | Qt.RightEdge # 便宜上

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        elif self._resize_edge:
            diff = event.globalPosition().toPoint() - (self.pos() + QPoint(self.width(), self.height()))
            new_size = self.size() + QSize(diff.x(), diff.y())
            if new_size.width() >= MIN_WIN_SIZE.width() and new_size.height() >= MIN_WIN_SIZE.height():
                self.resize(new_size)
        else:
            # カーソル変更
            pos = event.position().toPoint()
            bw = HANDLE_SIZE + 10
            if pos.x() > self.width() - bw and pos.y() > self.height() - bw:
                self.setCursor(Qt.SizeFDiagCursor)
            elif self._header.geometry().contains(self._container.mapFrom(self, pos)):
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        self._is_dragging = False
        self._resize_edge = Qt.Edge(0)

    # ------------------------------------------------------------------
    # 位置・外観
    # ------------------------------------------------------------------

    def reposition(self, overlay_rect: QRect) -> None:
        """初期配置のみオーバーレイに従う"""
        if self.isVisible(): return
        
        screen = QApplication.primaryScreen().availableGeometry()
        margin = 8
        x = overlay_rect.right() + margin
        if x + self.width() > screen.right():
            x = overlay_rect.left() - self.width() - margin
        
        y = overlay_rect.top()
        y = max(screen.top(), min(y, screen.bottom() - self.height()))
        self.move(x, y)

    def set_opacity(self, opacity: float): self.setWindowOpacity(opacity)
    def set_font_size(self, size: int): self._font_size = size
    def set_result_width(self, width: int): self.resize(width, self.height())
