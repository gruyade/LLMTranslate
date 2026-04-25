"""logger モジュールのテスト"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.core.logger import (
    ROOT_LOGGER_NAME,
    get_logger,
    set_log_level,
    setup_logging,
)


@pytest.fixture(autouse=True)
def reset_logger():
    """各テスト後にルートロガーをリセット"""
    yield
    root = logging.getLogger(ROOT_LOGGER_NAME)
    root.handlers.clear()
    root.setLevel(logging.NOTSET)


def test_setup_logging_creates_log_dir(tmp_path: Path, monkeypatch):
    """ログディレクトリが自動作成されること"""
    log_dir = tmp_path / "logs"
    log_file = log_dir / "test.log"
    monkeypatch.setattr("src.core.logger.LOG_DIR", log_dir)
    monkeypatch.setattr("src.core.logger.LOG_FILE", log_file)

    assert not log_dir.exists()
    setup_logging("INFO")
    assert log_dir.exists()


def test_setup_logging_default_level(tmp_path: Path, monkeypatch):
    """デフォルトレベルが INFO であること"""
    log_dir = tmp_path / "logs"
    monkeypatch.setattr("src.core.logger.LOG_DIR", log_dir)
    monkeypatch.setattr("src.core.logger.LOG_FILE", log_dir / "test.log")

    setup_logging()
    root = logging.getLogger(ROOT_LOGGER_NAME)
    assert root.level == logging.INFO


def test_setup_logging_debug_level(tmp_path: Path, monkeypatch):
    """DEBUG レベルが正しく設定されること"""
    log_dir = tmp_path / "logs"
    monkeypatch.setattr("src.core.logger.LOG_DIR", log_dir)
    monkeypatch.setattr("src.core.logger.LOG_FILE", log_dir / "test.log")

    setup_logging("DEBUG")
    root = logging.getLogger(ROOT_LOGGER_NAME)
    assert root.level == logging.DEBUG


def test_set_log_level(tmp_path: Path, monkeypatch):
    """実行時のレベル変更が反映されること"""
    log_dir = tmp_path / "logs"
    monkeypatch.setattr("src.core.logger.LOG_DIR", log_dir)
    monkeypatch.setattr("src.core.logger.LOG_FILE", log_dir / "test.log")

    setup_logging("INFO")
    set_log_level("WARNING")
    root = logging.getLogger(ROOT_LOGGER_NAME)
    assert root.level == logging.WARNING


def test_get_logger_returns_child():
    """子ロガーが正しい名前で返されること"""
    child = get_logger("test_module")
    assert child.name == f"{ROOT_LOGGER_NAME}.test_module"


def test_setup_logging_adds_handlers(tmp_path: Path, monkeypatch):
    """setup_logging 後にハンドラが追加されること"""
    log_dir = tmp_path / "logs"
    monkeypatch.setattr("src.core.logger.LOG_DIR", log_dir)
    monkeypatch.setattr("src.core.logger.LOG_FILE", log_dir / "test.log")

    setup_logging("INFO")
    root = logging.getLogger(ROOT_LOGGER_NAME)
    # StreamHandler + RotatingFileHandler の2つ
    assert len(root.handlers) == 2


def test_setup_logging_clears_existing_handlers(tmp_path: Path, monkeypatch):
    """再初期化時に既存ハンドラがクリアされること"""
    log_dir = tmp_path / "logs"
    monkeypatch.setattr("src.core.logger.LOG_DIR", log_dir)
    monkeypatch.setattr("src.core.logger.LOG_FILE", log_dir / "test.log")

    setup_logging("INFO")
    setup_logging("DEBUG")
    root = logging.getLogger(ROOT_LOGGER_NAME)
    # 再初期化後もハンドラが重複しないこと
    assert len(root.handlers) == 2
