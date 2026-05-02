"""非同期翻訳ワーカー - 専用スレッドでasyncioループを実行"""

from __future__ import annotations

import asyncio
import copy
import threading
from typing import Any

from PySide6.QtCore import QObject, Signal

from .config import ConfigManager
from .logger import get_logger
from .translator import TranslationClient

logger = get_logger("worker")


class AsyncTranslationWorker(QObject):
    """
    専用スレッドで asyncio イベントループを実行し、翻訳リクエストを処理するワーカー。

    スレッドセーフティのため、翻訳投入時にConfigManagerから設定の
    deepcopyを取得し、ワーカースレッドではそのスナップショットのみを参照する。
    """
    translation_started = Signal()
    chunk_received = Signal(str)
    translation_done = Signal(str)
    translation_error = Signal(str)
    translation_cancelled = Signal()

    def __init__(self, config: ConfigManager):
        super().__init__()
        self._config = config
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._current_task: asyncio.Task | None = None
        self._should_be_running = False

    def start_loop(self) -> None:
        """ワーカースレッドを起動"""
        if self._thread and self._thread.is_alive():
            return

        self._should_be_running = True
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="TranslationWorkerThread",
            daemon=True
        )
        self._thread.start()
        logger.debug("非同期ワーカー開始")

    def _run_loop(self) -> None:
        """ワーカースレッドのメインループ"""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            # 残っているタスクをキャンセル
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()

            if pending:
                self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

            self._loop.close()

    def stop_loop(self) -> None:
        """ワーカースレッドを停止"""
        self._should_be_running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
            self._loop = None
        logger.debug("非同期ワーカー停止")

    def _take_config_snapshot(self) -> dict[str, Any]:
        """メインスレッドで呼び出し、アクティブプリセットのdeepcopyを返す"""
        return copy.deepcopy(self._config.get_active_preset())

    def submit_translation(self, image_b64: str) -> None:
        """翻訳タスクを投入（メインスレッドから呼ばれる）"""
        if self.is_busy or not self._loop or not self._loop.is_running():
            return

        # メインスレッド上で設定スナップショットを取得
        snapshot = self._take_config_snapshot()

        self._loop.call_soon_threadsafe(
            self._schedule_translation, image_b64, snapshot
        )

    def _schedule_translation(self, image_b64: str, config_snapshot: dict[str, Any]) -> None:
        """イベントループ内でタスクをスケジュール"""
        self._current_task = self._loop.create_task(
            self._run_translation(image_b64, config_snapshot)
        )

    async def _run_translation(self, image_b64: str, config_snapshot: dict[str, Any]) -> None:
        """翻訳処理の実体（async）"""
        self.translation_started.emit()
        client = TranslationClient(config_snapshot)
        full_text = ""
        try:
            async for chunk in client.translate_stream(image_b64):
                full_text += chunk
                self.chunk_received.emit(chunk)

            self.translation_done.emit(full_text)
        except asyncio.CancelledError:
            self.translation_cancelled.emit()
        except Exception as e:
            logger.error("翻訳処理エラー: %s", e)
            self.translation_error.emit(str(e))
        finally:
            self._current_task = None

    def cancel_translation(self) -> None:
        """進行中の翻訳をキャンセル"""
        if self._loop and self._current_task:
            self._loop.call_soon_threadsafe(
                self._current_task.cancel
            )

    @property
    def is_busy(self) -> bool:
        """翻訳処理中かどうか"""
        return self._current_task is not None and not self._current_task.done()
