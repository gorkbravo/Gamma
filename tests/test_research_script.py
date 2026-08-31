from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import src.application.research_script_service as research_script_service_module
from src.api.main import create_app
from src.application.research_script_service import (
    ResearchScriptConflictError,
    ResearchScriptService,
    ResearchScriptValidationError,
)
from src.application.runtime import build_runtime
from src.models.research_script import (
    ResearchScriptCreateRequest,
    ResearchScriptDataExportRequest,
    ResearchScriptInputFileCreateRequest,
    ResearchScriptRevisionCreateRequest,
    ResearchScriptRunCreateRequest,
)
from src.services.research_script_runtime import MockResearchScriptRuntime, ResearchScriptRuntimeOutput
from src.services.research_script_store import ResearchScriptStore, ResearchScriptStoreCorruptionError


SOURCE = "# research-only fixture\nprint('this text is never executed')\n"


def make_service(base_dir: Path, *, run_history_limit: int = 100) -> ResearchScriptService:
    return ResearchScriptService(
        ResearchScriptStore(base_dir=base_dir, run_history_limit=run_history_limit),
        MockResearchScriptRuntime(),
    )


class FakeEquitySeries:
    empty = False

    def rename(self, _name: str):
        return self

    def to_csv(self, *, index_label: str) -> str:
        assert index_label == "date"
        return "date,close\n2026-08-28,100.0\n2026-08-29,101.5\n"


class FakeResearchProvider:
    def load_symbol_history(self, symbol: str, lookback_days: int):
        assert (symbol, lookback_days) == ("SPY", 40)
        return FakeEquitySeries()


class FakeMacroService:
    def get_series_history(self, series_id: str, **kwargs):
        assert series_id == "CPI"
        assert kwargs == {"region": "US", "timeframe": "1Y", "force_refresh": False}
        return SimpleNamespace(
            series_id="CPI",
            frequency="monthly",
            source_provider="gamma_macro_fixture",
            retrieved_at=datetime(2026, 8, 30),
            points=[SimpleNamespace(timestamp=datetime(2026, 7, 1), value=3.1)],
        )


@dataclass(frozen=True)
class FakeSavedResearch:
    id: str = "saved-1"
    object_type: str = "equity_note"
    title: str = "Bounded note"
    source_provider: str = "gamma_fixture"
    retrieved_at: datetime = datetime(2026, 8, 30)
    updated_at: datetime = datetime(2026, 8, 30)
    warnings: tuple[str, ...] = ()


class FakeSavedResearchService:
    def load_saved_research(self, object_id: str):
        return FakeSavedResearch() if object_id == "saved-1" else None


def create_script(service: ResearchScriptService, source: str = SOURCE):
    return service.create_script(
        ResearchScriptCreateRequest(
            session_id="test-session",
            title="Quality factor preview",
            source=source,
        )
    )


