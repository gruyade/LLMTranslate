# Implementation Plan: Dynamic Capture Exclusion

## Overview

翻訳キャプチャ時のみ動的にキャプチャ除外を適用し、通常時は Snipping Tool 等で映る状態を維持する。`CaptureExclusionManager` を `platform.py` に追加し、既存の MonitorService コールバック機構で統合する。

## Tasks

- [x] 1. CaptureExclusionManager と低レベル WDA 関数の実装
  - [x] 1.1 `src/core/platform.py` に `_WDA_NONE`, `_WDA_EXCLUDEFROMCAPTURE` 定数と `_set_window_display_affinity` 関数を追加
    - `sys.platform != "win32"` の場合は何もせず return
    - API 失敗時は `logger.warning`、例外時は `logger.error` でログ出力し継続
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [x] 1.2 `src/core/platform.py` に `CaptureExclusionManager` クラスを追加
    - `_handles: set[int]` で HWND を管理
    - `register(hwnd)`, `unregister(hwnd)`, `exclude_all()`, `restore_all()` メソッドを実装
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 4.1, 4.2, 4.3_
  - [x] 1.3 既存の `apply_wda_exclude_from_capture` を `_set_window_display_affinity` に委譲するようリファクタ
    - 後方互換を維持
    - _Requirements: 1.1, 1.2_

- [x] 2. CaptureExclusionManager のテスト
  - [x] 2.1 `tests/test_capture_exclusion.py` にプロパティテスト: レジストリ整合性
    - **Property 1: レジストリ整合性**
    - register/unregister 操作列後の `_handles` が期待通りの集合と一致することを検証
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
  - [x] 2.2 `tests/test_capture_exclusion.py` にプロパティテスト: 一括切り替えの完全性
    - **Property 2: 一括切り替えの完全性**
    - `exclude_all()` / `restore_all()` が全登録 HWND に対して正しい affinity で呼び出されることを検証
    - **Validates: Requirements 3.1, 3.2, 4.1, 4.3, 7.3**
  - [x] 2.3 `tests/test_capture_exclusion.py` にプロパティテスト: エラー耐性
    - **Property 3: エラー耐性（restore_all）**
    - 一部 HWND で `_set_window_display_affinity` が失敗しても全 HWND に対して呼び出しが試行されることを検証
    - **Validates: Requirements 4.2**
  - [x] 2.4 `tests/test_capture_exclusion.py` にユニットテスト
    - `_set_window_display_affinity` の非 Windows 環境スキップ（Requirements 1.3）
    - `_set_window_display_affinity` の API 失敗時ログ出力・例外なし（Requirements 1.4）
    - `exclude_all` / `restore_all` の空レジストリ正常終了（Requirements 3.2, 4.3）

- [x] 3. Checkpoint - テスト確認
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. showEvent からの常時キャプチャ除外削除
  - [x] 4.1 `src/ui/overlay_window.py` の `OverlayWindow.showEvent` から `apply_wda_exclude_from_capture` 呼び出しを削除
    - _Requirements: 5.1, 5.2_
  - [x] 4.2 `src/ui/overlay_window.py` の `InlineResultWidget.showEvent` から `apply_wda_exclude_from_capture` 呼び出しを削除
    - _Requirements: 5.1, 5.2_
  - [x] 4.3 `src/ui/result_window.py` の `ResultWindow.showEvent` から `apply_wda_exclude_from_capture` 呼び出しを削除
    - _Requirements: 5.1, 5.2_
  - [x] 4.4 showEvent テストの追加（`tests/test_capture_exclusion.py` に追加）
    - 各ウィンドウの `showEvent` で `apply_wda_exclude_from_capture` が呼ばれないことを検証
    - _Requirements: 5.1, 5.2_

- [x] 5. app.py での CaptureExclusionManager 統合
  - [x] 5.1 `src/app.py` に `CaptureExclusionManager` のインポートと `_init_capture_exclusion` メソッドを追加
    - `CaptureExclusionManager` を生成し `self._exclusion_mgr` に保持
    - OverlayWindow と ResultWindow の HWND を登録
    - MonitorService の `set_pre_capture_callback` / `set_post_capture_callback` に `exclude_all` / `restore_all` を接続
    - _Requirements: 6.1, 6.2, 7.1, 7.2_
  - [x] 5.2 `src/app.py` の `_apply_display_mode` で InlineResultWidget 生成時に HWND を登録
    - `enable_inline_result()` 後に `self._exclusion_mgr.register(int(widget.winId()))` を呼び出し
    - _Requirements: 2.2, 7.3_
  - [x] 5.3 `src/app.py` の `__init__` 内で `_init_capture_exclusion()` を適切な位置に配置
    - `_init_overlay()`, `_init_result_window()` の後、`_service.start()` の前に呼び出し
    - _Requirements: 6.1, 6.2, 7.1, 7.2_

- [x] 6. 統合テスト
  - [x] 6.1 `tests/test_app_service.py` に統合テストを追加
    - MonitorService + CaptureExclusionManager: `pre_capture_cb` で `exclude_all` が呼ばれることを検証（Requirements 6.1, 7.1）
    - MonitorService + CaptureExclusionManager: `post_capture_cb` で `restore_all` が呼ばれることを検証（Requirements 6.2, 7.2）
    - `capture_region` 例外時も `post_capture_cb` が呼ばれることを検証（Requirements 6.3）
    - 手動翻訳 `translate_once` でも pre/post コールバックが呼ばれることを検証（Requirements 6.4）

- [x] 7. Final checkpoint - 全テスト確認
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 設計で推奨された実装順序に従い、platform.py → テスト → showEvent 変更 → app.py 統合の順で進行
- MonitorService の `_do_translate` は既に try/finally パターンで pre/post コールバックを呼び出しているため、MonitorService 自体の変更は不要
- `apply_wda_exclude_from_capture` は後方互換のため削除せず、内部実装を `_set_window_display_affinity` に委譲
- Property-based tests use Hypothesis (already in project dependencies)
