"""スクリーンキャプチャエンジン - mssで指定領域をキャプチャしbase64エンコード"""

from __future__ import annotations

import base64
import io
from typing import TYPE_CHECKING

import mss
import mss.tools
from PIL import Image, ImageChops, ImageStat
import pytesseract

from .logger import get_logger

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

logger = get_logger("capture")


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


def has_text_content(image_b64: str, tesseract_path: str = "") -> bool:
    """OCRで画像にテキストが含まれるか判定する"""
    if not image_b64:
        return False

    try:
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path

        img = Image.open(io.BytesIO(base64.b64decode(image_b64)))
        # OCR実行（設定された言語に関わらず、文字があるかだけ見たいのでデフォルト）
        text = pytesseract.image_to_string(img)
        return bool(text.strip())
    except Exception as e:
        logger.warning("テキスト検出エラー: %s", e)
        # エラー時は念のためTrueを返し、LLM側に判定を任せる
        return True
