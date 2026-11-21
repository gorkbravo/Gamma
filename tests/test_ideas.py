"""Workstream 12 - Ideas, checkpoint I1: models, store and routes."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.application.idea_service import (
    IdeaCreateRequest,
    IdeaEvidenceCreateRequest,
    IdeaPatchRequest,
    IdeaService,
)
from src.application.runtime import build_runtime
from src.models.handoff import CrossTabHandoffEnvelope, HandoffEntity, HandoffTimeframe
from src.models.ideas import (
    CAPTURED_SERIES_MAX_POINTS,
    CAPTURED_VALUES_MAX_BYTES,
    IDEA_SCHEMA_VERSION,
    Idea,
    IdeaEvidence,
    IdeaJournalEntry,
    IdeaLeg,
    IdeaLifecycleError,
    IdeaOrigin,
    IdeaValidationError,
    assert_journal_append_only,
    downsample_series_points,
    freeze_captured_values,
    prepare_captured_values,
)
from src.models.provenance import ProvenanceRecord
from src.services.idea_store import DEFAULT_IDEA_MIGRATIONS, IdeaStore

T0 = datetime(2026, 11, 14, 9, 30)


class _Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        self.now = self.now + timedelta(seconds=1)
        return self.now


def _ids():
    counter = iter(range(1, 10_000))
    return lambda: f"id{next(counter):04d}"


def _service(tmp_path, store: IdeaStore | None = None) -> IdeaService:
    return IdeaService(store or IdeaStore(tmp_path / "ideas"), clock=_Clock(), id_factory=_ids())


def _entity(symbol: str = "XOM") -> HandoffEntity:
    return HandoffEntity(entity_type="equity", label=f"{symbol} Corp", normalized_id=symbol, metadata={"symbol": symbol})


def _reopen(tab: str = "fundamentals", mode: str | None = "overview", symbol: str = "XOM") -> CrossTabHandoffEnvelope:
    return CrossTabHandoffEnvelope(
        source_tab=tab,
        source_mode=mode,
        intended_target_tab=tab,
        intended_target_mode=mode,
        selected_entity=_entity(symbol),
        selected_timeframe=HandoffTimeframe(label="1Y"),
        normalized_ids={"symbol": symbol},
        timestamp=T0,
    )


def _provenance() -> ProvenanceRecord:
    return ProvenanceRecord(
        source_provider="sec_edgar",
        retrieved_at=T0 - timedelta(minutes=5),
        origin="fundamentals_service.overview",
        transformation_note="TTM sum of the last four 10-Q filings.",
    )


def _pin_request(stance: str = "supports", **overrides) -> IdeaEvidenceCreateRequest:
    payload = dict(
        kind="metric",
        stance=stance,
        title="XOM free cash flow",
        captured_values={"metrics": [{"label": "FCF TTM", "value": 36.1e9, "display": "$36.1B"}]},
        provenance=_provenance(),
        reopen=_reopen(),
    )
    payload.update(overrides)
    return IdeaEvidenceCreateRequest(**payload)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def test_evidence_requires_a_stance_and_freezes_captured_values():
    with pytest.raises(IdeaValidationError, match="stance is required"):
        IdeaEvidence(evidence_id="e1", idea_id="i1", kind="metric", stance="", title="FCF")
    with pytest.raises(IdeaValidationError, match="stance"):
        IdeaEvidence(evidence_id="e1", idea_id="i1", kind="metric", stance="bullish", title="FCF")

    raw = {"metrics": [{"label": "FCF", "value": 1.5}], "table": {"columns": ["a"], "rows": [[1]]}}
    evidence = IdeaEvidence(evidence_id="e1", idea_id="i1", kind="metric", stance="challenges", title="FCF", captured_values=raw)
    raw["metrics"][0]["value"] = 99.0  # mutating the caller's dict must not reach the pin
    assert evidence.captured_values["metrics"][0]["value"] == 1.5
    with pytest.raises(TypeError):
        evidence.captured_values["metrics"] = ()  # type: ignore[index]
    with pytest.raises(TypeError):
        evidence.captured_values["metrics"][0]["value"] = 2.0  # type: ignore[index]
    assert isinstance(evidence.captured_values["table"]["rows"], tuple)
    with pytest.raises(FrozenInstanceError):
        evidence.stance = "supports"  # type: ignore[misc]
    assert evidence.to_dict()["captured_values"] == {"metrics": [{"label": "FCF", "value": 1.5}], "table": {"columns": ["a"], "rows": [[1]]}}


def test_captured_values_are_bounded():
    with pytest.raises(IdeaValidationError, match="bytes"):
        freeze_captured_values({"rows": [{"text": "x" * 1_500} for _ in range(20)]})
    with pytest.raises(IdeaValidationError, match="non-finite"):
        freeze_captured_values({"value": float("nan")})
    with pytest.raises(IdeaValidationError, match="deeper"):
        freeze_captured_values({"a": {"b": {"c": {"d": {"e": {"f": {"g": 1}}}}}}})
    with pytest.raises(IdeaValidationError, match="unsupported"):
        freeze_captured_values({"value": object()})
    assert len(json.dumps({"x": "y" * 100})) < CAPTURED_VALUES_MAX_BYTES


def test_series_is_downsampled_with_the_method_recorded():
    points = [{"timestamp": f"2026-01-{index:03d}", "value": float(index)} for index in range(1, 1_001)]
    kept, note = downsample_series_points(points, CAPTURED_SERIES_MAX_POINTS)
    assert len(kept) == CAPTURED_SERIES_MAX_POINTS
    assert kept[0] == points[0] and kept[-1] == points[-1]
    assert note == {"method": "uniform_stride_keep_endpoints", "original_points": 1_000, "kept_points": CAPTURED_SERIES_MAX_POINTS}

    prepared = prepare_captured_values({"series": {"label": "Brent", "points": points}})
    assert prepared["series"]["downsampling"]["original_points"] == 1_000
    assert len(prepared["series"]["points"]) == CAPTURED_SERIES_MAX_POINTS
    assert downsample_series_points(points[:10], CAPTURED_SERIES_MAX_POINTS) == (points[:10], None)


def test_idea_validates_stance_status_and_ownership():
    with pytest.raises(IdeaValidationError, match="title"):
        Idea(idea_id="i1", title="  ")
    with pytest.raises(IdeaValidationError, match="stance"):
        Idea(idea_id="i1", title="t", stance="bullish")
    with pytest.raises(IdeaValidationError, match="status"):
        Idea(idea_id="i1", title="t", status="open")
    with pytest.raises(IdeaValidationError, match="closed_at"):
        Idea(idea_id="i1", title="t", status="closed")
    foreign = IdeaEvidence(evidence_id="e1", idea_id="other", kind="note", stance="context", title="n")
    with pytest.raises(IdeaValidationError, match="belong"):
        Idea(idea_id="i1", title="t", evidence=(foreign,))
    with pytest.raises(IdeaValidationError, match="weight"):
        IdeaLeg(entity=_entity(), weight=float("inf"))
    idea = Idea(idea_id="i1", title="t", tags=("Energy", " energy ", "Rates"))
    assert idea.tags == ("energy", "rates")
    assert idea.schema_version == IDEA_SCHEMA_VERSION


def test_idea_round_trips_through_dict():
    evidence = IdeaEvidence(
        evidence_id="e1",
        idea_id="i1",
        kind="prediction_contract",
        stance="supports",
        title="Fed cut by March",
        captured_values={"metrics": [{"label": "Prob", "value": 0.78, "display": "78%"}]},
        provenance=_provenance(),
        reopen=_reopen("prediction_markets", "contract", "KXFED"),
        captured_at=T0,
    )
    entry = IdeaJournalEntry(entry_id="j1", idea_id="i1", kind="note", author="user", body="Watching the dots.", created_at=T0)
    idea = Idea(
        idea_id="i1",
        title="Energy outperforms",
        thesis="Refiners beat the index into Q1.",
        stance="relative",
        legs=(IdeaLeg(entity=_entity("XOM"), weight=1.0), IdeaLeg(entity=_entity("SPY"), weight=-1.0)),
        origin=IdeaOrigin(kind="sitrep_follow_up", source_ref="fu1", label="Brent +3%", handoff=_reopen("macro", "snapshot")),
        evidence=(evidence,),
        journal=(entry,),
        created_at=T0,
        updated_at=T0,
    )
    restored = Idea.from_dict(json.loads(json.dumps(idea.to_dict())))
    assert restored.to_dict() == idea.to_dict()
    assert restored.evidence[0].entity is not None and restored.evidence[0].entity.normalized_id == "KXFED"


def test_journal_is_append_only():
    first = IdeaJournalEntry(entry_id="j1", idea_id="i1", kind="note", author="user", body="one", created_at=T0)
    second = IdeaJournalEntry(entry_id="j2", idea_id="i1", kind="decision", author="user", body="two", created_at=T0)
    assert_journal_append_only((first,), (first, second))
    with pytest.raises(IdeaValidationError, match="removed"):
        assert_journal_append_only((first, second), (first,))
    edited = replace(first, body="edited")
    with pytest.raises(IdeaValidationError, match="edited"):
        assert_journal_append_only((first,), (edited, second))
    with pytest.raises(IdeaValidationError, match="user journal entry"):
        IdeaJournalEntry(entry_id="j3", idea_id="i1", kind="edited", author="user", body="x")
    with pytest.raises(IdeaValidationError, match="system journal entry"):
        IdeaJournalEntry(entry_id="j3", idea_id="i1", kind="note", author="system", body="x")


def test_timestamps_with_offsets_become_naive_utc():
    evidence = IdeaEvidence.from_dict(
        {
            "evidence_id": "e1",
            "idea_id": "i1",
            "kind": "metric",
            "stance": "context",
            "title": "x",
            "captured_at": "2026-11-14T10:30:00+01:00",
            "provenance": {"source_provider": "fred", "origin": "macro", "retrieved_at": "2026-11-14T09:00:00Z"},
            "reopen": {"source_tab": "macro", "intended_target_tab": "macro", "timestamp": "2026-11-14T09:00:00Z"},
        }
    )
    assert evidence.captured_at == datetime(2026, 11, 14, 9, 30)
    assert evidence.provenance is not None and evidence.provenance.retrieved_at.tzinfo is None
    assert evidence.reopen is not None and evidence.reopen.timestamp == datetime(2026, 11, 14, 9, 0)


# ---------------------------------------------------------------------------
# Service and store
# ---------------------------------------------------------------------------


def test_service_journals_every_change_and_runs_the_i1_lifecycle(tmp_path):
    service = _service(tmp_path)
    idea = service.create_idea(IdeaCreateRequest(title="Energy outperforms", stance="long"))
    assert idea.status == "draft"
    assert [entry.kind for entry in idea.journal] == ["created"]

    with pytest.raises(IdeaLifecycleError, match="thesis"):
        service.activate(idea.idea_id)

    unchanged = service.update_idea(idea.idea_id, IdeaPatchRequest(title="Energy outperforms"))
    assert len(unchanged.journal) == 1, "a no-op patch writes no journal entry"

    edited = service.update_idea(
        idea.idea_id,
        IdeaPatchRequest(thesis="Refiners beat SPY into Q1.", legs=(IdeaLeg(entity=_entity(), weight=1.0),), tags=("energy",)),
    )
    edit_entry = edited.journal[-1]
    assert edit_entry.kind == "edited" and edit_entry.author == "system"
    changed = {item["field"]: item for item in edit_entry.details["changes"]}
    assert changed["thesis"]["before"] == "" and changed["thesis"]["after"] == "Refiners beat SPY into Q1."
    assert set(changed) == {"thesis", "legs", "tags"}

    active = service.activate(idea.idea_id)
    assert active.status == "active"
    with pytest.raises(IdeaLifecycleError):
        service.activate(idea.idea_id)
    archived = service.archive(idea.idea_id)
    assert archived.status == "archived"
    restored = service.restore(idea.idea_id)
    assert restored.status == "active", "restore returns to the status the idea had when archived"
    kinds = [entry.kind for entry in restored.journal]
    assert kinds == ["created", "edited", "status_changed", "status_changed", "status_changed"]


def test_pin_and_unpin_keep_the_record_in_the_journal(tmp_path):
    service = _service(tmp_path)
    idea = service.create_idea(IdeaCreateRequest(title="Energy"))
    idea, supports = service.pin_evidence(idea.idea_id, _pin_request("supports"))
    idea, challenges = service.pin_evidence(idea.idea_id, _pin_request("challenges", title="Refining margins fall"))
    assert idea.evidence_counts() == {"supports": 1, "challenges": 1, "context": 0}
    assert supports.captured_at < challenges.captured_at
    assert supports.provenance == _provenance(), "provenance is stored exactly as captured"
    assert "from Fundamentals / overview" in idea.journal[-1].body

    idea = service.unpin_evidence(idea.idea_id, supports.evidence_id)
    assert [item.evidence_id for item in idea.evidence] == [challenges.evidence_id]
    assert idea.journal[-1].kind == "evidence_unpinned"
    assert "XOM free cash flow" in idea.journal[-1].body
    with pytest.raises(Exception, match="not found"):
        service.unpin_evidence(idea.idea_id, supports.evidence_id)


def test_store_refuses_a_journal_rewrite(tmp_path):
    store = IdeaStore(tmp_path / "ideas")
    service = _service(tmp_path, store)
    idea = service.add_journal_entry(service.create_idea(IdeaCreateRequest(title="x")).idea_id, kind="note", body="first")
    with pytest.raises(IdeaValidationError, match="append-only"):
        store.update(idea.idea_id, lambda current: replace(current, journal=current.journal[:1]))
    assert len(store.require(idea.idea_id).journal) == 2


def test_store_survives_a_restart_and_reuses_a_consistent_index(tmp_path):
    base = tmp_path / "ideas"
    service = _service(tmp_path, IdeaStore(base))
    first = service.create_idea(IdeaCreateRequest(title="First", thesis="One."))
    second = service.create_idea(IdeaCreateRequest(title="Second", tags=("rates",)))
    service.pin_evidence(first.idea_id, _pin_request("context"))
    service.activate(first.idea_id)

    restarted = IdeaStore(base)
    assert restarted.index_rebuilt is False, "a consistent index.json is reused at start"
    summaries = {item.idea_id: item for item in restarted.list_summaries()}
    assert set(summaries) == {first.idea_id, second.idea_id}
    assert summaries[first.idea_id].status == "active"
    assert summaries[first.idea_id].evidence_counts["context"] == 1
    reloaded = restarted.require(first.idea_id)
    assert reloaded.to_dict() == service.get_idea(first.idea_id).to_dict()

    (base / "index.json").write_text("{not json", encoding="utf-8")
    rebuilt = IdeaStore(base)
    assert rebuilt.index_rebuilt is True
    assert {item.idea_id for item in rebuilt.list_summaries()} == {first.idea_id, second.idea_id}


def test_store_quarantines_a_corrupt_file_and_keeps_the_rest(tmp_path):
    base = tmp_path / "ideas"
    service = _service(tmp_path, IdeaStore(base))
    good = service.create_idea(IdeaCreateRequest(title="Good"))
    bad = service.create_idea(IdeaCreateRequest(title="Bad"))
    (base / "items" / f"{bad.idea_id}.json").write_text('{"idea_id": "truncated', encoding="utf-8")

    restarted = IdeaStore(base)
    assert [item.idea_id for item in restarted.list_summaries()] == [good.idea_id]
    assert restarted.get(bad.idea_id) is None
    preserved = list((base / "quarantine").glob(f"{bad.idea_id}.json.malformed.*.preserved"))
    assert len(preserved) == 1 and preserved[0].read_text(encoding="utf-8") == '{"idea_id": "truncated'
    warnings = restarted.storage_warnings()
    assert any(item.action == "quarantined" and item.file_name == f"{bad.idea_id}.json" for item in warnings)

    # A file that parses but breaks a domain rule is quarantined the same way.
    payload = json.loads((base / "items" / f"{good.idea_id}.json").read_text(encoding="utf-8"))
    payload["stance"] = "bullish"
    (base / "items" / f"{good.idea_id}.json").write_text(json.dumps(payload), encoding="utf-8")
    assert IdeaStore(base).list_summaries() == []
    assert list((base / "quarantine").glob(f"{good.idea_id}.json.invalid.*.preserved"))


def test_store_migrates_by_schema_version_and_skips_future_files(tmp_path):
    base = tmp_path / "ideas"
    service = _service(tmp_path, IdeaStore(base))
    idea = service.create_idea(IdeaCreateRequest(title="Old"))
    path = base / "items" / f"{idea.idea_id}.json"
    legacy = json.loads(path.read_text(encoding="utf-8"))
    legacy["schema_version"] = 0
    legacy["headline"] = legacy.pop("title")
    path.write_text(json.dumps(legacy), encoding="utf-8")

    def v0_to_v1(payload):
        payload["title"] = payload.pop("headline")
        return payload

    migrated = IdeaStore(base, migrations={**DEFAULT_IDEA_MIGRATIONS, 0: v0_to_v1})
    assert migrated.require(idea.idea_id).title == "Old"
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == IDEA_SCHEMA_VERSION
    assert any(item.action == "migrated" for item in migrated.storage_warnings())

    future = json.loads(path.read_text(encoding="utf-8"))
    future["schema_version"] = IDEA_SCHEMA_VERSION + 1
    path.write_text(json.dumps(future), encoding="utf-8")
    store = IdeaStore(base)
    assert store.get(idea.idea_id) is None
    assert path.exists(), "a file from a newer Gamma is left untouched"
    assert any(item.action == "skipped_future_version" for item in store.storage_warnings())

    unsupported = dict(future, schema_version=0)
    path.write_text(json.dumps(unsupported), encoding="utf-8")
    IdeaStore(base)
    assert not path.exists()
    assert list((base / "quarantine").glob(f"{idea.idea_id}.json.unsupported-v0.*.preserved"))


def test_store_recovers_an_interrupted_write(tmp_path):
    base = tmp_path / "ideas"
    service = _service(tmp_path, IdeaStore(base))
    idea = service.create_idea(IdeaCreateRequest(title="Recovered"))
    path = base / "items" / f"{idea.idea_id}.json"
    temp = base / "items" / f"{idea.idea_id}.abc123.json.tmp"
    temp.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.unlink()
    store = IdeaStore(base)
    assert store.require(idea.idea_id).title == "Recovered"
    assert not temp.exists()


def test_store_quarantines_a_non_object_entry_instead_of_failing_to_start(tmp_path):
    # Regresión: un elemento del diario que no es un objeto lanzaba AttributeError
    # desde IdeaStore.__init__ y el backend no arrancaba.
    base = tmp_path / "ideas"
    service = _service(tmp_path, IdeaStore(base))
    good = service.create_idea(IdeaCreateRequest(title="Good"))
    bad = service.create_idea(IdeaCreateRequest(title="Bad"))
    path = base / "items" / f"{bad.idea_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["journal"] = [None]
    path.write_text(json.dumps(payload), encoding="utf-8")
    (base / "index.json").unlink()

    restarted = IdeaStore(base)
    assert [item.idea_id for item in restarted.list_summaries()] == [good.idea_id]
    assert list((base / "quarantine").glob(f"{bad.idea_id}.json.invalid.*.preserved"))


def test_store_rejects_altered_ids_without_touching_the_real_file(tmp_path):
    # Regresión: en NTFS un id en mayúsculas abría el fichero real y lo mandaba a cuarentena;
    # y _safe_id eliminaba caracteres, de modo que "a/b" se convertía en otro id.
    base = tmp_path / "ideas"
    service = _service(tmp_path, IdeaStore(base))
    idea = service.create_idea(IdeaCreateRequest(title="Case"))
    altered = idea.idea_id.upper() if idea.idea_id.upper() != idea.idea_id else idea.idea_id + "X"
    assert service.store.get(altered) is None
    assert service.store.delete(altered) is False
    assert service.store.get(f"{idea.idea_id[:2]}/{idea.idea_id[2:]}") is None
    assert service.store.get(idea.idea_id) is not None
    assert not list((base / "quarantine").iterdir())
    assert [item.idea_id for item in IdeaStore(base).list_summaries()] == [idea.idea_id]


def test_delete_moves_the_file_to_trash(tmp_path):
    base = tmp_path / "ideas"
    service = _service(tmp_path, IdeaStore(base))
    idea = service.create_idea(IdeaCreateRequest(title="Gone"))
    assert service.delete_idea(idea.idea_id) is True
    assert service.store.get(idea.idea_id) is None
    assert service.delete_idea(idea.idea_id) is False
    assert len(list((base / "trash").glob(f"{idea.idea_id}.*.json"))) == 1
    assert IdeaStore(base).list_summaries() == []


def test_markdown_export_keeps_provenance_and_reopen_target(tmp_path):
    service = _service(tmp_path)
    idea = service.create_idea(IdeaCreateRequest(title="Energy | refiners", thesis="Refiners beat SPY.", stance="long"))
    service.pin_evidence(idea.idea_id, _pin_request("challenges"))
    service.add_journal_entry(idea.idea_id, kind="decision", body="Wait for the Q4 print.")
    markdown = service.export_markdown(idea.idea_id)
    assert markdown.startswith("# Energy | refiners")
    assert "## Thesis\n\nRefiners beat SPY." in markdown
    assert "### Challenges (1)" in markdown and "### Supports (0)" in markdown
    assert "  - FCF TTM: $36.1B" in markdown
    assert "- Source: sec_edgar · retrieved 2026-11-14 09:25 UTC · origin `fundamentals_service.overview`" in markdown
    assert "transformation: TTM sum of the last four 10-Q filings." in markdown
    assert "- Reopen: Fundamentals / overview on XOM Corp (`XOM`) · lens 1Y" in markdown
    assert "| user | decision | Wait for the Q4 print. |" in markdown
    assert "## Export provenance" in markdown and "not advice" in markdown

    exported = service.export_json(idea.idea_id)
    assert exported["format"] == "gamma.idea" and exported["format_version"] == 2
    assert Idea.from_dict(exported["idea"]).to_dict() == service.get_idea(idea.idea_id).to_dict()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path):
    runtime = build_runtime(
        mock_mode=True,
        cache_dir=tmp_path / "cache",
        history_dir=tmp_path / "data",
        sample_data_dir="sample_data",
    )
    with TestClient(create_app(runtime)) as test_client:
        test_client.runtime = runtime  # type: ignore[attr-defined]
        yield test_client


def _reopen_payload(tab: str, mode: str | None, entity_id: str, label: str, entity_type: str = "equity") -> dict:
    return {
        "source_tab": tab,
        "source_mode": mode,
        "intended_target_tab": tab,
        "intended_target_mode": mode,
        "selected_entity": {"entity_type": entity_type, "label": label, "normalized_id": entity_id, "metadata": {}},
        "selected_timeframe": {"label": "1Y", "start": None, "end": None},
        "provider": "mock",
        "source": None,
        "warnings": [],
        "normalized_ids": {"symbol": entity_id},
        "timestamp": "2026-11-14T09:00:00.000Z",
    }


def test_idea_routes_cover_the_i1_workflow(client):
    created = client.post(
        "/ideas",
        json={
            "title": "Energy outperforms",
            "thesis": "Refiners beat SPY into Q1.",
            "stance": "relative",
            "legs": [{"entity": {"entity_type": "equity", "label": "XOM", "normalized_id": "XOM"}, "weight": 1}],
            "tags": ["Energy"],
            "horizon": {"review_date": "2027-03-31", "holding_window": "3M"},
        },
    )
    assert created.status_code == 200, created.text
    idea = created.json()
    idea_id = idea["idea_id"]
    assert idea["status"] == "draft" and idea["tags"] == ["energy"]
    assert idea["provenance"]["source_provider"] == "gamma_ideas"

    pinned = client.post(
        f"/ideas/{idea_id}/evidence",
        json={
            "kind": "metric",
            "stance": "supports",
            "title": "XOM free cash flow",
            "captured_values": {"metrics": [{"label": "FCF TTM", "display": "$36.1B", "value": 36.1e9}]},
            "provenance": {"source_provider": "sample", "origin": "fundamentals.overview", "retrieved_at": "2026-11-14T08:59:00Z"},
            "freshness": {"label": "mock"},
            "reopen": _reopen_payload("fundamentals", "overview", "XOM", "Exxon Mobil"),
        },
    )
    assert pinned.status_code == 200, pinned.text
    evidence = pinned.json()["evidence"]
    assert evidence["provenance"]["retrieved_at"] == "2026-11-14T08:59:00"
    assert evidence["freshness"]["label"] == "mocked"
    assert evidence["reopen"]["selected_entity"]["normalized_id"] == "XOM"

    missing_stance = client.post(f"/ideas/{idea_id}/evidence", json={"kind": "metric", "title": "x"})
    assert missing_stance.status_code == 422
    too_big = client.post(
        f"/ideas/{idea_id}/evidence",
        json={"kind": "table", "stance": "context", "title": "big", "captured_values": {"rows": ["x" * 1_900] * 20}},
    )
    assert too_big.status_code == 422 and "bytes" in too_big.json()["detail"]

    patched = client.patch(f"/ideas/{idea_id}", json={"stance": "long", "notes": "## Why\nMargins."})
    assert patched.status_code == 200
    assert patched.json()["journal"][-1]["kind"] == "edited"

    journal = client.post(f"/ideas/{idea_id}/journal", json={"kind": "decision", "body": "Hold until the print."})
    assert journal.status_code == 200 and journal.json()["journal"][-1]["author"] == "user"
    assert client.post(f"/ideas/{idea_id}/journal", json={"kind": "edited", "body": "x"}).status_code == 422

    assert client.post(f"/ideas/{idea_id}/activate").json()["status"] == "active"
    assert client.post(f"/ideas/{idea_id}/activate").status_code == 422

    second = client.post("/ideas", json={"title": "Rates fall", "tags": ["rates"]}).json()
    listing = client.get("/ideas").json()
    assert listing["total"] == 2 and listing["status_counts"]["active"] == 1
    assert listing["tags"] == ["energy", "rates"]
    by_id = {item["idea_id"]: item for item in listing["items"]}
    assert by_id[idea_id]["evidence_counts"] == {"supports": 1, "challenges": 0, "context": 0}
    assert by_id[idea_id]["last_evidence_at"] is not None
    assert [item["idea_id"] for item in client.get("/ideas?status=draft").json()["items"]] == [second["idea_id"]]
    assert [item["idea_id"] for item in client.get("/ideas?tag=energy").json()["items"]] == [idea_id]
    assert client.get("/ideas?status=open").status_code == 422

    markdown = client.get(f"/ideas/{idea_id}/export?format=md")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert 'filename="idea-Energy-outperforms.md"' in markdown.headers["content-disposition"]
    assert "- Source: sample · retrieved 2026-11-14 08:59 UTC" in markdown.text
    exported = client.get(f"/ideas/{idea_id}/export?format=json")
    assert exported.headers["content-type"].startswith("application/json")
    assert exported.json()["idea"]["evidence"][0]["title"] == "XOM free cash flow"
    assert client.get(f"/ideas/{idea_id}/export?format=pdf").status_code == 422

    unpinned = client.delete(f"/ideas/{idea_id}/evidence/{evidence['evidence_id']}")
    assert unpinned.status_code == 200 and unpinned.json()["evidence"] == []
    assert client.delete(f"/ideas/{idea_id}/evidence/{evidence['evidence_id']}").status_code == 404

    assert client.post(f"/ideas/{idea_id}/archive").json()["status"] == "archived"
    assert client.post(f"/ideas/{idea_id}/restore").json()["status"] == "active"

    assert client.delete(f"/ideas/{second['idea_id']}").json() == {"success": True, "recoverable": True}
    assert client.get(f"/ideas/{second['idea_id']}").status_code == 404
    assert client.delete(f"/ideas/{second['idea_id']}").status_code == 404


def test_idea_routes_validate_input(client):
    assert client.post("/ideas", json={"title": ""}).status_code == 422
    assert client.post("/ideas", json={"title": "x", "stance": "bullish"}).status_code == 422
    assert client.post("/ideas", json={"title": "x", "tags": [f"t{i}" for i in range(20)]}).status_code == 422
    leg = {"entity": {"entity_type": "equity", "label": "X", "normalized_id": "X"}, "weight": 1e9}
    assert client.post("/ideas", json={"title": "x", "legs": [leg]}).status_code == 422
    assert client.get("/ideas/does-not-exist").status_code == 404
    assert client.patch("/ideas/does-not-exist", json={"title": "y"}).status_code == 404


def test_promoted_follow_up_keeps_its_handoff_and_note(client):
    follow_up = client.post(
        "/sitrep/follow-ups",
        json={"row_id": "macro-1", "title": "Brent +3.2% over 1W", "note": "Check refiners.", "handoff": {"targetTab": "commodities", "targetMode": "energy", "commodityId": "BRENT"}},
    ).json()
    created = client.post(
        "/ideas",
        json={
            "title": follow_up["title"],
            "notes": follow_up["note"],
            "origin": {
                "kind": "sitrep_follow_up",
                "source_ref": follow_up["id"],
                "label": follow_up["title"],
                "handoff": {
                    **_reopen_payload("commodities", "energy", "BRENT", "Brent", "commodity"),
                    "source_tab": "sitrep",
                    "source_mode": None,
                    "normalized_ids": {"commodity_id": "BRENT"},
                },
            },
        },
    )
    assert created.status_code == 200, created.text
    idea = created.json()
    assert idea["notes"] == "Check refiners."
    assert idea["origin"]["kind"] == "sitrep_follow_up" and idea["origin"]["source_ref"] == follow_up["id"]
    assert idea["origin"]["handoff"]["intended_target_tab"] == "commodities"
    assert idea["journal"][0]["body"].startswith("Promoted from the Sitrep follow-up")
    # The follow-up itself is not migrated or removed.
    assert [item["id"] for item in client.get("/sitrep/follow-ups").json()["items"]] == [follow_up["id"]]


def test_ideas_persist_across_a_runtime_restart(tmp_path):
    def make_client():
        runtime = build_runtime(mock_mode=True, cache_dir=tmp_path / "cache", history_dir=tmp_path / "data", sample_data_dir="sample_data")
        return TestClient(create_app(runtime))

    with make_client() as first:
        idea = first.post("/ideas", json={"title": "Survives"}).json()
        first.post(
            f"/ideas/{idea['idea_id']}/evidence",
            json={"kind": "note", "stance": "context", "title": "A note", "captured_values": {"text": "kept"}},
        )
    with make_client() as second:
        listing = second.get("/ideas").json()
        assert [item["title"] for item in listing["items"]] == ["Survives"]
        restored = second.get(f"/ideas/{idea['idea_id']}").json()
        assert restored["evidence"][0]["captured_values"] == {"text": "kept"}
        assert [entry["kind"] for entry in restored["journal"]] == ["created", "evidence_pinned"]
