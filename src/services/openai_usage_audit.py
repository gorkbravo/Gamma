"""Opt-in per-attempt Responses accounting. Never stores prompts or credentials."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import time
from uuid import uuid4

logger = logging.getLogger(__name__)
REPLACE_ATTEMPTS = 5


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
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.record, ensure_ascii=True), encoding="utf-8")
            # En Windows el antivirus o el indexador pueden bloquear un instante el destino
            # recién escrito (WinError 5); se reintenta antes de rendirse.
            for attempt in range(REPLACE_ATTEMPTS):
                try:
                    os.replace(temporary, self.path)
                    return
                except PermissionError:
                    if attempt == REPLACE_ATTEMPTS - 1:
                        raise
                    time.sleep(0.05 * (attempt + 1))
        except OSError as exc:
            # La auditoría es opcional: un fallo de E/S no debe abortar la llamada al modelo
            # (validación en vivo 2026-10-16). El registro en memoria se reintenta en el siguiente save.
            logger.warning("OpenAI usage audit write failed for %s: %s", self.path.name, type(exc).__name__)

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
