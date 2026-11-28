"""Mínimo de la beta (2026-11-28): claves desde Setup e informe de «Report a problem»."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.diagnostic_report import EXCLUDED_FROM_REPORT, REPORT_SCHEMA, redact_secrets, sanitize_message
from src.application.env_file import EnvValueError, read_env_assignments, update_env_file, validate_env_value
from src.application.runtime import build_runtime
from src.version import APP_VERSION

SECRET = "fred-test-0123456789abcdef"


@pytest.fixture
def env_path(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "app-data" / ".env"
    monkeypatch.setenv("GAMMA_ENV_FILE", str(path))
    return path


@pytest.fixture
def client(tmp_path, env_path, monkeypatch):
    monkeypatch.setenv("GAMMA_LOG_DIR", str(tmp_path / "logs"))
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    try:
        yield TestClient(create_app(runtime))
    finally:
        runtime.shutdown()


# --- .env ---------------------------------------------------------------------------------


def test_update_env_file_preserves_other_lines_and_replaces_in_place(tmp_path):
    path = tmp_path / ".env"
    path.write_bytes(b"# Gamma\r\nMOCK_DATA=true\r\nFRED_API_KEY=old\r\n# FRED_API_KEY=commented\r\nFRED_API_KEY=dup\r\n")

    update_env_file(path, {"FRED_API_KEY": "new-value", "EIA_API_KEY": "eia-1"})

    text = path.read_bytes().decode("utf-8")
    assert text.startswith("# Gamma\r\nMOCK_DATA=true\r\nFRED_API_KEY=new-value\r\n# FRED_API_KEY=commented\r\n")
    assert "FRED_API_KEY=dup" not in text  # la asignación repetida desaparece
    assert text.endswith("EIA_API_KEY=eia-1\r\n")
    assert read_env_assignments(path) == {"MOCK_DATA": "true", "FRED_API_KEY": "new-value", "EIA_API_KEY": "eia-1"}


def test_update_env_file_removes_and_creates(tmp_path):
    path = tmp_path / "nested" / ".env"
    update_env_file(path, {"OPENAI_API_KEY": "sk-test-abc"})
    assert read_env_assignments(path) == {"OPENAI_API_KEY": "sk-test-abc"}

    update_env_file(path, {"OPENAI_API_KEY": None})
    assert "OPENAI_API_KEY" not in read_env_assignments(path)


@pytest.mark.parametrize("value", ["has space", 'quo"te', "dollar$VAR", "hash#tag", "back\\slash", "", "x" * 513])
def test_env_values_that_dotenv_would_misread_are_rejected(value):
    with pytest.raises(EnvValueError):
        validate_env_value("FRED_API_KEY", value)


# --- claves desde Setup ---------------------------------------------------------------------


def test_setup_keys_are_saved_to_the_env_file_and_never_returned(client, env_path):
    response = client.post("/system/setup/keys", json={"keys": {"FRED_API_KEY": SECRET}})

    assert response.status_code == 200, response.text
    assert SECRET not in response.text
    assert read_env_assignments(env_path)["FRED_API_KEY"] == SECRET
    body = response.json()
    fred = next(row for row in body["providers"] if "FRED_API_KEY" in row["env_vars"])
    assert fred["configured"] is False  # este backend arrancó sin la clave
    assert fred["pending_restart"] is True
    assert any("Restart Gamma" in line for line in body["lines"])

    cleared = client.post("/system/setup/keys", json={"keys": {"FRED_API_KEY": ""}})
    assert cleared.status_code == 200
    assert "FRED_API_KEY" not in read_env_assignments(env_path)


def test_setup_keys_accept_the_copilot_key(client, env_path):
    response = client.post("/system/setup/keys", json={"keys": {"OPENAI_API_KEY": "sk-test-0123456789"}})

    assert response.status_code == 200, response.text
    assert response.json()["copilot"]["pending_restart"] is True
    assert "sk-test-0123456789" not in response.text


@pytest.mark.parametrize(
    "keys",
    [{"MOCK_DATA": "false"}, {"GAMMA_COPILOT_MODEL": "x"}, {"FRED_API_KEY": "with space"}],
)
def test_setup_keys_reject_other_variables_and_bad_values(client, env_path, keys):
    response = client.post("/system/setup/keys", json={"keys": keys})

    assert response.status_code == 422
    assert not env_path.exists()


# --- informe de diagnóstico -----------------------------------------------------------------


def test_sanitize_message_strips_urls_emails_accounts_and_secrets():
    text = (
        "GET https://api.example.com/v1?api_key=abc failed for ada@example.com on U1234567 "
        "with token=xyz sk-live-abcdefghijk and id 12345678901 " + "a" * 40
    )
    clean = sanitize_message(text)

    for leaked in ("https://", "ada@example.com", "U1234567", "xyz", "sk-live", "12345678901", "a" * 40):
        assert leaked not in clean
    assert len(sanitize_message("x " * 500)) <= 200


def test_the_tester_note_keeps_its_words_but_loses_keys():
    note = redact_secrets("Copilot failed with sk-proj-abcdefghijkl, see https://x.test/q?api_key=zzz&x=1")

    assert "sk-proj" not in note and "zzz" not in note
    assert note == "Copilot failed with <secret>, see https://x.test/q?api_key=<redacted>&x=1"


def test_diagnostic_report_contains_state_but_no_secrets(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-should-not-appear")
    response = client.post(
        "/system/diagnostic-report/preview",
        json={"note": "Risk tab froze", "client": {"active_tab": "risk", "last_error": "see https://x.test/q?token=1"}},
    )

    assert response.status_code == 200, response.text
    assert "sk-test-should-not-appear" not in response.text
    report = response.json()["report"]
    assert report["schema"] == REPORT_SCHEMA
    assert report["app"]["version"] == APP_VERSION
    assert report["runtime"]["data_mode"] == "demo"
    assert report["copilot"]["status"] == "demo"  # la suite fija GAMMA_COPILOT_PROVIDER=mock
    assert report["note"] == "Risk tab froze"
    assert report["generated_at"].endswith("Z")
    assert report["client"]["active_tab"] == "risk"
    assert "https://" not in report["client"]["last_error"]
    assert report["excluded"] == EXCLUDED_FROM_REPORT
    assert response.json()["path"] is None


def test_saving_the_report_writes_it_locally(client, tmp_path):
    response = client.post("/system/diagnostic-report", json={"note": "test"})

    assert response.status_code == 200, response.text
    path = Path(response.json()["path"])
    assert path.parent == tmp_path / "logs" / "reports"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["note"] == "test"


def test_app_version_matches_pyproject():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert APP_VERSION == pyproject["project"]["version"]
