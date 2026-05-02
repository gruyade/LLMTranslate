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
    _GRAB_H,
    _GRAB_W,
    _HANDLE_MARGIN,
    HANDLE_SIZE,
)

# ---------------------------------------------------------------------------
# テスト用のオーバーレイスタブ
# ---------------------------------------------------------------------------

# 最小ウィンドウサイズ: frame 部分が正の値になるよう保証
# frame_w = width - _BTN_PANEL_W - 2*m > 0  →  width > _BTN_PANEL_W + 2*m = 38
# frame_h = height - 2*m > 0                →  height > 2*m = 10
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
    # 初期表示フラグを解除して hover zone 判定を有効化
    ctrl._is_initial_show = False
    ctrl._is_operating = False
    return ctrl


# ---------------------------------------------------------------------------
# ヘルパー: フレーム座標計算
# ---------------------------------------------------------------------------

def _frame_params(w: int, h: int) -> tuple[int, int, int]:
    """(frame_w, frame_h, m) を返す"""
    m = _HANDLE_MARGIN
    frame_w = w - _BTN_PANEL_W - m * 2
    frame_h = h - m * 2
    return frame_w, frame_h, m


# ---------------------------------------------------------------------------
# Hypothesis ストラテジ
# ---------------------------------------------------------------------------

overlay_size_st = st.tuples(
    st.integers(min_value=_MIN_OVERLAY_W, max_value=2000),
    st.integers(min_value=_MIN_OVERLAY_H, max_value=2000),
)


# =========================================================================
# Property 1: Mouse outside boundary hides all elements
# =========================================================================


class TestMouseOutsideHidesAll:
    """Feature: overlay-ux-improvements, Property 1: Mouse outside boundary hides all elements

    **Validates: Requirements 1.1, 2.1, 3.1**
    """

    @given(
        size=overlay_size_st,
        data=st.data(),
    )
    @settings(max_examples=200)
    def test_outside_all_zones_targets_zero(
        self,
        size: tuple[int, int],
        data: st.DataObject,
    ) -> None:
        """全 Hover Zone の外にあるマウス位置では、全要素の target_opacity が 0。

        **Validates: Requirements 1.1, 2.1, 3.1**
        """
        w, h = size
        frame_w, frame_h, m = _frame_params(w, h)

        # 各 hover zone の境界を計算
        # ボタンパネル: x in [m+frame_w, m+frame_w+_BTN_PANEL_W+10], y in [m, m+frame_h]
        # グラブハンドル: x in [m, m+frame_w], y in [m-(_GRAB_H+15), m]
        # リサイズコーナー: 各コーナー中心から 15px 半径

        corner_centers = [
            (m, m),
            (m + frame_w, m),
            (m, m + frame_h),
            (m + frame_w, m + frame_h),
        ]

        # 全 zone の外にある座標を生成
        # 十分に離れた位置（ウィンドウ外の大きなマージン）を使用
        mx = data.draw(
            st.one_of(
                st.integers(min_value=-500, max_value=m - (_GRAB_H + 15) - 16),  # 左上方向に十分離れた位置
                st.integers(min_value=m + frame_w + _BTN_PANEL_W + 11, max_value=w + 500),  # 右方向に十分離れた位置
            ),
            label="mx",
        )
        my = data.draw(
            st.one_of(
                st.integers(min_value=-500, max_value=m - (_GRAB_H + 15) - 16),  # 上方向に十分離れた位置
                st.integers(min_value=m + frame_h + 16, max_value=h + 500),  # 下方向に十分離れた位置
            ),
            label="my",
        )

        # コーナーから 15px 以内でないことを確認（フィルタ）
        for cx, cy in corner_centers:
            if math.hypot(mx - cx, my - cy) <= 15.0:
                # このケースはスキップ（コーナー hover zone 内）
                return

        # ボタンパネル zone 内でないことを確認
        if (m + frame_w) <= mx <= (m + frame_w + _BTN_PANEL_W + 10) and m <= my <= (m + frame_h):
            return

        # グラブハンドル zone 内でないことを確認
        if m <= mx <= (m + frame_w) and (m - (_GRAB_H + 15)) <= my <= m:
            return

        ctrl = _make_controller(w, h)
        ctrl.update_mouse_position(QPoint(mx, my))

        assert ctrl._btn_fade.target_opacity == 0.0, (
            f"btn target should be 0 at ({mx}, {my})"
        )
        assert ctrl._grab_fade.target_opacity == 0.0, (
            f"grab target should be 0 at ({mx}, {my})"
        )
        for i in range(4):
            assert ctrl._resize_fades[i].target_opacity == 0.0, (
                f"resize[{i}] target should be 0 at ({mx}, {my})"
            )


# =========================================================================
# Property 2: Hover zone detection shows corresponding element
# =========================================================================


