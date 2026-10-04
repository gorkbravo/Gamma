"""Gamma-owned, versioned approval checkpoints. Never deserialize executable state."""
from __future__ import annotations

import json
from typing import Any

from src.models.copilot import (
    CopilotLocalContinuationTurn, CopilotRequestContext, CopilotResearchCardRequest,
    CopilotSynthesisRequest, CopilotSynthesisScope, MacroCopilotContext,
)
from src.services.copilot_store import CopilotStore, CURRENT_COPILOT_STORE_SCHEMA_VERSION


class CopilotRunRecovery:
    VERSION = "copilot.run-recovery.v1"

    def __init__(self, store: CopilotStore):
        self.store = store
        self.directory = store.base_dir / "runs"

    def _path(self, run_id: str):
        safe = self.store._safe_id(run_id)
        if not safe or safe != run_id:
            raise ValueError("Invalid Copilot run id.")
        return self.directory / f"{safe}.json"

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self.store._lock:
            state = self.store._load_json(self._path(run_id), record_type="run_recovery")
            if state is not None and (
                state.get("contract_version") != self.VERSION
                or state.get("run_id") != run_id
                or not isinstance(state.get("request"), dict)
                or not isinstance(state.get("plan"), dict)
                or not isinstance(state.get("result"), dict)
                or not isinstance(state.get("session_id"), str)
                or not isinstance(state.get("mutation_id"), str)
                or not isinstance(state.get("remaining_tools"), int)
                or state["remaining_tools"] < 0
                or not isinstance(state.get("elapsed_ms"), int)
                or state["elapsed_ms"] < 0
                or not isinstance(state.get("visited_steps"), list)
                or not isinstance(state["plan"].get("steps"), list)
                or not isinstance(state["plan"].get("max_elapsed_ms"), int)
                or not isinstance(state["plan"].get("max_tool_calls"), int)
            ):
                raise ValueError("Unsupported or incomplete Copilot recovery record; no action ran.")
            return state

    def save(self, state: dict[str, Any]) -> None:
        # JSON normalizes datetimes without provider objects, pickles or credentials.
        payload = json.loads(json.dumps(state, default=str))
        payload.update(contract_version=self.VERSION, schema_version=CURRENT_COPILOT_STORE_SCHEMA_VERSION)
        with self.store._lock:
            self.store._write_json(self._path(state["run_id"]), payload)

    def request(self, state: dict[str, Any]) -> CopilotResearchCardRequest:
        payload = dict(state["request"])

        def context(value):
            value = dict(value or {})
            if value.get("macro") is not None:
                value["macro"] = MacroCopilotContext(**value["macro"])
            return CopilotRequestContext(**value)

        payload["context"] = context(payload.get("context"))
        synthesis = payload.get("synthesis")
        if synthesis:
            payload["synthesis"] = CopilotSynthesisRequest(
                active_tab=synthesis.get("active_tab"),
                included_scopes=[CopilotSynthesisScope(**{**scope, "context": context(scope.get("context"))})
                                 for scope in synthesis.get("included_scopes", [])],
            )
        payload["model_resolution"] = self.store._model_resolution_from_json(payload.get("model_resolution"))
        payload["entity_resolution"] = self.store._entity_resolution_from_json(payload.get("entity_resolution"))
        payload["local_continuation"] = [CopilotLocalContinuationTurn(**item) for item in payload.get("local_continuation", [])]
        request = CopilotResearchCardRequest(**payload)
        if request.role != "research_operator" or request.user_session_id != state.get("session_id"):
            raise ValueError("Recovery record has invalid Operator/session authority.")
        return request
