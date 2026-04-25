"""capture モジュールのテスト"""
from __future__ import annotations

import base64
import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.core.capture import capture_region, has_text_content, images_differ


def _make_b64(color: tuple[int, int, int], size: tuple[int, int] = (10, 10)) -> str:
    """指定色の PNG 画像を Base64 文字列で返す"""
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


# ------------------------------------------------------------------
# capture_region
# ------------------------------------------------------------------


def test_capture_region_returns_base64():
    """キャプチャ結果が Base64 文字列であること"""
    mock_screenshot = MagicMock()
    mock_screenshot.size = (100, 100)
    # BGRA形式のダミーデータ（100x100x4バイト）
    mock_screenshot.bgra = bytes([0, 0, 0, 255] * 100 * 100)

    mock_sct = MagicMock()
    mock_sct.__enter__ = MagicMock(return_value=mock_sct)
    mock_sct.__exit__ = MagicMock(return_value=False)
    mock_sct.grab.return_value = mock_screenshot

    with patch("src.core.capture.mss.mss", return_value=mock_sct):
        result = capture_region(0, 0, 100, 100)

    # Base64 デコードできること
    decoded = base64.b64decode(result)
    assert len(decoded) > 0


def test_capture_region_invalid_size():
    """不正なサイズ指定で ValueError が発生すること"""
    with pytest.raises(ValueError):
        capture_region(0, 0, 0, 100)

    with pytest.raises(ValueError):
        capture_region(0, 0, 100, -1)


# ------------------------------------------------------------------
# images_differ
# ------------------------------------------------------------------


def test_images_differ_identical(sample_image_b64: str):
    """同一画像の場合に False を返すこと"""
    assert images_differ(sample_image_b64, sample_image_b64) is False


def test_images_differ_different(sample_image_b64: str, black_image_b64: str):
    """異なる画像の場合に True を返すこと"""
    assert images_differ(sample_image_b64, black_image_b64) is True


def test_images_differ_empty_first():
    """最初の画像が空の場合に True を返すこと"""
    b64 = _make_b64((255, 255, 255))
    assert images_differ("", b64) is True


def test_images_differ_empty_second():
    """2番目の画像が空の場合に True を返すこと"""
    b64 = _make_b64((255, 255, 255))
    assert images_differ(b64, "") is True


def test_images_differ_threshold_low():
    """閾値を 1.0 にすると同一画像でも False を返すこと"""
    white = _make_b64((255, 255, 255))
    # 閾値が非常に高いので差分なしと判定
    assert images_differ(white, white, threshold=1.0) is False


def test_images_differ_different_sizes():
    """サイズが異なる画像は True を返すこと"""
    small = _make_b64((255, 255, 255), (5, 5))
    large = _make_b64((255, 255, 255), (10, 10))
    assert images_differ(small, large) is True


# ------------------------------------------------------------------
# has_text_content
# ------------------------------------------------------------------


def test_has_text_content_with_text(sample_image_b64: str):
    """テキストを含む画像で True を返すこと（pytesseract モック）"""
    with patch("src.core.capture.pytesseract.image_to_string", return_value="Hello"):
        result = has_text_content(sample_image_b64)
    assert result is True


def test_has_text_content_without_text(sample_image_b64: str):
    """テキストを含まない画像で False を返すこと"""
    with patch("src.core.capture.pytesseract.image_to_string", return_value="   "):
        result = has_text_content(sample_image_b64)
    assert result is False


def test_has_text_content_empty_image():
    """空の画像文字列で False を返すこと"""
    assert has_text_content("") is False


def test_has_text_content_error_handling(sample_image_b64: str):
    """OCR エラー時に True を返すこと（LLM 側に判定を任せる）"""
    with patch(
        "src.core.capture.pytesseract.image_to_string",
        side_effect=Exception("tesseract not found"),
    ):
        result = has_text_content(sample_image_b64)
    assert result is True


def test_has_text_content_sets_tesseract_path(sample_image_b64: str):
    """tesseract_path が指定された場合に設定されること"""
    import src.core.capture as capture_module

    with patch("src.core.capture.pytesseract.image_to_string", return_value="text"):
        has_text_content(sample_image_b64, tesseract_path="/usr/bin/tesseract")

    import pytesseract
    assert pytesseract.pytesseract.tesseract_cmd == "/usr/bin/tesseract"
