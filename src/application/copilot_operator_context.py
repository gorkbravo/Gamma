"""Identidades que el usuario adjuntó de forma visible y que el Operator envía al modelo.

El bucle del Operator solo enviaba al modelo la tarea, el plan y los contratos. Las herramientas
cuyos argumentos obligatorios dependen del estado adjunto en la UI (ids seleccionados, la
composición de Strategy Lab, el workbench de Opciones, el Script adjunto...) quedaban sin poder
rellenarse: el 2026-10-16 las ejecuciones Script en vivo terminaban sin llamadas a herramientas.

Aquí se construye, por herramienta planificada, un bloque acotado de identidades y entradas que el
usuario fijó. Nunca se envían salidas, series ni resultados. Gamma sigue validando cada argumento:
este bloque no concede autoridad nueva. Lo usan el bucle Responses y la ruta opcional Agents SDK.
"""
from __future__ import annotations

import math
from enum import Enum
from typing import Any

from src.application.copilot_context_helpers import _validate_workbench_symbols, resolve_iv_surface
from src.models.copilot import CopilotOperatorPlan, CopilotRequestContext, CopilotResearchCardRequest


MAX_ATTACHED_SCRIPT_SOURCE_CHARS = 8_000
# Mismos máximos que los esquemas de las herramientas que consumen cada bloque.
MAX_ATTACHED_COMPOSITION_LEGS = 25
MAX_ATTACHED_RESEARCH_POSITIONS = 100
MAX_ATTACHED_WORKBENCH_LEGS = 8
MAX_ATTACHED_SYNTHESIS_DOMAINS = 16
MAX_ATTACHED_ID_CHARS = 200
MAX_ATTACHED_LABEL_CHARS = 120

ATTACHED_CONTEXT_NOTE = (
    "State the user visibly attached in Gamma. Use each entry only as its usage says; script_state "
    "holds the attached Script's exact ids and hashes. Explicit task values always win. Copy ids and "
    "hashes exactly; never invent, complete or substitute them. Gamma validates every argument."
)

_SCRIPT_KEYS = (
    "script_id", "canonical_revision_id", "source_sha256", "input_snapshot_id",
    "manifest_sha256", "selected_run_id", "selected_run_status",
)


def operator_attached_context(
    request: CopilotResearchCardRequest,
    plan: CopilotOperatorPlan,
) -> dict[str, Any] | None:
    """Devuelve el bloque `attached_context` para las herramientas de este plan, o None."""

    tools = {step.tool_id for step in plan.steps if step.tool_id}
    attached: dict[str, Any] = {}
    script = _attached_script(request, plan)
    if script is not None:
        attached["script_state"] = script
    builders = (
        ("run_crypto_token_analysis", "crypto", _attached_crypto),
        ("run_prediction_market_comparison", "prediction_markets", _attached_prediction_market),
        ("run_macro_series_analysis", "macro_view", _attached_macro_view),
        ("draft_options_strategy", "options", _attached_options),
        ("run_strategy_lab_portfolio_backtest", "strategy_lab_composition", _attached_composition),
        ("run_research_basket_analysis", "research_scope", _attached_research_scope),
        ("get_synthesis_domain_context", "synthesis_scope", _attached_synthesis_scope),
    )
    for tool_id, key, builder in builders:
        if tool_id in tools:
            value = builder(request)
            if value:
                attached[key] = value
    if not attached:
        return None
    return {"note": ATTACHED_CONTEXT_NOTE, **attached}


def _domain_context(request: CopilotResearchCardRequest, *domains: str) -> CopilotRequestContext | None:
    # Mismo orden que CopilotService._plan_execution_request_context: primero el ámbito de
    # síntesis del dominio y, si no existe, el contexto de la propia petición. Así el modelo ve
    # exactamente el estado que Gamma usará al ejecutar la herramienta.
    if request.synthesis is not None:
        for domain in domains:
            for scope in request.synthesis.included_scopes:
                if str(scope.domain or "").strip() == domain:
                    return scope.context
    return request.context


def _text(value: Any, limit: int = MAX_ATTACHED_ID_CHARS) -> str | None:
    # La API valida algunos estados con modelos tipados: scope_type llega como Enum.
    if isinstance(value, Enum):
        value = value.value
    text = str(value).strip() if value is not None else ""
    return text[:limit] if text else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _without_none(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None and value != []}


