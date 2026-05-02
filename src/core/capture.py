"""スクリーンキャプチャエンジン - mssで指定領域をキャプチャしbase64エンコード"""

from __future__ import annotations

import base64
import io
import statistics
import threading
from typing import TYPE_CHECKING

import mss
import mss.tools
from PIL import Image, ImageChops, ImageStat
from rapidocr_onnxruntime import RapidOCR as _RapidOCR

from .logger import get_logger

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

logger = get_logger("capture")

_rapid_engine: _RapidOCR | None = None
_engine_lock = threading.Lock()


def _get_rapid_engine() -> _RapidOCR:
    global _rapid_engine
    if _rapid_engine is None:
        with _engine_lock:
            if _rapid_engine is None:
                _rapid_engine = _RapidOCR()
    return _rapid_engine


def warmup_ocr_engine() -> None:
    """RapidOCR エンジンをウォームアップする（初回推論の遅延を事前に解消）"""
    try:
        engine = _get_rapid_engine()
        # 1x1 の白画像でダミー推論
        dummy = Image.new("RGB", (64, 32), color=(255, 255, 255))
        engine(dummy)
        logger.info("RapidOCR ウォームアップ完了")
    except Exception as e:
        logger.warning("RapidOCR ウォームアップ失敗: %s", e)


def capture_region(
    x: int,
    y: int,
    width: int,
    height: int,
    hide_widget: "QWidget | None" = None,
) -> str:
    """
    指定領域をキャプチャしてbase64エンコードされたPNG文字列を返す。
    hide_widgetは現在使用していません（透過ウィンドウのため不要）。
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"キャプチャサイズが不正: {width}x{height}")

    try:
        monitor = {"top": y, "left": x, "width": width, "height": height}
        with mss.mss() as sct:
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        result = base64.b64encode(buf.read()).decode("utf-8")
        logger.debug("キャプチャ完了: region=(%d, %d, %d, %d)", x, y, width, height)
        return result
    except Exception as e:
        logger.error("キャプチャ失敗: %s", e)
        raise


def images_differ(img_b64_a: str, img_b64_b: str, threshold: float = 0.05) -> bool:
    """
    2枚の画像（base64）を比較し、変化があればTrueを返す。

    PIL.ImageChops + ImageStat による正規化 MSE ベースの比較。
    threshold: 0.0〜1.0（正規化済み RMS）
    """
    if not img_b64_a or not img_b64_b:
        return True

    try:
        img_a = Image.open(io.BytesIO(base64.b64decode(img_b64_a))).convert("L")
        img_b = Image.open(io.BytesIO(base64.b64decode(img_b64_b))).convert("L")

        # サイズが異なる場合は変化ありとみなす
        if img_a.size != img_b.size:
            return True

        diff = ImageChops.difference(img_a, img_b)
        stat = ImageStat.Stat(diff)
        # stat.rms[0] は 0〜255 の RMS 差分。255 で正規化して threshold と比較
        normalized = stat.rms[0] / 255.0
        differs = normalized > threshold
        logger.debug("画像差分: rms=%.4f, threshold=%.4f, differs=%s", normalized, threshold, differs)
        return differs
    except Exception:
        return True


def ocr_analyze(
    image_b64: str,
    screen_dpi: float = 96.0,
    max_long_side: int = 800,
) -> tuple[bool, float | None]:
    """
    RapidOCR を1回だけ呼び出し、テキスト有無と文字高さ(pt)を同時に返す。

    画像の長辺が *max_long_side* を超える場合は縮小してから推論し、
    フォントサイズは元画像スケールに補正して返す。

    Returns
    -------
    (has_text, font_size_pt)
        has_text     : テキストが検出されたか
        font_size_pt : 検出されたテキスト行の中央値高さ(pt)、検出不可なら None
    """
    if not image_b64:
        return False, None

    try:
        img = Image.open(io.BytesIO(base64.b64decode(image_b64)))

        # --- 画像縮小（OCR 高速化） ---
        long_side = max(img.size)
        scale = 1.0
        if max_long_side > 0 and long_side > max_long_side:
            scale = max_long_side / long_side
            new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
            img = img.resize(new_size, Image.LANCZOS)
            logger.debug("OCR用に画像を縮小: %dx%d → %dx%d (scale=%.2f)",
                         int(new_size[0] / scale), int(new_size[1] / scale),
                         new_size[0], new_size[1], scale)

        result, elapse = _get_rapid_engine()(img)
        logger.debug("OCR推論時間: %s", elapse)
        if not result:
            return False, None

        # result[i][0] = [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        heights = []
        for item in result:
            bbox = item[0]
            ys = [p[1] for p in bbox]
            heights.append(max(ys) - min(ys))

        font_size_pt: float | None = None
        if heights:
            # 縮小した場合は元画像スケールに補正
            median_h = statistics.median(heights) / scale
            font_size_pt = round(median_h * 72.0 / screen_dpi, 1)

        return True, font_size_pt
    except Exception as e:
        logger.warning("OCR解析エラー: %s", e)
        # エラー時はテキストありとみなしてLLM側に判定を任せる
        return True, None


# 後方互換エイリアス（既存コードが直接呼んでいる場合に備える）
def has_text_content(image_b64: str, tesseract_path: str = "") -> bool:
    has_text, _ = ocr_analyze(image_b64)
    return has_text


def detect_text_height_pt(image_b64: str, screen_dpi: float = 96.0) -> float | None:
    _, font_size_pt = ocr_analyze(image_b64, screen_dpi)
    return font_size_pt
