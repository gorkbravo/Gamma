from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from dotenv import load_dotenv

DEFAULT_DESKTOP_CLIENT = "tauri"
SUPPORTED_DESKTOP_CLIENTS = ("tauri", "pyside")


@dataclass(frozen=True)
class LaunchSpec:
    client: str
    command: tuple[str, ...]
    cwd: Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the Gamma desktop client.")
    parser.add_argument(
        "--client",
        choices=SUPPORTED_DESKTOP_CLIENTS,
        help="Desktop client to launch. Defaults to GAMMA_DESKTOP_CLIENT or Tauri.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def resolve_client(args: argparse.Namespace, environ: Mapping[str, str]) -> str:
    configured = (args.client or environ.get("GAMMA_DESKTOP_CLIENT") or DEFAULT_DESKTOP_CLIENT).strip().lower()
    if configured not in SUPPORTED_DESKTOP_CLIENTS:
        supported = ", ".join(SUPPORTED_DESKTOP_CLIENTS)
        raise SystemExit(f"Unsupported desktop client '{configured}'. Supported clients: {supported}.")
    return configured


def resolve_launch_spec(client: str, environ: Mapping[str, str]) -> LaunchSpec:
    root = repo_root()
    if client == "pyside":
        return LaunchSpec(client="pyside", command=(sys.executable, "-m", "src.main"), cwd=root)
    return LaunchSpec(client="tauri", command=tuple(resolve_tauri_command(root, environ)), cwd=root / "frontend")


def resolve_tauri_command(root: Path, environ: Mapping[str, str]) -> list[str]:
    npm = environ.get("GAMMA_NPM") or shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise SystemExit("Unable to find npm for the default Tauri desktop launcher. Install Node.js or use --client pyside.")
    frontend_dir = root / "frontend"
    package_json = frontend_dir / "package.json"
    if not package_json.exists():
        raise SystemExit(f"Missing Tauri frontend manifest at {package_json}. Use --client pyside if this checkout is incomplete.")
    node_modules = frontend_dir / "node_modules"
    if not node_modules.exists():
        raise SystemExit(
            f"Tauri dependencies are not installed under {node_modules}. Run 'cd frontend && npm install' or use --client pyside."
        )
    return [npm, "run", "tauri:dev"]


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    args = parse_args(argv)
    client = resolve_client(args, os.environ)
    launch = resolve_launch_spec(client, os.environ)
    completed = subprocess.run(list(launch.command), cwd=launch.cwd, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
