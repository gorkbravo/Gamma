from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_desktop_backend_entry_serves_health(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    port = _free_port()
    log_dir = tmp_path / "logs"
    env = os.environ.copy()
    env.update(
        {
            "MOCK_DATA": "true",
            "GAMMA_API_PORT": str(port),
            "CACHE_DIR": str(tmp_path / "cache"),
            "PORTFOLIO_HISTORY_DIR": str(tmp_path / "data"),
            "SAMPLE_DATA_DIR": str((repo_root / "sample_data").resolve()),
            "GAMMA_LOG_DIR": str(log_dir),
            "GAMMA_BACKEND_FAILURE_REPORT": str(log_dir / "backend-failure.txt"),
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "src.api.desktop_entry"],
        cwd=str(repo_root),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 20
        last_error = None
        while time.time() < deadline:
            if process.poll() is not None:
                failure_report = log_dir / "backend-failure.txt"
                failure_detail = failure_report.read_text(encoding="utf-8") if failure_report.exists() else ""
                raise AssertionError(
                    f"desktop backend exited early with code {process.returncode}\n{failure_detail}".strip()
                )
            try:
                response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
                assert response.status_code == 200
                assert response.json()["status"] == "ok"
                return
            except Exception as exc:  # pragma: no cover - retry loop
                last_error = exc
                time.sleep(0.25)
        raise AssertionError(f"desktop backend health check timed out: {last_error}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
