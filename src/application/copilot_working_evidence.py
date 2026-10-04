"""Checkpoint 8 retained, tab-owned evidence contracts.

These are snapshots of existing Gamma analytics, not new saved-object families.
"""
from copy import deepcopy
from dataclasses import asdict

from src.models.copilot import CopilotToolExecution

EVIDENCE_CONTRACT = "copilot.retained-evidence.v1"
EVIDENCE_TARGETS = {
    "run_research_scope_analysis": ("research", "equity_research", "scope_analysis", "Research scope analysis"),
    "run_strategy_lab_backtest": ("strategy_lab", "strategy_lab", "backtest_analyze", "Strategy Lab analysis"),
    "run_macro_series_analysis": ("macro", "macro", "snapshot", "Macro series analysis"),
    "get_macro_series_history_summary": ("macro", "macro", "snapshot", "Macro series history"),
    "run_crypto_token_analysis": ("crypto", "crypto", "deep_dive", "Crypto token analysis"),
    "inspect_commodity_curve_fundamentals": ("commodities", "commodities", "curves_spreads", "Commodity curve and fundamentals"),
}


def retained_evidence_spec(execution: CopilotToolExecution, tool_id: str, identity: str) -> dict | None:
    target = EVIDENCE_TARGETS.get(tool_id)
    output = execution.output
    if target is None or not isinstance(output, dict) or output.get("error"):
        return None
    if output.get("status") in {"unavailable", "error", "unsupported", "missing"}:
        return None
    if tool_id == "run_research_scope_analysis" and (
        not (output.get("metrics") or {}).get("observations_count")
        or (output.get("coverage") or {}).get("missing_symbols")
    ):
        # Never open a partial basket as if it were the complete requested scope.
        return None
    if tool_id == "get_macro_series_history_summary" and not output.get("observations"):
        return None
    domain, tab, mode, title = target
    inputs = deepcopy(execution.trace.arguments)
    label = inputs.get("primary_symbol") or inputs.get("series_id") or inputs.get("token_id") or inputs.get("instrument_id") or inputs.get("result_kind")
    sources = [asdict(source) for source in execution.sources]
    return {
        "family_key": f"{tool_id}:{identity}", "domain": domain,
        "analysis_type": "retained_evidence", "title": f"{title}: {label}" if label else title,
        "entity": {"entity_type": domain, "normalized_id": str(label or identity)},
        "inputs": inputs, "outputs": {"result": deepcopy(output), "sources": sources},
        "warnings": list(output.get("warnings") or []), "owning_tab": tab, "owning_mode": mode,
        "materialization": {
            "target_tab": tab, "target_mode": mode, "payload_contract": EVIDENCE_CONTRACT,
            "durable": False, "navigation_context": {}, "persistence_policy": "non_durable_only",
            "save_target": None,
        },
        "source_provider": ", ".join(dict.fromkeys(s.provider for s in execution.sources if s.provider)) or "unknown",
        "origin": f"gamma.copilot.{tool_id}",
        "transformation_note": "Retained Gamma analytical output with exact effective inputs and original source timestamps. Opening does not recompute or save research state.",
    }
