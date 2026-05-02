"""AutoHideController のプロパティベーステスト — Hover Zone 判定・操作中フラグの検証"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtCore import QPoint

from src.ui.overlay_window import (
    AutoHideController,
    _BTN_PANEL_W,
    _HANDLE_MARGIN,
    _HOVER_DISTANCE,
)

# ---------------------------------------------------------------------------
# テスト用のオーバーレイスタブ
# ---------------------------------------------------------------------------

_MIN_OVERLAY_W = _BTN_PANEL_W + 2 * _HANDLE_MARGIN + 1  # 39
_MIN_OVERLAY_H = 2 * _HANDLE_MARGIN + 1                  # 11


def _make_overlay_stub(width: int, height: int) -> MagicMock:
    """AutoHideController に渡すオーバーレイスタブを生成"""
    stub = MagicMock()
    stub.width.return_value = width
    stub.height.return_value = height
    stub.isVisible.return_value = True
    stub.update.return_value = None
    return stub


def _make_controller(width: int, height: int) -> AutoHideController:
    """指定サイズのスタブ付き AutoHideController を生成"""
    stub = _make_overlay_stub(width, height)
    ctrl = AutoHideController(stub)
    ctrl._is_initial_show = False
    ctrl._is_operating = False
    return ctrl


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------

def _frame_params(w: int, h: int) -> tuple[int, int, int]:
    """(frame_w, frame_h, m) を返す"""
    m = _HANDLE_MARGIN
    frame_w = w - _BTN_PANEL_W - m * 2
    frame_h = h - m * 2
    return frame_w, frame_h, m


def _is_in_hover_zone(mx: int, my: int, w: int, h: int) -> bool:
    """実装と同じロジックでホバーゾーン判定を再現"""
    frame_w, frame_h, m = _frame_params(w, h)
    band = _HOVER_DISTANCE

    in_expanded = (
        m - band <= mx <= m + frame_w + _BTN_PANEL_W + band
        and m - band <= my <= m + frame_h + band
    )
    in_inner = (
        m + band <= mx <= m + frame_w - band
        and m + band <= my <= m + frame_h - band
    )
    in_border_band = in_expanded and not in_inner
    in_btn_panel = (
        m + frame_w - 10 <= mx <= m + frame_w + _BTN_PANEL_W + 10
        and m - 10 <= my <= m + frame_h + 10
    )
    return in_border_band or in_btn_panel


overlay_size_st = st.tuples(
    st.integers(min_value=_MIN_OVERLAY_W, max_value=2000),
    st.integers(min_value=_MIN_OVERLAY_H, max_value=2000),
)


# =========================================================================
# Property 1: ホバーゾーン外ではフェードターゲットが 0
# =========================================================================


class TestMouseOutsideHidesAll:

    @given(size=overlay_size_st, data=st.data())
    @settings(max_examples=200)
    def test_outside_all_zones_targets_zero(
        self, size: tuple[int, int], data: st.DataObject,
    ) -> None:
        """全 Hover Zone の外にあるマウス位置では target_opacity が 0。"""
        w, h = size
        frame_w, frame_h, m = _frame_params(w, h)
        band = _HOVER_DISTANCE

        mx = data.draw(st.one_of(
            st.integers(min_value=-500, max_value=m - band - 1),
            st.integers(min_value=m + frame_w + _BTN_PANEL_W + band + 1, max_value=w + 500),
        ), label="mx")
        my = data.draw(st.one_of(
            st.integers(min_value=-500, max_value=m - band - 1),
            st.integers(min_value=m + frame_h + band + 1, max_value=h + 500),
        ), label="my")

        if _is_in_hover_zone(mx, my, w, h):
            return

        ctrl = _make_controller(w, h)
        ctrl.update_mouse_position(QPoint(mx, my))

        assert ctrl._fade.target_opacity == 0.0, (
            f"target should be 0 at ({mx}, {my})"
        )


# =========================================================================
# Property 2: ホバーゾーン内ではフェードターゲットが 1
# =========================================================================


class TestHoverZoneShowsElement:

    @given(size=overlay_size_st, data=st.data())
    @settings(max_examples=200)
    def test_border_band_shows_all(
        self, size: tuple[int, int], data: st.DataObject,
    ) -> None:
        """枠線帯状ゾーン内のマウス位置で target_opacity が 1。"""
        w, h = size
        frame_w, frame_h, m = _frame_params(w, h)
        band = _HOVER_DISTANCE

        mx = data.draw(
            st.integers(min_value=m, max_value=m + frame_w), label="mx",
        )
        my = data.draw(
            st.integers(min_value=m - band, max_value=m + band - 1), label="my",
        )

        if not _is_in_hover_zone(mx, my, w, h):
            return

        ctrl = _make_controller(w, h)
        ctrl.update_mouse_position(QPoint(mx, my))

        assert ctrl._fade.target_opacity == 1.0, (
            f"target should be 1 at ({mx}, {my})"
        )

    @given(size=overlay_size_st, data=st.data())
    @settings(max_examples=200)
    def test_btn_panel_shows_all(
        self, size: tuple[int, int], data: st.DataObject,
    ) -> None:
        """ボタンパネル領域内のマウス位置で target_opacity が 1。"""
        w, h = size
        frame_w, frame_h, m = _frame_params(w, h)

        mx = data.draw(
            st.integers(min_value=m + frame_w, max_value=m + frame_w + _BTN_PANEL_W),
            label="mx",
        )
        my = data.draw(
            st.integers(min_value=m, max_value=m + frame_h), label="my",
        )

        ctrl = _make_controller(w, h)
        ctrl.update_mouse_position(QPoint(mx, my))

        assert ctrl._fade.target_opacity == 1.0, (
            f"target should be 1 at ({mx}, {my})"
        )


# =========================================================================
# Property 3: 操作中は全要素が強制表示
# =========================================================================


class TestOperatingForcesVisible:

    @given(
        size=overlay_size_st,
        mx=st.integers(min_value=-500, max_value=3000),
        my=st.integers(min_value=-500, max_value=3000),
    )
    @settings(max_examples=200)
    def test_operating_keeps_opacity_one(
        self, size: tuple[int, int], mx: int, my: int,
    ) -> None:
        """is_operating=True の場合、任意のマウス位置で不透明度が 1.0 を維持。"""
        w, h = size
        ctrl = _make_controller(w, h)
        ctrl.set_operating(True)
        ctrl.update_mouse_position(QPoint(mx, my))

        assert ctrl._fade.current_opacity == 1.0
        assert ctrl._fade.target_opacity == 1.0
