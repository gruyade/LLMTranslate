"""TranslationClient のテスト"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from src.core.config import ConfigManager, DEFAULT_PRESET
from src.core.translator import TranslationClient, TranslationError


def _make_snapshot(**overrides: Any) -> dict[str, Any]:
    """テスト用の設定スナップショットを生成"""
    import copy
    snapshot = copy.deepcopy(DEFAULT_PRESET)
    for section, values in overrides.items():
        if section in snapshot and isinstance(values, dict):
            snapshot[section].update(values)
        else:
            snapshot[section] = values
    return snapshot


@pytest.fixture
def snapshot() -> dict[str, Any]:
    """デフォルト設定スナップショット"""
    return _make_snapshot()


@pytest.fixture
def client(snapshot: dict[str, Any]) -> TranslationClient:
    return TranslationClient(snapshot)


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


def test_build_payload_parameters(snapshot: dict[str, Any], client: TranslationClient):
    """推論パラメータが正しく設定されること"""
    payload = client._build_payload("data")
    inf = snapshot["inference"]
    assert payload["temperature"] == inf["temperature"]
    assert payload["max_tokens"] == inf["max_tokens"]
    assert payload["top_p"] == inf["top_p"]


def test_build_payload_stop_sequences():
    """ストップシーケンスが正しくペイロードに含まれること"""
    snapshot = _make_snapshot(inference={"stop_sequences": "END,STOP"})
    client = TranslationClient(snapshot)
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


def test_get_headers_with_api_key():
    """APIキー設定時に Authorization ヘッダーが含まれること"""
    snapshot = _make_snapshot(server={"api_key": "sk-test-key"})
    client = TranslationClient(snapshot)
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


# ------------------------------------------------------------------
# normalize_base_url
# ------------------------------------------------------------------

from src.core.translator import normalize_base_url


def test_normalize_base_url_no_path():
    """パスなしURLに /v1 が補完されること"""
    assert normalize_base_url("http://localhost:1234") == "http://localhost:1234/v1"


def test_normalize_base_url_root_only():
    """ルートパスのみのURLに /v1 が補完されること"""
    assert normalize_base_url("http://localhost:1234/") == "http://localhost:1234/v1"


def test_normalize_base_url_with_v1():
    """既に /v1 がある場合はそのまま返ること"""
    assert normalize_base_url("http://localhost:1234/v1") == "http://localhost:1234/v1"


def test_normalize_base_url_with_v1_trailing_slash():
    """/v1/ の末尾スラッシュが除去されること"""
    assert normalize_base_url("http://localhost:1234/v1/") == "http://localhost:1234/v1"


def test_normalize_base_url_custom_path():
    """カスタムパスはそのまま保持されること"""
    assert normalize_base_url("http://example.com/api/v2") == "http://example.com/api/v2"


# ------------------------------------------------------------------
# ペイロード構築 — エッジケース
# ------------------------------------------------------------------


def test_build_payload_empty_system_prompt():
    """システムプロンプトが空の場合、systemメッセージが含まれないこと"""
    snapshot = _make_snapshot(prompt={"system_prompt": "", "target_language": "Japanese"})
    client = TranslationClient(snapshot)
    payload = client._build_payload("data")
    roles = [m["role"] for m in payload["messages"]]
    assert "system" not in roles


def test_build_payload_top_k_zero():
    """top_k=0 の場合、ペイロードに top_k が含まれないこと"""
    snapshot = _make_snapshot(inference={"top_k": 0})
    client = TranslationClient(snapshot)
    payload = client._build_payload("data")
    assert "top_k" not in payload


def test_build_payload_repeat_penalty_one():
    """repeat_penalty=1.0 の場合、ペイロードに含まれないこと"""
    snapshot = _make_snapshot(inference={"repeat_penalty": 1.0})
    client = TranslationClient(snapshot)
    payload = client._build_payload("data")
    assert "repeat_penalty" not in payload


def test_build_payload_seed_negative():
    """seed=-1 の場合、ペイロードに seed が含まれないこと"""
    snapshot = _make_snapshot(inference={"seed": -1})
    client = TranslationClient(snapshot)
    payload = client._build_payload("data")
    assert "seed" not in payload


def test_build_payload_seed_positive():
    """seed>=0 の場合、ペイロードに seed が含まれること"""
    snapshot = _make_snapshot(inference={"seed": 42})
    client = TranslationClient(snapshot)
    payload = client._build_payload("data")
    assert payload["seed"] == 42


def test_build_payload_empty_stop_sequences():
    """空のストップシーケンスではペイロードに stop が含まれないこと"""
    snapshot = _make_snapshot(inference={"stop_sequences": ""})
    client = TranslationClient(snapshot)
    payload = client._build_payload("data")
    assert "stop" not in payload


def test_build_payload_target_language_replacement():
    """{target_language} がシステムプロンプト内で置換されること"""
    snapshot = _make_snapshot(prompt={
        "system_prompt": "Translate to {target_language}.",
        "target_language": "French",
    })
    client = TranslationClient(snapshot)
    payload = client._build_payload("data")
    system_msg = next(m for m in payload["messages"] if m["role"] == "system")
    assert "French" in system_msg["content"]
    assert "{target_language}" not in system_msg["content"]
