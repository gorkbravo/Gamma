from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path

from src.utils.logging_config import setup_logging

API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8000
LOGGER = logging.getLogger("gamma.desktop_backend")


def _resolve_failure_report_path() -> Path | None:
    value = (os.getenv("GAMMA_BACKEND_FAILURE_REPORT") or "").strip()
    return Path(value).expanduser() if value else None


def _write_failure_report(message: str) -> None:
    path = _resolve_failure_report_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(message, encoding="utf-8")


def _clear_failure_report() -> None:
    path = _resolve_failure_report_path()
    if path is None or not path.exists():
        return
    path.unlink()


def _default_sample_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "sample_data"
    return Path.cwd() / "sample_data"


def _configure_runtime_paths() -> None:
    if not os.getenv("SAMPLE_DATA_DIR"):
        os.environ["SAMPLE_DATA_DIR"] = str(_default_sample_data_dir())


def _api_port() -> int:
    value = (os.getenv("GAMMA_API_PORT") or "").strip()
    if not value:
        return DEFAULT_API_PORT
    port = int(value)
    if port <= 0:
        raise ValueError("GAMMA_API_PORT must be greater than 0.")
    return port


def main() -> int:
    _configure_runtime_paths()
    setup_logging()
    _clear_failure_report()

    try:
        port = _api_port()
        LOGGER.info("Initializing Gamma desktop backend runtime")
        import uvicorn

        from src.api.main import create_app

        app = create_app()
        LOGGER.info("Starting Gamma desktop backend on http://%s:%s", API_HOST, port)
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host=API_HOST,
                port=port,
                log_level=(os.getenv("UVICORN_LOG_LEVEL") or os.getenv("LOG_LEVEL", "info")).lower(),
                access_log=(os.getenv("GAMMA_ACCESS_LOG", "false").lower() == "true"),
            )
        )
        server.run()
        if not server.started:
            raise RuntimeError("Desktop backend exited before becoming ready.")
        return 0
    except Exception:
        failure = traceback.format_exc()
        LOGGER.exception("Desktop backend startup failed")
        _write_failure_report(failure)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
