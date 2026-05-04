# Requirements Document

## Introduction

LLMTranslate のオーバーレイウィンドウ群（OverlayWindow, InlineResultWidget, ResultWindow）は、翻訳キャプチャへの映り込みを防ぐため `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` でキャプチャ除外されている。しかし現状は常時除外のため、Snipping Tool 等の通常スクリーンショット・録画にも映らない。

本機能では、翻訳キャプチャ時のみ動的にキャプチャ除外を適用し、通常時は Snipping Tool 等で映る状態を維持する。

## Glossary

- **Overlay_Windows**: OverlayWindow, InlineResultWidget, ResultWindow の総称。キャプチャ除外の対象となるトップレベルウィンドウ群
- **WDA_State**: `SetWindowDisplayAffinity` で設定されるウィンドウの Display Affinity 状態。`WDA_NONE`（通常表示）と `WDA_EXCLUDEFROMCAPTURE`（キャプチャ除外）の2値
- **Capture_Exclusion_Manager**: キャプチャ前後で Overlay_Windows の WDA_State を一括切り替えする管理コンポーネント
- **MonitorService**: 自動監視モードで定期キャプチャと翻訳を実行するサービス
- **Pre_Capture_Phase**: キャプチャ実行直前のフェーズ。Overlay_Windows をキャプチャ除外状態に切り替える
- **Post_Capture_Phase**: キャプチャ実行直後のフェーズ。Overlay_Windows を通常表示状態に復帰する

## Requirements

### Requirement 1: WDA 状態の動的切り替え API

**User Story:** As a developer, I want a reusable API to toggle WDA state on any window handle, so that capture exclusion can be applied and removed dynamically.

#### Acceptance Criteria

1. THE Capture_Exclusion_Manager SHALL provide a function to set a window handle to `WDA_EXCLUDEFROMCAPTURE` state
2. THE Capture_Exclusion_Manager SHALL provide a function to set a window handle to `WDA_NONE` state (通常表示に復帰)
3. WHEN the platform is not Windows, THE Capture_Exclusion_Manager SHALL skip the Win32 API call without raising an error
4. IF `SetWindowDisplayAffinity` fails, THEN THE Capture_Exclusion_Manager SHALL log the error and continue without crashing

### Requirement 2: ウィンドウ登録・管理

**User Story:** As a developer, I want to register multiple overlay windows with the manager, so that all windows can be toggled together before and after capture.

#### Acceptance Criteria

1. THE Capture_Exclusion_Manager SHALL maintain a registry of window handles (HWND) to manage
2. WHEN a new Overlay_Window is shown, THE Capture_Exclusion_Manager SHALL accept registration of that window handle
3. WHEN an Overlay_Window is destroyed or hidden permanently, THE Capture_Exclusion_Manager SHALL accept unregistration of that window handle
4. THE Capture_Exclusion_Manager SHALL support registering zero or more window handles simultaneously

### Requirement 3: キャプチャ前のキャプチャ除外適用

**User Story:** As a user, I want overlay windows to be excluded from capture only during translation capture, so that they don't appear in the translated image.

#### Acceptance Criteria

1. WHEN Pre_Capture_Phase begins, THE Capture_Exclusion_Manager SHALL set all registered Overlay_Windows to `WDA_EXCLUDEFROMCAPTURE` state
2. WHEN Pre_Capture_Phase begins with zero registered windows, THE Capture_Exclusion_Manager SHALL complete without error

### Requirement 4: キャプチャ後の通常表示復帰

**User Story:** As a user, I want overlay windows to return to normal display after translation capture, so that Snipping Tool and other screenshot tools can capture them.

#### Acceptance Criteria

1. WHEN Post_Capture_Phase begins, THE Capture_Exclusion_Manager SHALL set all registered Overlay_Windows to `WDA_NONE` state
2. IF an error occurs during Post_Capture_Phase for one window, THEN THE Capture_Exclusion_Manager SHALL continue processing remaining windows and log the error
3. WHEN Post_Capture_Phase begins with zero registered windows, THE Capture_Exclusion_Manager SHALL complete without error

### Requirement 5: 常時キャプチャ除外の廃止

**User Story:** As a user, I want overlay windows to be visible in Snipping Tool screenshots by default, so that I can share my screen setup with others.

#### Acceptance Criteria

1. WHEN an Overlay_Window is shown (showEvent), THE Overlay_Window SHALL remain in `WDA_NONE` state (通常表示)
2. THE Overlay_Windows SHALL remove the existing `apply_wda_exclude_from_capture` call from their `showEvent` handlers

### Requirement 6: MonitorService との統合

**User Story:** As a developer, I want the capture exclusion toggle to integrate with MonitorService's existing pre/post capture callbacks, so that the toggle happens at the correct timing.

#### Acceptance Criteria

1. THE MonitorService SHALL invoke Capture_Exclusion_Manager's exclude function as a pre-capture callback
2. THE MonitorService SHALL invoke Capture_Exclusion_Manager's restore function as a post-capture callback
3. WHEN capture raises an exception, THE MonitorService SHALL still invoke the post-capture callback to restore `WDA_NONE` state (既存の try/finally パターンを活用)
4. WHEN manual translation (translate_once) is triggered, THE MonitorService SHALL apply the same pre/post capture exclusion flow

### Requirement 7: キャプチャ除外の映り込み防止

**User Story:** As a user, I want the WDA state switch to happen reliably so that overlay windows don't appear in the captured translation image.

#### Acceptance Criteria

1. THE Capture_Exclusion_Manager SHALL apply `WDA_EXCLUDEFROMCAPTURE` to all registered windows before `capture_region()` is called
2. THE Capture_Exclusion_Manager SHALL restore `WDA_NONE` to all registered windows after `capture_region()` completes
3. WHEN multiple Overlay_Windows are registered, THE Capture_Exclusion_Manager SHALL process all windows in both exclude and restore phases
