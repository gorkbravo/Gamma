from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Any, Callable, Optional

from ib_insync import IB


@dataclass
class _IBTask:
    fn: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    done: threading.Event
    operation: str
    result: Any = None
    error: Exception | None = None
    started: bool = False
    cancelled: bool = False
    caller_timed_out: bool = False


class IBThreadBusyError(RuntimeError):
    """The IB thread is still finishing an operation whose caller timed out."""

    def __init__(self, operation: str) -> None:
        self.operation = operation
        self.still_finishing = True
        super().__init__(f"IB worker busy: still_finishing timed-out operation '{operation}'")


class IBTaskTimeoutError(TimeoutError):
    """A caller deadline expired after the IB task had already started."""

    def __init__(self, operation: str, *, still_finishing: bool) -> None:
        self.operation = operation
        self.still_finishing = still_finishing
        state = "still_finishing" if still_finishing else "cancelled_before_start"
        super().__init__(f"IB task timed out ({state}): {operation}")


class IBThreadRunner:
    def __init__(self, ready_timeout: float = 5.0) -> None:
        self._queue: Queue[_IBTask | None] = Queue()
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="IBKRThread")
        self._loop: asyncio.AbstractEventLoop | None = None
        self.ib: IB | None = None
        self.thread_id: int | None = None
        self._task_lock = threading.RLock()
        self._active_task: _IBTask | None = None
        self._thread.start()
        self._ready.wait(timeout=ready_timeout)

    def _run(self) -> None:
        self.thread_id = threading.get_ident()
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self.ib = IB()
        self._ready.set()
        try:
            while True:
                task: _IBTask | None
                try:
                    task = self._queue.get(timeout=0.05)
                except Empty:
                    self._pump_events()
                    continue
                if task is None:
                    self._queue.task_done()
                    break
                with self._task_lock:
                    if task.cancelled:
                        task.done.set()
                        self._queue.task_done()
                        continue
                    task.started = True
                    self._active_task = task
                try:
                    task.result = task.fn(*task.args, **task.kwargs)
                except Exception as exc:  # pragma: no cover - surfaced to caller
                    task.error = exc
                finally:
                    task.done.set()
                    with self._task_lock:
                        if self._active_task is task:
                            self._active_task = None
                    self._queue.task_done()
                    self._pump_events()
        finally:
            self._stopped.set()
            try:
                if self.ib is not None and self.ib.isConnected():
                    self.ib.disconnect()
            except Exception:
                pass
            if self._loop is not None:
                try:
                    self._loop.stop()
                except Exception:
                    pass
                try:
                    self._loop.close()
                except Exception:
                    pass

    def _pump_events(self) -> None:
        if self.ib is None:
            return
        try:
            if self.ib.isConnected():
                self.ib.waitOnUpdate(timeout=0.05)
            else:
                time.sleep(0.05)
        except Exception:
            pass

    def in_thread(self) -> bool:
        return self.thread_id is not None and threading.get_ident() == self.thread_id

    def run(self, fn: Callable[..., Any], *args: Any, timeout: float | None = None, **kwargs: Any) -> Any:
        if self.ib is None or self.thread_id is None:
            raise RuntimeError("IB thread not ready")
        if self.in_thread():
            return fn(*args, **kwargs)
        with self._task_lock:
            active = self._active_task
            if (
                active is not None
                and active.caller_timed_out
                and not active.done.is_set()
            ):
                raise IBThreadBusyError(active.operation)
        operation = str(getattr(fn, "__name__", "") or fn.__class__.__name__ or "ib_operation")
        task = _IBTask(
            fn=fn,
            args=args,
            kwargs=kwargs,
            done=threading.Event(),
            operation=operation,
        )
        self._queue.put(task)
        if not task.done.wait(timeout):
            with self._task_lock:
                if task.done.is_set():
                    pass
                elif task.started:
                    task.caller_timed_out = True
                    raise IBTaskTimeoutError(task.operation, still_finishing=True)
                else:
                    task.cancelled = True
                    task.done.set()
                    raise IBTaskTimeoutError(task.operation, still_finishing=False)
        if task.error is not None:
            raise task.error
        return task.result

    def busy_state(self) -> dict[str, Any]:
        with self._task_lock:
            active = self._active_task
            if active is None or active.done.is_set():
                return {
                    "busy": False,
                    "still_finishing": False,
                    "operation": None,
                }
            return {
                "busy": True,
                "still_finishing": bool(active.caller_timed_out),
                "operation": active.operation,
            }

    def stop(self) -> None:
        if self.thread_id is None:
            return
        self._queue.put(None)
        try:
            self._thread.join(timeout=2)
        except Exception:
            pass