def _attached_script(
    request: CopilotResearchCardRequest,
    plan: CopilotOperatorPlan,
) -> dict[str, Any] | None:
    # Sin estas identidades el modelo no puede rellenar script_id ni los hashes exactos que
    # exigen las herramientas Script (validación en vivo 2026-10-15). Solo identidades y el código
    # canónico acotado, no salidas ni datos. Se lee solo request.context, igual que
    # script_visible_to_request: un Script dentro de un ámbito de síntesis no queda autorizado.
    if plan.intent != "research_script_workflow":
        return None
    state = request.context.strategy_lab_state if request.context is not None else None
    script = state.get("script_state") if isinstance(state, dict) else None
    if not isinstance(script, dict) or not str(script.get("script_id") or "").strip():
        return None
    attached: dict[str, Any] = {key: script[key] for key in _SCRIPT_KEYS if script.get(key) is not None}
    source = script.get("canonical_source")
    if isinstance(source, str):
        attached["canonical_source"] = source[:MAX_ATTACHED_SCRIPT_SOURCE_CHARS]
        attached["canonical_source_truncated"] = len(source) > MAX_ATTACHED_SCRIPT_SOURCE_CHARS
    return attached


def _attached_crypto(request: CopilotResearchCardRequest) -> dict[str, Any] | None:
    context = _domain_context(request, "crypto")
    token_id = _text(context.crypto_token_id if context is not None else None)
    if token_id is None:
        return None
    return {
        "selected_token_id": token_id,
        "usage": "Token selected in Crypto. Use it as token_id when the task refers to the selected or current token.",
    }


def _attached_prediction_market(request: CopilotResearchCardRequest) -> dict[str, Any] | None:
    # El plan de comparación no añade el contrato seleccionado por sí mismo; solo se ofrece su
    # identidad para que el modelo la incluya cuando el usuario se refiera a él.
    context = _domain_context(request, "prediction_markets")
    market_id = _text(context.prediction_market_id if context is not None else None)
    if market_id is None:
        return None
    return {
        "selected_market_id": market_id,
        "usage": (
            "Contract selected in Prediction Markets. Include it in market_ids only when the task "
            "refers to the selected, current or this market; never add it otherwise."
        ),
    }


def _attached_macro_view(request: CopilotResearchCardRequest) -> dict[str, Any] | None:
    context = _domain_context(request, "macro")
    macro = context.macro if context is not None else None
    if macro is None:
        return None
    view = _without_none({
        "region": _text(getattr(macro, "region", None), 16),
        "timeframe": _text(getattr(macro, "timeframe", None), 8),
    })
    if not view:
        return None
    return {
        **view,
        "usage": "Region and timeframe visible in Macro. Use them only when the task refers to the current or active view.",
    }


def _attached_options(request: CopilotResearchCardRequest) -> dict[str, Any] | None:
    context = _domain_context(request, "iv")
    state = context.iv_state if context is not None and isinstance(context.iv_state, dict) else {}
    surface = state.get("surface") if isinstance(state.get("surface"), dict) else None
    session = state.get("session") if isinstance(state.get("session"), dict) else None
    active_surface = resolve_iv_surface(surface, session) or {}
    workbench = state.get("workbench") if isinstance(state.get("workbench"), dict) else {}
    # Mismo filtro que el resumen de Opciones: un workbench de otro subyacente se descarta.
    workbench, _ = _validate_workbench_symbols(workbench, active_surface)
    active_symbol = _text(
        active_surface.get("symbol") or (session or {}).get("active_symbol") or workbench.get("symbol"), 32
    )
    legs = [
        _without_none({
            "side": _text(leg.get("side"), 8),
            "option_type": _text(leg.get("option_type"), 8),
            "expiry": _text(leg.get("expiry"), 16),
            "strike": _number(leg.get("strike")),
            "quantity": _integer(leg.get("quantity")),
        })
        for leg in (workbench.get("legs") or [])[:MAX_ATTACHED_WORKBENCH_LEGS]
        if isinstance(leg, dict)
    ]
    attached = _without_none({
        "active_symbol": active_symbol.upper() if active_symbol else None,
        "workbench_symbol": _text(workbench.get("symbol"), 32),
        "selected_expiry": _text(workbench.get("selected_expiry"), 16),
        "contracts": _integer(workbench.get("contracts")),
        "workbench_detached": True if workbench.get("detached") else None,
        "workbench_legs": [leg for leg in legs if leg],
    })
    if not attached:
        return None
    # Primas, griegas y resultados de la estrategia son salidas: no se envían.
    return {
        **attached,
        "usage": (
            "Active Options symbol and the structure the user built in the Options workbench. Use the "
            "symbol, selected expiry or legs only when the task refers to them; apply only changes the task states."
        ),
    }


