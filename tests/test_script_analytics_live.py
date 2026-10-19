"""Opt-in configured-runtime gate. Never overrides runtime or model selection."""
import math
import os
import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4
from copy import deepcopy

import pytest
from dotenv import load_dotenv

from src.application.runtime import _build_research_script_runtime
from src.application.research_script_service import ResearchScriptService
from src.application.research_service import ResearchService
from src.application.script_analytics import inspect_analytics, open_analytics
from src.models.research_script import ResearchScriptCreateRequest, ResearchScriptRunCreateRequest, ResearchScriptInputFileCreateRequest
from src.services.research_script_store import ResearchScriptStore


SOURCE = '''import csv
import json
with open("prices.csv", newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))
observations = [{"date": row["date"], "value": float(row["close"]) / float(previous["close"]) - 1}
                for previous, row in zip(rows, rows[1:])]
common = {"name": "Supplied research prices", "meaning": "Close-to-close simple returns",
          "methodology": "Consecutive supplied closes; no fill", "assumptions": ["No costs"],
          "limitations": ["Supplied synthetic prices; no live market-data certification"]}
payload = {"contract_version": "gamma-script-analytics.v1",
           "instruments": [{"instrument_id": "research:prices", "namespace": "research",
                            "native_id": "prices", "label": "Supplied prices"}],
           "results": [{**common, "result_id": "returns", "kind": "returns", "instrument_id": "research:prices",
                        "unit": "fraction", "return_type": "simple", "frequency": "daily", "periods_per_year": 252, "observations": observations},
                       {**common, "result_id": "metric", "kind": "metric", "unit": "fraction", "instrument_id": "research:prices",
                        "as_of": rows[-1]["date"], "value": float(rows[-1]["close"]) / float(rows[0]["close"]) - 1}]}
with open("gamma_analytics.json", "w", encoding="utf-8") as handle:
    json.dump(payload, handle, allow_nan=False)
print("Retained six calculated returns and total-return metric")
'''


@pytest.mark.live_network
@pytest.mark.skipif(os.getenv("GAMMA_RUN_LIVE_SCRIPT_E4") != "true", reason="Explicit opt-in required")
def test_configured_isolated_python_to_analytics(tmp_path):
    load_dotenv()
    runtime = _build_research_script_runtime()
    capabilities = runtime.capabilities()
    if not capabilities.available or not capabilities.executes_source:
        pytest.skip(f"Configured runtime {capabilities.runtime_kind}: available={capabilities.available}, executes_source={capabilities.executes_source}; no runtime/model switch permitted")
    # No listed provider is used: copied supplied-file input, owning return service only.
    service = ResearchScriptService(ResearchScriptStore(tmp_path), runtime, research_service=ResearchService(None))
    detail = service.create_script(ResearchScriptCreateRequest(session_id="e4-live", title="E4 bounded live", source=SOURCE))
    prices = [100, 101, 99, 102, 103, 101, 104]
    dates = ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"]
    content = "date,close\n" + "".join(f"{d},{p}\n" for d, p in zip(dates, prices))
    run = service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest(input_files=[
        ResearchScriptInputFileCreateRequest(logical_filename="prices.csv", media_type="text/csv", content=content.encode())]))
    assert run.status == "completed", run.warnings
    artifact = inspect_analytics(service, run.run_id)["artifacts"][0]
    assert artifact["valid"], artifact["errors"]
    item = artifact["results"][0]
    analysis, provenance = open_analytics(service, run.run_id, artifact["output_id"], "returns", item["preview_sha256"])
    expected = [b / a - 1 for a, b in zip(prices, prices[1:])]
    assert analysis.returns.tolist() == pytest.approx(expected, abs=1e-14)
    assert analysis.metrics.total_return == pytest.approx(math.prod(1 + r for r in expected) - 1, abs=1e-14)
    assert artifact["results"][1]["result"]["value"] == pytest.approx(prices[-1] / prices[0] - 1, abs=1e-14)
    restarted = ResearchScriptService(ResearchScriptStore(tmp_path), runtime, research_service=service.research_service)
    assert inspect_analytics(restarted, run.run_id) == inspect_analytics(service, run.run_id)
    assert provenance["source_sha256"] == run.source_sha256


