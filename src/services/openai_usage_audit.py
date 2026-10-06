"""Opt-in per-attempt Responses accounting. Never stores prompts or credentials."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4


class UsageAttempt:
    def __init__(self, consumer: str, model: str):
        directory = os.getenv("GAMMA_OPENAI_USAGE_AUDIT_DIR")
        self.path = Path(directory) / f"{uuid4().hex}.json" if directory else None
        self.record = {"consumer": consumer, "model": model, "started_at": datetime.now(timezone.utc).isoformat(),
                       "status": "pending", "usage": None, "charge_status": "unknown"}
        self.save()

    def save(self):
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.record, ensure_ascii=True), encoding="utf-8")
        os.replace(temporary, self.path)

    def observe(self, response):
        if not isinstance(response, dict):
            dump = getattr(response, "model_dump", None)
            response = dump(mode="json") if callable(dump) else {}
        self.record.update({key: response[key] for key in ("id", "model", "status", "service_tier") if key in response})
        if isinstance(response.get("usage"), dict):
            self.record["usage"] = response["usage"]
            self.record["charge_status"] = "provider_usage_reported"
        self.save()


@contextmanager
def audit_response(consumer: str, model: str):
    attempt = UsageAttempt(consumer, model)
    try:
        yield attempt
    except BaseException as exc:
        # HTTP rejection/transport loss/cancellation must not become zero cost.
        attempt.record.update(status="interrupted", error_type=type(exc).__name__)
        raise
    finally:
        attempt.record["finished_at"] = datetime.now(timezone.utc).isoformat()
        attempt.save()
