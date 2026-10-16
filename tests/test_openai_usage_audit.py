import json
import os

from src.services import openai_usage_audit
from src.services.openai_usage_audit import audit_response


def test_transient_windows_lock_on_replace_is_retried(tmp_path, monkeypatch):
    # Regresión (validación en vivo 2026-10-16): WinError 5 al renombrar abortaba la ejecución del Operator.
    monkeypatch.setenv("GAMMA_OPENAI_USAGE_AUDIT_DIR", str(tmp_path))
    monkeypatch.setattr(openai_usage_audit.time, "sleep", lambda seconds: None)
    real_replace, failures = os.replace, {"left": 2}

    def flaky_replace(source, target):
        if failures["left"]:
            failures["left"] -= 1
            raise PermissionError(5, "Access is denied")
        return real_replace(source, target)

    monkeypatch.setattr(openai_usage_audit.os, "replace", flaky_replace)
    with audit_response("test", "gpt-test") as attempt:
        attempt.observe({"id": "resp_1", "usage": {"total_tokens": 3}})
    record = json.loads(attempt.path.read_text(encoding="utf-8"))
    assert record["usage"] == {"total_tokens": 3} and record["charge_status"] == "provider_usage_reported"


def test_persistent_audit_write_failure_does_not_abort_the_model_call(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("GAMMA_OPENAI_USAGE_AUDIT_DIR", str(tmp_path))
    monkeypatch.setattr(openai_usage_audit.time, "sleep", lambda seconds: None)

    def locked(source, target):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(openai_usage_audit.os, "replace", locked)
    completed = False
    with audit_response("test", "gpt-test") as attempt:
        attempt.observe({"id": "resp_2", "usage": {"total_tokens": 5}})
        completed = True
    assert completed and attempt.record["usage"] == {"total_tokens": 5}
    assert "OpenAI usage audit write failed" in caplog.text
