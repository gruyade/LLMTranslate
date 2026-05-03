# コーディング規約・スタイルガイド

## Python スタイル

### ファイル先頭
- `from __future__ import annotations` を必ず記述
- モジュール docstring は日本語で記述（例: `"""設定管理モジュール - JSON形式でポータブルに設定を保存・読み込み"""`)

### 型ヒント
- 積極的に使用する: `dict[str, Any]`, `list[str]`, `str | None`, `tuple[int, int, int, int]`
- `from typing import Any` は必要に応じてインポート
- 戻り値の型も明示する

### インポート順序
1. `from __future__ import annotations`
2. 標準ライブラリ (`sys`, `json`, `threading`, `pathlib` 等)
3. サードパーティ (`PySide6`, `mss`, `PIL`, `httpx`, `numpy` 等)
4. プロジェクト内モジュール（相対インポート: `from .core.config import ConfigManager`)

### ロギング
- `from .core.logger import get_logger` でインポート
- `logger = get_logger("モジュール名")` でモジュール先頭に定義
- ログメッセージは日本語（例: `logger.info("設定ファイルを読み込みました: %s", path)`)
- f-string ではなく `%s` フォーマットを使用（遅延評価のため）

### コメント・docstring
- 日本語で記述
- セクション区切りは `# ---` コメントで表現:
  ```python
  # ------------------------------------------------------------------
  # 初期化
  # ------------------------------------------------------------------
  ```

### 命名規則
- クラス: PascalCase (`ConfigManager`, `OverlayWindow`)
- 関数・メソッド: snake_case (`get_active_preset`, `_on_translation_done`)
- プライベート: アンダースコアプレフィックス (`_data`, `_init_overlay`)
- 定数: UPPER_SNAKE_CASE (`DEFAULT_PRESET`, `MAX_BYTES`)
- シグナル: snake_case (`translation_started`, `region_changed`)

## PySide6 / Qt パターン

### Signal/Slot
- シグナル定義はクラス直下:
  ```python
  class MonitorService(QObject):
      translation_started = Signal()
      translation_chunk = Signal(str)
      translation_done = Signal(str)
  ```
- 接続は `signal.connect(slot)` 形式
- 切断は `signal.disconnect(slot)` 形式（重複接続防止にフラグ管理）

### ウィンドウフラグ
- オーバーレイ系: `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool`
- `WA_TranslucentBackground` で透過背景
- `WDA_EXCLUDEFROMCAPTURE` でスクリーンキャプチャから除外

### スレッド間通信
- `AsyncTranslationWorker` が専用スレッドで asyncio イベントループを実行
- メインスレッド（Qt）→ ワーカー: `loop.call_soon_threadsafe()`
- ワーカー → メインスレッド: Qt シグナル経由

## 設定管理パターン

### 構造
```python
{
  "active_preset": "default",     # アクティブプリセット名
  "ui_language": "auto",          # UI言語 ("auto" = OS検出)
  "log_level": "INFO",            # ログレベル
  "presets": {
    "default": {
      "server":    { "api_base_url", "api_key", "model", "timeout" },
      "inference": { "temperature", "max_tokens", "top_p", "top_k", ... },
      "prompt":    { "system_prompt", "target_language" },
      "display":   { "border_color", "border_width", "result_opacity", "font_size", "result_width", "result_display_mode", "inline_opacity", "inline_max_height_ratio" },
      "monitor":   { "interval", "change_threshold" }
    }
  },
  "overlay": { "x", "y", "width", "height", "visible" },  # グローバル
  "auto_monitor": false                                      # グローバル
}
```

### 設定変更の反映
- `ConfigManager` で値を変更 → `save()` で JSON 書き込み
- `SettingsDialog.settings_applied` シグナル → `LLMTranslateApp._on_settings_applied()` で各コンポーネントに反映
- デフォルト値は `DEFAULT_PRESET` / `DEFAULT_CONFIG` に定義し、`_deep_merge()` でマージ

## 多言語対応 (i18n)

### 翻訳キー命名規則
ドット区切りで階層化:
- `menu.*` — トレイメニュー項目
- `overlay.*` — オーバーレイボタンラベル
- `result.*` — 結果ウィンドウ
- `settings.*` — 設定ダイアログ（`settings.tab.*` でタブ名）
- `msg.*` — メッセージボックス
- `error.*` — エラーメッセージ

### 翻訳ファイル形式
`src/core/translations/<lang_code>.py`:
```python
TRANSLATIONS = {
    "menu.translate": "翻訳を実行",
    "menu.auto_monitor": "自動監視モード",
    ...
}
```

### 使い方
- `from .core.i18n import tr`
- `tr("menu.translate")` — 翻訳テキスト取得
- `tr("msg.save_success", name="preset1")` — パラメータ付き
- 英語 (`en.py`) がフォールバック

### 新しい言語を追加する手順
1. `src/core/translations/<lang_code>.py` を作成（`en.py` をコピーして翻訳）
2. `src/core/i18n.py` の `SUPPORTED_LANGUAGES` に追加
3. 必要に応じて `LOCALE_MAP` にマッピング追加
4. `build.spec` の `hiddenimports` に `src.core.translations.<lang_code>` を追加

## テストパターン

> テスト同期ルール・実装中のテスト修正方針・コミットルールはグローバルステアリング `development-rules.md` を参照。

### テスト対応表
| ソースファイル | テストファイル |
|---------------|---------------|
| `src/core/app_service.py` | `tests/test_app_service.py` |
| `src/core/config.py` | `tests/test_config.py` |
| `src/core/logger.py` | `tests/test_logger.py` |
| `src/core/translator.py` | `tests/test_translator.py` |
| `src/core/capture.py` | `tests/test_capture.py` |
| `src/core/i18n.py` | `tests/test_i18n.py` |

### フィクスチャ
- `tmp_config` — 一時ディレクトリの ConfigManager（`monkeypatch` で `_get_config_path` と `LOG_DIR`/`LOG_FILE` を差し替え）
- `sample_image_b64` — 10x10 白画像 (Base64 PNG)
- `black_image_b64` — 10x10 黒画像 (Base64 PNG)

### HTTP モック
- `respx` でhttpx の非同期リクエストをモック
- テスト内で `respx.mock` コンテキストマネージャを使用

### 非同期テスト
- `pytest-asyncio` で `asyncio_mode = "auto"`
- `async def test_*` で非同期テスト関数を定義

## 重要な定数
| 定数 | 値 | 場所 | 用途 |
|------|-----|------|------|
| `_BTN_PANEL_W` | 28 | overlay_window.py | ボタンパネル幅 |
| `_BTN_SIZE` | 20 | overlay_window.py | ボタンサイズ |
| `_HANDLE_MARGIN` | 5 | overlay_window.py | ウィンドウ端クリック余白 |
| `HANDLE_SIZE` | 5 | overlay_window.py | リサイズハンドル当たり判定 |
| `MIN_SIZE` | (80, 60) | overlay_window.py | 最小ウィンドウサイズ |
| `MAX_BYTES` | 5MB | logger.py | ログローテーション上限 |
| `BACKUP_COUNT` | 3 | logger.py | ログバックアップ世代数 |
