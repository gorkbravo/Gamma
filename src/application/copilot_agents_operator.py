from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from time import perf_counter
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from src.application.copilot_context_helpers import dedupe_warnings
from src.application.copilot_model_policy import OPENAI_BASELINE_MODEL
from src.application.research_action_registry import (
    ResearchActionArgumentError,
    ResearchActionPermissionError,
    ResearchActionRegistry,
)
from src.models.copilot import (
    CopilotContextBundle,
    CopilotOperatorPlan,
    CopilotOperatorPlanStep,
    CopilotOperatorProgressEvent,
    CopilotResearchCardRequest,
    CopilotResearchCardResult,
    CopilotSourceRef,
    CopilotToolExecution,
    CopilotToolTrace,
    CopilotUsageRecord,
    ResearchCard,
    ResearchClaim,
    new_copilot_id,
)
from src.utils.time import now_utc

MAX_OPERATOR_FINAL_OUTPUT_BYTES = 50_000
SUPPORTED_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}


ContextBuilder = Callable[[str], CopilotContextBundle]
DefaultArgumentBuilder = Callable[[str, CopilotContextBundle], dict[str, Any] | None]
RegisteredActionExecutor = Callable[[str, dict[str, Any], CopilotContextBundle], CopilotToolExecution]
OperatorEventEmitter = Callable[[CopilotOperatorProgressEvent], None]
CancellationCheck = Callable[[], bool]
CardBuilder = Callable[
    [CopilotOperatorPlan, list[str], list[str], list[CopilotSourceRef], list[str]],
    ResearchCard,
]


@dataclass(frozen=True)
class _AgentsSdkModule:
    Agent: Any
    Runner: Any
    function_tool: Any
    ModelSettings: Any | None = None
    FunctionTool: Any | None = None


def _load_agents_sdk() -> _AgentsSdkModule:
    from agents import Agent, FunctionTool, ModelSettings, Runner, function_tool

    return _AgentsSdkModule(
        Agent=Agent,
        Runner=Runner,
        function_tool=function_tool,
        ModelSettings=ModelSettings,
        FunctionTool=FunctionTool,
    )


class _OperatorClaimOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    evidence_refs: list[str] = Field(default_factory=list)


class _OperatorFinalOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    hypothesis: str
    rationale: str
    required_data: list[str] = Field(default_factory=list)
    proposed_test: str = ""
    confounders: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    source_backed_claims: list[_OperatorClaimOutput] = Field(default_factory=list)
    inferred_claims: list[str] = Field(default_factory=list)
    stop_reason: str = "final_answer"


def _parse_positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        return default
    return max(1, value)


@dataclass(frozen=True)
class CopilotAgentsOperatorConfig:
    orchestrator: str = "custom"
    model: str = OPENAI_BASELINE_MODEL
    reasoning_effort: str | None = "low"
    verbosity: str | None = "low"
    include_usage: bool = True
    max_turns: int = 8

    @property
    def enabled(self) -> bool:
        return self.orchestrator in {"agents_sdk", "openai_agents_sdk"}

    @classmethod
    def from_env(cls) -> "CopilotAgentsOperatorConfig":
        return cls(
            orchestrator=(os.getenv("GAMMA_COPILOT_OPERATOR_ORCHESTRATOR", "custom") or "custom")
            .strip()
            .lower(),
            model=(
                os.getenv("GAMMA_COPILOT_OPERATOR_AGENTS_MODEL")
                or OPENAI_BASELINE_MODEL
            ).strip(),
            reasoning_effort=(
                os.getenv("GAMMA_COPILOT_OPERATOR_AGENTS_REASONING_EFFORT")
                or "low"
            ).strip()
            or None,
            verbosity=(
                os.getenv("GAMMA_COPILOT_OPERATOR_AGENTS_VERBOSITY")
                or "low"
            ).strip()
            or None,
            include_usage=(os.getenv("GAMMA_COPILOT_OPERATOR_AGENTS_INCLUDE_USAGE", "true") or "true")
            .strip()
            .lower()
            in {"1", "true", "yes", "on"},
            max_turns=_parse_positive_int_env("GAMMA_COPILOT_OPERATOR_AGENTS_MAX_TURNS", 8),
        )


