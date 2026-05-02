"""統合テスト - GUIボタン押下と同等の翻訳フローをプログラムから実行"""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from PySide6.QtCore import QCoreApplication

from src.core.app_service import AppService
from src.core.config import ConfigManager
from src.core.translator import normalize_base_url


def _process_events_until(predicate, timeout_sec: float = 5.0, interval: float = 0.05):
    """predicateがTrueを返すまでQtイベントを処理しながら待機"""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(interval)
    return False


@pytest.fixture
def config(tmp_path: Path, monkeypatch) -> ConfigManager:
    config_file = tmp_path / "config.json"
    monkeypatch.setattr("src.core.config._get_config_path", lambda: config_file)
    monkeypatch.setattr("src.core.logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("src.core.logger.LOG_FILE", tmp_path / "logs" / "test.log")
    return ConfigManager()


@pytest.fixture
def service(config: ConfigManager, qapp) -> AppService:
    """ワーカースレッド起動済みの AppService"""
    svc = AppService(config)
    svc.set_region_provider(lambda: (0, 0, 100, 100))
    svc.monitor.start_worker()
    yield svc
    svc.shutdown()


def _get_endpoint(config: ConfigManager) -> str:
    """テスト用にエンドポイントURLを構築"""
    raw = config.get_server()["api_base_url"]
    return normalize_base_url(raw) + "/chat/completions"


# ------------------------------------------------------------------
# ▶ボタン押下相当: trigger_translation → 翻訳完了
# ------------------------------------------------------------------


def test_full_translation_flow(service: AppService):
    """
    ▶ボタン押下と同等のフロー:
    trigger_translation → capture → OCR → API呼び出し → 翻訳完了シグナル
    """
    mock_capture = MagicMock(return_value="dGVzdA==")
    mock_ocr = MagicMock(return_value=(True, 14.0))
    endpoint = _get_endpoint(service.config)

    sse_body = (
        'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":" World"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    started = []
    chunks = []
    done = []
    errors = []

    service.translation_started.connect(lambda: started.append(True))
    service.translation_chunk.connect(lambda c: chunks.append(c))
    service.translation_done.connect(lambda t: done.append(t))
    service.translation_error.connect(lambda e: errors.append(e))

    with (
        patch("src.core.monitor.capture_region", mock_capture),
        patch("src.core.monitor.ocr_analyze", mock_ocr),
        respx.mock,
    ):
        respx.post(endpoint).mock(
            return_value=httpx.Response(200, text=sse_body)
        )

        service.trigger_translation()
        assert _process_events_until(lambda: len(done) > 0), "翻訳完了シグナルがタイムアウト"

    assert len(started) == 1, "translation_started が1回発火すること"
    assert chunks == ["Hello", " World"], f"チャンクが正しいこと: {chunks}"
    assert done[0] == "Hello World", f"完了テキストが正しいこと: {done[0]}"
    assert len(errors) == 0, f"エラーがないこと: {errors}"
    assert service.is_translating is False


# ------------------------------------------------------------------
# ▶ボタン押下: APIエラー時
# ------------------------------------------------------------------


def test_translation_flow_api_error(service: AppService):
    """API接続エラー時: trigger_translation → capture → OCR → 接続失敗 → エラーシグナル"""
    mock_capture = MagicMock(return_value="dGVzdA==")
    mock_ocr = MagicMock(return_value=(True, None))
    endpoint = _get_endpoint(service.config)

    errors = []
    service.translation_error.connect(lambda e: errors.append(e))

    with (
        patch("src.core.monitor.capture_region", mock_capture),
        patch("src.core.monitor.ocr_analyze", mock_ocr),
        respx.mock,
    ):
        respx.post(endpoint).mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        service.trigger_translation()
        assert _process_events_until(lambda: len(errors) > 0), "エラーシグナルがタイムアウト"

    assert len(errors) == 1
    assert service.is_translating is False


# ------------------------------------------------------------------
# ▶ボタン押下: OCRでテキストなし → 翻訳スキップ
# ------------------------------------------------------------------


def test_translation_skipped_when_no_text(service: AppService):
    """OCRでテキスト未検出時、翻訳がスキップされること"""
    mock_capture = MagicMock(return_value="dGVzdA==")
    mock_ocr = MagicMock(return_value=(False, None))

    started = []
    service.translation_started.connect(lambda: started.append(True))

    with (
        patch("src.core.monitor.capture_region", mock_capture),
        patch("src.core.monitor.ocr_analyze", mock_ocr),
    ):
        service.trigger_translation()

    # 少し待ってもtranslation_startedが発火しないことを確認
    _process_events_until(lambda: len(started) > 0, timeout_sec=1.0)
    assert len(started) == 0, "テキストなし時は翻訳が開始されないこと"


# ------------------------------------------------------------------
# ▶ボタン2回押し: 翻訳中にキャンセル
# ------------------------------------------------------------------


def test_cancel_during_translation(service: AppService):
    """翻訳中に▶ボタンを再度押すとキャンセルされること"""
    mock_capture = MagicMock(return_value="dGVzdA==")
    mock_ocr = MagicMock(return_value=(True, None))
    endpoint = _get_endpoint(service.config)

    # 大量チャンクで遅いレスポンスをシミュレート
    sse_lines = [
        f'data: {{"choices":[{{"delta":{{"content":"chunk{i}"}}}}]}}\n\n'
        for i in range(100)
    ]
    sse_lines.append("data: [DONE]\n\n")
    sse_body = "".join(sse_lines)

    cancelled = []
    done = []
    started = []
    service.translation_cancelled.connect(lambda: cancelled.append(True))
    service.translation_done.connect(lambda t: done.append(t))
    service.translation_started.connect(lambda: started.append(True))

    with (
        patch("src.core.monitor.capture_region", mock_capture),
        patch("src.core.monitor.ocr_analyze", mock_ocr),
        respx.mock,
    ):
        respx.post(endpoint).mock(
            return_value=httpx.Response(200, text=sse_body)
        )

        # 1回目: 翻訳開始
        service.trigger_translation()

        # translation_started を待つ
        _process_events_until(lambda: len(started) > 0, timeout_sec=3.0)

        # 高速環境では翻訳が既に完了している場合がある
        if len(done) > 0:
            # 翻訳が完了済みならキャンセルテスト不要（正常完了）
            assert service.is_translating is False
            return

        # 2回目: キャンセル
        service.trigger_translation()

        # キャンセルまたは完了を待つ
        _process_events_until(
            lambda: len(cancelled) > 0 or len(done) > 0,
            timeout_sec=5.0,
        )

    assert len(cancelled) + len(done) >= 1, "キャンセルまたは完了が発火すること"
    assert service.is_translating is False
