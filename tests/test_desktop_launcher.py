from __future__ import annotations

import argparse

import pytest

from src import desktop_launcher


def test_resolve_client_defaults_to_tauri():
    args = argparse.Namespace(client=None)

    assert desktop_launcher.resolve_client(args, {}) == "tauri"


def test_resolve_client_honors_env_override():
    args = argparse.Namespace(client=None)

    assert desktop_launcher.resolve_client(args, {"STRATALAB_DESKTOP_CLIENT": "pyside"}) == "pyside"


def test_resolve_client_honors_cli_override_over_env():
    args = argparse.Namespace(client="tauri")

    assert desktop_launcher.resolve_client(args, {"STRATALAB_DESKTOP_CLIENT": "pyside"}) == "tauri"


def test_resolve_client_rejects_unknown_value():
    args = argparse.Namespace(client=None)

    with pytest.raises(SystemExit, match="Unsupported desktop client"):
        desktop_launcher.resolve_client(args, {"STRATALAB_DESKTOP_CLIENT": "unknown"})


def test_resolve_launch_spec_uses_pyside_module():
    spec = desktop_launcher.resolve_launch_spec("pyside", {})

    assert spec.client == "pyside"
    assert spec.command == (desktop_launcher.sys.executable, "-m", "src.main")
    assert spec.cwd == desktop_launcher.repo_root()


def test_resolve_tauri_command_uses_explicit_npm_override(tmp_path):
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "package.json").write_text("{}", encoding="utf-8")
    (frontend_dir / "node_modules").mkdir()

    command = desktop_launcher.resolve_tauri_command(
        tmp_path,
        {"STRATALAB_NPM": "C:\\tools\\npm.cmd"},
    )

    assert command == ["C:\\tools\\npm.cmd", "run", "tauri:dev"]


def test_resolve_tauri_command_requires_node_modules(tmp_path, monkeypatch: pytest.MonkeyPatch):
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    (frontend_dir / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(desktop_launcher.shutil, "which", lambda _: "npm")

    with pytest.raises(SystemExit, match="npm install"):
        desktop_launcher.resolve_tauri_command(tmp_path, {})
