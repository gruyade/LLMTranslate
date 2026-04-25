"""TranslationClient のテスト"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
import respx

from src.core.config import ConfigManager
from src.core.translator import TranslationClient, TranslationError


@pytest.fixture
def config(tmp_path: Path, monkeypatch) -> ConfigManager:
    """テスト用 ConfigManager"""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr("src.core.config._get_config_path", lambda: config_file)
    monkeypatch.setattr("src.core.logger.LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr("src.core.logger.LOG_FILE", tmp_path / "logs" / "test.log")
    return ConfigManager()


@pytest.fixture
def client(config: ConfigManager) -> TranslationClient:
    return TranslationClient(config)


# ------------------------------------------------------------------
# ペイロード構築
# ------------------------------------------------------------------


def test_build_payload_structure(client: TranslationClient):
    """ペイロードが OpenAI Vision API 形式であること"""
    payload = client._build_payload("base64data")
    assert "model" in payload
    assert "messages" in payload
    assert "temperature" in payload
    assert "max_tokens" in payload
    assert payload["stream"] is True


def test_build_payload_with_system_prompt(client: TranslationClient):
    """システムプロンプトが messages に含まれること"""
    payload = client._build_payload("base64data")
    messages = payload["messages"]
    roles = [m["role"] for m in messages]
    assert "system" in roles


def test_build_payload_image_in_user_message(client: TranslationClient):
    """画像データが user メッセージに含まれること"""
    payload = client._build_payload("mybase64")
    user_msg = next(m for m in payload["messages"] if m["role"] == "user")
    content = user_msg["content"]
    assert isinstance(content, list)
    image_part = content[0]
    assert image_part["type"] == "image_url"
    assert "mybase64" in image_part["image_url"]["url"]


def test_build_payload_parameters(config: ConfigManager, client: TranslationClient):
    """推論パラメータが正しく設定されること"""
    payload = client._build_payload("data")
    inf = config.get_inference()
    assert payload["temperature"] == inf["temperature"]
    assert payload["max_tokens"] == inf["max_tokens"]
    assert payload["top_p"] == inf["top_p"]


def test_build_payload_stop_sequences(config: ConfigManager):
    """ストップシーケンスが正しくペイロードに含まれること"""
    preset = config.get_active_preset()
    preset["inference"]["stop_sequences"] = "END,STOP"
    config.save_preset("default", preset)

    client = TranslationClient(config)
    payload = client._build_payload("data")
    assert "stop" in payload
    assert "END" in payload["stop"]
    assert "STOP" in payload["stop"]


# ------------------------------------------------------------------
# ヘッダー・エンドポイント
# ------------------------------------------------------------------


def test_get_headers_without_api_key(client: TranslationClient):
    """APIキー未設定時は Authorization ヘッダーがないこと"""
    headers = client._get_headers()
    assert "Content-Type" in headers
    assert "Authorization" not in headers


def test_get_headers_with_api_key(config: ConfigManager):
    """APIキー設定時に Authorization ヘッダーが含まれること"""
    preset = config.get_active_preset()
    preset["server"]["api_key"] = "sk-test-key"
    config.save_preset("default", preset)

    client = TranslationClient(config)
    headers = client._get_headers()
    assert headers.get("Authorization") == "Bearer sk-test-key"


def test_get_endpoint(client: TranslationClient):
    """エンドポイント URL が正しく構築されること"""
    endpoint = client._get_endpoint()
    assert endpoint.endswith("/chat/completions")


# ------------------------------------------------------------------
# translate_stream（respx モック）
# ------------------------------------------------------------------


@respx.mock
async def test_translate_stream_success(client: TranslationClient, sample_image_b64: str):
    """正常なストリームレスポンスを処理できること"""
    endpoint = client._get_endpoint()
    sse_body = (
        'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":" World"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    respx.post(endpoint).mock(
        return_value=httpx.Response(200, text=sse_body)
    )

    chunks = []
    async for chunk in client.translate_stream(sample_image_b64):
        chunks.append(chunk)

    assert chunks == ["Hello", " World"]


@respx.mock
async def test_translate_stream_http_error(client: TranslationClient, sample_image_b64: str):
    """HTTP エラー時に TranslationError が発生すること"""
    endpoint = client._get_endpoint()
    respx.post(endpoint).mock(
        return_value=httpx.Response(401, text="Unauthorized")
    )

    with pytest.raises(TranslationError) as exc_info:
        async for _ in client.translate_stream(sample_image_b64):
            pass

    assert "401" in str(exc_info.value)


@respx.mock
async def test_translate_stream_connection_error(client: TranslationClient, sample_image_b64: str):
    """接続エラー時に TranslationError が発生すること"""
    endpoint = client._get_endpoint()
    respx.post(endpoint).mock(side_effect=httpx.ConnectError("Connection refused"))

    with pytest.raises(TranslationError) as exc_info:
        async for _ in client.translate_stream(sample_image_b64):
            pass

    assert "接続エラー" in str(exc_info.value)


@respx.mock
async def test_translate_stream_timeout(client: TranslationClient, sample_image_b64: str):
    """タイムアウト時に TranslationError が発生すること"""
    endpoint = client._get_endpoint()
    respx.post(endpoint).mock(side_effect=httpx.TimeoutException("timeout"))

    with pytest.raises(TranslationError) as exc_info:
        async for _ in client.translate_stream(sample_image_b64):
            pass

    assert "タイムアウト" in str(exc_info.value)


@respx.mock
async def test_translate_non_stream(client: TranslationClient, sample_image_b64: str):
    """`translate()` が完全なテキストを返すこと"""
    endpoint = client._get_endpoint()
    sse_body = (
        'data: {"choices":[{"delta":{"content":"翻訳"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"結果"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    respx.post(endpoint).mock(
        return_value=httpx.Response(200, text=sse_body)
    )

    result = await client.translate(sample_image_b64)
    assert result == "翻訳結果"


@respx.mock
async def test_translate_stream_skips_empty_delta(client: TranslationClient, sample_image_b64: str):
    """空の delta は yield されないこと"""
    endpoint = client._get_endpoint()
    sse_body = (
        'data: {"choices":[{"delta":{}}]}\n\n'
        'data: {"choices":[{"delta":{"content":""}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"text"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    respx.post(endpoint).mock(
        return_value=httpx.Response(200, text=sse_body)
    )

    chunks = []
    async for chunk in client.translate_stream(sample_image_b64):
        chunks.append(chunk)

    assert chunks == ["text"]
