"""翻訳クライアント - OpenAI互換API（Vision）への非同期通信"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from .config import ConfigManager
from .logger import get_logger

logger = get_logger("translator")


def _normalize_base_url(url: str) -> str:
    """URLパスが空またはルートのみの場合 /v1 を補完する。

    Examples
    --------
    "http://localhost:1234"   -> "http://localhost:1234/v1"
    "http://localhost:1234/"  -> "http://localhost:1234/v1"
    "http://localhost:1234/v1" -> "http://localhost:1234/v1"
    "http://localhost:1234/v2" -> "http://localhost:1234/v2"
    """
    from urllib.parse import urlparse
    url = url.rstrip("/")
    parsed = urlparse(url)
    if not parsed.path or parsed.path == "/":
        return url + "/v1"
    return url


class TranslationError(Exception):
    """API通信・レスポンス解析エラー"""


class TranslationClient:
    """
    OpenAI Chat Completions API（Vision対応）クライアント。
    ストリーミング・非ストリーミング両対応。
    """

    def __init__(self, config: ConfigManager) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _build_payload(self, image_b64: str) -> dict[str, Any]:
        """APIリクエストのペイロードを構築"""
        server = self._config.get_server()
        inf = self._config.get_inference()
        prompt_cfg = self._config.get_prompt()

        target_lang = prompt_cfg.get("target_language", "Japanese")
        system_prompt = prompt_cfg.get("system_prompt", "").replace(
            "{target_language}", target_lang
        )

        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}"
                        },
                    }
                ],
            }
        )

        payload: dict[str, Any] = {
            "model": server.get("model", ""),
            "messages": messages,
            "temperature": inf.get("temperature", 0.3),
            "max_tokens": inf.get("max_tokens", 2048),
            "top_p": inf.get("top_p", 0.95),
            "frequency_penalty": inf.get("frequency_penalty", 0.0),
            "presence_penalty": inf.get("presence_penalty", 0.0),
            "stream": True,
        }

        # オプションパラメータ（0/デフォルト値の場合は省略）
        top_k = inf.get("top_k", 40)
        if top_k and top_k > 0:
            payload["top_k"] = top_k

        repeat_penalty = inf.get("repeat_penalty", 1.1)
        if repeat_penalty != 1.0:
            payload["repeat_penalty"] = repeat_penalty

        seed = inf.get("seed", -1)
        if seed is not None and seed >= 0:
            payload["seed"] = seed

        stop_raw = inf.get("stop_sequences", "")
        if stop_raw:
            stops = [s.strip() for s in stop_raw.split(",") if s.strip()]
            if stops:
                payload["stop"] = stops

        return payload

    def _get_headers(self) -> dict[str, str]:
        server = self._config.get_server()
        headers = {"Content-Type": "application/json"}
        api_key = server.get("api_key", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _get_endpoint(self) -> str:
        server = self._config.get_server()
        raw = server.get("api_base_url", "http://localhost:1234/v1")
        base = _normalize_base_url(raw)
        return f"{base}/chat/completions"

    def _get_timeout(self) -> float:
        return float(self._config.get_server().get("timeout", 60))

    # ------------------------------------------------------------------
    # 公開API
    # ------------------------------------------------------------------

    async def translate_stream(self, image_b64: str) -> AsyncGenerator[str, None]:
        """
        画像をAPIに送信し、翻訳テキストをストリーミングで yield する。

        Yields
        ------
        str: デルタテキスト（チャンク）
        """
        payload = self._build_payload(image_b64)
        headers = self._get_headers()
        endpoint = self._get_endpoint()
        timeout = self._get_timeout()

        # 画像データを除いたペイロードをデバッグログに出力
        log_payload = {k: v for k, v in payload.items() if k != "messages"}
        logger.info("翻訳リクエスト送信: endpoint=%s, model=%s", endpoint, payload.get("model", ""))
        logger.debug("リクエストパラメータ: %s", log_payload)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    endpoint,
                    json=payload,
                    headers=headers,
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        error_text = body.decode("utf-8", errors="replace")
                        logger.error("APIエラー: status=%d, body=%s", response.status_code, error_text)
                        raise TranslationError(
                            f"APIエラー {response.status_code}: {error_text}"
                        )

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[len("data:"):].strip()
                        if data_str == "[DONE]":
                            logger.info("翻訳完了")
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = (
                                chunk.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content", "")
                            )
                            if delta:
                                logger.debug("ストリームチャンク受信: %r", delta)
                                yield delta
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue

        except asyncio.CancelledError:
            # キャンセル時は適切に再送出
            raise
        except httpx.TimeoutException as e:
            logger.error("タイムアウト: timeout=%ss, %s", timeout, e)
            raise TranslationError(f"タイムアウト ({timeout}秒): {e}") from e
        except httpx.ConnectError as e:
            logger.error("接続エラー: %s", e)
            raise TranslationError(f"接続エラー: {e}") from e
        except httpx.HTTPError as e:
            logger.error("HTTPエラー: %s", e)
            raise TranslationError(f"HTTPエラー: {e}") from e

    async def translate(self, image_b64: str) -> str:
        """
        画像をAPIに送信し、翻訳テキスト全体を返す（ストリームを結合）。
        """
        parts: list[str] = []
        async for chunk in self.translate_stream(image_b64):
            parts.append(chunk)
        return "".join(parts)
