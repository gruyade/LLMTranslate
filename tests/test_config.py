"""ConfigManager のテスト"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.config import (
    DEFAULT_CONFIG,
    DEFAULT_PRESET,
    ConfigManager,
    _deep_merge,
)


# ------------------------------------------------------------------
# _deep_merge
# ------------------------------------------------------------------


def test_deep_merge_flat():
    """フラットな dict のマージ"""
    result = _deep_merge({"a": 1, "b": 2}, {"b": 99, "c": 3})
    assert result == {"a": 1, "b": 99, "c": 3}


def test_deep_merge_nested():
    """ネストされた dict を再帰的にマージ"""
    base = {"server": {"url": "http://a", "key": "old"}}
    override = {"server": {"key": "new"}}
    result = _deep_merge(base, override)
    assert result["server"]["url"] == "http://a"
    assert result["server"]["key"] == "new"


def test_deep_merge_does_not_mutate_base():
    """base が変更されないこと"""
    base = {"a": {"x": 1}}
    _deep_merge(base, {"a": {"x": 99}})
    assert base["a"]["x"] == 1


# ------------------------------------------------------------------
# ConfigManager 基本動作
# ------------------------------------------------------------------


def test_default_values(tmp_config: ConfigManager):
    """初回起動時にデフォルト値が設定されること"""
    assert tmp_config.get_active_preset_name() == "default"
    assert tmp_config.get_ui_language() == "auto"
    assert tmp_config.get_log_level() == "INFO"
    assert tmp_config.get_auto_monitor() is False


def test_save_and_load(tmp_path: Path, monkeypatch):
    """save() → load() でデータが永続化されること"""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr("src.core.config._get_config_path", lambda: config_file)
    monkeypatch.setattr("src.core.logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("src.core.logger.LOG_FILE", tmp_path / "logs" / "test.log")

    config = ConfigManager()
    config.set_ui_language("ja")
    config.save()

    config2 = ConfigManager()
    assert config2.get_ui_language() == "ja"


def test_save_creates_directory(tmp_path: Path, monkeypatch):
    """設定ディレクトリが存在しない場合に自動作成されること"""
    nested = tmp_path / "deep" / "nested" / "config.json"
    monkeypatch.setattr("src.core.config._get_config_path", lambda: nested)
    monkeypatch.setattr("src.core.logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("src.core.logger.LOG_FILE", tmp_path / "logs" / "test.log")

    config = ConfigManager()
    config.save()
    assert nested.exists()


def test_corrupt_config_fallback(tmp_path: Path, monkeypatch):
    """破損した JSON の場合にデフォルトにフォールバックすること"""
    config_file = tmp_path / "config.json"
    config_file.write_text("{ invalid json }", encoding="utf-8")
    monkeypatch.setattr("src.core.config._get_config_path", lambda: config_file)
    monkeypatch.setattr("src.core.logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("src.core.logger.LOG_FILE", tmp_path / "logs" / "test.log")

    config = ConfigManager()
    assert config.get_active_preset_name() == "default"


# ------------------------------------------------------------------
# プリセット操作
# ------------------------------------------------------------------


def test_get_active_preset(tmp_config: ConfigManager):
    """アクティブプリセットが正しく取得されること"""
    preset = tmp_config.get_active_preset()
    assert "server" in preset
    assert "inference" in preset
    assert "prompt" in preset
    assert "display" in preset
    assert "monitor" in preset


def test_set_active_preset(tmp_config: ConfigManager):
    """プリセット切替が動作すること"""
    tmp_config.save_preset("custom", DEFAULT_PRESET.copy())
    tmp_config.set_active_preset("custom")
    assert tmp_config.get_active_preset_name() == "custom"


def test_save_preset(tmp_config: ConfigManager):
    """新規プリセットの保存が動作すること"""
    data = DEFAULT_PRESET.copy()
    tmp_config.save_preset("my_preset", data)
    assert "my_preset" in tmp_config.get_preset_names()


def test_delete_preset(tmp_config: ConfigManager):
    """プリセット削除が動作すること"""
    tmp_config.save_preset("to_delete", DEFAULT_PRESET.copy())
    tmp_config.delete_preset("to_delete")
    assert "to_delete" not in tmp_config.get_preset_names()


def test_delete_default_preset_is_noop(tmp_config: ConfigManager):
    """default プリセットは削除不可であること"""
    tmp_config.delete_preset("default")
    assert "default" in tmp_config.get_preset_names()


def test_rename_preset(tmp_config: ConfigManager):
    """プリセットのリネームが動作すること"""
    tmp_config.save_preset("old_name", DEFAULT_PRESET.copy())
    tmp_config.rename_preset("old_name", "new_name")
    assert "new_name" in tmp_config.get_preset_names()
    assert "old_name" not in tmp_config.get_preset_names()


def test_rename_default_preset_is_noop(tmp_config: ConfigManager):
    """default プリセットはリネーム不可であること"""
    tmp_config.rename_preset("default", "renamed")
    assert "default" in tmp_config.get_preset_names()
    assert "renamed" not in tmp_config.get_preset_names()


def test_delete_active_preset_falls_back_to_default(tmp_config: ConfigManager):
    """アクティブなプリセットを削除すると default に戻ること"""
    tmp_config.save_preset("active_one", DEFAULT_PRESET.copy())
    tmp_config.set_active_preset("active_one")
    tmp_config.delete_preset("active_one")
    assert tmp_config.get_active_preset_name() == "default"


# ------------------------------------------------------------------
# getter 系
# ------------------------------------------------------------------


def test_get_server_config(tmp_config: ConfigManager):
    """サーバー設定の getter が正しい値を返すこと"""
    server = tmp_config.get_server()
    assert "api_base_url" in server
    assert "timeout" in server


def test_set_overlay(tmp_config: ConfigManager):
    """オーバーレイ設定の保存が動作すること"""
    tmp_config.set_overlay(10, 20, 300, 200, True)
    overlay = tmp_config.get_overlay()
    assert overlay["x"] == 10
    assert overlay["y"] == 20
    assert overlay["width"] == 300
    assert overlay["height"] == 200
    assert overlay["visible"] is True


def test_get_log_level_default(tmp_config: ConfigManager):
    """デフォルトのログレベルが INFO であること"""
    assert tmp_config.get_log_level() == "INFO"


def test_set_log_level(tmp_config: ConfigManager):
    """ログレベルの変更が保存されること"""
    tmp_config.set_log_level("DEBUG")
    assert tmp_config.get_log_level() == "DEBUG"