LIFECYCLE_SOURCE = '''import csv
import json
with open("spy.json", encoding="utf-8") as handle:
    dataset = json.load(handle)
with open("settings.json", encoding="utf-8") as handle:
    settings = json.load(handle)
with open("rules.csv", newline="", encoding="utf-8") as handle:
    rules = {row["rule"]: float(row["value"]) for row in csv.DictReader(handle)}
points = dataset["data"]["points"]
identity = dataset["metadata"]["object_id"]
returns = [{"date": row["timestamp"][:10], "value": (row["close"] / previous["close"] - 1) * settings["return_multiplier"]}
           for previous, row in zip(points, points[1:])]
signals = [{"date": row["date"], "value": 1 if row["value"] > rules["threshold"] else -1 if row["value"] < -rules["threshold"] else 0} for row in returns]
weights = [{"date": row["date"], "value": rules["long_weight"] if row["value"] > 0 else rules["short_weight"] if row["value"] < 0 else 0} for row in signals]
common = {"name": "Live SPY research", "meaning": "Close-to-close price returns, not total returns",
          "methodology": "Consecutive provider closes copied by Gamma; observed date without filling or resampling",
          "assumptions": ["252 periods/year", "No costs or dividends independently added"],
          "limitations": ["Bounded price history only; inspect retained upstream warnings"]}
series = {"instrument_id": identity, "frequency": "daily"}
payload = {"contract_version": "gamma-script-analytics.v1",
           "instruments": [{"instrument_id": identity, "namespace": "gamma_catalog", "native_id": identity, "label": "SPY exact curated instrument"}],
           "results": [
               {**common, **series, "result_id": "returns", "kind": "returns", "unit": "fraction", "return_type": "simple", "periods_per_year": 252, "observations": returns},
               {**common, "result_id": "total", "kind": "metric", "unit": "fraction", "instrument_id": identity, "as_of": returns[-1]["date"], "value": points[-1]["close"] / points[0]["close"] - 1},
               {**common, **series, "result_id": "signal", "kind": "signals", "unit": "indicator", "observations": signals,
                "meaning": "Same-day diagnostic sign, not a forecast or tradable position",
                "methodology": "Compare the same day's observed return with a supplied threshold; no performance claim"},
               {**common, **series, "result_id": "weights", "kind": "weights", "unit": "fraction_nav", "weight_semantics": "signed_nav_exposure", "hypothetical": True, "observations": weights,
                "meaning": "Illustrative signed hypothetical NAV exposures, never applied to returns",
                "methodology": "Apply supplied +0.6/-0.4 exposure illustration to same-day diagnostic signs; not a backtest"}
           ]}
with open("gamma_analytics.json", "w", encoding="utf-8") as handle:
    json.dump(payload, handle, allow_nan=False, indent=2)
with open("computed_returns.csv", "w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=["date", "value"])
    writer.writeheader()
    writer.writerows(returns)
chart_points = " ".join(str(20 + i * 680 / max(len(returns) - 1, 1)) + "," + str(120 - row["value"] * 2000) for i, row in enumerate(returns))
with open("returns.svg", "w", encoding="utf-8") as handle:
    handle.write('<svg width="720" height="240" viewBox="0 0 720 240"><polyline fill="none" stroke="steelblue" points="' + chart_points + '"/></svg>')
with open("standalone.txt", "w", encoding="utf-8") as handle:
    handle.write("Three copied inputs read successfully; no Gamma imports or network calls.")
print("LIVE_LIFECYCLE_OK", len(returns), "calculated returns; supplied multiplier", settings["return_multiplier"])
'''


