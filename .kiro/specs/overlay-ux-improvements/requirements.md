# Requirements Document

## Introduction

LLMTranslate のオーバーレイ UI を改善し、ユーザーの主要コンテンツ（ゲーム、外国語ソフトウェア等）を妨げない、モダンで使いやすいインターフェースを実現する。本ドキュメントでは、UI 要素の自動非表示、ResultWindow のリサイズバグ修正、欠落翻訳キーの追加の 3 つの改善を定義する。

## Glossary

- **Overlay_Window**: `OverlayWindow` クラス。透過フレームレスウィンドウとして画面上に表示されるキャプチャ枠線。ボタンパネル、グラブハンドル、リサイズハンドルを含む
- **Button_Panel**: オーバーレイフレーム右外側に縦並びで配置された 4 つの操作ボタン（設定、翻訳実行、モード切替、表示モード切替）の領域
- **Grab_Handle**: オーバーレイフレーム上辺外側に表示されるピル型のドラッグ移動用ハンドル（現在 36×5px）
- **Resize_Handle**: オーバーレイフレーム四隅に表示される角丸ドット型のリサイズ用ハンドル（現在 5×5px）
- **Result_Window**: `ResultWindow` クラス。翻訳結果をバブル UI で履歴表示するフローティングウィンドウ
- **Auto_Hide_Controller**: マウス位置を監視し、UI 要素の表示・非表示をフェードアニメーション付きで制御するロジック
- **Hover_Zone**: マウスがこの領域に入ると対応する UI 要素の表示をトリガーする不可視の検出領域
- **Fade_Animation**: UI 要素の不透明度を時間経過で滑らかに変化させるアニメーション効果
- **I18n_Manager**: `I18nManager` クラス。多言語翻訳キーの管理とテキスト取得を担当するシングルトン
- **Translation_File**: `src/core/translations/<lang_code>.py` に配置される言語辞書ファイル。`TRANSLATIONS` 辞書を定義する

## Requirements

### Requirement 1: Button Panel Auto-Hide

**User Story:** As a user, I want the button panel to automatically hide when my mouse is away from the overlay, so that the overlay does not obstruct the content underneath.

#### Acceptance Criteria

1. WHILE the mouse cursor is outside the Overlay_Window boundary, THE Auto_Hide_Controller SHALL hide the Button_Panel by setting its opacity to 0
2. WHEN the mouse cursor enters the Hover_Zone adjacent to the right edge of the overlay frame, THE Auto_Hide_Controller SHALL show the Button_Panel by fading its opacity from 0 to 1
3. THE Fade_Animation SHALL complete the opacity transition within 150 milliseconds
4. WHEN the mouse cursor leaves the Overlay_Window boundary, THE Auto_Hide_Controller SHALL begin a fade-out after a 300-millisecond delay
5. WHILE the Overlay_Window is first shown or repositioned, THE Auto_Hide_Controller SHALL keep the Button_Panel visible for 1 second before applying auto-hide behavior
6. WHILE a drag or resize operation is in progress, THE Auto_Hide_Controller SHALL keep all UI elements visible regardless of mouse position

### Requirement 2: Grab Handle Hover Expansion

**User Story:** As a user, I want the grab handle to enlarge when I hover near it, so that I can easily grab it for dragging while it stays small and unobtrusive when not needed.

#### Acceptance Criteria

1. WHILE the mouse cursor is outside the Overlay_Window boundary, THE Overlay_Window SHALL hide the Grab_Handle by setting its opacity to 0
2. WHEN the mouse cursor enters the Hover_Zone near the top edge of the overlay frame, THE Overlay_Window SHALL show the Grab_Handle by fading its opacity from 0 to 1
3. WHEN the mouse cursor hovers within 15 pixels of the Grab_Handle center, THE Overlay_Window SHALL expand the Grab_Handle from its default size (36×5px) to an enlarged size (60×10px) with a smooth 100-millisecond transition
4. WHEN the mouse cursor moves away from the Grab_Handle Hover_Zone, THE Overlay_Window SHALL shrink the Grab_Handle back to its default size (36×5px) with a smooth 100-millisecond transition
5. THE Grab_Handle expansion SHALL use eased interpolation to feel natural and responsive

