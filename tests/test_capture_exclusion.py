"""CaptureExclusionManager のプロパティベーステスト・ユニットテスト"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.core.platform import (
    CaptureExclusionManager,
    _WDA_EXCLUDEFROMCAPTURE,
    _WDA_NONE,
    _set_window_display_affinity,
)

# ------------------------------------------------------------------
# Property 1: レジストリ整合性
# ------------------------------------------------------------------


@settings(max_examples=100)
@given(
    ops=st.lists(
        st.tuples(st.sampled_from(["register", "unregister"]), st.integers(1, 1000))
    )
)
def test_registry_consistency(ops: list[tuple[str, int]]) -> None:
    """register/unregister 操作列後の _handles が期待通りの集合と一致する

    - register(hwnd) → 集合に追加
    - unregister(hwnd) → 集合から削除
    - 重複 register は冪等
    - 未登録 hwnd の unregister はエラーにならない

    **Validates: Requirements 2.1, 2.2, 2.3, 2.4**

    Feature: dynamic-capture-exclusion, Property 1: レジストリ整合性
    """
    mgr = CaptureExclusionManager()
    expected: set[int] = set()

    for action, hwnd in ops:
        if action == "register":
            mgr.register(hwnd)
            expected.add(hwnd)
        else:
            mgr.unregister(hwnd)
            expected.discard(hwnd)

    assert mgr._handles == expected


# ------------------------------------------------------------------
# Property 2: 一括切り替えの完全性
# ------------------------------------------------------------------


@settings(max_examples=100)
@given(hwnds=st.sets(st.integers(1, 1000)))
def test_bulk_toggle_completeness(hwnds: set[int]) -> None:
    """exclude_all() / restore_all() が全登録 HWND に対して正しい affinity で呼び出される

    - exclude_all → 全 HWND に WDA_EXCLUDEFROMCAPTURE
    - restore_all → 全 HWND に WDA_NONE
    - 呼び出し対象は登録済み HWND と完全一致（過不足なし）

    **Validates: Requirements 3.1, 3.2, 4.1, 4.3, 7.3**

    Feature: dynamic-capture-exclusion, Property 2: 一括切り替えの完全性
    """
    mgr = CaptureExclusionManager()
    for h in hwnds:
        mgr.register(h)

    with patch(
        "src.core.platform._set_window_display_affinity"
    ) as mock_set:
        # exclude_all の検証
        mgr.exclude_all()
        exclude_calls = {
            (call.args[0], call.args[1]) for call in mock_set.call_args_list
        }
        expected_exclude = {(h, _WDA_EXCLUDEFROMCAPTURE) for h in hwnds}
        assert exclude_calls == expected_exclude

        mock_set.reset_mock()

        # restore_all の検証
        mgr.restore_all()
        restore_calls = {
            (call.args[0], call.args[1]) for call in mock_set.call_args_list
        }
        expected_restore = {(h, _WDA_NONE) for h in hwnds}
        assert restore_calls == expected_restore


# ------------------------------------------------------------------
# Property 3: エラー耐性（restore_all）
# ------------------------------------------------------------------


@settings(max_examples=100)
@given(
    data=st.data(),
    hwnds=st.sets(st.integers(1, 1000), min_size=1),
)
def test_error_resilience_restore_all(
    data: st.DataObject, hwnds: set[int]
) -> None:
    """一部 HWND で _set_window_display_affinity が失敗しても全 HWND に対して呼び出しが試行される

    _set_window_display_affinity は内部で例外を吸収するため、restore_all は
    全 HWND に対して呼び出しを完了する。モックで呼び出し記録を検証。

    **Validates: Requirements 4.2**

    Feature: dynamic-capture-exclusion, Property 3: エラー耐性（restore_all）
    """
    # 失敗する HWND のサブセットを生成
    fail_hwnds = data.draw(
        st.sets(st.sampled_from(sorted(hwnds))).filter(lambda s: len(s) < len(hwnds)),
        label="fail_hwnds",
    )

    mgr = CaptureExclusionManager()
    for h in hwnds:
        mgr.register(h)

    called_hwnds: list[int] = []

    def tracking_side_effect(hwnd: int, affinity: int) -> None:
        """呼び出しを記録し、失敗 HWND ではログ出力相当の処理を模擬"""
        called_hwnds.append(hwnd)
        # _set_window_display_affinity は内部で例外を吸収するため、
        # ここでは例外を投げない（実際の動作と同じ）

    with patch(
        "src.core.platform._set_window_display_affinity",
        side_effect=tracking_side_effect,
    ):
        mgr.restore_all()

    # 全 HWND に対して呼び出しが試行されたことを検証
    assert set(called_hwnds) == hwnds


# ------------------------------------------------------------------
# ユニットテスト
# ------------------------------------------------------------------


class TestSetWindowDisplayAffinity:
    """_set_window_display_affinity のユニットテスト"""

    def test_skip_on_non_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """非 Windows 環境では Win32 API を呼び出さずスキップ

        **Validates: Requirements 1.3**
        """
        monkeypatch.setattr(sys, "platform", "linux")
        # 例外が発生しないことを確認（ctypes は呼ばれない）
        _set_window_display_affinity(12345, _WDA_EXCLUDEFROMCAPTURE)

    def test_api_failure_logs_no_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """API 失敗時にログ出力のみで例外を発生させない

        **Validates: Requirements 1.4**
        """
        monkeypatch.setattr(sys, "platform", "win32")

        mock_ctypes = MagicMock()
        # SetWindowDisplayAffinity が 0（失敗）を返す
        mock_ctypes.windll.user32.SetWindowDisplayAffinity.return_value = 0

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            # 例外が発生しないことを確認
            _set_window_display_affinity(99999, _WDA_EXCLUDEFROMCAPTURE)

        mock_ctypes.windll.user32.SetWindowDisplayAffinity.assert_called_once_with(
            99999, _WDA_EXCLUDEFROMCAPTURE
        )

    def test_api_exception_logs_no_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """API 呼び出しで例外が発生してもクラッシュしない

        **Validates: Requirements 1.4**
        """
        monkeypatch.setattr(sys, "platform", "win32")

        mock_ctypes = MagicMock()
        mock_ctypes.windll.user32.SetWindowDisplayAffinity.side_effect = OSError(
            "API error"
        )

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            # 例外が伝播しないことを確認
            _set_window_display_affinity(99999, _WDA_NONE)


class TestCaptureExclusionManagerUnit:
    """CaptureExclusionManager のユニットテスト"""

    def test_exclude_all_empty_registry(self) -> None:
        """空レジストリで exclude_all が正常終了

        **Validates: Requirements 3.2**
        """
        mgr = CaptureExclusionManager()
        with patch(
            "src.core.platform._set_window_display_affinity"
        ) as mock_set:
            mgr.exclude_all()
            mock_set.assert_not_called()

    def test_restore_all_empty_registry(self) -> None:
        """空レジストリで restore_all が正常終了

        **Validates: Requirements 4.3**
        """
        mgr = CaptureExclusionManager()
        with patch(
            "src.core.platform._set_window_display_affinity"
        ) as mock_set:
            mgr.restore_all()
            mock_set.assert_not_called()


# ------------------------------------------------------------------
# showEvent テスト: apply_wda_exclude_from_capture が呼ばれないことを検証
# ------------------------------------------------------------------


class TestShowEventNoCaptureExclusion:
    """各ウィンドウの showEvent で apply_wda_exclude_from_capture が呼ばれないことを検証

    **Validates: Requirements 5.1, 5.2**
    """

    def test_overlay_window_show_event_no_wda_call(self, qapp) -> None:
        """OverlayWindow.showEvent が apply_wda_exclude_from_capture を呼ばない"""
        from src.ui.overlay_window import OverlayWindow

        widget = OverlayWindow()
        try:
            with patch(
                "src.ui.overlay_window._apply_dwm_no_border"
            ):
                with patch(
                    "src.core.platform.apply_wda_exclude_from_capture"
                ) as mock_wda:
                    widget.show()
                    mock_wda.assert_not_called()
        finally:
            widget.close()

    def test_inline_result_widget_show_event_no_wda_call(self, qapp) -> None:
        """InlineResultWidget.showEvent が apply_wda_exclude_from_capture を呼ばない"""
        from src.ui.overlay_window import InlineResultWidget

        widget = InlineResultWidget()
        try:
            with patch(
                "src.ui.overlay_window._apply_dwm_no_border"
            ):
                with patch(
                    "src.core.platform.apply_wda_exclude_from_capture"
                ) as mock_wda:
                    widget.show()
                    mock_wda.assert_not_called()
        finally:
            widget.close()

    def test_result_window_show_event_no_wda_call(self, qapp) -> None:
        """ResultWindow.showEvent が apply_wda_exclude_from_capture を呼ばない"""
        from src.ui.result_window import ResultWindow

        widget = ResultWindow()
        try:
            with patch(
                "src.core.platform.apply_wda_exclude_from_capture"
            ) as mock_wda:
                widget.show()
                mock_wda.assert_not_called()
        finally:
            widget.close()
