from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.models.copilot import (
    CopilotContextBundle,
    CopilotResearchCardRequest,
    CopilotResearchCardResult,
    CopilotSourceRef,
    CopilotToolTrace,
    ResearchCard,
    ResearchClaim,
)
from src.services.copilot_provider import CopilotProvider, ToolExecutor


RESEARCH_CARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string"},
        "hypothesis": {"type": "string"},
        "rationale": {"type": "string"},
        "required_data": {"type": "array", "items": {"type": "string"}},
        "proposed_test": {"type": "string"},
        "confounders": {"type": "array", "items": {"type": "string"}},
        "next_steps": {"type": "array", "items": {"type": "string"}},
        "caveats": {"type": "array", "items": {"type": "string"}},
        "source_backed_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "claim": {"type": "string"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["claim", "evidence_refs"],
            },
        },
        "inferred_claims": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title",
        "hypothesis",
        "rationale",
        "required_data",
        "proposed_test",
        "confounders",
        "next_steps",
        "caveats",
        "source_backed_claims",
        "inferred_claims",
    ],
}


@dataclass
class OpenAIResponsesCopilotProvider(CopilotProvider):
    api_key: str
    model: str
    reasoning_effort: str
    api_url: str = "https://api.openai.com/v1/responses"
    timeout_seconds: float = 45.0
    store_responses: bool = False
    provider_name: str = "openai_responses"

    def generate_research_card(
        self,
        *,
        request: CopilotResearchCardRequest,
        context: CopilotContextBundle,
        tool_specs: list[dict[str, object]],
        execute_tool: ToolExecutor,
    ) -> CopilotResearchCardResult:
        input_items: list[dict[str, Any]] = [self._build_user_message(request, context)]
        tool_traces: list[CopilotToolTrace] = []
        tool_sources: dict[str, CopilotSourceRef] = {source.source_id: source for source in context.sources}
        warnings = list(context.warnings)

        for turn in range(5):
            payload: dict[str, Any] = {
                "model": self.model,
                "instructions": self._build_instructions(context),
                "input": input_items,
                "tools": tool_specs,
                "tool_choice": "auto",
                "parallel_tool_calls": False,
                "max_output_tokens": 1400,
                "reasoning": {"effort": self.reasoning_effort},
                "text": {
                    "verbosity": "low",
                    "format": {
                        "type": "json_schema",
                        "name": "gamma_research_card",
                        "strict": True,
                        "schema": RESEARCH_CARD_SCHEMA,
                    },
                },
                "store": self.store_responses,
                "safety_identifier": self._safety_identifier(request),
                "prompt_cache_key": f"gamma-copilot:{request.domain}:research-card:v1",
                "metadata": {
                    "app": "gamma",
                    "domain": request.domain,
                    "current_tab": context.current_tab,
                },
            }
            if turn == 0 and request.previous_response_id:
                payload["previous_response_id"] = request.previous_response_id

            try:
                response = self._post_json(payload)
            except RuntimeError as exc:
                return CopilotResearchCardResult(
                    domain=request.domain,
                    current_tab=context.current_tab,
                    status="error",
                    provider=self.provider_name,
                    model=self.model,
                    message=str(exc),
                    sources=list(tool_sources.values()),
                    tool_traces=tool_traces,
                    warnings=warnings,
                )

            tool_calls = [item for item in response.get("output", []) if item.get("type") == "function_call"]
            if tool_calls:
                input_items.extend(response.get("output", []))
                for item in tool_calls:
                    tool_name = str(item.get("name") or "").strip()
                    arguments = self._parse_tool_arguments(item.get("arguments"))
                    execution = execute_tool(tool_name, arguments, context)
                    tool_traces.append(execution.trace)
                    for source in execution.sources:
                        tool_sources[source.source_id] = source
                    input_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": item.get("call_id"),
                            "output": self._format_tool_output(execution.output),
                        }
                    )
                continue

            refusal = self._extract_refusal(response)
            if refusal:
                return CopilotResearchCardResult(
                    domain=request.domain,
                    current_tab=context.current_tab,
                    status="error",
                    provider=self.provider_name,
                    model=str(response.get("model") or self.model),
                    response_id=str(response.get("id") or ""),
                    message=refusal,
                    sources=list(tool_sources.values()),
                    tool_traces=tool_traces,
                    warnings=warnings,
                )

            try:
                card = self._parse_research_card(response)
            except RuntimeError as exc:
                return CopilotResearchCardResult(
                    domain=request.domain,
                    current_tab=context.current_tab,
                    status="error",
                    provider=self.provider_name,
                    model=str(response.get("model") or self.model),
                    response_id=str(response.get("id") or ""),
                    message=str(exc),
                    sources=list(tool_sources.values()),
                    tool_traces=tool_traces,
                    warnings=warnings,
                )

            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=context.current_tab,
                status="ready",
                provider=self.provider_name,
                model=str(response.get("model") or self.model),
                response_id=str(response.get("id") or ""),
                card=card,
                sources=list(tool_sources.values()),
                tool_traces=tool_traces,
                warnings=warnings,
            )

        return CopilotResearchCardResult(
            domain=request.domain,
            current_tab=context.current_tab,
            status="error",
            provider=self.provider_name,
            model=self.model,
            message="Copilot exceeded the allowed number of tool rounds.",
            sources=list(tool_sources.values()),
            tool_traces=tool_traces,
            warnings=warnings,
        )

    def _build_user_message(
        self,
        request: CopilotResearchCardRequest,
        context: CopilotContextBundle,
    ) -> dict[str, Any]:
        default_prompt = (
            "Generate a concise research card for the current Gamma workspace."
            if request.domain == "macro"
            else "Generate a concise research card for the selected Gamma prediction market."
        )
        requested_prompt = (request.prompt or "").strip() or default_prompt
        body = {
            "task": requested_prompt,
            "domain": request.domain,
            "current_tab": context.current_tab,
            "workspace_context": context.summary_data,
            "available_source_refs": [
                {
                    "source_id": source.source_id,
                    "label": source.label,
                    "kind": source.kind,
                    "provider": source.provider,
                }
                for source in context.sources
            ],
            "warnings": context.warnings,
        }
        return {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": json.dumps(body, ensure_ascii=True),
                }
            ],
        }

    def _build_instructions(self, context: CopilotContextBundle) -> str:
        source_ids = ", ".join(source.source_id for source in context.sources) or "none"
        return (
            "You are Gamma Copilot inside a read-only research application. "
            "Stay anchored to the supplied Gamma workspace state and Gamma-owned tools. "
            "Do not imply that you executed trades, changed app state, or retrieved external data. "
            "Use tools only when the current context is insufficient. "
            "Every source-backed claim must cite one or more `source_id` values from the available sources or tool outputs. "
            "Anything that extends beyond explicit source evidence belongs in `inferred_claims` or `caveats`. "
            "Keep the card analytical, concise, and research-oriented. "
            f"Initial source ids: {source_ids}."
        )

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw)
                message = body.get("error", {}).get("message") or raw
            except json.JSONDecodeError:
                message = raw or str(exc)
            raise RuntimeError(f"OpenAI request failed: {message}") from exc
        except URLError as exc:
            raise RuntimeError(f"OpenAI request failed: {exc.reason}") from exc

    @staticmethod
    def _parse_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        text = str(raw_arguments or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _format_tool_output(output: dict[str, Any] | list[Any] | str) -> str:
        if isinstance(output, str):
            return output
        return json.dumps(output, ensure_ascii=True)

    @staticmethod
    def _extract_refusal(response: dict[str, Any]) -> str | None:
        for item in response.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "refusal":
                    return str(content.get("refusal") or "The model refused the request.")
        return None

    @staticmethod
    def _parse_research_card(response: dict[str, Any]) -> ResearchCard:
        text_chunks: list[str] = []
        for item in response.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    text_chunks.append(str(content.get("text") or ""))
        raw_text = "\n".join(chunk for chunk in text_chunks if chunk.strip()).strip()
        if not raw_text:
            raise RuntimeError("OpenAI returned no structured research card.")
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenAI returned a non-JSON research card payload.") from exc
        return ResearchCard(
            title=str(payload.get("title") or ""),
            hypothesis=str(payload.get("hypothesis") or ""),
            rationale=str(payload.get("rationale") or ""),
            required_data=[str(item) for item in payload.get("required_data", [])],
            proposed_test=str(payload.get("proposed_test") or ""),
            confounders=[str(item) for item in payload.get("confounders", [])],
            next_steps=[str(item) for item in payload.get("next_steps", [])],
            caveats=[str(item) for item in payload.get("caveats", [])],
            source_backed_claims=[
                ResearchClaim(
                    claim=str(item.get("claim") or ""),
                    evidence_refs=[str(ref) for ref in item.get("evidence_refs", [])],
                )
                for item in payload.get("source_backed_claims", [])
                if isinstance(item, dict)
            ],
            inferred_claims=[str(item) for item in payload.get("inferred_claims", [])],
        )

    @staticmethod
    def _safety_identifier(request: CopilotResearchCardRequest) -> str:
        seed = (request.user_session_id or "anonymous").strip() or "anonymous"
        return sha256(seed.encode("utf-8")).hexdigest()[:64]
