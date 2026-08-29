from __future__ import annotations

from datetime import datetime
from pathlib import Path

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
    assert client.get(
        f"/research/strategy-lab/script-runs/{run['run_id']}/outputs/missing"
    ).status_code == 404
    assert client.get("/research/strategy-lab/scripts/missing").status_code == 404

    runtime.shutdown()
