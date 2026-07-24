from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time
from functools import cached_property
from hashlib import sha256
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from src.models.copilot import (
    CopilotContextBundle,
    CopilotResearchCardRequest,
    CopilotResearchCardResult,
    CopilotSourceRef,
    CopilotToolTrace,
    ResearchCard,
    ResearchClaim,
)
from src.services.copilot_provider import (
    CancelCheck,
    CopilotProvider,
    CopilotRunCancelled,
    RunEventEmitter,
    ToolExecutor,
)


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

SUPPORTED_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}
STRUCTURED_CARD_PARSE_ERRORS = {
    "OpenAI returned no structured research card.",
    "OpenAI returned a non-JSON research card payload.",
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
    provider_id: str = "openai_copilot"

    @staticmethod
    def _json_default(value: Any) -> str:
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        return str(value)

    @classmethod
    def _json_dumps(cls, value: Any) -> str:
        return json.dumps(value, ensure_ascii=True, default=cls._json_default)

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
        reasoning_effort = self._resolve_reasoning_effort(request.reasoning_effort)

        for turn in range(5):
            payload = self._build_response_payload(
                request=request,
                context=context,
                input_items=input_items,
                reasoning_effort=reasoning_effort,
                tool_specs=tool_specs,
                tool_choice="auto",
                max_output_tokens=1400,
                prompt_cache_key=f"gamma-copilot:{request.domain}:research-card:v2",
            )
            if turn == 0 and request.previous_response_id and self.store_responses:
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
                input_items.extend(self._continuation_output_items(response))
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
                if self._is_structured_card_parse_error(str(exc)):
                    retry_result = self._retry_structured_research_card(
                        request=request,
                        context=context,
                        input_items=input_items,
                        reasoning_effort=reasoning_effort,
                        parse_error=str(exc),
                        tool_sources=tool_sources,
                        tool_traces=tool_traces,
                        warnings=warnings,
                    )
                    if retry_result is not None:
                        return retry_result
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

    def stream_research_card(
        self,
        *,
        request: CopilotResearchCardRequest,
        context: CopilotContextBundle,
        tool_specs: list[dict[str, object]],
        execute_tool: ToolExecutor,
        emit: RunEventEmitter,
        should_cancel: CancelCheck,
    ) -> CopilotResearchCardResult:
        """Provider-native streaming variant of `generate_research_card`.

        Emits semantic run events (`text.delta`, `tool.call`, `tool.result`,
        `warning`, `refusal`, `incomplete`, `usage`) while the Responses SSE
        stream is consumed. Raises `CopilotRunCancelled` when `should_cancel`
        trips mid-stream. Returns the final result exactly like the
        synchronous path so persistence and replay stay identical.
        """
        input_items: list[dict[str, Any]] = [self._build_user_message(request, context)]
        tool_traces: list[CopilotToolTrace] = []
        tool_sources: dict[str, CopilotSourceRef] = {source.source_id: source for source in context.sources}
        warnings = list(context.warnings)
        reasoning_effort = self._resolve_reasoning_effort(request.reasoning_effort)

        def build_result(
            *,
            status: str,
            message: str | None = None,
            card: ResearchCard | None = None,
            model: str | None = None,
            response_id: str | None = None,
        ) -> CopilotResearchCardResult:
            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=context.current_tab,
                status=status,
                provider=self.provider_name,
                model=model or self.model,
                response_id=response_id,
                message=message,
                card=card,
                sources=list(tool_sources.values()),
                tool_traces=tool_traces,
                warnings=warnings,
            )

        for turn in range(5):
            payload = self._build_response_payload(
                request=request,
                context=context,
                input_items=input_items,
                reasoning_effort=reasoning_effort,
                tool_specs=tool_specs,
                tool_choice="auto",
                max_output_tokens=1400,
                prompt_cache_key=f"gamma-copilot:{request.domain}:research-card:v2",
            )
            payload["stream"] = True
            if turn == 0 and request.previous_response_id and self.store_responses:
                payload["previous_response_id"] = request.previous_response_id

            try:
                response, terminal = self._post_json_stream(payload, emit, should_cancel)
            except CopilotRunCancelled:
                raise
            except RuntimeError as exc:
                emit("provider.error", {"message": str(exc), "provider": self.provider_name})
                return build_result(status="error", message=str(exc))

            self._emit_usage(emit, response)

            if terminal == "incomplete":
                reason = str(
                    (response.get("incomplete_details") or {}).get("reason") or "incomplete"
                )
                emit("incomplete", {"reason": reason})
                return build_result(
                    status="incomplete",
                    message=f"OpenAI ended the response early: {reason}.",
                    model=str(response.get("model") or self.model),
                    response_id=str(response.get("id") or "") or None,
                )

            tool_calls = [item for item in response.get("output", []) if item.get("type") == "function_call"]
            if tool_calls:
                input_items.extend(self._continuation_output_items(response))
                for item in tool_calls:
                    if should_cancel():
                        raise CopilotRunCancelled()
                    tool_name = str(item.get("name") or "").strip()
                    arguments = self._parse_tool_arguments(item.get("arguments"))
                    emit("tool.call", {"tool_name": tool_name, "arguments": arguments})
                    execution = execute_tool(tool_name, arguments, context)
                    tool_traces.append(execution.trace)
                    for source in execution.sources:
                        tool_sources[source.source_id] = source
                    emit(
                        "tool.result",
                        {
                            "tool_name": tool_name,
                            "summary": execution.trace.summary,
                            "source_ids": list(execution.trace.source_ids),
                        },
                    )
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
                emit("refusal", {"message": refusal})
                return build_result(
                    status="refused",
                    message=refusal,
                    model=str(response.get("model") or self.model),
                    response_id=str(response.get("id") or "") or None,
                )

            try:
                card = self._parse_research_card(response)
            except RuntimeError as exc:
                if self._is_structured_card_parse_error(str(exc)):
                    emit(
                        "warning",
                        {"message": f"Structured research card parse failed; retrying once: {exc}"},
                    )
                    retry_result = self._retry_structured_research_card(
                        request=request,
                        context=context,
                        input_items=input_items,
                        reasoning_effort=reasoning_effort,
                        parse_error=str(exc),
                        tool_sources=tool_sources,
                        tool_traces=tool_traces,
                        warnings=warnings,
                    )
                    if retry_result is not None:
                        return retry_result
                return build_result(
                    status="error",
                    message=str(exc),
                    model=str(response.get("model") or self.model),
                    response_id=str(response.get("id") or "") or None,
                )

            return build_result(
                status="ready",
                card=card,
                model=str(response.get("model") or self.model),
                response_id=str(response.get("id") or "") or None,
            )

        return build_result(
            status="error",
            message="Copilot exceeded the allowed number of tool rounds.",
        )

    @staticmethod
    def _emit_usage(emit: RunEventEmitter, response: dict[str, Any]) -> None:
        usage = response.get("usage")
        if not isinstance(usage, dict):
            return
        emit(
            "usage",
            {
                key: usage.get(key)
                for key in ("input_tokens", "output_tokens", "total_tokens")
                if usage.get(key) is not None
            },
        )

    def _post_json_stream(
        self,
        payload: dict[str, Any],
        emit: RunEventEmitter,
        should_cancel: CancelCheck,
    ) -> tuple[dict[str, Any], str]:
        """Use the supported OpenAI SDK and consume typed Responses events.

        Returns `(final_response, terminal)` where terminal is `completed` or
        `incomplete`. Provider failures raise RuntimeError; cancellation
        raises CopilotRunCancelled between SSE lines.
        """
        try:
            stream = self._open_stream(payload)
        except (APIStatusError, APIConnectionError, APITimeoutError) as exc:
            raise RuntimeError(self._sdk_error_message(exc)) from exc

        try:
            return self._consume_response_stream(stream, emit, should_cancel)
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()

    def _open_stream(self, payload: dict[str, Any]):
        """Open a typed Responses stream. Overridable by provider tests."""
        return self._client.responses.create(**payload)

    def _consume_response_stream(
        self,
        stream: Any,
        emit: RunEventEmitter,
        should_cancel: CancelCheck,
    ) -> tuple[dict[str, Any], str]:
        for sdk_event in stream:
            if should_cancel():
                raise CopilotRunCancelled()
            parsed = self._sdk_to_dict(sdk_event)
            outcome = self._dispatch_response_event(parsed, emit)
            if outcome is not None:
                return outcome
        raise RuntimeError("OpenAI stream ended without a terminal response event.")

    @staticmethod
    def _dispatch_response_event(
        parsed: dict[str, Any],
        emit: RunEventEmitter,
    ) -> tuple[dict[str, Any], str] | None:
        event_type = str(parsed.get("type") or "")
        if event_type == "response.output_text.delta":
            delta = str(parsed.get("delta") or "")
            if delta:
                emit("text.delta", {"delta": delta})
            return None
        if event_type == "response.function_call_arguments.done":
            emit(
                "function.arguments",
                {
                    "item_id": parsed.get("item_id"),
                    "output_index": parsed.get("output_index"),
                    "arguments": parsed.get("arguments") or "{}",
                },
            )
            return None
        if event_type == "response.refusal.done":
            refusal = str(parsed.get("refusal") or "The model refused the request.")
            emit("refusal", {"message": refusal})
            return None
        if event_type == "response.completed":
            response = parsed.get("response")
            return (response if isinstance(response, dict) else {}, "completed")
        if event_type == "response.incomplete":
            response = parsed.get("response")
            return (response if isinstance(response, dict) else {}, "incomplete")
        if event_type == "response.failed":
            response = parsed.get("response")
            error = (response or {}).get("error") if isinstance(response, dict) else None
            message = (error or {}).get("message") if isinstance(error, dict) else None
            raise RuntimeError(f"OpenAI request failed: {message or 'response.failed'}")
        if event_type == "error":
            raise RuntimeError(f"OpenAI request failed: {parsed.get('message') or 'stream error'}")
        return None

    @staticmethod
    def _sdk_to_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            rendered = model_dump(mode="json")
            return rendered if isinstance(rendered, dict) else {}
        return {}

    @cached_property
    def _client(self) -> OpenAI:
        base_url = self.api_url.rstrip("/")
        if base_url.endswith("/responses"):
            base_url = base_url[: -len("/responses")]
        return OpenAI(
            api_key=self.api_key,
            base_url=base_url,
            timeout=self.timeout_seconds,
        )

    @staticmethod
    def _sdk_error_message(exc: Exception) -> str:
        if isinstance(exc, APITimeoutError):
            return "OpenAI request timed out."
        if isinstance(exc, APIConnectionError):
            return "OpenAI is currently unreachable."
        if isinstance(exc, APIStatusError):
            status = getattr(exc, "status_code", None)
            message = getattr(exc, "message", None) or str(exc)
            prefix = f"OpenAI request failed ({status})" if status else "OpenAI request failed"
            return f"{prefix}: {message}"
        return f"OpenAI request failed: {exc}"

    def _build_response_payload(
        self,
        *,
        request: CopilotResearchCardRequest,
        context: CopilotContextBundle,
        input_items: list[dict[str, Any]],
        reasoning_effort: str,
        tool_specs: list[dict[str, object]],
        tool_choice: str | None,
        max_output_tokens: int,
        prompt_cache_key: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "instructions": self._build_instructions(context),
            "input": input_items,
            "parallel_tool_calls": False,
            "max_output_tokens": max_output_tokens,
            "reasoning": {"effort": reasoning_effort},
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
            "prompt_cache_key": prompt_cache_key,
            "metadata": {
                "app": "gamma",
                "domain": request.domain,
                "current_tab": context.current_tab,
            },
        }
        if tool_specs:
            payload["tools"] = tool_specs
            payload["tool_choice"] = tool_choice or "auto"
        return payload

    def _retry_structured_research_card(
        self,
        *,
        request: CopilotResearchCardRequest,
        context: CopilotContextBundle,
        input_items: list[dict[str, Any]],
        reasoning_effort: str,
        parse_error: str,
        tool_sources: dict[str, CopilotSourceRef],
        tool_traces: list[CopilotToolTrace],
        warnings: list[str],
    ) -> CopilotResearchCardResult | None:
        retry_payload = self._build_response_payload(
            request=request,
            context=context,
            input_items=[*input_items, self._build_structured_retry_message(parse_error)],
            reasoning_effort=reasoning_effort,
            tool_specs=[],
            tool_choice=None,
            max_output_tokens=1200,
            prompt_cache_key=f"gamma-copilot:{request.domain}:research-card:v2:structured-retry",
        )
        try:
            retry_response = self._post_json(retry_payload)
        except RuntimeError as exc:
            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=context.current_tab,
                status="error",
                provider=self.provider_name,
                model=self.model,
                message=f"OpenAI structured-output retry failed: {exc}",
                sources=list(tool_sources.values()),
                tool_traces=tool_traces,
                warnings=warnings,
            )

        refusal = self._extract_refusal(retry_response)
        if refusal:
            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=context.current_tab,
                status="error",
                provider=self.provider_name,
                model=str(retry_response.get("model") or self.model),
                response_id=str(retry_response.get("id") or ""),
                message=refusal,
                sources=list(tool_sources.values()),
                tool_traces=tool_traces,
                warnings=warnings,
            )

        try:
            card = self._parse_research_card(retry_response)
        except RuntimeError as exc:
            if self._is_structured_card_parse_error(str(exc)):
                message = f"{str(exc).rstrip('.')} after one structured-output retry."
            else:
                message = str(exc)
            return CopilotResearchCardResult(
                domain=request.domain,
                current_tab=context.current_tab,
                status="error",
                provider=self.provider_name,
                model=str(retry_response.get("model") or self.model),
                response_id=str(retry_response.get("id") or ""),
                message=message,
                sources=list(tool_sources.values()),
                tool_traces=tool_traces,
                warnings=warnings,
            )

        return CopilotResearchCardResult(
            domain=request.domain,
            current_tab=context.current_tab,
            status="ready",
            provider=self.provider_name,
            model=str(retry_response.get("model") or self.model),
            response_id=str(retry_response.get("id") or ""),
            card=card,
            sources=list(tool_sources.values()),
            tool_traces=tool_traces,
            warnings=warnings,
        )

    @staticmethod
    def _is_structured_card_parse_error(message: str) -> bool:
        return message in STRUCTURED_CARD_PARSE_ERRORS

    @staticmethod
    def _build_structured_retry_message(parse_error: str) -> dict[str, Any]:
        return {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "The previous response could not be rendered by Gamma because "
                        f"{parse_error} Return exactly one schema-valid JSON research card. "
                        "Use only the supplied Gamma context, source ids, tool outputs, and warnings. "
                        "Do not include prose outside the JSON object."
                    ),
                }
            ],
        }

    def _build_user_message(
        self,
        request: CopilotResearchCardRequest,
        context: CopilotContextBundle,
    ) -> dict[str, Any]:
        default_prompt = {
            "portfolio": "Generate a concise research card for the active Gamma portfolio workspace.",
            "research": "Generate a concise research card for the active Gamma research scope.",
            "equity_research": "Generate a concise research card for the active Gamma equity research workspace.",
            "strategy_lab": "Generate a concise research card for the active Gamma strategy lab workspace.",
            "macro": "Generate a concise research card for the current Gamma macro workspace.",
            "prediction_markets": "Generate a concise research card for the selected Gamma prediction market.",
            "risk": "Generate a concise research card for the active Gamma risk workspace.",
            "iv": "Generate a concise research card for the active Gamma IV workspace.",
            "synthesis": "Generate a concise cross-context research synthesis for the selected Gamma domains.",
        }.get(request.domain, "Generate a concise research card for the current Gamma workspace.")
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
            "read_only_safety": context.read_only_safety,
        }
        return {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": self._json_dumps(body),
                }
            ],
        }

    def _resolve_reasoning_effort(self, request_effort: str | None) -> str:
        normalized = str(request_effort or "").strip().lower()
        if normalized in SUPPORTED_REASONING_EFFORTS:
            return normalized
        configured = str(self.reasoning_effort or "").strip().lower()
        return configured if configured in SUPPORTED_REASONING_EFFORTS else "medium"

    def _build_instructions(self, context: CopilotContextBundle) -> str:
        source_ids = ", ".join(source.source_id for source in context.sources) or "none"
        synthesis_clause = ""
        if context.domain == "synthesis":
            synthesis_clause = (
                "When the domain is `synthesis`, compare the included Gamma contexts explicitly and keep the output framed as a read-only research synthesis rather than a generic chat reply. "
            )
        strategy_lab_clause = ""
        if context.domain in {"strategy_lab", "synthesis"}:
            strategy_lab_clause = (
                "When Strategy Lab handoff context is present, state whether each item is pending, resolved, unsupported, errored, or stale; cite resolved handoff source ids as evidence and treat pending handoffs as unresolved user intent. "
            )
        return (
            "You are Gamma Copilot inside a read-only research application. "
            "Stay anchored to the supplied Gamma workspace state and Gamma-owned tools. "
            "Do not imply that you executed trades, changed app state, or retrieved external data. "
            "Use tools only when the current context is insufficient. "
            "Every source-backed claim must cite one or more `source_id` values from the available sources or tool outputs. "
            "Anything that extends beyond explicit source evidence belongs in `inferred_claims` or `caveats`. "
            f"{synthesis_clause}"
            f"{strategy_lab_clause}"
            "Keep the card analytical, concise, and research-oriented. "
            f"Initial source ids: {source_ids}."
        )

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.responses.create(**payload)
        except (APIStatusError, APIConnectionError, APITimeoutError) as exc:
            raise RuntimeError(self._sdk_error_message(exc)) from exc
        rendered = self._sdk_to_dict(response)
        if not rendered:
            raise RuntimeError("OpenAI returned an unreadable response payload.")
        return rendered

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
        return OpenAIResponsesCopilotProvider._json_dumps(output)

    def _continuation_output_items(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        output_items = response.get("output", [])
        # Reasoning items returned alongside function calls must be supplied on
        # the next Responses request, including when provider storage is off.
        return [
            dict(item)
            for item in output_items
            if isinstance(item, dict)
        ]

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
