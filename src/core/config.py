"""設定管理モジュール - JSON形式でポータブルに設定を保存・読み込み"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .logger import get_logger

logger = get_logger("config")


DEFAULT_SYSTEM_PROMPT = (
    "You are a professional translator. "
    "Translate the text shown in the image to {target_language}.\n"
    "Only output the translated text, no explanations or additional content."
)

DEFAULT_PRESET: dict[str, Any] = {
    "server": {
        "api_base_url": "http://localhost:1234/v1",
        "api_key": "",
        "model": "",
        "timeout": 60,
    },
    "inference": {
        "temperature": 0.3,
        "max_tokens": 2048,
        "top_p": 0.95,
        "top_k": 40,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "repeat_penalty": 1.1,
        "seed": -1,
        "stop_sequences": "",
    },
    "prompt": {
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "target_language": "Japanese",
    },
    "display": {
        "border_color": "#FF0000",
        "border_width": 2,
        "result_opacity": 0.9,
        "font_size": 14,
        "result_width": 350,
    },
    "monitor": {
        "interval": 2.0,
        "change_threshold": 0.05,
        "use_ocr_precheck": False,
        "tesseract_path": "",
    },
}

DEFAULT_CONFIG: dict[str, Any] = {
    "active_preset": "default",
    "ui_language": "auto",  # auto = OSロケール
    "log_level": "INFO",
    "presets": {
        "default": DEFAULT_PRESET,
    },
    "overlay": {
        "x": 100,
        "y": 100,
        "width": 400,
        "height": 300,
        "visible": True,
    },
    "auto_monitor": False,
}


def _get_config_path() -> Path:
    """exeと同ディレクトリ、または開発時はプロジェクトルートに config.json を配置"""
    if getattr(sys, "frozen", False):
        # PyInstallerでビルドされた場合
        base = Path(sys.executable).parent
    else:
        # 開発時: src の2階層上（プロジェクトルート）
        base = Path(__file__).parent.parent.parent
    return base / "config.json"


def _deep_merge(base: dict, override: dict) -> dict:
    """baseにoverrideを再帰的にマージ（overrideが優先）"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ConfigManager:
    """設定の読み込み・保存・プリセット管理を担当"""

    def __init__(self) -> None:
        self._path = _get_config_path()
        self._data: dict[str, Any] = {}
        self.load()

    # ------------------------------------------------------------------
    # ファイルI/O
    # ------------------------------------------------------------------

    def load(self) -> None:
        """設定ファイルを読み込む。存在しない場合はデフォルト値で初期化"""
        if self._path.exists():
            try:
                with self._path.open("r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self._data = _deep_merge(DEFAULT_CONFIG, loaded)
                logger.info("設定ファイルを読み込みました: %s", self._path)
            except (json.JSONDecodeError, OSError):
                logger.warning("設定ファイルの読み込みに失敗。デフォルト値を使用します: %s", self._path)
                self._data = _deep_merge({}, DEFAULT_CONFIG)
        else:
            logger.warning("設定ファイルが見つかりません。デフォルト値を使用します")
            self._data = _deep_merge({}, DEFAULT_CONFIG)
        self.save()

    def save(self) -> None:
        """設定ファイルに書き込む"""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            logger.debug("設定を保存しました: %s", self._path)
        except OSError as e:
            logger.error("設定の保存に失敗: %s", e)

    # ------------------------------------------------------------------
    # プリセット操作
    # ------------------------------------------------------------------

    def get_preset_names(self) -> list[str]:
        return list(self._data.get("presets", {}).keys())

    def get_active_preset_name(self) -> str:
        return self._data.get("active_preset", "default")

    def get_active_preset(self) -> dict[str, Any]:
        name = self.get_active_preset_name()
        presets = self._data.get("presets", {})
        preset = presets.get(name, {})
        return _deep_merge(DEFAULT_PRESET, preset)

    def set_active_preset(self, name: str) -> None:
        if name in self._data.get("presets", {}):
            self._data["active_preset"] = name
            self.save()

    def save_preset(self, name: str, preset_data: dict[str, Any]) -> None:
        """プリセットを保存（新規作成 or 上書き）"""
        if "presets" not in self._data:
            self._data["presets"] = {}
        self._data["presets"][name] = preset_data
        self._data["active_preset"] = name
        self.save()

    def delete_preset(self, name: str) -> None:
        """プリセットを削除（defaultは削除不可）"""
        if name == "default":
            return
        presets = self._data.get("presets", {})
        if name in presets:
            del presets[name]
            if self._data.get("active_preset") == name:
                self._data["active_preset"] = "default"
            self.save()

    def rename_preset(self, old_name: str, new_name: str) -> None:
        if old_name == "default" or old_name not in self._data.get("presets", {}):
            return
        presets = self._data["presets"]
        presets[new_name] = presets.pop(old_name)
        if self._data.get("active_preset") == old_name:
            self._data["active_preset"] = new_name
        self.save()

    # ------------------------------------------------------------------
    # アクティブプリセットの各セクション取得
    # ------------------------------------------------------------------

    def get_server(self) -> dict[str, Any]:
        return self.get_active_preset().get("server", DEFAULT_PRESET["server"])

    def get_inference(self) -> dict[str, Any]:
        return self.get_active_preset().get("inference", DEFAULT_PRESET["inference"])

    def get_prompt(self) -> dict[str, Any]:
        return self.get_active_preset().get("prompt", DEFAULT_PRESET["prompt"])

    def get_display(self) -> dict[str, Any]:
        return self.get_active_preset().get("display", DEFAULT_PRESET["display"])

    def get_monitor_config(self) -> dict[str, Any]:
        return self.get_active_preset().get("monitor", DEFAULT_PRESET["monitor"])

    # ------------------------------------------------------------------
    # オーバーレイ位置（プリセット外のグローバル設定）
    # ------------------------------------------------------------------

    def get_overlay(self) -> dict[str, Any]:
        return self._data.get("overlay", DEFAULT_CONFIG["overlay"])

    def set_overlay(self, x: int, y: int, width: int, height: int, visible: bool) -> None:
        self._data["overlay"] = {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "visible": visible,
        }
        self.save()

    # ------------------------------------------------------------------
    # 自動監視モード（グローバル設定）
    # ------------------------------------------------------------------

    def get_auto_monitor(self) -> bool:
        return bool(self._data.get("auto_monitor", False))

    def set_auto_monitor(self, enabled: bool) -> None:
        self._data["auto_monitor"] = enabled
        self.save()

    # ------------------------------------------------------------------
    # UI言語設定
    # ------------------------------------------------------------------

    def get_ui_language(self) -> str:
        return str(self._data.get("ui_language", "auto"))

    def set_ui_language(self, lang_code: str) -> None:
        self._data["ui_language"] = lang_code
        self.save()

    # ------------------------------------------------------------------
    # ログレベル設定（グローバル設定）
    # ------------------------------------------------------------------

    def get_log_level(self) -> str:
        return str(self._data.get("log_level", "INFO"))

    def set_log_level(self, level: str) -> None:
        self._data["log_level"] = level.upper()
        self.save()
