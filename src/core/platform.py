"""プラットフォーム固有ユーティリティ - Win32 API呼び出し"""

from __future__ import annotations

import sys


def apply_wda_exclude_from_capture(hwnd: int) -> None:
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
