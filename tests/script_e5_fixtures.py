"""Fixtures deterministas de E5. El runtime de fixture NO ejecuta Python: genera un gamma_analytics.json a
partir de los parámetros recibidos para ejercitar barridos, libro de pesos y walk-forward. Declara ejecución
solo para probar las puertas de elegibilidad; no es certificación del runtime real.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import replace
from datetime import date, timedelta

from src.application.research_script_service import ResearchScriptService
from src.application.research_service import ResearchService
from src.models.research_script import ResearchScriptCreateRequest
from src.services.research_script_runtime import MockResearchScriptRuntime, ResearchScriptRuntimeOutput
from src.services.research_script_store import ResearchScriptStore
from src.services.saved_research_store import SavedResearchStore

E5_SOURCE = """import json, os
# Parámetros separados del código: el mismo fuente sirve para todo el barrido.
params = json.load(open("gamma_parameters.json")) if os.path.exists("gamma_parameters.json") else {"lookback": 10, "leverage": 1.0}
print("lookback", params["lookback"], "leverage", params["leverage"])
"""


def business_days(start: date, count: int) -> list[str]:
    days, current = [], start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    return days


DATES = business_days(date(2026, 1, 2), 160)
# Activo sintético con régimen (tendencia al principio, reversión después) y ruido determinista de semilla fija.
_NOISE = random.Random(20261020)
ASSET = [0.004 * math.sin(i / 9) + 0.002 * math.cos(i / 4) + (0.0015 if i < 80 else -0.0010) + _NOISE.gauss(0, 0.009)
         for i in range(len(DATES))]


def strategy_payload(lookback: int, leverage: float) -> dict:
    """Momentum sobre la suma de los últimos ``lookback`` rendimientos; decisión al cierre de t."""
    decisions = []
    for i in range(len(DATES)):
        window = ASSET[max(0, i - lookback + 1): i + 1]
        decisions.append(leverage * (1.0 if sum(window) >= 0 else -1.0))
    # Rendimiento declarado por el autor: posición decidida en t-1 aplicada al rendimiento de t (causal).
    strategy = [{"date": DATES[i], "value": decisions[i - 1] * ASSET[i]} for i in range(1, len(DATES))]
    common = {"meaning": "Hypothetical momentum research", "methodology": "Sign of trailing sum; decided at close",
              "assumptions": ["No costs in author returns"], "limitations": ["Synthetic deterministic fixture"]}
    return {
        "contract_version": "gamma-script-analytics.v1",
        "instruments": [
            {"instrument_id": "research:asset", "namespace": "research", "native_id": "asset", "label": "Synthetic asset"},
            {"instrument_id": "research:strategy", "namespace": "research", "native_id": "strategy", "label": "Strategy"},
        ],
        "results": [
            {**common, "result_id": "strategy", "name": "Strategy returns", "kind": "returns", "unit": "fraction",
             "return_type": "simple", "periods_per_year": 252, "instrument_id": "research:strategy",
             "frequency": "daily", "observations": strategy},
            {**common, "result_id": "asset_returns", "name": "Asset returns", "kind": "returns", "unit": "fraction",
             "return_type": "simple", "periods_per_year": 252, "instrument_id": "research:asset",
             "frequency": "daily", "observations": [{"date": d, "value": v} for d, v in zip(DATES, ASSET)]},
            {**common, "result_id": "weights", "name": "Target exposure", "kind": "weights", "unit": "fraction_nav",
             "weight_semantics": "signed_nav_exposure", "hypothetical": True, "instrument_id": "research:asset",
             "frequency": "daily", "observations": [{"date": d, "value": w} for d, w in zip(DATES, decisions)]},
        ],
    }


class ParameterFixtureRuntime(MockResearchScriptRuntime):
    """Deriva el artefacto de los parámetros entregados; registra lo recibido para las aserciones."""

    def __init__(self, *, executed: bool = True, failing_points: set[str] | None = None):
        self.executed = executed
        self.failing_points = failing_points or set()
        self.requests = []

    def capabilities(self):
        return replace(super().capabilities(), provider="e5_deterministic_fixture",
                       runtime_kind="e5_fixture" if self.executed else "mock_safe_preview",
                       executes_source=self.executed)

    def start_run(self, request):
        self.requests.append(request)
        result = super().start_run(request)
        params = json.loads(request.parameters_content) if request.parameters_content else {"lookback": 10, "leverage": 1.0}
        outputs = [ResearchScriptRuntimeOutput(output_id="log", kind="log", sequence=1, media_type="text/plain",
                                               text=f"fixture lookback={params['lookback']} leverage={params['leverage']}")]
        status = "failed" if request.parameters_sha256 in self.failing_points else "completed"
        if status == "completed":
            outputs.append(ResearchScriptRuntimeOutput(
                output_id="analytics", kind="file", sequence=2, media_type="application/json",
                filename="gamma_analytics.json", run_association_verified=True,
                artifact_bytes=json.dumps(strategy_payload(int(params["lookback"]), float(params["leverage"]))).encode()))
        return replace(result, status=status, outputs=outputs, usage={**result.usage, "executed_code": self.executed},
                       executed_source_sha256=request.source_sha256,
                       warnings=["Deterministic E5 fixture: no Python was executed; outputs are derived from the parameters for gate testing."])


class NoProvider:
    def __getattr__(self, name):
        raise AssertionError(f"E5 must not acquire provider data: {name}")


def e5_service(tmp_path, runtime=None):
    owner = ResearchService(NoProvider(), SavedResearchStore(base_dir=tmp_path / "saved"))
    runtime = runtime or ParameterFixtureRuntime()
    service = ResearchScriptService(ResearchScriptStore(base_dir=tmp_path / "scripts"), runtime, research_service=owner)
    detail = service.create_script(ResearchScriptCreateRequest(session_id="e5", title="E5 sweep", source=E5_SOURCE))
    return service, detail