def test_create_and_revise_preserves_immutable_source_and_exact_hash(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    initial = create_script(service)
    first = initial.revisions[0]
    next_source = f"{SOURCE}# revision two\n"

    revised = service.create_revision(
        initial.script.script_id,
        ResearchScriptRevisionCreateRequest(
            source=next_source,
            expected_parent_sha256=first.source_sha256,
            change_summary="Add a visible research note",
        ),
    )

    assert first.source == SOURCE
    assert first.source_sha256 == service.source_sha256(SOURCE)
    assert revised.revisions[0] == first
    assert revised.revisions[1].parent_revision_id == first.revision_id
    assert revised.revisions[1].source_sha256 == service.source_sha256(next_source)
    assert revised.script.canonical_revision_id == revised.revisions[1].revision_id

    reopened = service.get_script(initial.script.script_id)
    assert [item.source for item in reopened.revisions] == [SOURCE, next_source]


def test_revision_conflict_and_source_limits_are_explicit(tmp_path: Path, monkeypatch) -> None:
    service = make_service(tmp_path)
    initial = create_script(service)

    with pytest.raises(ResearchScriptValidationError, match="Only user-authored"):
        service.create_script(
            ResearchScriptCreateRequest(
                session_id="test-session",
                title="Deferred Operator draft",
                source=SOURCE,
                created_by="operator",
            )
        )

    with pytest.raises(ResearchScriptConflictError):
        service.create_revision(
            initial.script.script_id,
            ResearchScriptRevisionCreateRequest(
                source=f"{SOURCE}# stale\n",
                expected_parent_sha256="0" * 64,
            ),
        )

    monkeypatch.setattr(research_script_service_module, "MAX_RESEARCH_SCRIPT_SOURCE_BYTES", 8)
    with pytest.raises(ResearchScriptValidationError, match="source exceeds"):
        create_script(service, source="x" * 9)


def test_input_snapshot_hashes_content_and_rejects_unsafe_names(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    detail = create_script(service)
    run = service.create_run(
        detail.script.script_id,
        ResearchScriptRunCreateRequest(
            input_files=[
                ResearchScriptInputFileCreateRequest(
                    logical_filename="prices.csv",
                    media_type="text/csv",
                    content=b"date,close\n2026-01-01,100\n",
                )
            ],
            dataset_refs=[{"dataset_id": "mock-prices", "version": "v1"}],
            source_refs=[{"provider": "fixture", "as_of": "2026-01-01"}],
        ),
    )
    snapshot = service.store.load_input_snapshot(run.input_snapshot_id)

    assert snapshot is not None
    assert snapshot.files[0].content_sha256
    assert snapshot.manifest_sha256 == run.input_manifest_sha256
    assert snapshot.total_bytes == len(b"date,close\n2026-01-01,100\n")

    stored_input = service.store.inputs_dir / snapshot.snapshot_id / "files" / "prices.csv"
    stored_input.write_bytes(b"tampered")
    with pytest.raises(ResearchScriptStoreCorruptionError, match="immutable manifest"):
        service.create_run(
            detail.script.script_id,
            ResearchScriptRunCreateRequest(input_snapshot_id=snapshot.snapshot_id),
        )

    for unsafe_filename in ("../secret.txt", "prices.csv:secret", "CON"):
        with pytest.raises(ResearchScriptValidationError, match="Unsafe input filename"):
            service.create_run(
                detail.script.script_id,
                ResearchScriptRunCreateRequest(
                    input_files=[
                        ResearchScriptInputFileCreateRequest(
                            logical_filename=unsafe_filename,
                            media_type="text/plain",
                            content=b"blocked",
                        )
                    ]
                ),
            )


def test_named_limits_enforce_input_and_output_bounds(tmp_path: Path, monkeypatch) -> None:
    service = make_service(tmp_path)
    detail = create_script(service)
    limits = service.limits()
    assert limits["source_bytes"] == 64 * 1024
    assert limits["run_duration_seconds"] == 120
    assert limits["output_artifacts"] == 32
    assert limits["total_output_bytes"] == 64 * 1024 * 1024
    assert limits["stored_run_history"] == 100

    monkeypatch.setattr(research_script_service_module, "MAX_RESEARCH_SCRIPT_INDIVIDUAL_INPUT_BYTES", 3)
    with pytest.raises(ResearchScriptValidationError, match="Input file .* exceeds 3 bytes"):
        service.create_run(
            detail.script.script_id,
            ResearchScriptRunCreateRequest(
                input_files=[
                    ResearchScriptInputFileCreateRequest(
                        logical_filename="too-large.txt",
                        media_type="text/plain",
                        content=b"four",
                    )
                ]
            ),
        )

    outputs = [
        ResearchScriptRuntimeOutput(
            output_id=f"output-{index}",
            kind="log",
            sequence=index,
            media_type="text/plain",
            text="bounded",
        )
        for index in (1, 2)
    ]
    monkeypatch.setattr(research_script_service_module, "MAX_RESEARCH_SCRIPT_OUTPUT_ARTIFACTS", 1)
    with pytest.raises(ResearchScriptValidationError, match="output count exceeds 1"):
        service._normalize_outputs("test-run", outputs, datetime(2026, 8, 29))

    monkeypatch.setattr(research_script_service_module, "MAX_RESEARCH_SCRIPT_OUTPUT_ARTIFACTS", 32)
    monkeypatch.setattr(research_script_service_module, "MAX_RESEARCH_SCRIPT_TOTAL_OUTPUT_BYTES", 5)
    with pytest.raises(ResearchScriptValidationError, match="output exceeds 5 bytes"):
        service._normalize_outputs("test-run", outputs[:1], datetime(2026, 8, 29))


def test_mock_runs_are_deterministic_typed_and_never_execute_source(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    dangerous_text = "raise RuntimeError('would fail if executed')\n"
    detail = create_script(service, source=dangerous_text)

    first = service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest())
    second = service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest())

    assert first.status == "completed"
    assert first.source_sha256 == service.source_sha256(dangerous_text)
    assert first.provider_response_id == second.provider_response_id
    assert first.runtime_kind == "mock_safe_preview"
    assert first.usage["executed_code"] is False
    assert first.usage["network_access"] is False
    assert [item.kind for item in first.outputs] == ["log", "metric", "table", "image", "file", "warning"]
    assert first.outputs[1].metric_value == len(dangerous_text.encode("utf-8"))
    assert first.outputs[2].rows == second.outputs[2].rows
    assert all("Safe preview" in warning or "safe preview" in warning for warning in first.warnings)


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("failed", "failed"),
        ("timed_out", "timed_out"),
        ("unavailable", "unavailable"),
        ("incomplete", "incomplete"),
    ],
)
def test_mock_terminal_states_are_persisted(
    tmp_path: Path,
    scenario: str,
    expected: str,
) -> None:
    service = make_service(tmp_path / scenario)
    detail = create_script(service)
    run = service.create_run(
        detail.script.script_id,
        ResearchScriptRunCreateRequest(runtime_scenario=scenario),  # type: ignore[arg-type]
    )

    assert run.status == expected
    assert service.get_run(run.run_id) == run
    if scenario == "incomplete":
        assert [item.output_id for item in run.outputs] == ["output-source-association-error"]
        assert "withheld" in (run.outputs[0].text or "")