class TestHoverZoneShowsElement:
    """Feature: overlay-ux-improvements, Property 2: Hover zone detection shows corresponding element

    **Validates: Requirements 1.2, 2.2, 3.2**
    """

    @given(
        size=overlay_size_st,
        data=st.data(),
    )
    @settings(max_examples=200)
    def test_btn_zone_shows_btn_panel(
        self,
        size: tuple[int, int],
        data: st.DataObject,
    ) -> None:
        """ボタンパネル Hover Zone 内のマウス位置で btn target_opacity が 1。

        **Validates: Requirements 1.2**
        """
        w, h = size
        frame_w, frame_h, m = _frame_params(w, h)

        btn_zone_left = m + frame_w
        btn_zone_right = m + frame_w + _BTN_PANEL_W + 10
        btn_zone_top = m
        btn_zone_bottom = m + frame_h

        # ボタンパネル zone 内の座標を生成
        mx = data.draw(
            st.integers(min_value=btn_zone_left, max_value=btn_zone_right),
            label="mx",
        )
        my = data.draw(
            st.integers(min_value=btn_zone_top, max_value=btn_zone_bottom),
            label="my",
        )

        ctrl = _make_controller(w, h)
        ctrl.update_mouse_position(QPoint(mx, my))

        assert ctrl._btn_fade.target_opacity == 1.0, (
            f"btn target should be 1 at ({mx}, {my}) in zone "
            f"[{btn_zone_left}, {btn_zone_right}] x [{btn_zone_top}, {btn_zone_bottom}]"
        )

    @given(
        size=overlay_size_st,
        data=st.data(),
    )
    @settings(max_examples=200)
    def test_grab_zone_shows_grab_handle(
        self,
        size: tuple[int, int],
        data: st.DataObject,
    ) -> None:
        """グラブハンドル Hover Zone 内のマウス位置で grab target_opacity が 1。

        **Validates: Requirements 2.2**
        """
        w, h = size
        frame_w, frame_h, m = _frame_params(w, h)

        grab_zone_left = m
        grab_zone_right = m + frame_w
        grab_zone_top = m - (_GRAB_H + 15)
        grab_zone_bottom = m

        # グラブハンドル zone 内の座標を生成
        mx = data.draw(
            st.integers(min_value=grab_zone_left, max_value=grab_zone_right),
            label="mx",
        )
        my = data.draw(
            st.integers(min_value=grab_zone_top, max_value=grab_zone_bottom),
            label="my",
        )

        ctrl = _make_controller(w, h)
        ctrl.update_mouse_position(QPoint(mx, my))

        assert ctrl._grab_fade.target_opacity == 1.0, (
            f"grab target should be 1 at ({mx}, {my}) in zone "
            f"[{grab_zone_left}, {grab_zone_right}] x [{grab_zone_top}, {grab_zone_bottom}]"
        )

    @given(
        size=overlay_size_st,
        corner_idx=st.integers(min_value=0, max_value=3),
        data=st.data(),
    )
    @settings(max_examples=200)
    def test_corner_zone_shows_resize_handle(
        self,
        size: tuple[int, int],
        corner_idx: int,
        data: st.DataObject,
    ) -> None:
        """リサイズコーナー Hover Zone 内（15px 半径）のマウス位置で対応する resize target_opacity が 1。

        **Validates: Requirements 3.2**
        """
        w, h = size
        frame_w, frame_h, m = _frame_params(w, h)

        corner_centers = [
            (m, m),                     # TL
            (m + frame_w, m),           # TR
            (m, m + frame_h),           # BL
            (m + frame_w, m + frame_h), # BR
        ]
        cx, cy = corner_centers[corner_idx]

        # コーナー中心から 15px 以内の座標を生成
        # 角度と距離で生成し、整数座標に変換
        angle = data.draw(st.floats(min_value=0.0, max_value=2 * math.pi), label="angle")
        dist = data.draw(st.floats(min_value=0.0, max_value=14.9), label="dist")

        mx = int(cx + dist * math.cos(angle))
        my = int(cy + dist * math.sin(angle))

        # 整数丸めで 15px を超える可能性があるのでガード
        if math.hypot(mx - cx, my - cy) > 15.0:
            return

        ctrl = _make_controller(w, h)
        ctrl.update_mouse_position(QPoint(mx, my))

        assert ctrl._resize_fades[corner_idx].target_opacity == 1.0, (
            f"resize[{corner_idx}] target should be 1 at ({mx}, {my}), "
            f"dist={math.hypot(mx - cx, my - cy):.2f} from center ({cx}, {cy})"
        )


# =========================================================================
# Property 3: Operating flag forces all elements visible
# =========================================================================


class TestOperatingForcesVisible:
    """Feature: overlay-ux-improvements, Property 3: Operating flag forces all elements visible

    **Validates: Requirements 1.6**
    """

    @given(
        size=overlay_size_st,
        mx=st.integers(min_value=-500, max_value=3000),
        my=st.integers(min_value=-500, max_value=3000),
    )
    @settings(max_examples=200)
    def test_operating_keeps_all_opacities_one(
        self,
        size: tuple[int, int],
        mx: int,
        my: int,
    ) -> None:
        """is_operating=True の場合、任意のマウス位置で全要素の不透明度が 1.0 を維持。

        **Validates: Requirements 1.6**
        """
        w, h = size
        ctrl = _make_controller(w, h)

        # 操作中フラグを設定（force_visible で全 opacity を 1.0 に）
        ctrl.set_operating(True)

        # update_mouse_position は is_operating 中は早期リターンするため
        # target_opacity は変更されない
        ctrl.update_mouse_position(QPoint(mx, my))

        # 全要素の current_opacity が 1.0 であること
        assert ctrl._btn_fade.current_opacity == 1.0, (
            f"btn current_opacity should be 1.0 during operating, got {ctrl._btn_fade.current_opacity}"
        )
        assert ctrl._grab_fade.current_opacity == 1.0, (
            f"grab current_opacity should be 1.0 during operating, got {ctrl._grab_fade.current_opacity}"
        )
        for i in range(4):
            assert ctrl._resize_fades[i].current_opacity == 1.0, (
                f"resize[{i}] current_opacity should be 1.0 during operating, "
                f"got {ctrl._resize_fades[i].current_opacity}"
            )

        # target_opacity も 1.0 のまま（update_mouse_position が早期リターンするため）
        assert ctrl._btn_fade.target_opacity == 1.0
        assert ctrl._grab_fade.target_opacity == 1.0
        for i in range(4):
            assert ctrl._resize_fades[i].target_opacity == 1.0
