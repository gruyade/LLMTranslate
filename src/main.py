"""エントリーポイント - QApplicationの初期化とアプリ起動"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from .app import LLMTranslateApp
from .core.config import ConfigManager
from .core.i18n import setup_i18n
from .core.logger import setup_logging


def main() -> None:
    # High-DPI対応
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # 設定と多言語対応の初期化
    config = ConfigManager()
    setup_logging(config.get_log_level())
    ui_lang = config.get_ui_language()
    setup_i18n(None if ui_lang == "auto" else ui_lang)

    app = QApplication(sys.argv)
    app.setApplicationName("LLMTranslate")
    app.setApplicationVersion("1.0.0")
    # タスクトレイアプリはウィンドウを全て閉じても終了しない
    app.setQuitOnLastWindowClosed(False)

    # アプリケーション起動
    _app = LLMTranslateApp(config)  # noqa: F841 (参照を保持)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
