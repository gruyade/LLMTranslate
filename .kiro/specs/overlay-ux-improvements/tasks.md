# Implementation Plan: Overlay UX Improvements

## Overview

オーバーレイ UI の 3 領域を改善する実装計画。AutoHideController・HoverExpander を `overlay_window.py` 内に新規クラスとして追加し、既存の `paintEvent` を拡張する。ResultWindow のリサイズバグを修正し、全 10 言語ファイルに `result.cancelled` キーを追加する。

## Tasks

- [x] 1. Add `result.cancelled` translation key to all language files
  - [x] 1.1 Add `result.cancelled` key to all 10 translation files
    - Add `"result.cancelled"` entry to each `src/core/translations/*.py` file
    - Values: en=Cancelled, ja=キャンセル, fr=Annulé, de=Abgebrochen, th=ยกเลิกแล้ว, zh_CN=已取消, zh_TW=已取消, pt_BR=Cancelado, es_419=Cancelado, ko=취소됨
    - Place the key after `"result.delete"` to maintain `result.*` namespace grouping
    - _Requirements: 5.1, 5.3, 5.4_

  - [x] 1.2 Write unit tests for `result.cancelled` key presence
    - Add tests to `tests/test_i18n.py` verifying all 10 languages resolve `result.cancelled` to a non-empty string
    - Verify key follows `result.*` naming convention
    - _Requirements: 5.1, 5.3, 5.4_

- [x] 2. Fix ResultWindow resize bug
  - [x] 2.1 Record initial position and size on drag start in `ResultWindow.mousePressEvent`
    - Add `_resize_start_pos` and `_resize_start_size` fields to `ResultWindow`
    - In `mousePressEvent`, record `event.globalPosition().toPoint()` and `self.size()` when resize edge is detected
    - _Requirements: 4.1_

  - [x] 2.2 Fix `ResultWindow.mouseMoveEvent` to use delta-based calculation
    - Calculate `delta = current_global_pos - _resize_start_pos`
    - Compute `new_size = _resize_start_size + QSize(delta.x(), delta.y())`
    - Clamp to `MIN_WIN_SIZE` (250×200)
    - _Requirements: 4.2, 4.3, 4.5_

  - [x] 2.3 Reset drag state in `ResultWindow.mouseReleaseEvent`
    - Clear `_resize_start_pos` and `_resize_start_size` to `None`
    - _Requirements: 4.4_

  - [x] 2.4 Write property test for resize delta linearity (Property 6)
    - **Property 6: Resize delta is linear and clamped**
    - Generate random initial sizes (w≥250, h≥200), initial mouse positions, and current mouse positions
    - Assert `new_size == max(initial_size + delta, min_size)` for all inputs
    - Create `tests/test_result_window.py` for this test
    - **Validates: Requirements 4.2, 4.3, 4.5**

- [x] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement AutoHideController class
  - [x] 4.1 Create `AutoHideController` class in `src/ui/overlay_window.py`
    - Define timing constants: `FADE_DURATION_MS=150`, `FADE_OUT_DELAY_MS=300`, `INITIAL_SHOW_MS=1000`, `TICK_INTERVAL_MS=16`
    - Implement `_FadeState` dataclass with `current_opacity`, `target_opacity`, `velocity`
    - Create fade states for button panel, grab handle, and 4 resize handles
    - Implement `_fade_timer` (QTimer) for animation ticks at ~60fps
    - Implement `_fade_out_delay_timer` (QTimer, singleShot) for 300ms delay
    - Implement `_initial_show_timer` (QTimer, singleShot) for 1s initial visibility
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 4.2 Implement hover zone detection in `AutoHideController`
    - `update_mouse_position(local_pos)`: determine which hover zones the mouse is in
    - Button panel hover zone: right edge of frame + `_BTN_PANEL_W + 10px`
    - Grab handle hover zone: top edge of frame + `_GRAB_H + 15px`
    - Resize handle hover zones: 15px radius from each corner
    - Set target opacity to 1.0 for elements whose hover zone contains the mouse
    - Set target opacity to 0.0 for elements whose hover zone does not contain the mouse
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 3.1, 3.2_

  - [x] 4.3 Implement fade animation tick and control methods
    - `_on_fade_tick()`: interpolate each fade state toward target at velocity derived from `FADE_DURATION_MS`
    - Clamp opacity to [0.0, 1.0] range
    - Call `overlay.update()` when any opacity changes
    - Stop timer when all states reach their targets
    - `on_mouse_enter()` / `on_mouse_leave()`: start/cancel fade-out delay timer
    - `force_visible()`: set all opacities to 1.0 immediately
    - `set_operating(bool)`: keep all elements visible during drag/resize
    - `on_show_or_reposition()`: trigger 1s initial visibility
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 3.3_

  - [x] 4.4 Expose opacity properties on `AutoHideController`
    - `btn_opacity` → float property for button panel
    - `grab_handle_opacity` → float property for grab handle
    - `resize_handle_opacity(corner_index)` → float method for each corner
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 3.1, 3.2_

  - [x] 4.5 Write property test: mouse outside hides all elements (Property 1)
    - **Property 1: Mouse outside boundary hides all elements**
    - Generate random overlay geometries and mouse positions outside the boundary
    - Assert all target opacities are 0 after `update_mouse_position`
    - Create `tests/test_auto_hide.py`
    - **Validates: Requirements 1.1, 2.1, 3.1**

  - [x] 4.6 Write property test: hover zone shows corresponding element (Property 2)
    - **Property 2: Hover zone detection shows corresponding element**
    - Generate mouse positions within each hover zone
    - Assert the corresponding element's target opacity is 1
    - **Validates: Requirements 1.2, 2.2, 3.2**

  - [x] 4.7 Write property test: operating flag forces all visible (Property 3)
    - **Property 3: Operating flag forces all elements visible**
    - Generate any mouse position with `is_operating=True`
    - Assert all opacities remain 1.0
    - **Validates: Requirements 1.6**

