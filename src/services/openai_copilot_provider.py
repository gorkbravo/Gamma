from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from functools import cached_property
from hashlib import sha256
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from src.models.copilot import (
    CopilotContextBundle,
    CopilotEquityEntityProposal,
    CopilotOperatorPlan,
    CopilotResearchCardRequest,
    CopilotResearchCardResult,
    CopilotSourceRef,
    CopilotToolTrace,
    CopilotUsageRecord,
    ResearchCard,
    ResearchClaim,
)
from src.services.copilot_provider import (
    CancelCheck,
    CopilotProvider,
    CopilotRunCancelled,
    OperatorToolExecutor,
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
MAX_OPERATOR_OBSERVATION_BYTES = 50_000
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

    def propose_equity_entity(
        self,
        *,
        request: CopilotResearchCardRequest,
    ) -> CopilotEquityEntityProposal:
        """Let the model propose one issuer, without granting identity authority.

        Gamma validates the returned ticker and issuer name against its SEC
        reference adapter before the proposal can enter an Operator context.
        """

        tool_name = "propose_equity_entity"
        payload: dict[str, Any] = {
            "model": (
                request.model_resolution.model
                if request.model_resolution is not None and request.model_resolution.model
                else self.model
            ),
            "instructions": (
                "Identify the one primary publicly listed company, if any, that "
                "the user wants Gamma to research. Use ordinary language knowledge "
                "to map company names or brands to a likely listed issuer and ticker. "
                "This is only a proposal: Gamma will validate it against SEC identity "
                "data. If there is no company, more than one intended company, or the "
                "request is genuinely ambiguous, return null identity fields. Return "
                "the legal issuer name rather than only a brand name when known."
            ),
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": self._json_dumps({"task": (request.prompt or "").strip()}),
                        }
                    ],
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "name": tool_name,
                    "description": "Propose one public-company identity for authoritative Gamma validation.",
                    "parameters": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "mention": {"type": ["string", "null"]},
                            "ticker": {"type": ["string", "null"]},
                            "issuer_name": {"type": ["string", "null"]},
                            "exchange": {"type": ["string", "null"]},
                            "confidence": {
                                "type": ["number", "null"],
                                "minimum": 0,
                                "maximum": 1,
                            },
                            "reason": {"type": "string"},
                        },
                        "required": [
                            "mention",
                            "ticker",
                            "issuer_name",
                            "exchange",
                            "confidence",
                            "reason",
                        ],
                    },
                    "strict": True,
                }
            ],
            "tool_choice": {"type": "function", "name": tool_name},
            "parallel_tool_calls": False,
            "max_output_tokens": 260,
            "reasoning": {"effort": self._resolve_reasoning_effort(request.reasoning_effort)},
            "store": self._store_responses(request),
            "safety_identifier": self._safety_identifier(request),
            "prompt_cache_key": "gamma-copilot:entity-resolution:v1",
            "metadata": {
                "app": "gamma",
                "role": "entity_resolution",
                "operator_contract": "copilot.entity-resolution.v1",
            },
        }
        response = self._post_json(payload)
        usage = replace(self._usage_from_response(response), provider_calls=1, tool_calls=0)
        call = next(
            (
                item
                for item in response.get("output", [])
                if item.get("type") == "function_call" and item.get("name") == tool_name
            ),
            None,
        )
        arguments = self._parse_tool_arguments(call.get("arguments") if call else None)
        confidence = arguments.get("confidence")
        return CopilotEquityEntityProposal(
            mention=self._optional_text(arguments.get("mention")),
            ticker=self._optional_text(arguments.get("ticker")),
            issuer_name=self._optional_text(arguments.get("issuer_name")),
            exchange=self._optional_text(arguments.get("exchange")),
            confidence=(
                max(0.0, min(1.0, float(confidence)))
                if isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
                else None
            ),
            reason=self._optional_text(arguments.get("reason")),
            provider=self.provider_name,
            model=str(response.get("model") or self.model),
            usage=usage,
        )

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
        usage = CopilotUsageRecord(provider_calls=0, tool_calls=0)

        def with_usage(result: CopilotResearchCardResult) -> CopilotResearchCardResult:
            combined = self._merge_usage_records(usage, result.usage)
            return replace(
                result,
                usage=replace(combined, tool_calls=len(tool_traces)),
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
            if turn == 0 and request.previous_response_id and self._store_responses(request):
                payload["previous_response_id"] = request.previous_response_id

            try:
                usage = replace(
                    usage,
                    provider_calls=(usage.provider_calls or 0) + 1,
                )
                response = self._post_json(payload)
            except RuntimeError as exc:
                return with_usage(CopilotResearchCardResult(
                    domain=request.domain,
                    current_tab=context.current_tab,
                    status="error",
                    provider=self.provider_name,
                    model=self.model,
                    message=str(exc),
                    sources=list(tool_sources.values()),
                    tool_traces=tool_traces,
                    warnings=warnings + self._turn_failure_warnings(turn, input_items, tool_traces),
                ))
            usage = self._merge_usage_records(
                usage,
                self._usage_from_response(response),
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
                return with_usage(CopilotResearchCardResult(
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
                ))

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
                        return with_usage(retry_result)
                return with_usage(CopilotResearchCardResult(
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
                ))

            return with_usage(CopilotResearchCardResult(
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
            ))

        return with_usage(CopilotResearchCardResult(
            domain=request.domain,
            current_tab=context.current_tab,
            status="error",
            provider=self.provider_name,
            model=self.model,
            message="Copilot exceeded the allowed number of tool rounds.",
            sources=list(tool_sources.values()),
            tool_traces=tool_traces,
            warnings=warnings,
        ))

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
        usage = CopilotUsageRecord(provider_calls=0, tool_calls=0)

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
                usage=replace(usage, tool_calls=len(tool_traces)),
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
            if turn == 0 and request.previous_response_id and self._store_responses(request):
                payload["previous_response_id"] = request.previous_response_id

            try:
                usage = replace(
                    usage,
                    provider_calls=(usage.provider_calls or 0) + 1,
                )
                response, terminal = self._post_json_stream(payload, emit, should_cancel)
            except CopilotRunCancelled:
                raise
            except RuntimeError as exc:
                warnings.extend(self._turn_failure_warnings(turn, input_items, tool_traces))
                emit("provider.error", {"message": str(exc), "provider": self.provider_name, "turn": turn + 1})
                return build_result(status="error", message=str(exc))

            self._emit_usage(emit, response)
            usage = self._merge_usage_records(
                usage,
                self._usage_from_response(response),
            )

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
                        return replace(
                            retry_result,
                            usage=self._merge_usage_records(usage, retry_result.usage),
                        )
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

    def stream_research_operator(
        self,
        *,
        request: CopilotResearchCardRequest,
        plan: CopilotOperatorPlan,
        tool_specs: list[dict[str, object]],
        execute_tool: OperatorToolExecutor,
        emit: RunEventEmitter,
        should_cancel: CancelCheck,
    ) -> CopilotResearchCardResult:
        """Run the custom Responses-based closed-loop Research Operator.

        The model selects one strict Gamma action at a time, receives the
        validated execution result as an observation, and owns the final
        schema-valid synthesis. Gamma still owns authorization, validation,
        execution, budgets, persistence, and cancellation.
        """

        context = CopilotContextBundle(
            domain="synthesis",
            current_tab=request.context.current_tab or "copilot",
            summary_data={
                "operator_intent": plan.intent,
                "depth_profile": plan.depth_profile,
                "target_entities": [
                    {
                        "kind": entity.kind,
                        "id": entity.id,
                        "label": entity.label,
                        "confidence": entity.confidence,
                    }
                    for entity in plan.target_entities
                ],
                "allowed_actions": [
                    {
                        "step_id": step.step_id,
                        "tool_id": step.tool_id,
                        "domain": step.domain,
                        "action_type": step.action_type,
                        "rationale": step.rationale,
                        "stop_conditions": list(step.stop_conditions),
                    }
                    for step in plan.steps
                    if step.tool_id
                    and step.action_type
                    in {"read_context", "run_analysis", "fetch_external_context"}
                    and not step.requires_confirmation
                ],
                "budgets": {
                    "max_tool_calls": plan.max_tool_calls,
                    "max_provider_calls": plan.max_provider_calls,
                    "max_elapsed_ms": plan.max_elapsed_ms,
                },
                "confirmation_checkpoints": [
                    {
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "after_step_id": checkpoint.after_step_id,
                        "reason": checkpoint.reason,
                        "required_for_tool_ids": list(
                            checkpoint.required_for_tool_ids
                        ),
                    }
                    for checkpoint in plan.confirmation_checkpoints
                ],
            },
            warnings=list(plan.warnings),
        )
        input_items: list[dict[str, Any]] = [
            self._build_operator_user_message(request, plan)
        ]
        tool_traces: list[CopilotToolTrace] = []
        tool_sources: dict[str, CopilotSourceRef] = {}
        warnings = list(plan.warnings)
        reasoning_effort = self._resolve_reasoning_effort(request.reasoning_effort)
        usage = CopilotUsageRecord(provider_calls=0, tool_calls=0)
        max_model_turns = min(10, max(2, plan.max_tool_calls + 2))
        instructions = self._build_operator_instructions(plan)

        def build_result(
            *,
            status: str,
            message: str | None = None,
            card: ResearchCard | None = None,
            model: str | None = None,
            response_id: str | None = None,
        ) -> CopilotResearchCardResult:
            return CopilotResearchCardResult(
                domain="synthesis",
                current_tab=context.current_tab,
                status=status,
                provider=f"{self.provider_name}_operator",
                model=model or self.model,
                response_id=response_id,
                message=message,
                card=card,
                sources=list(tool_sources.values()),
                tool_traces=tool_traces,
                warnings=warnings,
                usage=replace(usage, tool_calls=len(tool_traces)),
            )

        for turn in range(max_model_turns):
            if should_cancel():
                raise CopilotRunCancelled()
            payload = self._build_response_payload(
                request=request,
                context=context,
                input_items=input_items,
                reasoning_effort=reasoning_effort,
                tool_specs=tool_specs,
                tool_choice="auto",
                max_output_tokens=1600,
                prompt_cache_key="gamma-copilot:operator:closed-loop:v1",
                instructions_override=instructions,
                metadata_override={
                    "role": "research_operator",
                    "operator_contract": "copilot.operator.loop.v1",
                },
            )
            payload["stream"] = True

            try:
                usage = replace(
                    usage,
                    provider_calls=(usage.provider_calls or 0) + 1,
                )
                response, terminal = self._post_json_stream(
                    payload,
                    emit,
                    should_cancel,
                )
            except CopilotRunCancelled:
                raise
            except RuntimeError as exc:
                emit(
                    "provider.error",
                    {"message": str(exc), "provider": self.provider_name},
                )
                return build_result(status="error", message=str(exc))

            self._emit_usage(emit, response)
            usage = self._merge_usage_records(
                usage,
                self._usage_from_response(response),
            )

            if terminal == "incomplete":
                reason = str(
                    (response.get("incomplete_details") or {}).get("reason")
                    or "incomplete"
                )
                emit("incomplete", {"reason": reason})
                return build_result(
                    status="incomplete",
                    message=f"OpenAI ended the Operator response early: {reason}.",
                    model=str(response.get("model") or self.model),
                    response_id=str(response.get("id") or "") or None,
                )

            tool_calls = [
                item
                for item in response.get("output", [])
                if item.get("type") == "function_call"
            ]
            if tool_calls:
                input_items.extend(self._continuation_output_items(response))
                for item in tool_calls:
                    if should_cancel():
                        raise CopilotRunCancelled()
                    tool_name = str(item.get("name") or "").strip()
                    arguments = self._parse_operator_tool_arguments(
                        item.get("arguments")
                    )
                    emit(
                        "tool.call",
                        {
                            "tool_name": tool_name,
                            "arguments": arguments,
                            "decision_index": turn + 1,
                        },
                    )
                    execution = execute_tool(tool_name, arguments)
                    tool_traces.append(execution.trace)
                    for source in execution.sources:
                        tool_sources[source.source_id] = source
                    observation = {
                        "status": (
                            "failed"
                            if isinstance(execution.output, dict)
                            and execution.output.get("error")
                            else "completed"
                        ),
                        "tool_id": tool_name,
                        "arguments": execution.trace.arguments,
                        "trace_summary": execution.trace.summary,
                        "source_ids": list(execution.trace.source_ids),
                        "output": self._bounded_operator_observation(
                            execution.output
                        ),
                    }
                    emit(
                        "tool.result",
                        {
                            "tool_name": tool_name,
                            "summary": execution.trace.summary,
                            "source_ids": list(execution.trace.source_ids),
                            "decision_index": turn + 1,
                            "observation_status": observation["status"],
                        },
                    )
                    input_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": item.get("call_id"),
                            "output": self._format_tool_output(observation),
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
                self._validate_operator_final_card(card)
            except RuntimeError as exc:
                emit(
                    "warning",
                    {
                        "message": (
                            "Operator final synthesis was not schema-valid: "
                            f"{exc}"
                        )
                    },
                )
                return build_result(
                    status="ready",
                    message=str(exc),
                    model=str(response.get("model") or self.model),
                    response_id=str(response.get("id") or "") or None,
                )

            return build_result(
                status="ready",
                message=(
                    "Research Operator synthesized the requested conclusion from "
                    f"{len(tool_traces)} validated tool observation(s)."
                ),
                card=card,
                model=str(response.get("model") or self.model),
                response_id=str(response.get("id") or "") or None,
            )

        message = (
            "Research Operator exhausted its model-turn budget before producing "
            "a final synthesis."
        )
        emit("incomplete", {"reason": "model_turn_budget_exhausted"})
        return build_result(status="incomplete", message=message)

    @staticmethod
    def _emit_usage(emit: RunEventEmitter, response: dict[str, Any]) -> None:
        usage = OpenAIResponsesCopilotProvider._usage_from_response(response)
        payload = {
            key: value
            for key, value in usage.__dict__.items()
            if key != "raw" and value is not None
        }
        if not payload:
            return
        emit("usage", payload)

    @staticmethod
    def _usage_from_response(response: dict[str, Any]) -> CopilotUsageRecord:
        usage = response.get("usage")
        if not isinstance(usage, dict):
            return CopilotUsageRecord()
        input_details = usage.get("input_tokens_details")
        input_details = input_details if isinstance(input_details, dict) else {}
        output_details = usage.get("output_tokens_details")
        output_details = output_details if isinstance(output_details, dict) else {}
        return CopilotUsageRecord(
            input_tokens=OpenAIResponsesCopilotProvider._optional_usage_int(
                usage.get("input_tokens")
            ),
            output_tokens=OpenAIResponsesCopilotProvider._optional_usage_int(
                usage.get("output_tokens")
            ),
            reasoning_tokens=OpenAIResponsesCopilotProvider._optional_usage_int(
                output_details.get("reasoning_tokens")
            ),
            total_tokens=OpenAIResponsesCopilotProvider._optional_usage_int(
                usage.get("total_tokens")
            ),
            cache_read_tokens=OpenAIResponsesCopilotProvider._optional_usage_int(
                input_details.get("cached_tokens")
            ),
            cache_write_tokens=OpenAIResponsesCopilotProvider._optional_usage_int(
                usage.get("cache_write_tokens")
                if usage.get("cache_write_tokens") is not None
                else input_details.get("cache_write_tokens")
            ),
        )

    @staticmethod
    def _optional_usage_int(value: Any) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _merge_usage_records(
        first: CopilotUsageRecord,
        second: CopilotUsageRecord,
    ) -> CopilotUsageRecord:
        def merged(field_name: str) -> int | None:
            left = getattr(first, field_name)
            right = getattr(second, field_name)
            if left is None and right is None:
                return None
            return int(left or 0) + int(right or 0)

        return CopilotUsageRecord(
            input_tokens=merged("input_tokens"),
            output_tokens=merged("output_tokens"),
            reasoning_tokens=merged("reasoning_tokens"),
            total_tokens=merged("total_tokens"),
            cache_read_tokens=merged("cache_read_tokens"),
            cache_write_tokens=merged("cache_write_tokens"),
            provider_calls=merged("provider_calls"),
            tool_calls=merged("tool_calls"),
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
        """Render a provider failure with the fields that identify its cause.

        A bare status and prose left a 4xx on a tool continuation undiagnosable
        (GUA-20260903-2): `param` names the exact rejected input item and `code`
        names the rule it broke, which is what separates a malformed replayed
        item from a model or account problem. All three fields are provider
        metadata, not prompt content.
        """
        if isinstance(exc, APITimeoutError):
            return "OpenAI request timed out."
        if isinstance(exc, APIConnectionError):
            return "OpenAI is currently unreachable."
        if isinstance(exc, APIStatusError):
            status = getattr(exc, "status_code", None)
            message = getattr(exc, "message", None) or str(exc)
            prefix = f"OpenAI request failed ({status})" if status else "OpenAI request failed"
            details = []
            for label, attribute in (("code", "code"), ("param", "param"), ("request_id", "request_id")):
                value = getattr(exc, attribute, None)
                text = str(value).strip() if value is not None else ""
                if text and text.lower() != "none":
                    details.append(f"{label}={text}")
            suffix = f" [{', '.join(details)}]" if details else ""
            return f"{prefix}: {message}{suffix}"
        return f"OpenAI request failed: {exc}"

    @staticmethod
    def _turn_failure_warnings(
        turn: int,
        input_items: list[dict[str, Any]],
        tool_traces: list[CopilotToolTrace],
    ) -> list[str]:
        """Say where in the exchange a provider call died.

        A failure on the first call and a failure while replaying tool output are
        different problems with different fixes, and the audit could not tell them
        apart from the rendered error (GUA-20260903-2).
        """
        if turn <= 0:
            return []
        replayed = sum(1 for item in input_items if isinstance(item, dict) and item.get("type") == "function_call_output")
        tool_names = ", ".join(trace.tool_name for trace in tool_traces[-3:]) or "none"
        return [
            f"The provider call failed while continuing after tool output (turn {turn + 1}, "
            f"{len(input_items)} replayed input items, {replayed} tool results, recent tools: {tool_names}). "
            "The initial request succeeded, so the failure is in the continuation, not the prompt."
        ]

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
        instructions_override: str | None = None,
        metadata_override: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": (
                request.model_resolution.model
                if request.model_resolution is not None and request.model_resolution.model
                else self.model
            ),
            "instructions": instructions_override or self._build_instructions(context),
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
            "store": self._store_responses(request),
            "safety_identifier": self._safety_identifier(request),
            "prompt_cache_key": prompt_cache_key,
            "metadata": {
                "app": "gamma",
                "domain": request.domain,
                "current_tab": context.current_tab,
                **(metadata_override or {}),
            },
        }
        if tool_specs:
            payload["tools"] = tool_specs
            payload["tool_choice"] = tool_choice or "auto"
        return payload

    def _build_operator_user_message(
        self,
        request: CopilotResearchCardRequest,
        plan: CopilotOperatorPlan,
    ) -> dict[str, Any]:
        body = {
            "task": (request.prompt or "").strip(),
            "operator_plan": {
                "intent": plan.intent,
                "depth_profile": plan.depth_profile,
                "target_entities": [
                    {
                        "kind": entity.kind,
                        "id": entity.id,
                        "label": entity.label,
                    }
                    for entity in plan.target_entities
                ],
                "steps": [
                    {
                        "step_id": step.step_id,
                        "tool_id": step.tool_id,
                        "domain": step.domain,
                        "rationale": step.rationale,
                        "stop_conditions": list(step.stop_conditions),
                    }
                    for step in plan.steps
                    if step.tool_id
                ],
                "budgets": {
                    "max_tool_calls": plan.max_tool_calls,
                    "max_provider_calls": plan.max_provider_calls,
                    "max_elapsed_ms": plan.max_elapsed_ms,
                },
            },
            "parameter_contract": (
                "Preserve every explicit user entity, leg, weight, shock, date, "
                "horizon, assumption, and comparison target in strict tool "
                "arguments. If a required value is missing, stop or ask for it; "
                "do not substitute an unrelated default."
            ),
            "completion_contract": (
                "After inspecting tool observations, return one research card "
                "that directly answers the task from those outputs. A tool-count "
                "summary is not a successful answer."
            ),
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

    @staticmethod
    def _build_operator_instructions(plan: CopilotOperatorPlan) -> str:
        allowed = ", ".join(
            step.tool_id
            for step in plan.steps
            if step.tool_id
            and step.action_type
            in {"read_context", "run_analysis", "fetch_external_context", "draft_change"}
            and not step.requires_confirmation
        ) or "none"
        return (
            "You are Gamma's Research Operator inside a read-only research "
            "application. Use only the supplied strict Gamma function tools. "
            f"Allowed actions for this run: {allowed}. "
            "Treat every tool result as an observation: inspect it before choosing "
            "the next action, revising parameters, stopping for insufficient "
            "evidence, or finishing. Preserve explicit user parameters exactly "
            "through the tool schemas; never replace them with unrelated defaults. "
            "Gamma validates permissions and arguments and may return a validation "
            "or budget error as an observation. Do not bypass it or invent a tool. "
            "Never place trades, rebalance, mutate accounts or wallets, invoke shell, "
            "install packages, access a runtime network, or apply durable local changes. "
            "The two strategy_lab Research Script actions are the only authorized code-workflow "
            "surface: draft only when the current turn explicitly requests Script authoring, and "
            "run only when it explicitly requests execution with exact immutable ids and hashes. "
            "Your final schema-valid research card must directly answer the user's "
            "goal from actual tool outputs, distinguish evidence from inference, "
            "cite only source_id values returned by tools, retain warnings and "
            "missing-data limits, cite relevant Script/revision/run identities, never claim a "
            "failed, timed-out, unavailable, or incomplete Script run succeeded, and never end "
            "with only a generic count of steps."
        )

    def _store_responses(self, request: CopilotResearchCardRequest) -> bool:
        if request.model_resolution is not None:
            return request.model_resolution.provider_storage.effective == "enabled"
        return self.store_responses

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
                usage=CopilotUsageRecord(
                    provider_calls=1,
                    tool_calls=len(tool_traces),
                ),
            )
        retry_usage = replace(
            self._usage_from_response(retry_response),
            provider_calls=1,
            tool_calls=len(tool_traces),
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
                usage=retry_usage,
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
                usage=retry_usage,
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
            usage=retry_usage,
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
            "commodities": "Generate a concise research card for the active Gamma commodities workspace.",
            "maritime": "Generate a concise research card for the active Gamma Sealanes workspace.",
            "external_context": "Generate a concise research card from the approved item-level news context.",
            "synthesis": "Generate a concise cross-context research synthesis for the selected Gamma domains.",
        }.get(request.domain, "Generate a concise research card for the current Gamma workspace.")
        requested_prompt = (request.prompt or "").strip() or default_prompt
        body = {
            "task": requested_prompt,
            "local_continuation": [
                {
                    "turn_id": turn.turn_id,
                    "role": turn.role,
                    "user_request": turn.prompt,
                    "assistant_result": turn.assistant_result,
                }
                for turn in request.local_continuation[-8:]
            ],
            "domain": request.domain,
            "current_tab": context.current_tab,
            "workspace_context": context.summary_data,
            "available_source_refs": [
                {
                    "source_id": source.source_id,
                    "label": source.label,
                    "kind": source.kind,
                    "provider": source.provider,
                    "provider_native_id": source.provider_native_id,
                    "url": source.url,
                    "navigation_supported": source.navigation_supported,
                    "navigation_reason": source.navigation_reason,
                }
                for source in context.sources
            ],
            "warnings": context.warnings,
            "read_only_safety": context.read_only_safety,
            "context_contract": (
                context.context_contract.to_dict()
                if context.context_contract is not None
                else None
            ),
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
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _parse_operator_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
        """Preserve malformed model arguments as a validation failure.

        The general research-card path historically treated malformed JSON as an
        empty object. The Operator must not silently convert malformed output
        into plausible defaults, including for actions whose valid schema is an
        empty object, so it sends an impossible marker to Gamma's authoritative
        registry boundary instead.
        """

        if isinstance(raw_arguments, dict):
            return dict(raw_arguments)
        text = str(raw_arguments or "").strip()
        if text:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return parsed
        return {
            "__gamma_invalid_tool_arguments_json__": (
                text[:1_000] if text else "<empty>"
            )
        }

    @classmethod
    def _bounded_operator_observation(cls, output: Any) -> Any:
        rendered = cls._json_dumps(output)
        if len(rendered.encode("utf-8")) <= MAX_OPERATOR_OBSERVATION_BYTES:
            return output
        return {
            "truncated": True,
            "summary": cls._compact_operator_value(output),
            "warning": (
                "Gamma bounded this observation before returning it to the "
                "Operator model; the complete output remains in the local trace."
            ),
        }

    @classmethod
    def _compact_operator_value(
        cls,
        value: Any,
        *,
        depth: int = 0,
    ) -> Any:
        if depth >= 3:
            return f"<{type(value).__name__}>"
        if isinstance(value, dict):
            items = list(value.items())
            compact = {
                str(key): cls._compact_operator_value(
                    nested,
                    depth=depth + 1,
                )
                for key, nested in items[:24]
            }
            if len(items) > 24:
                compact["_omitted_key_count"] = len(items) - 24
            return compact
        if isinstance(value, list):
            compact_rows = [
                cls._compact_operator_value(item, depth=depth + 1)
                for item in value[:12]
            ]
            if len(value) > 12:
                compact_rows.append(
                    {"_omitted_item_count": len(value) - 12}
                )
            return compact_rows
        if isinstance(value, str) and len(value) > 1_000:
            return f"{value[:1_000]}…"
        return value

    @staticmethod
    def _validate_operator_final_card(card: ResearchCard) -> None:
        required_text = {
            "title": card.title,
            "hypothesis": card.hypothesis,
            "rationale": card.rationale,
            "proposed_test": card.proposed_test,
        }
        missing = [
            field_name
            for field_name, value in required_text.items()
            if not str(value or "").strip()
        ]
        if missing:
            raise RuntimeError(
                "OpenAI Operator final synthesis is missing substantive field(s): "
                f"{', '.join(missing)}."
            )
        rationale = str(card.rationale or "").strip()
        if re.fullmatch(
            r"(?:the\s+)?(?:research\s+)?operator\s+executed\s+\d+\s+"
            r"(?:validated\s+)?tools?(?:\s+successfully)?\.?",
            rationale,
            flags=re.IGNORECASE,
        ):
            raise RuntimeError(
                "OpenAI Operator final synthesis was only a generic tool-count summary."
            )

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