def _attached_composition(request: CopilotResearchCardRequest) -> dict[str, Any] | None:
    context = _domain_context(request, "strategy_lab")
    composition: Any = None
    if context is not None and isinstance(context.strategy_lab_state, dict):
        composition = context.strategy_lab_state.get("composition")
    if not isinstance(composition, dict) and context is not None and isinstance(context.research_state, dict):
        composition = context.research_state.get("strategy_composition")
    inputs = composition.get("portfolio_inputs") if isinstance(composition, dict) else None
    if not isinstance(inputs, dict):
        return None
    legs = [
        _without_none({
            "label": _text(leg.get("label"), MAX_ATTACHED_LABEL_CHARS),
            "asset_class": _text(leg.get("asset_class"), 32),
            "identifier": _text(leg.get("identifier")),
            "weight": _number(leg.get("weight")),
        })
        for leg in (inputs.get("legs") or [])[:MAX_ATTACHED_COMPOSITION_LEGS]
        if isinstance(leg, dict)
    ]
    legs = [leg for leg in legs if leg.get("identifier")]
    if not legs:
        return None
    # Las series de rentabilidad de cada pata y los objetos resueltos son datos: no se envían.
    return {
        **_without_none({
            "name": _text(inputs.get("name"), MAX_ATTACHED_LABEL_CHARS),
            "benchmark_symbol": _text(inputs.get("benchmark_symbol"), 32),
            "lookback_days": _integer(inputs.get("lookback_days")),
            "min_observations": _integer(inputs.get("min_observations")),
        }),
        "legs": legs,
        "legs_truncated": len(inputs.get("legs") or []) > MAX_ATTACHED_COMPOSITION_LEGS,
        "usage": (
            "Signed inputs of the current Strategy Lab composition. Use them only when the task refers to "
            "the current composition; apply only changes the task states. Legs whose asset_class the tool "
            "does not accept cannot be re-run."
        ),
    }


def _attached_research_scope(request: CopilotResearchCardRequest) -> dict[str, Any] | None:
    context = _domain_context(request, "research", "equity_research")
    research_state = context.research_state if context is not None and isinstance(context.research_state, dict) else {}
    result = research_state.get("result")
    if not isinstance(result, dict):
        return None
    positions = [
        _without_none({"symbol": _text(row.get("symbol"), 32), "weight": _number(row.get("weight"))})
        for row in (result.get("weights") or [])[:MAX_ATTACHED_RESEARCH_POSITIONS]
        if isinstance(row, dict)
    ]
    positions = [row for row in positions if row.get("symbol")]
    scope = _without_none({
        "scope_type": _text(result.get("scope_type"), 32),
        "primary_symbol": _text(result.get("primary_symbol"), 32),
        "benchmark_symbol": _text(result.get("benchmark_symbol"), 32),
        "positions": positions,
    })
    if not scope.get("positions") and not scope.get("primary_symbol"):
        return None
    # Métricas, curvas y constituyentes del resultado son salidas: no se envían.
    return {
        **scope,
        "positions_truncated": len(result.get("weights") or []) > MAX_ATTACHED_RESEARCH_POSITIONS,
        "usage": (
            "Active Research scope. Use its positions or benchmark only when the task refers to the current "
            "or active scope; apply only changes the task states."
        ),
    }


def _attached_synthesis_scope(request: CopilotResearchCardRequest) -> dict[str, Any] | None:
    if request.synthesis is None:
        return None
    domains: list[str] = []
    for scope in request.synthesis.included_scopes:
        domain = _text(scope.domain, 64)
        if domain and domain not in domains:
            domains.append(domain)
    if not domains:
        return None
    return {
        "included_domains": domains[:MAX_ATTACHED_SYNTHESIS_DOMAINS],
        "usage": "Contexts the user selected for this Copilot turn; the only valid get_synthesis_domain_context domains.",
    }