def test_store_recovers_after_restart_prunes_history_and_quarantines_corruption(tmp_path: Path) -> None:
    service = make_service(tmp_path, run_history_limit=2)
    detail = create_script(service)
    run_ids = [
        service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest()).run_id
        for _ in range(3)
    ]

    restarted = make_service(tmp_path, run_history_limit=2)
    reopened = restarted.get_script(detail.script.script_id)
    runs = restarted.list_runs(detail.script.script_id)
    assert reopened.script.script_id == detail.script.script_id
    assert len(runs) == 2
    assert run_ids[-1] in {item.run_id for item in runs}

    broken_path = restarted.store.scripts_dir / "broken.json"
    broken_path.write_text("{not-json", encoding="utf-8")
    assert all(item.script_id != "broken" for item in restarted.list_scripts())
    assert any("malformed research_script" in item for item in restarted.store.storage_warnings)
    assert any(path.name.startswith("broken.json.malformed") for path in restarted.store.quarantine_dir.rglob("*"))

    surviving_path = restarted.store.scripts_dir / f"{detail.script.script_id}.json"
    temp_path = surviving_path.with_name(f"{surviving_path.name}.tmp")
    temp_path.write_text(surviving_path.read_text(encoding="utf-8"), encoding="utf-8")
    recovered = ResearchScriptStore(base_dir=tmp_path, run_history_limit=2)
    assert recovered.load_script(detail.script.script_id) is not None
    assert any("authoritative record exists" in item for item in recovered.storage_warnings)

    orphaned_bytes = recovered.inputs_dir / "orphan" / "files" / "input.csv.tmp"
    orphaned_bytes.parent.mkdir(parents=True, exist_ok=True)
    orphaned_bytes.write_bytes(b"partial")
    recovered_again = ResearchScriptStore(base_dir=tmp_path, run_history_limit=2)
    assert not orphaned_bytes.exists()
    assert any("interrupted artifact write" in item for item in recovered_again.storage_warnings)


