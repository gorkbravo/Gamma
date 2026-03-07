from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from queue import Queue
from typing import Any, Callable


logger = logging.getLogger(__name__)


@dataclass
class _Task:
    fn: Callable[[], Any]
    on_success: Callable[[Any], None]
    on_error: Callable[[Exception], None]
    max_retries: int
    backoff_seconds: float
    attempt: int = 0


class ThrottleQueue:
    def __init__(self, min_interval_seconds: float = 1.0) -> None:
        self.min_interval = min_interval_seconds
        self.queue: Queue[_Task] = Queue()
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def submit(
        self,
        fn: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[Exception], None],
        max_retries: int = 0,
        backoff_seconds: float = 2.0,
    ) -> None:
        self.queue.put(_Task(fn, on_success, on_error, max_retries, backoff_seconds))

    def _worker(self) -> None:
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        last_time = 0.0
        while True:
            task = self.queue.get()
            now = time.time()
            elapsed = now - last_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            try:
                result = task.fn()
                try:
                    task.on_success(result)
                except Exception as callback_exc:
                    self._safe_callback(task.on_error, callback_exc)
            except Exception as exc:
                if task.attempt < task.max_retries:
                    task.attempt += 1
                    backoff = task.backoff_seconds * (2 ** (task.attempt - 1))
                    time.sleep(backoff)
                    self.queue.put(task)
                else:
                    self._safe_callback(task.on_error, exc)
            last_time = time.time()
            self.queue.task_done()

    @staticmethod
    def _safe_callback(callback: Callable[[Exception], None], exc: Exception) -> None:
        try:
            callback(exc)
        except Exception:
            logger.exception("ThrottleQueue callback failed")
