# LLMTranslate プロジェクト概要

## プロジェクトについて
LLMTranslate は Windows デスクトップ向けのスクリーン翻訳アプリ。
画面上にオーバーレイ枠を表示し、枠内のテキストを LLM（OpenAI 互換 API）の Vision 機能で翻訳する。

## 技術スタック
- 言語: Python 3.11+
- UI: PySide6 (Qt for Python)
- 画面キャプチャ: mss
- 画像処理: Pillow, RapidOCR (onnxruntime)
- HTTP通信: httpx (非同期)
- ビルド: PyInstaller (one-dir モード)
- テスト: pytest, pytest-asyncio, respx

## ディレクトリ構成
```
run.py                  # エントリーポイント（PyInstaller / 直接実行両対応）
config.json             # ユーザー設定ファイル（JSON、実行時に自動生成）
build.spec              # PyInstaller ビルド設定
src/
  main.py               # QApplication 初期化・i18n/logging セットアップ
  app.py                # LLMTranslateApp: コンポーネント統合・シグナル中継
  core/
    config.py            # ConfigManager: JSON設定管理・プリセット
    logger.py            # RotatingFileHandler ベースのロギング
    i18n.py              # I18nManager (シングルトン): 多言語対応
    translator.py        # TranslationClient: OpenAI Vision API クライアント
    capture.py           # スクリーンキャプチャ・RapidOCR・画像差分検出
    monitor.py           # MonitorService: 自動監視・翻訳トリガー
    async_worker.py      # AsyncTranslationWorker: 専用スレッドで asyncio ループ
    translations/        # 言語辞書 (en, ja, fr, de, th, zh_CN, zh_TW, pt_BR, es_419, ko)
  ui/
    overlay_window.py    # OverlayWindow: キャプチャ枠線・ボタンパネル・InlineResultWidget
    result_window.py     # ResultWindow: バブル形式の翻訳結果表示
    settings_dialog.py   # SettingsDialog: 5タブ設定ダイアログ
  resources/
    icon.ico, icon.png   # アプリアイコン
tests/
  conftest.py            # 共通フィクスチャ (tmp_config, sample_image_b64 等)
  test_capture.py        # キャプチャ・OCR・画像差分テスト
  test_config.py         # 設定管理・プリセット操作テスト
  test_i18n.py           # 多言語対応・翻訳キー取得テスト
  test_logger.py         # ロギング初期化・レベル変更テスト
  test_translator.py     # API クライアントテスト（respx モック）
```

## 起動フロー
```
run.py → src/main.py (ConfigManager, setup_logging, setup_i18n, QApplication)
  → LLMTranslateApp(config)
    ├─ _init_overlay()     → OverlayWindow 生成・シグナル接続
    ├─ _init_result_window() → ResultWindow 生成
    ├─ _init_monitor()     → MonitorService 生成・ワーカースレッド起動
    ├─ _init_tray()        → QSystemTrayIcon・メニュー構築
    └─ _init_shortcuts()   → グローバルショートカット設定
```

## モジュール依存関係
```
LLMTranslateApp (app.py)
  ├─ OverlayWindow (ui/overlay_window.py)
  │   └─ InlineResultWidget (同ファイル内)
  ├─ ResultWindow (ui/result_window.py)
  │   └─ BubbleWidget (同ファイル内)
  ├─ SettingsDialog (ui/settings_dialog.py)
  │   └─ ColorButton (同ファイル内)
  ├─ MonitorService (core/monitor.py)
  │   ├─ AsyncTranslationWorker (core/async_worker.py)
  │   │   └─ TranslationClient (core/translator.py)
  │   ├─ capture_region() (core/capture.py)
  │   ├─ images_differ() (core/capture.py)
  │   └─ ocr_analyze() (core/capture.py)
  ├─ ConfigManager (core/config.py)
  └─ QSystemTrayIcon
```

## 翻訳実行のデータフロー
```
ユーザー操作（▶ボタン or Ctrl+Shift+T）
  → OverlayWindow.translate_requested シグナル
  → LLMTranslateApp._trigger_translation()
  → MonitorService.translate_once()
  → capture_region() → image_b64
  → ocr_analyze() → テキスト有無・フォントサイズ
  → AsyncTranslationWorker.submit_translation(image_b64)
  → TranslationClient.translate_stream() (httpx 非同期 SSE)
  → chunk_received シグナル → ResultWindow / InlineResultWidget に逐次表示
  → translation_done シグナル → 表示完了
```

## 表示モード
- **bubble_window**: ResultWindow（フレーム横の半透明フローティングウィンドウ）
- **inline_overlay**: OverlayWindow 内の InlineResultWidget（フレーム内に直接オーバーレイ）
- 両モードとも常に ResultWindow にデータを蓄積（モード切替時に履歴を復元可能）

## テスト実行
```bash
pytest              # 全テスト
pytest tests/test_config.py  # 特定ファイル
pytest -v           # 詳細表示
```

## ビルド
```bash
pyinstaller build.spec
# 出力: dist/LLMTranslate/
```
