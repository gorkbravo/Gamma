from __future__ import annotations

import logging
import os
from pathlib import Path


def setup_logging(*, log_dir: str | os.PathLike[str] | None = None, log_name: str = "gamma.log") -> Path | None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not any(
        isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
        for handler in root_logger.handlers
    ):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

    resolved_log_dir = Path(log_dir or os.getenv("GAMMA_LOG_DIR", "")).expanduser() if (log_dir or os.getenv("GAMMA_LOG_DIR")) else None
    log_path: Path | None = None
    if resolved_log_dir:
        resolved_log_dir.mkdir(parents=True, exist_ok=True)
        log_path = resolved_log_dir / log_name
        existing_files = {
            Path(handler.baseFilename).resolve()
            for handler in root_logger.handlers
            if isinstance(handler, logging.FileHandler) and getattr(handler, "baseFilename", None)
        }
        if log_path.resolve() not in existing_files:
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)

    logging.getLogger("kaleido").setLevel(logging.WARNING)
    logging.getLogger("choreographer").setLevel(logging.WARNING)
    logging.getLogger("ib_insync").setLevel(logging.WARNING)
    logging.getLogger("ib_insync.wrapper").setLevel(logging.WARNING)
    logging.getLogger("ib_insync.client").setLevel(logging.WARNING)
    return log_path
