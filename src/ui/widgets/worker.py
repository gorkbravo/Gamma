from __future__ import annotations

import inspect
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int, int, str)


class Worker(QRunnable):
    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            sig = inspect.signature(self.fn)
            if "progress_cb" in sig.parameters and "progress_cb" not in self.kwargs:
                self.kwargs["progress_cb"] = self.signals.progress.emit
            result = self.fn(*self.args, **self.kwargs)
            self.signals.finished.emit(result)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            tb = traceback.format_exc().strip()
            self.signals.error.emit(f"{message}\n{tb}")
