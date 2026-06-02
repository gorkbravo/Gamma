from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from typing import Any, Callable

from src.application.copilot_context_helpers import dedupe_warnings
from src.application.research_action_registry import ResearchActionRegistry
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
    ResearchCard,
    new_copilot_id,
)
from src.utils.time import now_utc


ContextBuilder = Callable[[str], CopilotContextBundle]
DefaultArgumentBuilder = Callable[[str, CopilotContextBundle], dict[str, Any] | None]
RegisteredActionExecutor = Callable[[str, dict[str, Any], CopilotContextBundle], CopilotToolExecution]
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


def _load_agents_sdk() -> _AgentsSdkModule:
    from agents import Agent, ModelSettings, Runner, function_tool

    return _AgentsSdkModule(Agent=Agent, Runner=Runner, function_tool=function_tool, ModelSettings=ModelSettings)


def _parse_positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        return default
    return max(1, value)


@dataclass(frozen=True)
class CopilotAgentsOperatorConfig:
    orchestrator: str = "custom"
    model: str = "gpt-5.4"
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
                or os.getenv("GAMMA_COPILOT_MODEL")
                or "gpt-5.4"
            ).strip(),
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
    ) -> CopilotResearchCardResult:
        run_id = new_copilot_id("oprun")
        response_id = new_copilot_id("opexec")
        events: list[CopilotOperatorProgressEvent] = []
        sources: dict[str, CopilotSourceRef] = {}
        tool_traces: list[CopilotToolTrace] = []
        warnings: list[str] = list(plan.warnings)
        executed_steps: list[str] = []
        skipped_steps: list[str] = []
        failed_steps: list[str] = []
        outputs: dict[str, Any] = {}
        output_summaries: dict[str, Any] = {}
        remaining_tool_calls = plan.max_tool_calls
        provider_calls_used = 0

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
            events.append(
                CopilotOperatorProgressEvent(
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
            )

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
                "orchestrator": self.provider_name,
                "model": self.config.model,
                "allowed_tool_ids": list(allowed_tool_ids),
            },
        )
        for warning in plan.warnings:
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
                build_card=build_card,
                status="error",
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
                build_card=build_card,
                status="error",
            )

        def execute_registered_action(tool_id: str, arguments_json: str = "{}") -> str:
            """Execute one approved Gamma Research Action Registry tool by id."""
            nonlocal provider_calls_used
            nonlocal remaining_tool_calls
            normalized_tool_id = str(tool_id or "").strip()
            step = step_by_tool.get(normalized_tool_id)
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
                skipped_steps.append(step.step_id)
                message = f"Stopped operator execution after {plan.max_tool_calls} tools."
                record_warning(message, step=step)
                record_event("tool-result", step=step, message=message, payload={"status": "skipped"})
                return self._json_dumps({"status": "skipped", "warning": message})
            if definition.external_provider:
                if provider_calls_used + 1 > plan.max_provider_calls:
                    skipped_steps.append(step.step_id)
                    message = (
                        f"Skipped `{normalized_tool_id}` because provider calls would exceed the "
                        f"{plan.max_provider_calls} call guard."
                    )
                    record_warning(message, step=step)
                    record_event("tool-result", step=step, message=message, payload={"status": "skipped"})
                    return self._json_dumps({"status": "skipped", "warning": message})
                provider_calls_used += 1

            parsed_arguments = self._parse_json_object(arguments_json)
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

            arguments = parsed_arguments or default_arguments(normalized_tool_id, context)
            if arguments is None:
                skipped_steps.append(step.step_id)
                trace = CopilotToolTrace(
                    tool_name=normalized_tool_id,
                    summary="Skipped because operator execution could not infer required arguments.",
                    arguments={},
                    source_ids=[],
                )
                tool_traces.append(trace)
                record_event(
                    "tool-result",
                    step=step,
                    message=trace.summary,
                    payload={"status": "skipped", "arguments": {}},
                )
                return self._json_dumps({"status": "skipped", "warning": trace.summary})

            execution = execute_action(normalized_tool_id, arguments, context)
            remaining_tool_calls -= 1
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
                    "trace_summary": execution.trace.summary,
                    "source_ids": list(execution.trace.source_ids),
                    "output": self._compact_output(execution.output),
                }
            )

        execute_gamma_action = sdk.function_tool(execute_registered_action)
        agent_kwargs = {
            "name": "Gamma Research Operator",
            "model": self.config.model,
            "instructions": self._instructions(),
            "tools": [execute_gamma_action],
        }
        if sdk.ModelSettings is not None:
            agent_kwargs["model_settings"] = sdk.ModelSettings(parallel_tool_calls=False)
        agent = sdk.Agent(**agent_kwargs)
        prompt = self._operator_prompt(request, plan, allowed_tool_ids)

        try:
            asyncio.run(sdk.Runner.run(agent, prompt, max_turns=self.config.max_turns))
        except Exception as exc:
            record_warning(f"Agents SDK operator run failed: {exc.__class__.__name__}: {exc}")

        if plan.confirmation_checkpoints:
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
            status="ready" if executed_steps else "error",
            outputs=outputs,
            output_summaries=output_summaries,
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
    ) -> CopilotResearchCardResult:
        warnings = dedupe_warnings(warnings)
        run_id = events[0].run_id if events else new_copilot_id("oprun")
        events.append(
            CopilotOperatorProgressEvent(
                run_id=run_id,
                event_id=new_copilot_id("opevent"),
                sequence=len(events) + 1,
                event_type="artifact-created",
                timestamp=now_utc(),
                title="Operator trace",
                message="Created an operator event trace for this run.",
                payload={"artifact_type": "operator_trace", "artifact_id": run_id, "event_count": len(events) + 3},
            )
        )
        events.append(
            CopilotOperatorProgressEvent(
                run_id=run_id,
                event_id=new_copilot_id("opevent"),
                sequence=len(events) + 1,
                event_type="artifact-created",
                timestamp=now_utc(),
                title="Operator report",
                message="Created the final Research Operator result card.",
                payload={"artifact_type": "operator_report", "artifact_id": response_id},
            )
        )
        events.append(
            CopilotOperatorProgressEvent(
                run_id=run_id,
                event_id=new_copilot_id("opevent"),
                sequence=len(events) + 1,
                event_type="final-report",
                timestamp=now_utc(),
                title="Final operator report",
                message=f"Executed {len(executed_steps)} Agents SDK-selected operator step(s).",
                payload={
                    "status": status,
                    "orchestrator": self.provider_name,
                    "executed_steps": list(executed_steps),
                    "skipped_steps": list(skipped_steps),
                    "failed_steps": list(failed_steps),
                    "warning_count": len(warnings),
                    "source_count": len(sources),
                    "tool_trace_count": len(tool_traces),
                    "output_summaries": output_summaries or {},
                    "outputs": outputs or {},
                },
                source_ids=[source.source_id for source in list(sources.values())[:10]],
                warnings=warnings,
            )
        )
        return CopilotResearchCardResult(
            domain="synthesis",
            current_tab=request.context.current_tab or "copilot",
            status=status,
            provider=self.provider_name,
            model=self.config.model,
            response_id=response_id,
            message=f"Executed {len(executed_steps)} Agents SDK-selected operator step(s).",
            card=build_card(plan, executed_steps, skipped_steps, list(sources.values()), warnings),
            sources=list(sources.values()),
            tool_traces=tool_traces,
            operator_events=events,
            warnings=warnings,
        )

    @staticmethod
    def _instructions() -> str:
        return (
            "You are Gamma's Research Operator orchestrator. "
            "Call only the provided Gamma action-registry tool. "
            "Use only action ids listed in the user payload under allowed_tool_ids. "
            "Do not apply local state changes, place trades, modify accounts, sign wallet messages, "
            "rebalance portfolios, or run arbitrary strategy code. "
            "Stop at confirmation checkpoints and leave durable research-state changes to Gamma's confirmation flow."
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
            "required_behavior": (
                "Call execute_registered_action for each relevant allowed read-only action. "
                "Pass an empty JSON object for arguments when Gamma should infer defaults. "
                "Do not call tools that are missing from allowed_tool_ids."
            ),
        }
        return cls._json_dumps(payload)

    @staticmethod
    def _parse_json_object(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        text = str(value or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @classmethod
    def _json_dumps(cls, value: Any) -> str:
        return json.dumps(value, ensure_ascii=True, default=cls._json_default)

    @staticmethod
    def _json_default(value: Any) -> str:
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        return str(value)

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
