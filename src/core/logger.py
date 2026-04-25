"""ログ設定モジュール - アプリケーション全体のロギングを管理"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / ".llmtranslate" / "logs"
LOG_FILE = LOG_DIR / "llmtranslate.log"
ROOT_LOGGER_NAME = "LLMTranslate"

# ログフォーマット
CONSOLE_FORMAT = "%(levelname)-8s %(name)s | %(message)s"
FILE_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"

# ローテーション設定
MAX_BYTES = 5 * 1024 * 1024  # 5MB
BACKUP_COUNT = 3


def setup_logging(level: str = "INFO") -> None:
    """アプリケーションのログ設定を初期化する"""
    # ログディレクトリ作成
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger(ROOT_LOGGER_NAME)
    root_logger.setLevel(level.upper())

    # 既存のハンドラをクリア（再初期化対応）
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # コンソール出力
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT))
    root_logger.addHandler(console_handler)

    # ファイル出力
    try:
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter(FILE_FORMAT))
        root_logger.addHandler(file_handler)
    except Exception as e:
        # ファイルロガー初期化失敗はコンソールに出力して続行
        print(f"[logger] ファイルロガーの初期化に失敗: {e}")


def set_log_level(level: str) -> None:
    """実行時にログレベルを変更する"""
    logging.getLogger(ROOT_LOGGER_NAME).setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    """モジュール用の子ロガーを取得する"""
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
