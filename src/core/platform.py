"""プラットフォーム固有ユーティリティ - Win32 API呼び出し"""

from __future__ import annotations

import sys

from .logger import get_logger

logger = get_logger("platform")

# ------------------------------------------------------------------
# WDA 定数
# ------------------------------------------------------------------

_WDA_NONE = 0x00
"""通常表示（キャプチャに映る）"""

_WDA_EXCLUDEFROMCAPTURE = 0x11
"""キャプチャ除外（キャプチャに映らない）"""


# ------------------------------------------------------------------
# 低レベル WDA 関数
# ------------------------------------------------------------------


def _set_window_display_affinity(hwnd: int, affinity: int) -> None:
    """SetWindowDisplayAffinity を呼び出す低レベル関数

    Parameters
    ----------
    hwnd : int
        対象ウィンドウハンドル
    affinity : int
        設定する Display Affinity 値（_WDA_NONE or _WDA_EXCLUDEFROMCAPTURE）
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, affinity)
        if not result:
            logger.warning(
                "SetWindowDisplayAffinity 失敗: hwnd=%s, affinity=0x%02X",
                hwnd,
                affinity,
            )
    except Exception as e:
        logger.error("SetWindowDisplayAffinity 例外: hwnd=%s, error=%s", hwnd, e)


# ------------------------------------------------------------------
# CaptureExclusionManager
# ------------------------------------------------------------------


class CaptureExclusionManager:
    """キャプチャ前後で Overlay Windows の WDA 状態を一括切り替えする管理クラス"""

    def __init__(self) -> None:
        self._handles: set[int] = set()

    def register(self, hwnd: int) -> None:
        """ウィンドウハンドルを登録"""
        self._handles.add(hwnd)

    def unregister(self, hwnd: int) -> None:
        """ウィンドウハンドルを登録解除"""
        self._handles.discard(hwnd)

    def exclude_all(self) -> None:
        """全登録ウィンドウを WDA_EXCLUDEFROMCAPTURE に設定"""
        for hwnd in self._handles:
            _set_window_display_affinity(hwnd, _WDA_EXCLUDEFROMCAPTURE)

    def restore_all(self) -> None:
        """全登録ウィンドウを WDA_NONE に設定（通常表示に復帰）"""
        for hwnd in self._handles:
            _set_window_display_affinity(hwnd, _WDA_NONE)


# ------------------------------------------------------------------
# 後方互換関数
# ------------------------------------------------------------------


def apply_wda_exclude_from_capture(hwnd: int) -> None:
    """スクリーンキャプチャからウィンドウを除外する（Win32 WDA_EXCLUDEFROMCAPTURE）

    後方互換のため維持。内部実装は _set_window_display_affinity に委譲。
    """
    _set_window_display_affinity(hwnd, _WDA_EXCLUDEFROMCAPTURE)
