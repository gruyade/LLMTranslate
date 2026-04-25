"""共通フィクスチャ"""
from __future__ import annotations

import base64
import io
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def tmp_config(tmp_path: Path, monkeypatch):
    """一時ディレクトリを使う ConfigManager を提供"""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "src.core.config._get_config_path",
        lambda: config_file,
    )
    # logger.py の LOG_DIR も tmp_path に向ける（ファイルロック回避）
    monkeypatch.setattr(
        "src.core.logger.LOG_DIR",
        tmp_path / "logs",
    )
    monkeypatch.setattr(
        "src.core.logger.LOG_FILE",
        tmp_path / "logs" / "test.log",
    )
    from src.core.config import ConfigManager

    return ConfigManager()


@pytest.fixture
def sample_image_b64() -> str:
    """テスト用の小さな Base64 エンコード PNG 画像（10x10 白画像）"""
    img = Image.new("RGB", (10, 10), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


@pytest.fixture
def black_image_b64() -> str:
    """テスト用の黒画像（差分テスト用）"""
    img = Image.new("RGB", (10, 10), color=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")