class CopilotAgentsOperatorService:
    """Agents SDK-backed Research Operator orchestration over Gamma's action registry."""

    provider_name = "openai_agents_sdk_operator"

    def __init__(self, config: CopilotAgentsOperatorConfig | None = None) -> None:
        self.config = config or CopilotAgentsOperatorConfig.from_env()

    def execute(
        self,
        *,
        request: CopilotResearchCardRequest,
        plan: CopilotOperatorPlan,
        action_registry: ResearchActionRegistry,
        build_context: ContextBuilder,
        default_arguments: DefaultArgumentBuilder,
        execute_action: RegisteredActionExecutor,
        build_card: CardBuilder,
        run_id: str | None = None,
        emit_event: OperatorEventEmitter | None = None,
        should_cancel: CancellationCheck | None = None,
    ) -> CopilotResearchCardResult:
        run_id = str(run_id or "").strip() or new_copilot_id("oprun")
        response_id = new_copilot_id("opexec")
        events: list[CopilotOperatorProgressEvent] = []
        sources: dict[str, CopilotSourceRef] = {}
        tool_traces: list[CopilotToolTrace] = []
        warnings: list[str] = [
            warning
            for warning in plan.warnings
            if not warning.startswith("Planner-only prototype")
        ]
        executed_steps: list[str] = []
        skipped_steps: list[str] = []
        failed_steps: list[str] = []
        outputs: dict[str, Any] = {}
        output_summaries: dict[str, Any] = {}
        remaining_tool_calls = plan.max_tool_calls
        provider_calls_used = 0
        tool_call_counts: dict[str, int] = {}
        operator_started_at = perf_counter()
        boundary_stop_reason: str | None = None
        sdk_duration_ms: int | None = None
        model_usage: dict[str, Any] = {}
        cancelled_at_boundary = False
        provider_progress_count = 0
        final_card: ResearchCard | None = None
        final_stop_reason: str | None = None
        synthesis_error: str | None = None

        def record_event(
            event_type: str,
            *,
            step: CopilotOperatorPlanStep | None = None,
            title: str | None = None,
            message: str | None = None,
            payload: dict[str, Any] | None = None,
            source_ids: list[str] | None = None,
            event_warnings: list[str] | None = None,
        ) -> None:
            event = CopilotOperatorProgressEvent(
                    run_id=run_id,
                    event_id=new_copilot_id("opevent"),
                    sequence=len(events) + 1,
                    event_type=event_type,
                    timestamp=now_utc(),
                    step_id=step.step_id if step else None,
                    tool_id=step.tool_id if step else None,
                    title=title or (step.title if step else None),
                    message=message,
                    payload=payload or {},
                    source_ids=source_ids or [],
                    warnings=event_warnings or [],
                )
            events.append(event)
            if emit_event is not None:
                try:
                    emit_event(event)
                except Exception:
                    # Event delivery must not change operator authority or tool execution.
                    pass

        def record_warning(message: str, *, step: CopilotOperatorPlanStep | None = None) -> None:
            warnings.append(message)
            record_event("warning", step=step, title="Operator warning", message=message, event_warnings=[message])

        step_by_tool = {
            step.tool_id: step
            for step in plan.steps
            if step.tool_id
        }
        allowed_tool_ids = [
            step.tool_id
            for step in plan.steps
            if step.tool_id
            and step.action_type in {"read_context", "run_analysis", "fetch_external_context"}
            and not step.requires_confirmation
            and step.permission_policy != "confirmation_required"
        ]
        reasoning_effort = self._resolve_reasoning_effort(request.reasoning_effort)
        resolved_model = (
            request.model_resolution.model
            if request.model_resolution is not None and request.model_resolution.model
            else self.config.model
        )
        max_model_turns = min(
            self.config.max_turns,
            max(2, plan.max_tool_calls + 2),
        )

        record_event(
            "plan",
            title="Agents SDK operator plan",
            message=f"Prepared {len(plan.steps)} Research Operator step(s) for Agents SDK orchestration.",
            payload={
                "intent": plan.intent,
                "role": plan.role,
                "depth_profile": plan.depth_profile,
                "step_count": len(plan.steps),
                "checkpoint_count": len(plan.confirmation_checkpoints),
                "max_tool_calls": plan.max_tool_calls,
                "max_provider_calls": plan.max_provider_calls,
                "max_elapsed_ms": plan.max_elapsed_ms,
                "max_model_turns": max_model_turns,
                "orchestrator": self.provider_name,
                "operator_contract": "copilot.operator.loop.v1",
                "model": resolved_model,
                "reasoning_effort": reasoning_effort,
                "allowed_tool_ids": list(allowed_tool_ids),
            },
        )
        for warning in warnings:
            record_event("warning", title="Plan warning", message=warning, event_warnings=[warning])

        if not allowed_tool_ids and not plan.confirmation_checkpoints:
            record_warning("Agents SDK operator path found no automatic read-only registry actions to run.")
        if not (os.getenv("OPENAI_API_KEY", "") or "").strip():
            record_warning("Agents SDK operator path is unavailable until OPENAI_API_KEY is configured.")
            return self._finalize_result(
                request=request,
                plan=plan,
                response_id=response_id,
                events=events,
                sources=sources,
                tool_traces=tool_traces,
                warnings=warnings,
                executed_steps=executed_steps,
                skipped_steps=skipped_steps,
                failed_steps=failed_steps,
                build_card=build_card,
                status="error",
                reasoning_effort=reasoning_effort,
                emit_event=emit_event,
            )

        try:
            sdk = _load_agents_sdk()
        except Exception as exc:
            record_warning(f"Agents SDK operator path is unavailable: {exc.__class__.__name__}: {exc}")
            return self._finalize_result(
                request=request,
                plan=plan,
                response_id=response_id,
                events=events,
                sources=sources,
                tool_traces=tool_traces,
                warnings=warnings,
                executed_steps=executed_steps,
                skipped_steps=skipped_steps,
                failed_steps=failed_steps,
                build_card=build_card,
                status="error",
                reasoning_effort=reasoning_effort,
                emit_event=emit_event,
            )

        def execute_registered_action(
            tool_id: str,
            arguments: dict[str, Any],
        ) -> str:
            """Execute one strict, approved Gamma registry action."""
            nonlocal cancelled_at_boundary
            nonlocal boundary_stop_reason
            nonlocal provider_calls_used
            nonlocal remaining_tool_calls
            normalized_tool_id = str(tool_id or "").strip()
            step = step_by_tool.get(normalized_tool_id)
            if should_cancel is not None and should_cancel():
                cancelled_at_boundary = True
                message = (
                    "Research Operator cancellation took effect before the next "
                    "Agents SDK tool boundary."
                )
                record_warning(message, step=step)
                return self._json_dumps({"status": "cancelled", "warning": message})
            elapsed_ms = int((perf_counter() - operator_started_at) * 1000)
            if elapsed_ms >= plan.max_elapsed_ms:
                boundary_stop_reason = "elapsed_budget_exhausted"
                message = (
                    "Research Operator elapsed-time budget of "
                    f"{plan.max_elapsed_ms}ms is exhausted."
                )
                record_warning(message, step=step)
                record_event(
                    "tool-result",
                    step=step,
                    message=message,
                    payload={
                        "status": "elapsed_budget_exhausted",
                        "stop_reason": boundary_stop_reason,
                    },
                    event_warnings=[message],
                )
                return self._json_dumps(
                    {
                        "status": "elapsed_budget_exhausted",
                        "warning": message,
                        "stop_reason": boundary_stop_reason,
                    }
                )
            if step is None:
                message = f"Agents SDK requested an action outside the operator plan: `{normalized_tool_id}`."
                record_warning(message)
                return self._json_dumps({"status": "rejected", "warning": message})
            record_event(
                "step-start",
                step=step,
                message=f"Starting `{normalized_tool_id}` through the Agents SDK operator.",
                payload={
                    "order": step.order,
                    "domain": step.domain,
                    "action_type": step.action_type,
                    "permission_policy": step.permission_policy,
                    "orchestrator": self.provider_name,
                },
            )
            definition = action_registry.get(normalized_tool_id)
            if definition is None:
                skipped_steps.append(step.step_id)
                message = f"Skipped unsupported registry action `{normalized_tool_id}`."
                record_warning(message, step=step)
                record_event("tool-result", step=step, message=message, payload={"status": "skipped"})
                return self._json_dumps({"status": "skipped", "warning": message})
            if normalized_tool_id not in allowed_tool_ids:
                skipped_steps.append(step.step_id)
                message = f"Skipped `{normalized_tool_id}` because it is not an automatic read-only operator action."
                record_warning(message, step=step)
                record_event("tool-result", step=step, message=message, payload={"status": "skipped"})
                return self._json_dumps({"status": "skipped", "warning": message})
            if remaining_tool_calls <= 0:
                boundary_stop_reason = "tool_budget_exhausted"
                skipped_steps.append(step.step_id)
                message = f"Stopped operator execution after {plan.max_tool_calls} tools."
                record_warning(message, step=step)
                record_event(
                    "tool-result",
                    step=step,
                    message=message,
                    payload={
                        "status": "budget_exhausted",
                        "stop_reason": boundary_stop_reason,
                    },
                )
                return self._json_dumps(
                    {
                        "status": "budget_exhausted",
                        "warning": message,
                        "stop_reason": boundary_stop_reason,
                    }
                )
            remaining_tool_calls -= 1
            call_count = tool_call_counts.get(normalized_tool_id, 0) + 1
            tool_call_counts[normalized_tool_id] = call_count
            if call_count > definition.request_limit:
                boundary_stop_reason = "tool_request_limit_exhausted"
                skipped_steps.append(step.step_id)
                message = (
                    f"`{normalized_tool_id}` exceeded its per-run request limit "
                    f"of {definition.request_limit}."
                )
                record_warning(message, step=step)
                record_event(
                    "tool-result",
                    step=step,
                    message=message,
                    payload={
                        "status": "budget_exhausted",
                        "stop_reason": boundary_stop_reason,
                    },
                    event_warnings=[message],
                )
                return self._json_dumps(
                    {
                        "status": "budget_exhausted",
                        "warning": message,
                        "stop_reason": boundary_stop_reason,
                    }
                )
            if definition.external_provider:
                if provider_calls_used + 1 > plan.max_provider_calls:
                    boundary_stop_reason = "external_provider_budget_exhausted"
                    skipped_steps.append(step.step_id)
                    message = (
                        f"Skipped `{normalized_tool_id}` because provider calls would exceed the "
                        f"{plan.max_provider_calls} call guard."
                    )
                    record_warning(message, step=step)
                    record_event(
                        "tool-result",
                        step=step,
                        message=message,
                        payload={
                            "status": "budget_exhausted",
                            "stop_reason": boundary_stop_reason,
                        },
                    )
                    return self._json_dumps(
                        {
                            "status": "budget_exhausted",
                            "warning": message,
                            "stop_reason": boundary_stop_reason,
                        }
                    )
                provider_calls_used += 1

            try:
                context = build_context(step.domain)
            except ValueError as exc:
                skipped_steps.append(step.step_id)
                message = f"Skipped {step.step_id}: {exc}"
                record_warning(message, step=step)
                record_event("tool-result", step=step, message=message, payload={"status": "skipped"})
                return self._json_dumps({"status": "skipped", "warning": message})
            for source in context.sources:
                sources[source.source_id] = source
            for warning in context.warnings:
                record_warning(warning, step=step)

            try:
                validated_arguments = action_registry.validate_arguments(
                    normalized_tool_id,
                    arguments,
                )
            except (
                ResearchActionArgumentError,
                ResearchActionPermissionError,
            ) as exc:
                skipped_steps.append(step.step_id)
                failed_steps.append(step.step_id)
                message = str(exc)
                record_warning(message, step=step)
                record_event(
                    "tool-result",
                    step=step,
                    message=message,
                    payload={
                        "status": "invalid_arguments",
                        "arguments": arguments,
                        "stop_reason": "argument_validation_failed",
                    },
                    event_warnings=[message],
                )
                return self._json_dumps(
                    {
                        "status": "invalid_arguments",
                        "warning": message,
                        "arguments": arguments,
                    }
                )

            execution = execute_action(
                normalized_tool_id,
                validated_arguments,
                context,
            )
            tool_traces.append(execution.trace)
            outputs[step.step_id] = execution.output
            output_summaries[step.step_id] = self._compact_output(execution.output)
            for source in execution.sources:
                sources[source.source_id] = source
            if isinstance(execution.output, dict) and execution.output.get("error"):
                skipped_steps.append(step.step_id)
                failed_steps.append(step.step_id)
                message = f"{normalized_tool_id} failed: {execution.output['error']}"
                record_warning(message, step=step)
                record_event(
                    "tool-result",
                    step=step,
                    message=message,
                    payload={
                        "status": "failed",
                        "trace_summary": execution.trace.summary,
                        "output_summary": output_summaries[step.step_id],
                    },
                    source_ids=list(execution.trace.source_ids),
                    event_warnings=[message],
                )
                return self._json_dumps({"status": "failed", "warning": message, "output": execution.output})

            executed_steps.append(step.step_id)
            record_event(
                "tool-result",
                step=step,
                message=execution.trace.summary,
                payload={
                    "status": "completed",
                    "arguments": execution.trace.arguments,
                    "output_kind": type(execution.output).__name__,
                    "output_summary": output_summaries[step.step_id],
                },
                source_ids=list(execution.trace.source_ids),
            )
            return self._json_dumps(
                {
                    "status": "completed",
                    "tool_id": normalized_tool_id,
                    "arguments": execution.trace.arguments,
                    "trace_summary": execution.trace.summary,
                    "source_ids": list(execution.trace.source_ids),
                    "output": self._bounded_observation(execution.output),
                }
            )

        sdk_tools: list[Any] = []
        if sdk.FunctionTool is not None:
            for tool_id in allowed_tool_ids:
                definition = action_registry.require(tool_id)

                async def invoke_strict_action(
                    _context: Any,
                    arguments_json: str,
                    *,
                    resolved_tool_id: str = tool_id,
                ) -> str:
                    parsed = self._parse_json_object(arguments_json)
                    return execute_registered_action(
                        resolved_tool_id,
                        parsed,
                    )

                sdk_tools.append(
                    sdk.FunctionTool(
                        name=definition.tool_id,
                        description=definition.description,
                        params_json_schema=definition.input_schema,
                        on_invoke_tool=invoke_strict_action,
                        strict_json_schema=True,
                        timeout_seconds=definition.timeout_seconds,
                    )
                )
        else:
            # Compatibility for injected test doubles that predate manual
            # FunctionTool support. Production SDK execution always uses the
            # per-action strict tools above.
            def execute_gamma_action(
                tool_id: str,
                arguments_json: str = "{}",
            ) -> str:
                return execute_registered_action(
                    tool_id,
                    self._parse_json_object(arguments_json),
                )

            sdk_tools = [sdk.function_tool(execute_gamma_action)]

        agent_kwargs = {
            "name": "Gamma Research Operator",
            "model": resolved_model,
            "instructions": self._instructions(),
            "tools": sdk_tools,
        }
        if sdk.FunctionTool is not None:
            agent_kwargs["output_type"] = _OperatorFinalOutput
        if sdk.ModelSettings is not None:
            agent_kwargs["model_settings"] = sdk.ModelSettings(
                **self._model_settings_kwargs(reasoning_effort=reasoning_effort)
            )
        agent = sdk.Agent(**agent_kwargs)
        prompt = self._operator_prompt(request, plan, allowed_tool_ids)

        async def run_agents_operator() -> Any:
            nonlocal cancelled_at_boundary
            nonlocal provider_progress_count
            run_streamed = getattr(sdk.Runner, "run_streamed", None)
            if not callable(run_streamed):
                return await sdk.Runner.run(
                    agent,
                    prompt,
                    max_turns=max_model_turns,
                )
            streamed = run_streamed(
                agent,
                prompt,
                max_turns=max_model_turns,
            )
            if asyncio.iscoroutine(streamed):
                streamed = await streamed
            async for sdk_event in streamed.stream_events():
                event_type = str(
                    getattr(sdk_event, "type", None)
                    or sdk_event.__class__.__name__
                )
                if (
                    event_type not in {"raw_response_event", "RawResponsesStreamEvent"}
                    and provider_progress_count < 24
                ):
                    provider_progress_count += 1
                    record_event(
                        "provider-progress",
                        title="Agents SDK progress",
                        message=f"Agents SDK emitted {event_type.replace('_', ' ')}.",
                        payload={
                            "orchestrator": self.provider_name,
                            "sdk_event_type": event_type,
                        },
                    )
                if (
                    not cancelled_at_boundary
                    and should_cancel is not None
                    and should_cancel()
                ):
                    cancelled_at_boundary = True
                    streamed.cancel(mode="after_turn")
                    record_warning(
                        "Research Operator cancellation was requested; the Agents SDK "
                        "will stop after the current safe turn boundary."
                    )
            return streamed

        try:
            started_at = perf_counter()
            if should_cancel is not None and should_cancel():
                cancelled_at_boundary = True
                record_warning(
                    "Research Operator was cancelled before Agents SDK orchestration began."
                )
                run_result = None
            else:
                run_result = asyncio.run(run_agents_operator())
            sdk_duration_ms = int((perf_counter() - started_at) * 1000)
            if run_result is not None:
                model_usage = self._extract_run_usage(run_result)
                final_card, final_stop_reason, synthesis_error = (
                    self._parse_final_output(
                        getattr(run_result, "final_output", None)
                    )
                )
        except Exception as exc:
            synthesis_error = (
                f"Agents SDK operator run failed: {exc.__class__.__name__}: {exc}"
            )
            record_warning(synthesis_error)

        if plan.confirmation_checkpoints and not cancelled_at_boundary:
            message = "Operator plan includes confirmation checkpoints that were not applied by automatic execution."
            warnings.append(message)
            for checkpoint in plan.confirmation_checkpoints:
                record_event(
                    "confirmation-needed",
                    title="Confirmation checkpoint",
                    message=checkpoint.reason,
                    payload={
                        "checkpoint_id": checkpoint.checkpoint_id,
                        "after_step_id": checkpoint.after_step_id,
                        "required_for_tool_ids": list(checkpoint.required_for_tool_ids),
                        "default_policy": checkpoint.default_policy,
                    },
                    event_warnings=[message],
                )

        return self._finalize_result(
            request=request,
            plan=plan,
            response_id=response_id,
            events=events,
            sources=sources,
            tool_traces=tool_traces,
            warnings=warnings,
            executed_steps=executed_steps,
            skipped_steps=skipped_steps,
            failed_steps=failed_steps,
            build_card=build_card,
            status=(
                "cancelled"
                if cancelled_at_boundary
                else "ready"
                if executed_steps and final_card is not None
                else "incomplete"
                if executed_steps
                else "error"
            ),
            outputs=outputs,
            output_summaries=output_summaries,
            sdk_duration_ms=sdk_duration_ms,
            model_usage=model_usage,
            reasoning_effort=reasoning_effort,
            emit_event=emit_event,
            final_card=final_card,
            stop_reason=(
                "user_cancelled"
                if cancelled_at_boundary
                else boundary_stop_reason
                if boundary_stop_reason is not None
                else final_stop_reason
                if final_card is not None
                else "invalid_final_synthesis"
                if synthesis_error
                else "insufficient_evidence"
            ),
            synthesis_error=synthesis_error,
            tool_calls_used=plan.max_tool_calls - remaining_tool_calls,
            external_provider_calls_used=provider_calls_used,
            max_model_turns=max_model_turns,
        )

    def _finalize_result(
        self,
        *,
        request: CopilotResearchCardRequest,
        plan: CopilotOperatorPlan,
        response_id: str,
        events: list[CopilotOperatorProgressEvent],
        sources: dict[str, CopilotSourceRef],
        tool_traces: list[CopilotToolTrace],
        warnings: list[str],
        executed_steps: list[str],
        skipped_steps: list[str],
        failed_steps: list[str],
        build_card: CardBuilder,
        status: str,
        outputs: dict[str, Any] | None = None,
        output_summaries: dict[str, Any] | None = None,
        sdk_duration_ms: int | None = None,
        model_usage: dict[str, Any] | None = None,
        reasoning_effort: str | None = None,
        emit_event: OperatorEventEmitter | None = None,
        final_card: ResearchCard | None = None,
        stop_reason: str | None = None,
        synthesis_error: str | None = None,
        tool_calls_used: int = 0,
        external_provider_calls_used: int = 0,
        max_model_turns: int | None = None,
    ) -> CopilotResearchCardResult:
        warnings = dedupe_warnings(warnings)
        run_id = events[0].run_id if events else new_copilot_id("oprun")
        final_outputs, output_retention = self._bounded_outputs(outputs or {}, output_summaries or {})
        next_sequence = len(events) + 1
        final_message = (
            "Research Operator stopped at the current Agents SDK turn boundary."
            if status == "cancelled"
            else (
                "Research Operator synthesized the requested conclusion from "
                f"{len(executed_steps)} validated tool observation(s)."
            )
            if status == "ready" and final_card is not None
            else synthesis_error
            or "Research Operator did not produce a schema-valid final synthesis."
        )
        final_events = [
            CopilotOperatorProgressEvent(
                run_id=run_id,
                event_id=new_copilot_id("opevent"),
                sequence=next_sequence,
                event_type="artifact-created",
                timestamp=now_utc(),
                title="Operator trace",
                message="Created an operator event trace for this run.",
                payload={"artifact_type": "operator_trace", "artifact_id": run_id, "event_count": len(events) + 3},
            ),
            CopilotOperatorProgressEvent(
                run_id=run_id,
                event_id=new_copilot_id("opevent"),
                sequence=next_sequence + 1,
                event_type="artifact-created",
                timestamp=now_utc(),
                title="Operator report",
                message="Created the final Research Operator result card.",
                payload={"artifact_type": "operator_report", "artifact_id": response_id},
            ),
            CopilotOperatorProgressEvent(
                run_id=run_id,
                event_id=new_copilot_id("opevent"),
                sequence=next_sequence + 2,
                event_type="final-report",
                timestamp=now_utc(),
                title="Final operator report",
                message=final_message,
                payload={
                    "status": status,
                    "stop_reason": stop_reason or status,
                    "orchestrator": self.provider_name,
                    "operator_contract": "copilot.operator.loop.v1",
                    "synthesis_source": (
                        "model_final_output"
                        if final_card is not None
                        else "typed_non_success"
                    ),
                    "executed_steps": list(executed_steps),
                    "skipped_steps": list(skipped_steps),
                    "failed_steps": list(failed_steps),
                    "warning_count": len(warnings),
                    "source_count": len(sources),
                    "tool_trace_count": len(tool_traces),
                    "model": (
                        request.model_resolution.model
                        if request.model_resolution is not None
                        and request.model_resolution.model
                        else self.config.model
                    ),
                    "reasoning_effort": reasoning_effort,
                    "verbosity": self.config.verbosity,
                    "sdk_duration_ms": sdk_duration_ms,
                    "model_usage": model_usage or {},
                    "tool_calls_used": tool_calls_used,
                    "tool_calls_remaining": max(
                        0,
                        plan.max_tool_calls - tool_calls_used,
                    ),
                    "external_provider_calls_used": (
                        external_provider_calls_used
                    ),
                    "max_model_turns": max_model_turns,
                    "output_summaries": output_summaries or {},
                    "output_retention": output_retention,
                    "outputs": final_outputs,
                },
                source_ids=[source.source_id for source in list(sources.values())[:10]],
                warnings=warnings,
            ),
        ]
        for event in final_events:
            events.append(event)
            if emit_event is not None:
                try:
                    emit_event(event)
                except Exception:
                    pass
        return CopilotResearchCardResult(
            domain="synthesis",
            current_tab=request.context.current_tab or "copilot",
            status=status,
            provider=self.provider_name,
            model=(
                request.model_resolution.model
                if request.model_resolution is not None
                and request.model_resolution.model
                else self.config.model
            ),
            response_id=response_id,
            message=final_message,
            card=(
                final_card
                if final_card is not None
                else build_card(
                    plan,
                    executed_steps,
                    skipped_steps,
                    list(sources.values()),
                    warnings,
                )
                if status == "ready"
                else None
            ),
            sources=list(sources.values()),
            tool_traces=tool_traces,
            operator_events=events,
            warnings=warnings,
            usage=self._usage_record(model_usage or {}, len(tool_traces)),
        )

    @staticmethod
    def _instructions() -> str:
        return (
            "You are Gamma's Research Operator orchestrator. "
            "Your outcome is a traceable, read-only Gamma research run followed "
            "by a schema-valid analytical answer grounded in the actual tool "
            "observations. Call only the provided strict Gamma action tools and "
            "only action ids listed in the user payload under allowed_tool_ids. "
            "Preserve every explicit user entity, portfolio leg, weight, scenario "
            "shock, date, horizon, assumption, and comparison target in the tool "
            "arguments. Do not replace them with unrelated defaults. "
            "After each tool result, inspect the observation and decide whether to "
            "adapt, call another authorized tool, stop for insufficient evidence, "
            "or produce the final answer. "
            "Do not apply local state changes, place trades, modify accounts, sign wallet messages, "
            "rebalance portfolios, or run arbitrary strategy code. "
            "Stop at confirmation checkpoints and leave durable research-state changes to Gamma's confirmation flow. "
            "Prefer the smallest set of relevant allowed actions that satisfies "
            "the user's requested research task. A generic count of executed "
            "steps is not a successful final answer."
        )

    @classmethod
    def _operator_prompt(
        cls,
        request: CopilotResearchCardRequest,
        plan: CopilotOperatorPlan,
        allowed_tool_ids: list[str],
    ) -> str:
        payload = {
            "user_prompt": request.prompt,
            "intent": plan.intent,
            "allowed_tool_ids": list(allowed_tool_ids),
            "operator_steps": [
                {
                    "step_id": step.step_id,
                    "order": step.order,
                    "title": step.title,
                    "domain": step.domain,
                    "action_type": step.action_type,
                    "tool_id": step.tool_id,
                    "permission_policy": step.permission_policy,
                    "requires_confirmation": step.requires_confirmation,
                }
                for step in plan.steps
            ],
            "confirmation_checkpoints": [asdict(item) for item in plan.confirmation_checkpoints],
            "success_criteria": [
                "Select only Gamma registry actions that directly support the user request and operator plan.",
                "Run automatic read-only analysis tools when they are relevant and bounded.",
                "Never run tools that require confirmation; leave those for Gamma's confirmation checkpoints.",
                "Preserve explicit user parameters in the strict tool inputs.",
                "Synthesize the requested conclusion from the returned tool observations.",
            ],
            "stopping_rules": [
                "Stop after the relevant allowed read-only plan actions have completed or been skipped with warnings.",
                "Stop before any durable local research-state change or action outside the allowed_tool_ids list.",
                "Stop if Gamma returns a confirmation checkpoint, permission warning, or tool-call budget guard.",
            ],
            "required_behavior": (
                "Call the relevant named Gamma action tools with schema-valid "
                "arguments derived from the request. Do not call tools that are "
                "missing from allowed_tool_ids. Return a final structured answer "
                "that directly addresses user_prompt and cites only source ids "
                "returned by the tools."
            ),
        }
        return cls._json_dumps(payload)

    def _model_settings_kwargs(self, *, reasoning_effort: str | None = None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "parallel_tool_calls": False,
            "include_usage": self.config.include_usage,
        }
        resolved_effort = self._resolve_reasoning_effort(reasoning_effort)
        if resolved_effort:
            kwargs["reasoning"] = {"effort": resolved_effort}
        if self.config.verbosity:
            kwargs["verbosity"] = self.config.verbosity
        return kwargs

    def _resolve_reasoning_effort(self, request_effort: str | None) -> str | None:
        normalized = str(request_effort or "").strip().lower()
        if normalized in SUPPORTED_REASONING_EFFORTS:
            return normalized
        configured = str(self.config.reasoning_effort or "").strip().lower()
        return configured if configured in SUPPORTED_REASONING_EFFORTS else None

    @classmethod
    def _parse_final_output(
        cls,
        value: Any,
    ) -> tuple[ResearchCard | None, str | None, str | None]:
        if value is None:
            return None, None, "Agents SDK returned no final analytical output."
        if isinstance(value, _OperatorFinalOutput):
            payload = value.model_dump()
        elif isinstance(value, dict):
            payload = dict(value)
        else:
            model_dump = getattr(value, "model_dump", None)
            if callable(model_dump):
                dumped = model_dump()
                payload = dumped if isinstance(dumped, dict) else {}
            else:
                text = str(value or "").strip()
                if not text:
                    return None, None, "Agents SDK returned an empty final analytical output."
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    return (
                        None,
                        None,
                        "Agents SDK final analytical output was not schema-valid JSON.",
                    )
                payload = parsed if isinstance(parsed, dict) else {}
        try:
            validated = _OperatorFinalOutput.model_validate(payload)
        except Exception as exc:
            return (
                None,
                None,
                f"Agents SDK final analytical output failed validation: {exc}",
            )
        return (
            ResearchCard(
                title=validated.title,
                hypothesis=validated.hypothesis,
                rationale=validated.rationale,
                required_data=list(validated.required_data),
                proposed_test=validated.proposed_test,
                confounders=list(validated.confounders),
                next_steps=list(validated.next_steps),
                caveats=list(validated.caveats),
                source_backed_claims=[
                    ResearchClaim(
                        claim=claim.claim,
                        evidence_refs=list(claim.evidence_refs),
                    )
                    for claim in validated.source_backed_claims
                ],
                inferred_claims=list(validated.inferred_claims),
            ),
            validated.stop_reason,
            None,
        )

    @staticmethod
    def _parse_json_object(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        text = str(value or "").strip()
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
    def _bounded_observation(cls, output: Any) -> Any:
        """Keep analytical rows available to the model within a hard bound."""

        rendered = cls._json_dumps(output)
        if len(rendered.encode("utf-8")) <= MAX_OPERATOR_FINAL_OUTPUT_BYTES:
            return output
        return {
            "truncated": True,
            "summary": cls._compact_output(output),
            "warning": (
                "Gamma bounded this observation before returning it to the "
                "Operator model; the complete output remains in the local trace."
            ),
        }

    @classmethod
    def _json_dumps(cls, value: Any) -> str:
        return json.dumps(value, ensure_ascii=True, default=cls._json_default)

    @staticmethod
    def _json_default(value: Any) -> str:
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        return str(value)

    @classmethod
    def _extract_run_usage(cls, run_result: Any) -> dict[str, Any]:
        usage: dict[str, Any] = {}
        raw_responses = getattr(run_result, "raw_responses", None)
        if not isinstance(raw_responses, list):
            return usage
        usage["provider_calls"] = len(raw_responses)
        for response in raw_responses:
            response_usage = cls._object_to_mapping(getattr(response, "usage", None))
            if response_usage:
                cls._merge_usage(usage, response_usage)
        return usage

    @classmethod
    def _usage_record(
        cls,
        usage: dict[str, Any],
        tool_calls: int,
    ) -> CopilotUsageRecord:
        input_details = usage.get("input_tokens_details")
        input_details = input_details if isinstance(input_details, dict) else {}
        output_details = usage.get("output_tokens_details")
        output_details = output_details if isinstance(output_details, dict) else {}

        def optional_int(value: Any) -> int | None:
            if value is None or isinstance(value, bool):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        return CopilotUsageRecord(
            input_tokens=optional_int(usage.get("input_tokens")),
            output_tokens=optional_int(usage.get("output_tokens")),
            reasoning_tokens=optional_int(output_details.get("reasoning_tokens")),
            total_tokens=optional_int(usage.get("total_tokens")),
            cache_read_tokens=optional_int(
                input_details.get("cached_tokens")
                if input_details.get("cached_tokens") is not None
                else usage.get("cached_tokens")
            ),
            cache_write_tokens=optional_int(
                usage.get("cache_write_tokens")
                if usage.get("cache_write_tokens") is not None
                else input_details.get("cache_write_tokens")
            ),
            provider_calls=optional_int(usage.get("provider_calls")),
            tool_calls=tool_calls,
        )

    @classmethod
    def _merge_usage(cls, total: dict[str, Any], item: dict[str, Any]) -> None:
        for key, value in item.items():
            if isinstance(value, (int, float)):
                total[key] = total.get(key, 0) + value
            elif isinstance(value, dict):
                nested = total.setdefault(key, {})
                if isinstance(nested, dict):
                    cls._merge_usage(nested, value)

    @classmethod
    def _object_to_mapping(cls, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if value is None:
            return {}
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            return dumped if isinstance(dumped, dict) else {}
        return {
            key: item
            for key in dir(value)
            if not key.startswith("_")
            for item in [getattr(value, key, None)]
            if isinstance(item, (int, float, dict))
        }

    @staticmethod
    def _compact_output(output: Any) -> Any:
        if isinstance(output, list):
            return {"kind": "list", "count": len(output), "items": output[:5]}
        if not isinstance(output, dict):
            return {"kind": type(output).__name__, "value": output}
        summary: dict[str, Any] = {
            "kind": "dict",
            "keys": list(output.keys())[:12],
        }
        for key in (
            "symbol",
            "ticker",
            "scenario_label",
            "scenario_type",
            "scope_type",
            "result_kind",
            "portfolio_label",
            "benchmark_symbol",
            "snapshot_available",
            "source_provider",
            "origin",
            "freshness_label",
        ):
            if key in output:
                summary[key] = output.get(key)
        nested_summary = output.get("summary")
        if isinstance(nested_summary, dict):
            summary["summary"] = {
                key: value
                for key, value in nested_summary.items()
                if isinstance(value, (str, int, float, bool)) or value is None
            }
        metrics = output.get("metrics")
        if isinstance(metrics, dict):
            summary["metrics"] = {
                key: value
                for key, value in metrics.items()
                if isinstance(value, (str, int, float, bool)) or value is None
            }
        for list_key in (
            "warnings",
            "expiry_comparisons",
            "top_contributions",
            "relative_metrics",
            "coverage",
            "constituents",
        ):
            value = output.get(list_key)
            if isinstance(value, list):
                summary[f"{list_key}_count"] = len(value)
            elif isinstance(value, dict):
                summary[list_key] = {
                    key: item
                    for key, item in value.items()
                    if isinstance(item, (str, int, float, bool)) or item is None
                }
        return summary

    @classmethod
    def _bounded_outputs(
        cls,
        outputs: dict[str, Any],
        output_summaries: dict[str, Any],
        *,
        max_bytes: int = MAX_OPERATOR_FINAL_OUTPUT_BYTES,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        estimated_bytes = cls._json_size_bytes(outputs)
        retention = {
            "mode": "full",
            "reason": None,
            "output_count": len(outputs),
            "estimated_full_output_bytes": estimated_bytes,
            "max_full_output_bytes": max_bytes,
        }
        if estimated_bytes <= max_bytes:
            return outputs, retention
        compact_outputs = {
            step_id: {
                "truncated": True,
                "retention_reason": "full_output_exceeded_payload_budget",
                "output_summary": output_summaries.get(step_id) or cls._compact_output(output),
            }
            for step_id, output in outputs.items()
        }
        retention["mode"] = "compact"
        retention["reason"] = "full_output_exceeded_payload_budget"
        return compact_outputs, retention

    @staticmethod
    def _json_size_bytes(value: Any) -> int:
        try:
            return len(json.dumps(value, ensure_ascii=True, default=str).encode("utf-8"))
        except (TypeError, ValueError):
            return len(str(value).encode("utf-8"))