def test_slice_five_domain_exports_are_bounded_and_provenanced(tmp_path: Path) -> None:
    service = ResearchScriptService(
        ResearchScriptStore(base_dir=tmp_path),
        MockResearchScriptRuntime(),
        research_provider=FakeResearchProvider(),
        research_service=FakeSavedResearchService(),
        macro_service=FakeMacroService(),
    )
    detail = create_script(service)
    requests = [
        ResearchScriptDataExportRequest(
            domain="equity_history",
            object_id="spy",
            logical_filename="spy.csv",
            lookback_days=40,
            frequency="daily",
        ),
        ResearchScriptDataExportRequest(
            domain="macro_series",
            object_id="CPI",
            logical_filename="cpi.csv",
            region="US",
            timeframe="1Y",
        ),
        ResearchScriptDataExportRequest(
            domain="saved_research",
            object_id="saved-1",
            logical_filename="saved.json",
        ),
    ]

    snapshots = [service.export_domain_input(detail.script.script_id, request) for request in requests]

    assert [snapshot.files[0].logical_filename for snapshot in snapshots] == [
        "spy.csv",
        "cpi.csv",
        "saved.json",
    ]
    assert all(snapshot.files[0].source_kind == "gamma_state" for snapshot in snapshots)
    assert all(snapshot.manifest_sha256 for snapshot in snapshots)
    assert [snapshot.dataset_refs[0]["domain"] for snapshot in snapshots] == [
        "equity_history",
        "macro_series",
        "saved_research",
    ]
    saved_bytes = service.store.load_input_contents(snapshots[-1])["saved.json"]
    assert b'"title": "Bounded note"' in saved_bytes
    assert b"api_key" not in saved_bytes


def test_slice_five_lifecycle_comparison_export_and_cleanup(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    detail = create_script(service)
    first = service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest())
    second = service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest())

    comparison = service.compare_runs(first.run_id, second.run_id)
    assert comparison.same_revision is True
    assert comparison.output_count_delta == 0
    assert comparison.metric_deltas[0]["delta"] == 0.0

    filename, bundle_bytes = service.export_run_bundle(first.run_id)
    assert filename.endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(bundle_bytes)) as bundle:
        names = set(bundle.namelist())
        assert {"source.py", "input/manifest.json", "run.json", "README.txt"} <= names
        assert any(name.startswith("outputs/") for name in names)
        assert bundle.read("source.py") == SOURCE.encode("utf-8")

    duplicate = service.duplicate_script(detail.script.script_id)
    assert duplicate.script.script_id != detail.script.script_id
    assert duplicate.revisions[0].source == SOURCE
    archived = service.archive_script(detail.script.script_id)
    assert archived.script.status == "archived"
    assert detail.script.script_id not in {item.script_id for item in service.list_scripts()}
    assert detail.script.script_id in {
        item.script_id for item in service.list_scripts(include_archived=True)
    }
    with pytest.raises(ResearchScriptConflictError, match="Restore"):
        service.create_run(detail.script.script_id, ResearchScriptRunCreateRequest())
    assert service.restore_script(detail.script.script_id).script.status == "active"

    orphan_dir = service.store.outputs_dir / "orphan-safe-id"
    orphan_dir.mkdir()
    (orphan_dir / "stale.csv").write_bytes(b"stale")
    assert service.storage_diagnostics().orphan_output_count == 1
    cleaned = service.cleanup_retained_outputs()
    assert cleaned.orphan_output_count == 0
    assert not orphan_dir.exists()
    assert cleaned.retained_output_count > 0


@pytest.mark.parametrize(
    "source",
    [
        "import requests\nrequests.get('https://example.com')\n",
        "import os\nprint(os.getenv('OPENAI_API_KEY'))\n",
        "open('../outside.txt').read()\n",
        "print((1).__class__.__mro__)\n",
        "import subprocess\nsubprocess.run(['python'])\n",
    ],
)
def test_slice_five_escape_sources_fail_before_runtime_dispatch(tmp_path: Path, source: str) -> None:
    service = make_service(tmp_path)

    with pytest.raises(ResearchScriptValidationError):
        create_script(service, source=source)

    assert service.list_scripts() == []


