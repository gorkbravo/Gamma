from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.application.runtime import build_runtime
from src.models.copilot import CopilotResearchCardRequest, CopilotRequestContext


SOURCE = """from pathlib import Path
print('gamma operator eval')
Path('result.csv').write_text('metric,value\\nreturn,0.12\\n', encoding='utf-8')
"""


def request(prompt: str, script_state: dict | None = None) -> CopilotResearchCardRequest:
    return CopilotResearchCardRequest(
        domain="strategy_lab",
        prompt=prompt,
        user_session_id="research-script-operator-eval",
        role="research_operator",
        context=CopilotRequestContext(
            current_tab="copilot",
            workspace_mode="research",
            strategy_lab_state=(
                {"script_state": script_state}
                if script_state is not None
                else None
            ),
        ),
    )


def strict_objects(schema: dict) -> bool:
    if schema.get("type") == "object":
        properties = schema.get("properties") or {}
        if schema.get("additionalProperties") is not False:
            return False
        if set(schema.get("required") or []) != set(properties):
            return False
        if not all(
            strict_objects(child)
            for child in properties.values()
            if isinstance(child, dict)
        ):
            return False
    if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
        return strict_objects(schema["items"])
    return True


def main() -> int:
    os.environ["GAMMA_RESEARCH_SCRIPT_RUNTIME"] = "mock"
    with TemporaryDirectory(prefix="gamma-research-script-operator-eval-") as temp_dir:
        root = Path(temp_dir)
        runtime = build_runtime(
            mock_mode=True,
            cache_dir=root / "cache",
            history_dir=root / "data",
            sample_data_dir="sample_data",
        )
        try:
            copilot = runtime.copilot_service
            copilot.create_session(session_id="research-script-operator-eval")
            definitions = {
                item.tool_id: item
                for item in copilot.list_research_action_definitions()
            }
            draft_definition = definitions["strategy_lab.draft_research_script"]
            run_definition = definitions["strategy_lab.run_research_script"]
            draft_request = request(
                "Build a monthly moving-average Research Script for SPY. Show the code, but do not run it."
            )
            draft_plan = copilot.plan_research_operator(draft_request)
            draft_arguments = {
                "title": "SPY monthly crossover",
                "research_intent": "Compare monthly fast and slow moving averages for SPY.",
                "python_source": SOURCE,
                "language": "python",
                "authorized_input_references": [],
            }
            draft = copilot._execute_registered_operator_action(
                "strategy_lab.draft_research_script",
                draft_arguments,
                copilot._build_strategy_lab_context(draft_request),
                request=draft_request,
                run_id="eval-draft",
            )
            draft_output = dict(draft.output)
            run_request = request(
                "Run it.",
                {
                    "script_id": draft_output["script_id"],
                    "source_sha256": draft_output["source_sha256"],
                },
            )
            run_plan = copilot.plan_research_operator(run_request)
            run_arguments = {
                "script_id": draft_output["script_id"],
                "revision_id": draft_output["revision_id"],
                "input_snapshot_id": draft_output["input_snapshot_id"],
                "source_sha256": draft_output["source_sha256"],
                "manifest_sha256": draft_output["manifest_sha256"],
            }
            run = copilot._execute_registered_operator_action(
                "strategy_lab.run_research_script",
                run_arguments,
                copilot._build_strategy_lab_context(run_request),
                request=run_request,
                run_id="eval-run",
            )
            run_output = dict(run.output)
            research_agent = copilot.generate_research_card(
                replace(draft_request, role="research_agent")
            )
            blocked_plan = copilot.plan_research_operator(
                request("Build a Research Script and access my broker account.")
            )
            checks = {
                "strict_draft_schema": strict_objects(draft_definition.input_schema),
                "strict_run_schema": strict_objects(run_definition.input_schema),
                "draft_only_selects_draft": [step.tool_id for step in draft_plan.steps]
                == ["strategy_lab.draft_research_script"],
                "explicit_run_selects_run": [step.tool_id for step in run_plan.steps]
                == ["strategy_lab.run_research_script"],
                "draft_did_not_execute": draft_output.get("revision_status") == "canonical"
                and not draft_output.get("run_id"),
                "exact_source_identity": run_output.get("source_sha256")
                == draft_output.get("source_sha256"),
                "exact_manifest_identity": run_output.get("manifest_sha256")
                == draft_output.get("manifest_sha256"),
                "typed_outputs_observed": run_output.get("status") == "completed"
                and bool(run_output.get("outputs")),
                "research_agent_denied": research_agent.status == "incomplete"
                and not research_agent.tool_traces,
                "forbidden_authority_has_no_steps": not blocked_plan.steps,
                "backtest_action_unchanged": definitions["run_strategy_lab_backtest"].tool_id
                == "run_strategy_lab_backtest",
                "non_durable_materialization": run_output["materialization"]
                == {
                    "target_tab": "strategy_lab",
                    "target_mode": "script",
                    "payload_contract": "copilot.strategy-lab-script-working-analysis.v1",
                    "durable": False,
                    "navigation_context": {
                        "script_id": run_output["script_id"],
                        "revision_id": run_output["revision_id"],
                        "input_snapshot_id": run_output["input_snapshot_id"],
                        "selected_run_id": run_output["run_id"],
                    },
                },
            }
            result = {"passed": all(checks.values()), "checks": checks}
            print(json.dumps(result, indent=2))
            return 0 if result["passed"] else 1
        finally:
            runtime.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
