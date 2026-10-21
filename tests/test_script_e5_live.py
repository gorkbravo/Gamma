"""Opt-in E5 gate on the configured runtime (dos ejecuciones reales). Nunca cambia runtime, modelo ni límites.

Activar con GAMMA_RUN_LIVE_SCRIPT_E5=true. Los precios son sintéticos y se suministran como fichero: no es una
certificación de proveedores de mercado. Comprueba que el wrapper verifica y copia gamma_parameters.json, que el
fuente no cambia entre puntos y que libro de pesos y walk-forward se recalculan desde salidas retenidas reales.
"""
import math
import os
from datetime import date

import pytest
from dotenv import load_dotenv

from src.analytics.script_walk_forward import WalkForwardConfig
from src.analytics.script_weight_book import BookOptions, compute_weight_book
from src.application import script_experiments
from src.application.research_script_service import ResearchScriptService
from src.application.research_service import ResearchService
from src.application.runtime import _build_research_script_runtime
from src.application.script_analytics import inspect_analytics
from src.application.script_parameters import PARAMETERS_FILENAME
from src.models.research_script import (
    ResearchScriptCreateRequest, ResearchScriptInputBundleRequest, ResearchScriptInputFileCreateRequest,
    ResearchScriptSweepAxis, ResearchScriptSweepCreateRequest,
)
from src.services.research_script_store import ResearchScriptStore

from script_e5_fixtures import business_days

SOURCE = '''import csv, json
params = json.load(open("gamma_parameters.json"))
with open("prices.csv", newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))
closes = [float(row["close"]) for row in rows]
dates = [row["date"] for row in rows]
returns = [{"date": dates[i], "value": closes[i] / closes[i - 1] - 1} for i in range(1, len(rows))]
lookback = int(params["lookback"])
weights = []
for i in range(1, len(rows)):
    window = [r["value"] for r in returns[max(0, i - lookback):i]]
    weights.append({"date": dates[i], "value": 1.0 if sum(window) >= 0 else -1.0})
common = {"meaning": "Trailing-sum sign exposure on supplied prices", "methodology": "Decision at close; Gamma applies it later",
          "assumptions": ["No author costs"], "limitations": ["Synthetic supplied prices"]}
payload = {"contract_version": "gamma-script-analytics.v1",
           "instruments": [{"instrument_id": "research:asset", "namespace": "research", "native_id": "asset", "label": "Supplied asset"}],
           "results": [
               {**common, "result_id": "asset_returns", "name": "Asset returns", "kind": "returns", "instrument_id": "research:asset",
                "unit": "fraction", "return_type": "simple", "frequency": "daily", "periods_per_year": 252, "observations": returns},
               {**common, "result_id": "weights", "name": "Signed exposure", "kind": "weights", "instrument_id": "research:asset",
                "unit": "fraction_nav", "weight_semantics": "signed_nav_exposure", "hypothetical": True, "frequency": "daily", "observations": weights}]}
with open("gamma_analytics.json", "w", encoding="utf-8") as handle:
    json.dump(payload, handle, allow_nan=False)
print("E5_LIVE_OK lookback", lookback)
'''

DATES = business_days(date(2026, 7, 1), 40)
# Redondeados a 6 decimales: son exactamente los valores del CSV que lee el script.
PRICES = [round(100 * math.exp(sum(0.01 * math.sin(i / 3) + 0.004 * math.cos(i * 1.7) for i in range(k + 1))), 6)
          for k in range(len(DATES))]


@pytest.mark.live_network
@pytest.mark.skipif(os.getenv("GAMMA_RUN_LIVE_SCRIPT_E5") != "true", reason="Explicit opt-in required")
def test_live_parameters_sweep_weight_book_and_walk_forward(tmp_path):
    load_dotenv()
    runtime = _build_research_script_runtime()
    capabilities = runtime.capabilities()
    if not capabilities.available or not capabilities.executes_source:
        pytest.skip(f"Configured runtime {capabilities.runtime_kind} does not execute source; no runtime/model switch permitted")
    service = ResearchScriptService(ResearchScriptStore(tmp_path), runtime, research_service=ResearchService(None))
    detail = service.create_script(ResearchScriptCreateRequest(session_id="e5-live", title="E5 bounded live", source=SOURCE))
    content = "date,close\n" + "".join(f"{d},{p:.6f}\n" for d, p in zip(DATES, PRICES))
    bundle = service.create_input_bundle(detail.script.script_id, ResearchScriptInputBundleRequest(input_files=[
        ResearchScriptInputFileCreateRequest(logical_filename="prices.csv", media_type="text/csv", content=content.encode())]))
    sweep = script_experiments.create_sweep(service, detail.script.script_id, ResearchScriptSweepCreateRequest(
        revision_id=detail.script.canonical_revision_id, input_snapshot_id=bundle.snapshot_id,
        axes=[ResearchScriptSweepAxis("lookback", [3, 8])]))
    runs = [script_experiments.run_sweep_point(service, sweep.sweep_id, point.index) for point in sweep.points]
    for run, point in zip(runs, sweep.points):
        assert run.status == "completed", run.warnings
        assert run.usage["executed_code"] and run.parameters_sha256 == point.parameters_sha256
        assert point.parameters_sha256 in run.usage["executed_wrapper"]
        assert PARAMETERS_FILENAME not in {output.filename for output in run.outputs}
        assert any("E5_LIVE_OK lookback " + str(point.parameters["lookback"]) in (o.text or "") for o in run.outputs)
    assert runs[0].source_sha256 == runs[1].source_sha256 and runs[0].input_manifest_sha256 == runs[1].input_manifest_sha256

    artifact = inspect_analytics(service, runs[0].run_id, BookOptions(execution_lag=1, cost_bps=5))["artifacts"][0]
    assert artifact["valid"] and artifact["eligible"], artifact
    book = artifact["weight_book"]
    assert book["can_open"], book["unsupported_reason"]
    returns = [(d, p / q - 1) for d, p, q in zip(DATES[1:], PRICES[1:], PRICES)]
    payload_weights = [(o["date"], o["value"]) for o in artifact["results"][1]["result"]["observations"]]
    expected = compute_weight_book({"research:asset": payload_weights}, {"research:asset": returns}, BookOptions(1, 5))
    assert [row["value"] for row in book["mapping"]["rows"]] == pytest.approx([row["value"] for row in expected.rows], abs=1e-12)

    report = script_experiments.walk_forward_sweep(service, sweep.sweep_id,
        script_experiments.EvaluationTarget("weight_book", book_options=BookOptions(1, 5)), WalkForwardConfig(20, 5))
    assert report["causality"]["verified"] and report["trials"] == 2
    assert all(fold["train_end"] < fold["test_start"] for fold in report["folds"])