### Requirement 3: Resize Handle Auto-Hide and Hover Expansion

**User Story:** As a user, I want the resize corner handles to automatically hide when my mouse is away and enlarge when I hover near them, so that they do not clutter the overlay when I am not resizing but are easy to grab when needed.

#### Acceptance Criteria

1. WHILE the mouse cursor is outside the Overlay_Window boundary, THE Auto_Hide_Controller SHALL hide all four Resize_Handle elements by setting their opacity to 0
2. WHEN the mouse cursor enters the Hover_Zone near any corner of the overlay frame, THE Auto_Hide_Controller SHALL show the corresponding Resize_Handle by fading its opacity from 0 to 1
3. THE Resize_Handle fade-in and fade-out SHALL use the same timing as the Button_Panel (150ms transition, 300ms fade-out delay)
4. WHILE any Resize_Handle is visible, THE Overlay_Window SHALL display the appropriate resize cursor when the mouse hovers over the handle
5. WHEN the mouse cursor hovers within 15 pixels of a Resize_Handle center, THE Overlay_Window SHALL expand that Resize_Handle from its default size (5×5px) to an enlarged size (10×10px) with a smooth 100-millisecond transition
6. WHEN the mouse cursor moves away from a Resize_Handle Hover_Zone, THE Overlay_Window SHALL shrink that Resize_Handle back to its default size (5×5px) with a smooth 100-millisecond transition

### Requirement 4: ResultWindow Resize Bug Fix

**User Story:** As a user, I want to resize the ResultWindow smoothly and predictably, so that the window does not accelerate or jump during resize operations.

#### Acceptance Criteria

1. WHEN the user initiates a resize drag on the Result_Window, THE Result_Window SHALL record the initial mouse position and initial window geometry at drag start
2. WHILE the user drags to resize, THE Result_Window SHALL calculate the new size as the initial size plus the delta between the current mouse position and the initial mouse position
3. THE Result_Window SHALL enforce a minimum size of 250×200 pixels during resize operations
4. WHEN the user releases the mouse button, THE Result_Window SHALL finalize the resize and reset all drag state
5. FOR ALL resize drag sequences, the Result_Window size change SHALL be linearly proportional to the mouse movement distance (no acceleration)

### Requirement 5: Missing Translation Key Addition

**User Story:** As a user, I want to see a properly translated cancellation message when a translation is cancelled, so that I do not see raw key strings in the UI.

#### Acceptance Criteria

1. THE I18n_Manager SHALL resolve the key `result.cancelled` to a localized string for all 10 supported languages (en, ja, fr, de, th, zh_CN, zh_TW, pt_BR, es_419, ko)
2. WHEN a translation is cancelled, THE Overlay_Window SHALL display the localized `result.cancelled` text instead of the raw key string
3. THE `result.cancelled` key SHALL follow the existing Translation_File format and naming convention (`result.*` namespace)
4. FOR ALL 10 Translation_File files, the `result.cancelled` entry SHALL be present and contain a non-empty string value

### Requirement 6: Preserve Existing Functionality

**User Story:** As a user, I want all existing overlay features to continue working after the UX improvements, so that I do not lose any functionality.

#### Acceptance Criteria

1. THE Overlay_Window SHALL continue to support drag-move via the Grab_Handle during and after auto-hide implementation
2. THE Overlay_Window SHALL continue to support 8-direction resize via frame edges and corner handles during and after auto-hide implementation
3. THE Button_Panel SHALL continue to emit the correct signals (settings_requested, translate_requested, mode_toggle_requested, view_mode_toggle_requested) when clicked in the visible state
4. THE Overlay_Window SHALL continue to exclude itself from screen capture via `WDA_EXCLUDEFROMCAPTURE`
5. WHILE auto-hide is active, THE Overlay_Window SHALL continue to respond to keyboard shortcuts (Ctrl+Shift+T, Ctrl+Shift+H, Ctrl+Shift+M)
