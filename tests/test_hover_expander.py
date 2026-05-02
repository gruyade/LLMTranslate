"""HoverExpander のプロパティベーステスト — 距離ベースホバー拡大・ease-out 補間の検証"""

from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtCore import QPoint, QRect

from src.ui.overlay_window import (
    HoverExpander,
    _ease_out,
    _HANDLE_MARGIN,
    _BTN_PANEL_W,
    _HOVER_DISTANCE,
)

# ---------------------------------------------------------------------------
# ヘルパー: フレーム矩形の計算
# ---------------------------------------------------------------------------

# 最小ウィンドウサイズ: frame 部分が正の値になるよう保証
_MIN_OVERLAY_W = _BTN_PANEL_W + 2 * _HANDLE_MARGIN + 1  # 39
_MIN_OVERLAY_H = 2 * _HANDLE_MARGIN + 1                  # 11


def _make_frame_rect(w: int, h: int) -> QRect:
    """OverlayWindow サイズからフレーム矩形を計算"""
    m = _HANDLE_MARGIN
    frame_w = w - _BTN_PANEL_W - m * 2
    frame_h = h - m * 2
    return QRect(m, m, frame_w, frame_h)


# ---------------------------------------------------------------------------
# Hypothesis ストラテジ
# ---------------------------------------------------------------------------

overlay_size_st = st.tuples(
    st.integers(min_value=_MIN_OVERLAY_W, max_value=2000),
    st.integers(min_value=_MIN_OVERLAY_H, max_value=2000),
)


# =========================================================================
# Property 4: Distance-based hover expansion
# =========================================================================


class TestDistanceBasedHoverExpansion:
    """Feature: overlay-ux-improvements, Property 4: Distance-based hover expansion

    **Validates: Requirements 2.3, 2.4, 3.5, 3.6**
    """

    @given(
        size=overlay_size_st,
        mx=st.integers(min_value=-500, max_value=3000),
        my=st.integers(min_value=-500, max_value=3000),
    )
    @settings(max_examples=200)
    def test_grab_expansion_iff_within_distance(
        self,
        size: tuple[int, int],
        mx: int,
        my: int,
    ) -> None:
        """グラブハンドル中心から ≤15px なら target=1.0、そうでなければ target=0.0。

        **Validates: Requirements 2.3, 2.4**
        """
        w, h = size
        frame_rect = _make_frame_rect(w, h)

        # グラブハンドル中心: フレーム上辺の中央
        grab_cx = frame_rect.x() + frame_rect.width() / 2.0
        grab_cy = float(frame_rect.y())
        dist = math.hypot(mx - grab_cx, my - grab_cy)

        expander = HoverExpander()
        expander.update_mouse_position(QPoint(mx, my), frame_rect)

        expected = 1.0 if dist <= _HOVER_DISTANCE else 0.0
        assert expander._grab_scale.target == expected, (
            f"grab target should be {expected} at ({mx}, {my}), "
            f"dist={dist:.2f} from center ({grab_cx:.1f}, {grab_cy:.1f})"
        )

    @given(
        size=overlay_size_st,
        corner_idx=st.integers(min_value=0, max_value=3),
        mx=st.integers(min_value=-500, max_value=3000),
        my=st.integers(min_value=-500, max_value=3000),
    )
    @settings(max_examples=200)
    def test_resize_expansion_iff_within_distance(
        self,
        size: tuple[int, int],
        corner_idx: int,
        mx: int,
        my: int,
    ) -> None:
        """リサイズハンドル中心から ≤15px なら target=1.0、そうでなければ target=0.0。

        **Validates: Requirements 3.5, 3.6**
        """
        w, h = size
        frame_rect = _make_frame_rect(w, h)

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
        cx, cy = corner_centers[corner_idx]
        dist = math.hypot(mx - cx, my - cy)

        expander = HoverExpander()
        expander.update_mouse_position(QPoint(mx, my), frame_rect)

        expected = 1.0 if dist <= _HOVER_DISTANCE else 0.0
        assert expander._resize_scales[corner_idx].target == expected, (
            f"resize[{corner_idx}] target should be {expected} at ({mx}, {my}), "
            f"dist={dist:.2f} from center ({cx:.1f}, {cy:.1f})"
        )


# =========================================================================
# Property 5: Ease-out interpolation is monotonic and bounded
# =========================================================================


class TestEaseOutMonotonicAndBounded:
    """Feature: overlay-ux-improvements, Property 5: Ease-out interpolation is monotonic and bounded

    **Validates: Requirements 2.5**
    """

    @given(t=st.floats(min_value=0.0, max_value=1.0))
    @settings(max_examples=200)
    def test_ease_out_bounded(self, t: float) -> None:
        """任意の t ∈ [0, 1] に対して _ease_out(t) ∈ [0, 1]。

        **Validates: Requirements 2.5**
        """
        result = _ease_out(t)
        assert 0.0 <= result <= 1.0, (
            f"_ease_out({t}) = {result}, expected in [0.0, 1.0]"
        )

    @given(
        t1=st.floats(min_value=0.0, max_value=1.0),
        t2=st.floats(min_value=0.0, max_value=1.0),
    )
    @settings(max_examples=200)
    def test_ease_out_monotonic(self, t1: float, t2: float) -> None:
        """任意の t1 ≤ t2 に対して _ease_out(t1) ≤ _ease_out(t2)（単調非減少）。

        **Validates: Requirements 2.5**
        """
        if t1 > t2:
            t1, t2 = t2, t1

        r1 = _ease_out(t1)
        r2 = _ease_out(t2)
        assert r1 <= r2, (
            f"_ease_out({t1}) = {r1} > _ease_out({t2}) = {r2}, "
            f"violates monotonicity"
        )
