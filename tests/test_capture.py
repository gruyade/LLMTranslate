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
    """テキストを含む画像で True を返すこと（RapidOCR モック）"""
    mock_engine = MagicMock()
    # RapidOCR の返却形式: (result_list, _)
    # result_list[i] = [bbox, text, score]
    mock_engine.return_value = (
        [[ [[0, 0], [10, 0], [10, 10], [0, 10]], "Hello", 0.9 ]],
        None,
    )
    with patch("src.core.capture._get_rapid_engine", return_value=mock_engine):
        result = has_text_content(sample_image_b64)
    assert result is True


def test_has_text_content_without_text(sample_image_b64: str):
    """テキストを含まない画像で False を返すこと"""
    mock_engine = MagicMock()
    mock_engine.return_value = (None, None)
    with patch("src.core.capture._get_rapid_engine", return_value=mock_engine):
        result = has_text_content(sample_image_b64)
    assert result is False


def test_has_text_content_empty_image():
    """空の画像文字列で False を返すこと"""
    assert has_text_content("") is False


def test_has_text_content_error_handling(sample_image_b64: str):
    """OCR エラー時に True を返すこと（LLM 側に判定を任せる）"""
    mock_engine = MagicMock()
    # _get_rapid_engine() が返すエンジンの呼び出し時に例外を発生させる
    mock_engine.side_effect = Exception("OCR engine error")
    with patch("src.core.capture._get_rapid_engine", return_value=mock_engine):
        result = has_text_content(sample_image_b64)
    assert result is True


# ------------------------------------------------------------------
# ocr_analyze（直接テスト）
# ------------------------------------------------------------------

from src.core.capture import ocr_analyze, detect_text_height_pt


def test_ocr_analyze_empty_image():
    """空の画像文字列で (False, None) を返すこと"""
    has_text, font_size = ocr_analyze("")
    assert has_text is False
    assert font_size is None


def test_ocr_analyze_with_text(sample_image_b64: str):
    """テキスト検出時に (True, float) を返すこと"""
    mock_engine = MagicMock()
    # bbox高さ20pxのテキスト行を返す
    mock_engine.return_value = (
        [[ [[0, 0], [100, 0], [100, 20], [0, 20]], "Hello", 0.9 ]],
        {"det": 0.01, "rec": 0.02},
    )
    with patch("src.core.capture._get_rapid_engine", return_value=mock_engine):
        has_text, font_size = ocr_analyze(sample_image_b64)
    assert has_text is True
    assert font_size is not None
    # 20px * 72 / 96 = 15.0pt
    assert font_size == 15.0


def test_ocr_analyze_no_text(sample_image_b64: str):
    """テキスト未検出時に (False, None) を返すこと"""
    mock_engine = MagicMock()
    mock_engine.return_value = (None, None)
    with patch("src.core.capture._get_rapid_engine", return_value=mock_engine):
        has_text, font_size = ocr_analyze(sample_image_b64)
    assert has_text is False
    assert font_size is None


def test_ocr_analyze_error_returns_true(sample_image_b64: str):
    """OCRエラー時に (True, None) を返すこと"""
    mock_engine = MagicMock()
    mock_engine.side_effect = Exception("engine error")
    with patch("src.core.capture._get_rapid_engine", return_value=mock_engine):
        has_text, font_size = ocr_analyze(sample_image_b64)
    assert has_text is True
    assert font_size is None


def test_ocr_analyze_multiple_lines(sample_image_b64: str):
    """複数行テキストで中央値高さが計算されること"""
    mock_engine = MagicMock()
    # 高さ10px, 20px, 30px → 中央値20px → 20*72/96=15.0pt
    mock_engine.return_value = (
        [
            [ [[0, 0], [100, 0], [100, 10], [0, 10]], "Line1", 0.9 ],
            [ [[0, 20], [100, 20], [100, 40], [0, 40]], "Line2", 0.9 ],
            [ [[0, 50], [100, 50], [100, 80], [0, 80]], "Line3", 0.9 ],
        ],
        None,
    )
    with patch("src.core.capture._get_rapid_engine", return_value=mock_engine):
        has_text, font_size = ocr_analyze(sample_image_b64)
    assert has_text is True
    assert font_size == 15.0  # median(10,20,30)=20 → 20*72/96=15.0


def test_ocr_analyze_custom_dpi(sample_image_b64: str):
    """カスタムDPIでフォントサイズが正しく計算されること"""
    mock_engine = MagicMock()
    mock_engine.return_value = (
        [[ [[0, 0], [100, 0], [100, 20], [0, 20]], "Hello", 0.9 ]],
        None,
    )
    with patch("src.core.capture._get_rapid_engine", return_value=mock_engine):
        # 20px * 72 / 144 = 10.0pt
        has_text, font_size = ocr_analyze(sample_image_b64, screen_dpi=144.0)
    assert font_size == 10.0


# ------------------------------------------------------------------
# ocr_analyze — 画像縮小テスト
# ------------------------------------------------------------------


def test_ocr_analyze_downscale_large_image():
    """大きな画像が縮小されてOCRに渡され、フォントサイズがスケール補正されること"""
    # 1600x1200 の画像を作成（max_long_side=800 で 0.5 倍に縮小される）
    img = Image.new("RGB", (1600, 1200), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    large_b64 = base64.b64encode(buf.read()).decode("utf-8")

    mock_engine = MagicMock()
    # 縮小後の画像上で高さ10pxのテキスト → 元画像では20px
    mock_engine.return_value = (
        [[ [[0, 0], [50, 0], [50, 10], [0, 10]], "Hello", 0.9 ]],
        None,
    )
    with patch("src.core.capture._get_rapid_engine", return_value=mock_engine):
        has_text, font_size = ocr_analyze(large_b64, max_long_side=800)
    assert has_text is True
    # 10px / 0.5 = 20px → 20 * 72 / 96 = 15.0pt
    assert font_size == 15.0


def test_ocr_analyze_no_downscale_small_image(sample_image_b64: str):
    """小さな画像は縮小されないこと"""
    mock_engine = MagicMock()
    mock_engine.return_value = (
        [[ [[0, 0], [10, 0], [10, 5], [0, 5]], "Hi", 0.9 ]],
        None,
    )
    with patch("src.core.capture._get_rapid_engine", return_value=mock_engine):
        # 10x10画像、max_long_side=800 → 縮小なし、scale=1.0
        has_text, font_size = ocr_analyze(sample_image_b64, max_long_side=800)
    assert has_text is True
    # 5px * 72 / 96 = 3.8pt（縮小補正なし）
    assert font_size == 3.8


# ------------------------------------------------------------------
# detect_text_height_pt（後方互換エイリアス）
# ------------------------------------------------------------------


def test_detect_text_height_pt_delegates(sample_image_b64: str):
    """detect_text_height_ptがocr_analyzeに委譲すること"""
    mock_engine = MagicMock()
    mock_engine.return_value = (
        [[ [[0, 0], [100, 0], [100, 20], [0, 20]], "Hello", 0.9 ]],
        None,
    )
    with patch("src.core.capture._get_rapid_engine", return_value=mock_engine):
        result = detect_text_height_pt(sample_image_b64)
    assert result == 15.0