@pytest.mark.live_network
@pytest.mark.skipif(os.getenv("GAMMA_RUN_LIVE_SCRIPT_E4_LIFECYCLE") != "true", reason="Explicit live lifecycle opt-in required")
def test_live_complete_script_lifecycle(monkeypatch):
    """Three real executions, one configured owning-provider acquisition; no host source execution."""
    from dotenv import dotenv_values
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api.routes.research import router
    from src.api.session_auth import GammaSessionMiddleware
    from src.api.schemas.research import StrategyLabAnalyzeResponseModel
    from src.application.runtime import build_runtime
    from src.models.research_lab import ImportedReturnStreamRequest
    from src.models.research_script import ResearchScriptDataExportRequest, ResearchScriptInputBundleRequest, ResearchScriptRevisionCreateRequest
    from src.services.saved_research_store import SavedResearchStore
    from src.utils.time import now_utc

    configured = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
    # Undo only pytest's safety pins for the expressly invoked owning provider.
    # These values come from the user's current configuration, not a fallback.
    providers = configured.get("RESEARCH_MARKET_DATA_PROVIDERS")
    if not providers or "mock" in providers:
        pytest.skip("Configured listed-history provider is absent/mock; no provider substitution permitted")
    monkeypatch.setenv("RESEARCH_MARKET_DATA_PROVIDERS", providers)
    monkeypatch.setenv("MOCK_DATA", configured.get("MOCK_DATA") or "false")
    root = Path("output/playwright/script-e4-live-lifecycle") / uuid4().hex[:12]
    root.mkdir(parents=True)
    runtime = build_runtime(cache_dir=root / "cache", history_dir=root / "history", sample_data_dir="sample_data")
    service = runtime.research_script_service
    capabilities = service.capabilities()
    assert capabilities.available and capabilities.executes_source, capabilities.sanitized_provider_status
    assert capabilities.model == "gpt-6.1-sol"
    evidence = {"started_at": now_utc().isoformat(), "model": capabilities.model, "runtime": capabilities.runtime_kind,
                "network_access": capabilities.network_access, "configured_history_providers": providers,
                "checks": {}, "runs": [], "limitations": ["This is not E3 model-driven Operator certification or cross-domain provider certification.", "Hypothetical weights remain standalone because no faithful owning-service mapping exists."]}
    checks = evidence["checks"]
    try:
        detail = service.create_script(ResearchScriptCreateRequest(session_id="e4-live-lifecycle", title="Live SPY + supplied files acceptance", source=LIFECYCLE_SOURCE))
        external = service.create_input_bundle(detail.script.script_id, ResearchScriptInputBundleRequest(input_files=[
            ResearchScriptInputFileCreateRequest("settings.json", "application/json", b'{"return_multiplier":1.0}'),
            ResearchScriptInputFileCreateRequest("rules.csv", "text/csv", b"rule,value\nthreshold,0.0\nlong_weight,0.6\nshort_weight,-0.4\n"),
        ]))
        identity = next(key for key, item in service.dataset_catalog.equities().items() if item.symbol == "SPY")
        selection = ResearchScriptDataExportRequest(domain="equity_history", object_id=identity, logical_filename="spy.json", lookback_days=40, frequency="daily")
        preview = service.dataset_catalog.preview(detail.script.script_id, selection)
        from dataclasses import replace
        bundle = service.export_domain_input(detail.script.script_id, replace(selection, preview_id=preview["preview_id"], base_snapshot_id=external.snapshot_id))
        copied = service.store.load_input_contents(bundle)
        dataset = json.loads(copied["spy.json"])
        assert dataset["data"]["source_provider"] not in {"mock", "gamma_mock"}, dataset["data"]["source_provider"]
        evidence["dataset"] = {"identity": identity, "metadata": dataset["metadata"], "provider": dataset["data"]["source_provider"], "point_count": len(dataset["data"]["points"])}
        assert len(bundle.files) == 3
        checks["real_gamma_dataset_plus_external_json_csv"] = True
        run = service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest(input_snapshot_id=bundle.snapshot_id))
        evidence["runs"].append(asdict(run))
        assert run.status == "completed", run.warnings
        assert run.usage["executed_code"] and run.usage["executes_source"] and not run.usage["network_access"]
        assert any(o.kind == "log" and "LIVE_LIFECYCLE_OK" in (o.text or "") for o in run.outputs)
        assert run.source_sha256 == detail.revisions[0].source_sha256 and run.input_manifest_sha256 == bundle.manifest_sha256
        assert {o.filename for o in run.outputs} >= {"gamma_analytics.json", "computed_returns.csv", "returns.svg", "standalone.txt"}
        checks["isolated_python_and_retained_table_image_file_logs"] = True

        app = FastAPI(); app.include_router(router)
        app.add_middleware(GammaSessionMiddleware, session_token="test-gamma-session")
        app.state.runtime = runtime
        client = TestClient(app)
        path = f"/research/strategy-lab/script-runs/{run.run_id}/analytics"
        report = client.get(path).json()
        artifact = report["artifacts"][0]
        assert artifact["valid"] and artifact["eligible"], artifact
        assert {i["result"]["kind"] for i in artifact["results"]} == {"returns", "metric", "signals", "weights"}
        assert [i["can_open"] for i in artifact["results"]] == [True, False, False, False]
        item = artifact["results"][0]
        body = dict(output_id=artifact["output_id"], result_id="returns", preview_sha256=item["preview_sha256"])
        response = client.post(path + "/open", json=body)
        assert response.status_code == 200, response.text
        analysis = response.json()
        points = dataset["data"]["points"]
        expected = [b["close"] / a["close"] - 1 for a, b in zip(points, points[1:])]
        assert [p["value"] for p in analysis["returns_points"]] == pytest.approx(expected, abs=1e-14)
        assert analysis["metrics"]["total_return"] == pytest.approx(math.prod(1 + r for r in expected) - 1, abs=1e-14)
        assert artifact["results"][1]["result"]["value"] == pytest.approx(points[-1]["close"] / points[0]["close"] - 1, abs=1e-14)
        expected_signals = [1 if value > 0 else -1 if value < 0 else 0 for value in expected]
        assert [p["value"] for p in artifact["results"][2]["result"]["observations"]] == expected_signals
        assert [p["value"] for p in artifact["results"][3]["result"]["observations"]] == [.6 if value > 0 else -.4 if value < 0 else 0 for value in expected_signals]
        owner = runtime.research_service.analyze_strategy_lab(ImportedReturnStreamRequest(rows=item["mapping"]["rows"], date_column="date", value_column="value"))
        assert analysis["metrics"] == StrategyLabAnalyzeResponseModel.from_domain(owner).model_dump(mode="json")["metrics"]
        checks["all_four_result_kinds_and_exact_owner_independent_numeric_fidelity"] = True

        assert runtime.research_service.list_saved_research() == []
        assert client.post(path + "/open", json=body).status_code == 200
        assert runtime.research_service.list_saved_research() == []
        save_body = dict(object_type="strategy_lab", title="Explicit live acceptance save", payload=analysis, source_provider="gamma_script_analytics")
        saved_response = client.post("/research/saved", json=save_body)
        assert saved_response.status_code == 200, saved_response.text
        saved = saved_response.json()
        changed = deepcopy(save_body); changed["payload"]["returns_points"][0]["value"] = .99
        assert client.post("/research/saved", json=changed).status_code == 422
        assert client.post(path + "/open", json={**body, "preview_sha256": "0" * 64}).status_code == 422
        checks["temporary_open_repeated_actions_separate_save_tamper_refusal"] = True

        # Use the actual owning store location rather than assuming the path layout.
        reopened_owner = ResearchService(None, SavedResearchStore(runtime.research_service.saved_store.base_dir))
        restarted = ResearchScriptService(ResearchScriptStore(service.store.base_dir), service.runtime, research_service=reopened_owner)
        assert inspect_analytics(restarted, run.run_id) == report
        reopened = reopened_owner.load_saved_research(saved["id"])
        assert reopened.payload["analytical_provenance"] == analysis["analytical_provenance"]
        service.create_revision(run.script_id, ResearchScriptRevisionCreateRequest("print('later source edit; not executed')", run.source_sha256))
        later_bundle = service.create_input_bundle(run.script_id, ResearchScriptInputBundleRequest(base_snapshot_id=bundle.snapshot_id,
            input_files=[ResearchScriptInputFileCreateRequest("later.txt", "text/plain", b"Not used by the retained run")]))
        assert later_bundle.manifest_sha256 != bundle.manifest_sha256
        assert inspect_analytics(restarted, run.run_id) == report
        filename, content = restarted.export_run_bundle(run.run_id)
        (root / filename).write_bytes(content)
        (root / "saved-analysis.json").write_text(json.dumps(saved, indent=2), encoding="utf-8")
        (root / "analytical-validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        checks["restart_later_edits_input_changes_and_provenance_export"] = True

        for title, source, invalid in [
            ("Ordinary Python standalone", 'print("ORDINARY_STANDALONE_OK")\nwith open("ordinary.txt", "w") as handle:\n    handle.write("No analytical contract required")\n', False),
            ("Invalid optional output standalone", 'print("INVALID_OPTIONAL_EXECUTION_OK")\nwith open("gamma_analytics.json", "w") as handle:\n    handle.write(\'{"contract_version":"unsupported"}\')\nwith open("ordinary.txt", "w") as handle:\n    handle.write("Valid standalone file survives invalid optional output")\n', True),
        ]:
            plain_detail = service.create_script(ResearchScriptCreateRequest("e4-live-lifecycle", title, source))
            plain_run = service.create_run(plain_detail.script.script_id, ResearchScriptRunCreateRequest())
            evidence["runs"].append(asdict(plain_run))
            assert plain_run.status == "completed", plain_run.warnings
            assert any(o.filename == "ordinary.txt" for o in plain_run.outputs)
            assert any(o.kind == "log" and "_OK" in (o.text or "") for o in plain_run.outputs)
            plain_report = inspect_analytics(service, plain_run.run_id)
            if invalid:
                assert plain_report["artifacts"] and not plain_report["artifacts"][0]["valid"]
                assert not plain_report["artifacts"][0]["eligible"]
                from src.application.research_script_service import ResearchScriptValidationError
                with pytest.raises(ResearchScriptValidationError):
                    open_analytics(service, plain_run.run_id, plain_report["artifacts"][0]["output_id"], "returns", "0" * 64)
            else:
                assert plain_report["artifacts"] == []
            _, content = service.export_run_bundle(plain_run.run_id)
            (root / f"{'invalid' if invalid else 'ordinary'}-run.zip").write_bytes(content)
        checks["ordinary_python_without_contract"] = True
        checks["invalid_optional_output_preserves_completed_python_logs_files"] = True
        evidence["status"] = "passed"
        evidence["expected_total_return"] = math.prod(1 + r for r in expected) - 1
        evidence["actual_total_return"] = analysis["metrics"]["total_return"]
    except BaseException as exc:
        evidence["failure"] = f"{type(exc).__name__}: {exc}"[:4000]
        raise
    finally:
        evidence["finished_at"] = now_utc().isoformat()
        (root / "evidence.json").write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
        runtime.shutdown()
        print(json.dumps({"evidence": str(root.resolve()), "status": evidence.get("status", "incomplete"), "checks": checks}, indent=2))