def test_route_vertical_slice_and_conflicts(tmp_path: Path) -> None:
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir=Path("sample_data"),
    )
    client = TestClient(create_app(runtime))
    created = client.post(
        "/research/strategy-lab/scripts",
        json={"session_id": "route-session", "title": "Route script", "source": SOURCE},
    )
    assert created.status_code == 201
    detail = created.json()
    script_id = detail["script"]["script_id"]
    first_hash = detail["revisions"][0]["source_sha256"]

    assert client.get("/research/strategy-lab/scripts").json()["items"][0]["script_id"] == script_id
    capabilities = client.get("/research/strategy-lab/scripts/runtime-capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["configured_runtime"] == "mock"
    assert capabilities.json()["available"] is True
    assert capabilities.json()["network_access"] is False
    assert client.get(f"/research/strategy-lab/scripts/{script_id}").status_code == 200

    conflict = client.post(
        f"/research/strategy-lab/scripts/{script_id}/revisions",
        json={"source": f"{SOURCE}# changed\n", "expected_parent_sha256": "0" * 64},
    )
    assert conflict.status_code == 409

    revised = client.post(
        f"/research/strategy-lab/scripts/{script_id}/revisions",
        json={"source": f"{SOURCE}# changed\n", "expected_parent_sha256": first_hash},
    )
    assert revised.status_code == 201
    revision = revised.json()["revisions"][-1]

    ran = client.post(
        f"/research/strategy-lab/scripts/{script_id}/runs",
        json={
            "revision_id": revision["revision_id"],
            "input_files": [
                {"logical_filename": "input.csv", "media_type": "text/csv", "content": "x,y\n1,2\n"}
            ],
        },
    )
    assert ran.status_code == 201
    run = ran.json()
    assert run["source_sha256"] == revision["source_sha256"]
    assert run["input_manifest_sha256"]
    assert run["runtime_kind"] == "mock_safe_preview"
    assert {item["kind"] for item in run["outputs"]} >= {"log", "table", "image", "metric"}

    listed = client.get(f"/research/strategy-lab/scripts/{script_id}/runs")
    fetched = client.get(f"/research/strategy-lab/script-runs/{run['run_id']}")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["run_id"] == run["run_id"]
    assert fetched.status_code == 200
    assert fetched.json()["run_id"] == run["run_id"]
    image_output = next(item for item in run["outputs"] if item["kind"] == "image")
    downloaded = client.get(
        f"/research/strategy-lab/script-runs/{run['run_id']}/outputs/{image_output['output_id']}"
    )
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("image/svg+xml")
    assert downloaded.content.startswith(b"<svg")
    input_snapshot = client.get(
        f"/research/strategy-lab/script-inputs/{run['input_snapshot_id']}"
    )
    assert input_snapshot.status_code == 200
    assert input_snapshot.json()["manifest_sha256"] == run["input_manifest_sha256"]
    second_run = client.post(
        f"/research/strategy-lab/scripts/{script_id}/runs",
        json={"revision_id": revision["revision_id"], "input_snapshot_id": run["input_snapshot_id"]},
    )
    assert second_run.status_code == 201
    compared = client.get(
        "/research/strategy-lab/script-runs/compare",
        params={"base_run_id": run["run_id"], "comparison_run_id": second_run.json()["run_id"]},
    )
    assert compared.status_code == 200
    assert compared.json()["same_revision"] is True
    exported = client.get(f"/research/strategy-lab/script-runs/{run['run_id']}/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(io.BytesIO(exported.content)) as bundle:
        assert "source.py" in bundle.namelist()

    duplicate = client.post(
        f"/research/strategy-lab/scripts/{script_id}/duplicate",
        json={"title": "Route script copy"},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["script"]["script_id"] != script_id
    assert client.post(f"/research/strategy-lab/scripts/{script_id}/archive").status_code == 200
    assert script_id not in {
        item["script_id"] for item in client.get("/research/strategy-lab/scripts").json()["items"]
    }
    archived_items = client.get(
        "/research/strategy-lab/scripts", params={"include_archived": True}
    ).json()["items"]
    assert script_id in {item["script_id"] for item in archived_items}
    assert client.post(f"/research/strategy-lab/scripts/{script_id}/restore").status_code == 200
    diagnostics = client.get("/research/strategy-lab/scripts/storage-diagnostics")
    assert diagnostics.status_code == 200
    assert diagnostics.json()["run_count"] >= 2
    assert client.post("/research/strategy-lab/scripts/storage-diagnostics/cleanup").status_code == 200
    assert client.get(
        f"/research/strategy-lab/script-runs/{run['run_id']}/outputs/missing"
    ).status_code == 404
    assert client.get("/research/strategy-lab/scripts/missing").status_code == 404

    runtime.shutdown()
