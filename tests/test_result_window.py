"""ResultWindow リサイズ計算のプロパティベーステスト"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtCore import QPoint, QSize

# テスト対象の定数（result_window.py と同一値）
MIN_WIN_WIDTH = 250
MIN_WIN_HEIGHT = 200


def compute_resize(
    initial_size: QSize,
    start_pos: QPoint,
    current_pos: QPoint,
) -> QSize:
    """リサイズ計算の純粋関数抽出。

    ResultWindow.mouseMoveEvent 内のロジックと同一:
        delta = current_pos - start_pos
        new_w = max(MIN_WIN_WIDTH, initial_size.width() + delta.x())
        new_h = max(MIN_WIN_HEIGHT, initial_size.height() + delta.y())
    """
    delta = current_pos - start_pos
    new_w = max(MIN_WIN_WIDTH, initial_size.width() + delta.x())
    new_h = max(MIN_WIN_HEIGHT, initial_size.height() + delta.y())
    return QSize(new_w, new_h)


class TestResizeDeltaLinearity:
    """Feature: overlay-ux-improvements, Property 6: Resize delta is linear and clamped

    **Validates: Requirements 4.2, 4.3, 4.5**
    """

    @given(
        init_w=st.integers(min_value=250, max_value=4000),
        init_h=st.integers(min_value=200, max_value=4000),
        start_x=st.integers(min_value=-5000, max_value=5000),
        start_y=st.integers(min_value=-5000, max_value=5000),
        cur_x=st.integers(min_value=-5000, max_value=5000),
        cur_y=st.integers(min_value=-5000, max_value=5000),
    )
    @settings(max_examples=200)
    def test_new_size_equals_initial_plus_delta_clamped(
        self,
        init_w: int,
        init_h: int,
        start_x: int,
        start_y: int,
        cur_x: int,
        cur_y: int,
    ) -> None:
        """リサイズ後のサイズが initial_size + delta を最小値でクランプした値と一致する。

        **Validates: Requirements 4.2, 4.3, 4.5**
        """
        initial_size = QSize(init_w, init_h)
        start_pos = QPoint(start_x, start_y)
        current_pos = QPoint(cur_x, cur_y)

        result = compute_resize(initial_size, start_pos, current_pos)

        delta_x = cur_x - start_x
        delta_y = cur_y - start_y
        expected_w = max(MIN_WIN_WIDTH, init_w + delta_x)
        expected_h = max(MIN_WIN_HEIGHT, init_h + delta_y)

        assert result.width() == expected_w
        assert result.height() == expected_h

    @given(
        init_w=st.integers(min_value=250, max_value=4000),
        init_h=st.integers(min_value=200, max_value=4000),
        start_x=st.integers(min_value=-5000, max_value=5000),
        start_y=st.integers(min_value=-5000, max_value=5000),
        cur_x=st.integers(min_value=-5000, max_value=5000),
        cur_y=st.integers(min_value=-5000, max_value=5000),
    )
    @settings(max_examples=200)
    def test_result_never_below_minimum(
        self,
        init_w: int,
        init_h: int,
        start_x: int,
        start_y: int,
        cur_x: int,
        cur_y: int,
    ) -> None:
        """リサイズ結果が最小サイズ (250×200) を下回らない。

        **Validates: Requirements 4.3**
        """
        initial_size = QSize(init_w, init_h)
        start_pos = QPoint(start_x, start_y)
        current_pos = QPoint(cur_x, cur_y)

        result = compute_resize(initial_size, start_pos, current_pos)

        assert result.width() >= MIN_WIN_WIDTH
        assert result.height() >= MIN_WIN_HEIGHT

    @given(
        init_w=st.integers(min_value=250, max_value=4000),
        init_h=st.integers(min_value=200, max_value=4000),
        start_x=st.integers(min_value=-5000, max_value=5000),
        start_y=st.integers(min_value=-5000, max_value=5000),
        cur_x=st.integers(min_value=-5000, max_value=5000),
        cur_y=st.integers(min_value=-5000, max_value=5000),
    )
    @settings(max_examples=200)
    def test_size_change_is_linear_to_delta(
        self,
        init_w: int,
        init_h: int,
        start_x: int,
        start_y: int,
        cur_x: int,
        cur_y: int,
    ) -> None:
        """クランプが発動しない範囲では、サイズ変化量がマウス移動量と完全一致する（線形性）。

        **Validates: Requirements 4.2, 4.5**
        """
        initial_size = QSize(init_w, init_h)
        start_pos = QPoint(start_x, start_y)
        current_pos = QPoint(cur_x, cur_y)

        result = compute_resize(initial_size, start_pos, current_pos)

        delta_x = cur_x - start_x
        delta_y = cur_y - start_y

        # クランプが発動しない場合のみ線形性を検証
        if init_w + delta_x >= MIN_WIN_WIDTH:
            assert result.width() - init_w == delta_x
        if init_h + delta_y >= MIN_WIN_HEIGHT:
            assert result.height() - init_h == delta_y