- [x] 5. Implement HoverExpander class
  - [x] 5.1 Create `HoverExpander` class in `src/ui/overlay_window.py`
    - Define constants: `EXPAND_DURATION_MS=100`, `TICK_INTERVAL_MS=16`
    - Define size ranges: grab default (36×5) → expanded (60×10), resize default 5 → expanded 10
    - Implement `_ScaleState` dataclass with `current`, `target`, `velocity`
    - Create scale states for grab handle and 4 resize handles
    - Implement `_anim_timer` (QTimer) for animation ticks
    - _Requirements: 2.3, 2.4, 3.5, 3.6_

  - [x] 5.2 Implement distance-based hover detection and ease-out interpolation
    - `update_mouse_position(local_pos, frame_rect)`: calculate distance from mouse to each handle center
    - Set expansion target to 1.0 if distance ≤ 15px, else 0.0
    - Implement ease-out interpolation: `t = 1 - (1 - linear_t) ** 2`
    - Interpolate grab width/height and resize handle sizes using ease-out curve
    - _Requirements: 2.3, 2.4, 2.5, 3.5, 3.6_

  - [x] 5.3 Expose size properties on `HoverExpander`
    - `grab_width` / `grab_height` → float properties (interpolated values)
    - `resize_handle_size(corner_index)` → float method
    - `needs_repaint` → bool property (True while animating)
    - _Requirements: 2.3, 3.5_

  - [x] 5.4 Write property test: distance-based hover expansion (Property 4)
    - **Property 4: Distance-based hover expansion**
    - Generate random overlay geometries and mouse positions
    - Assert expansion target is 1.0 iff distance to handle center ≤ 15px
    - Create `tests/test_hover_expander.py`
    - **Validates: Requirements 2.3, 2.4, 3.5, 3.6**

  - [x] 5.5 Write property test: ease-out interpolation monotonic and bounded (Property 5)
    - **Property 5: Ease-out interpolation is monotonic and bounded**
    - Generate `t` values in [0.0, 1.0]
    - Assert output is in [0.0, 1.0] and `ease_out(t1) ≤ ease_out(t2)` for `t1 ≤ t2`
    - **Validates: Requirements 2.5**

- [x] 6. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Integrate AutoHideController and HoverExpander into OverlayWindow
  - [x] 7.1 Initialize controllers in `OverlayWindow.__init__`
    - Create `self._auto_hide = AutoHideController(self)`
    - Create `self._hover_expander = HoverExpander()`
    - Call `self._auto_hide.on_show_or_reposition()` in `showEvent`
    - _Requirements: 1.5, 6.4_

  - [x] 7.2 Add `enterEvent` and `leaveEvent` to `OverlayWindow`
    - `enterEvent`: call `self._auto_hide.on_mouse_enter()`
    - `leaveEvent`: call `self._auto_hide.on_mouse_leave()`
    - _Requirements: 1.1, 1.4_

  - [x] 7.3 Update `OverlayWindow.mouseMoveEvent` to feed controllers
    - Call `self._auto_hide.update_mouse_position(pos)` on every mouse move
    - Call `self._hover_expander.update_mouse_position(pos, frame_rect)` on every mouse move
    - _Requirements: 1.2, 2.2, 2.3, 3.2, 3.5_

  - [x] 7.4 Update `OverlayWindow._set_operating` to notify AutoHideController
    - Call `self._auto_hide.set_operating(operating)` when operating state changes
    - _Requirements: 1.6_

  - [x] 7.5 Update `OverlayWindow.moveEvent` to trigger initial show
    - Call `self._auto_hide.on_show_or_reposition()` on window move
    - _Requirements: 1.5_

- [x] 8. Modify `paintEvent` to use opacity and size from controllers
  - [x] 8.1 Update grab handle drawing with opacity and dynamic size
    - Get `grab_opacity` from `self._auto_hide.grab_handle_opacity`
    - Get `gw`, `gh` from `self._hover_expander.grab_width`, `grab_height`
    - Skip drawing if opacity < 0.01
    - Apply alpha: `handle_color.setAlpha(int(180 * grab_opacity))`
    - Use `QRectF` for sub-pixel positioning with dynamic size
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 8.2 Update button panel drawing with opacity
    - Get `btn_opacity` from `self._auto_hide.btn_opacity`
    - Skip drawing if opacity < 0.01
    - Use `painter.setOpacity(btn_opacity)` before button drawing, reset to 1.0 after
    - _Requirements: 1.1, 1.2, 6.3_

  - [x] 8.3 Update resize handle drawing with opacity and dynamic size
    - Get per-corner opacity from `self._auto_hide.resize_handle_opacity(i)`
    - Get per-corner size from `self._hover_expander.resize_handle_size(i)`
    - Skip drawing if opacity < 0.01
    - Apply alpha and dynamic size to each corner handle
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.6_

  - [x] 8.4 Adjust `_hit_test` for expanded handle sizes
    - Use `self._hover_expander.grab_width` / `grab_height` for grab handle hit area when expanded
    - Use `self._hover_expander.resize_handle_size(i)` for corner handle hit areas when expanded
    - Ensure existing edge-based resize detection is preserved
    - _Requirements: 6.1, 6.2_

- [x] 9. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- AutoHideController and HoverExpander are implemented as classes within `overlay_window.py` (not separate files)
- Follow project conventions: Japanese docstrings, `from __future__ import annotations`, type hints
