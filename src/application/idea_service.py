"""Application service for Ideas (Workstream 12, checkpoint I1).

The service owns the rules around the store: every edit, pin, unpin and
lifecycle change writes a system journal entry; the journal only grows; and the
I1 lifecycle is ``draft`` -> ``active`` -> ``archived`` (plus restore and
delete). Nothing here evaluates criteria, tracks prices or calls a provider:
a pin stores exactly what the user saw, with the provenance they saw.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any
from uuid import uuid4

from src.models.handoff import CrossTabHandoffEnvelope
from src.models.ideas import (
    EVIDENCE_STANCES,
    IDEA_I1_STATUSES,
    IDEA_SCHEMA_VERSION,
    IDEA_STATUSES,
    Idea,
    IdeaEvidence,
    IdeaHorizon,
    IdeaJournalEntry,
    IdeaLeg,
    IdeaLifecycleError,
    IdeaOrigin,
    IdeaValidationError,
    normalize_tags,
    prepare_captured_values,
    thaw_captured_values,
)
from src.models.provenance import FreshnessRecord, ProvenanceRecord
from src.services.idea_store import IdeaNotFoundError, IdeaStorageWarning, IdeaStore, IdeaSummary
from src.utils.time import now_utc

IDEA_EXPORT_FORMAT = "gamma.idea"
IDEA_EXPORT_FORMAT_VERSION = 1
IDEAS_SOURCE_PROVIDER = "gamma_ideas"

_TAB_LABELS = {
    "sitrep": "Sitrep",
    "ideas": "Ideas",
    "equity_research": "Equity Research",
    "strategy_lab": "Strategy Lab",
    "macro": "Macro",
    "prediction_markets": "Prediction Markets",
    "crypto": "Crypto",
    "fundamentals": "Fundamentals",
    "commodities": "Commodities",
    "maritime": "Sealanes",
    "copilot": "Copilot",
    "risk": "Risk",
    "iv": "Options",
    "portfolio": "Portfolio",
}
_STANCE_HEADINGS = {"supports": "Supports", "challenges": "Challenges", "context": "Context"}
_EDITABLE_TEXT_FIELDS = ("title", "thesis", "stance")


@dataclass(frozen=True)
class IdeaCreateRequest:
    title: str
    thesis: str = ""
    notes: str = ""
    stance: str = "neutral"
    legs: tuple[IdeaLeg, ...] = ()
    horizon: IdeaHorizon = field(default_factory=IdeaHorizon)
    tags: tuple[str, ...] = ()
    origin: IdeaOrigin = field(default_factory=IdeaOrigin)


@dataclass(frozen=True)
class IdeaPatchRequest:
    """Fields left as ``None`` are unchanged."""

    title: str | None = None
    thesis: str | None = None
    notes: str | None = None
    stance: str | None = None
    legs: tuple[IdeaLeg, ...] | None = None
    horizon: IdeaHorizon | None = None
    tags: tuple[str, ...] | None = None


@dataclass(frozen=True)
class IdeaEvidenceCreateRequest:
    kind: str
    stance: str
    title: str
    captured_values: Mapping[str, Any] = field(default_factory=dict)
    provenance: ProvenanceRecord | None = None
    freshness: FreshnessRecord | None = None
    reopen: CrossTabHandoffEnvelope | None = None
    note: str = ""


@dataclass(frozen=True)
class IdeaListResult:
    items: list[IdeaSummary]
    total: int
    status_counts: dict[str, int]
    tags: list[str]
    storage_warnings: list[IdeaStorageWarning]
    retrieved_at: datetime


class IdeaService:
    def __init__(
        self,
        store: IdeaStore,
        *,
        clock: Callable[[], datetime] = now_utc,
        id_factory: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        self.store = store
        self._clock = clock
        self._new_id = id_factory

    # -- reads ---------------------------------------------------------------

    def list_ideas(self, *, statuses: Sequence[str] = (), tags: Sequence[str] = ()) -> IdeaListResult:
        wanted_statuses = {str(item).strip().lower() for item in statuses if str(item).strip()}
        unknown = wanted_statuses - set(IDEA_STATUSES)
        if unknown:
            raise IdeaValidationError(f"Unknown status filter {sorted(unknown)}; use {IDEA_STATUSES}.")
        wanted_tags = set(normalize_tags(tags))
        summaries = self.store.list_summaries()
        status_counts = {status: 0 for status in IDEA_STATUSES}
        all_tags: set[str] = set()
        for summary in summaries:
            status_counts[summary.status] = status_counts.get(summary.status, 0) + 1
            all_tags.update(summary.tags)
        items = [
            summary
            for summary in summaries
            if (not wanted_statuses or summary.status in wanted_statuses)
            and wanted_tags.issubset(summary.tags)
        ]
        return IdeaListResult(
            items=items,
            total=len(summaries),
            status_counts=status_counts,
            tags=sorted(all_tags),
            storage_warnings=self.store.storage_warnings(),
            retrieved_at=self._clock(),
        )

    def get_idea(self, idea_id: str) -> Idea:
        return self.store.require(idea_id)

    # -- writes --------------------------------------------------------------

    def create_idea(self, request: IdeaCreateRequest) -> Idea:
        now = self._clock()
        idea_id = self._new_id()
        idea = Idea(
            idea_id=idea_id,
            title=request.title,
            thesis=request.thesis,
            notes=request.notes,
            stance=request.stance,
            legs=tuple(request.legs),
            horizon=request.horizon,
            status="draft",
            origin=request.origin,
            tags=tuple(request.tags),
            created_at=now,
            updated_at=now,
        )
        body = "Created the idea."
        if request.origin.kind == "sitrep_follow_up":
            body = f"Promoted from the Sitrep follow-up “{request.origin.label or idea.title}”."
        elif request.origin.kind != "manual":
            body = f"Created from {request.origin.kind.replace('_', ' ')}" + (
                f" “{request.origin.label}”." if request.origin.label else "."
            )
        idea = idea.with_journal_entry(
            self._system_entry(idea_id, "created", body, now, {"origin_kind": request.origin.kind})
        )
        return self.store.create(idea)

    def update_idea(self, idea_id: str, patch: IdeaPatchRequest) -> Idea:
        def mutate(current: Idea) -> Idea:
            now = self._clock()
            changes: dict[str, Any] = {}
            if patch.title is not None:
                changes["title"] = patch.title
            if patch.thesis is not None:
                changes["thesis"] = patch.thesis
            if patch.notes is not None:
                changes["notes"] = patch.notes
            if patch.stance is not None:
                changes["stance"] = patch.stance
            if patch.legs is not None:
                changes["legs"] = tuple(patch.legs)
            if patch.horizon is not None:
                changes["horizon"] = patch.horizon
            if patch.tags is not None:
                changes["tags"] = tuple(patch.tags)
            candidate = replace(current, **changes)
            diff = _describe_changes(current, candidate)
            if not diff:
                return current
            candidate = replace(candidate, updated_at=now)
            labels = ", ".join(item["field"] for item in diff)
            return candidate.with_journal_entry(
                self._system_entry(idea_id, "edited", f"Edited {labels}.", now, {"changes": diff}),
                touched_at=now,
            )

        return self.store.update(idea_id, mutate)

    def delete_idea(self, idea_id: str) -> bool:
        return self.store.delete(idea_id)

    def pin_evidence(self, idea_id: str, request: IdeaEvidenceCreateRequest) -> tuple[Idea, IdeaEvidence]:
        pinned: dict[str, IdeaEvidence] = {}

        def mutate(current: Idea) -> Idea:
            now = self._clock()
            evidence = IdeaEvidence(
                evidence_id=self._new_id(),
                idea_id=idea_id,
                kind=request.kind,
                stance=request.stance,
                title=request.title,
                captured_values=prepare_captured_values(request.captured_values),
                provenance=request.provenance,
                freshness=request.freshness,
                reopen=request.reopen,
                captured_at=now,
                note=request.note,
            )
            pinned["item"] = evidence
            source = _source_label(evidence)
            body = f"Pinned “{evidence.title}” as {evidence.stance}" + (f" from {source}." if source else ".")
            updated = replace(current, evidence=(*current.evidence, evidence), updated_at=now)
            return updated.with_journal_entry(
                self._system_entry(
                    idea_id,
                    "evidence_pinned",
                    body,
                    now,
                    {"evidence_id": evidence.evidence_id, "stance": evidence.stance, "kind": evidence.kind},
                ),
                touched_at=now,
            )

        idea = self.store.update(idea_id, mutate)
        return idea, pinned["item"]

    def unpin_evidence(self, idea_id: str, evidence_id: str) -> Idea:
        def mutate(current: Idea) -> Idea:
            match = next((item for item in current.evidence if item.evidence_id == evidence_id), None)
            if match is None:
                raise IdeaNotFoundError(f"Evidence {evidence_id} was not found on idea {idea_id}.")
            now = self._clock()
            updated = replace(
                current,
                evidence=tuple(item for item in current.evidence if item.evidence_id != evidence_id),
                updated_at=now,
            )
            # The journal keeps what was removed, so unpinning cannot rewrite the record.
            return updated.with_journal_entry(
                self._system_entry(
                    idea_id,
                    "evidence_unpinned",
                    f"Unpinned “{match.title}” ({match.stance}, captured {match.captured_at.strftime('%Y-%m-%d %H:%M')} UTC).",
                    now,
                    {"evidence_id": match.evidence_id, "stance": match.stance, "kind": match.kind},
                ),
                touched_at=now,
            )

        return self.store.update(idea_id, mutate)

    def add_journal_entry(self, idea_id: str, *, kind: str, body: str) -> Idea:
        def mutate(current: Idea) -> Idea:
            now = self._clock()
            entry = IdeaJournalEntry(
                entry_id=self._new_id(),
                idea_id=idea_id,
                kind=kind,
                author="user",
                body=body,
                created_at=now,
            )
            return replace(current, updated_at=now).with_journal_entry(entry, touched_at=now)

        return self.store.update(idea_id, mutate)

    def activate(self, idea_id: str) -> Idea:
        def mutate(current: Idea) -> Idea:
            if current.status != "draft":
                raise IdeaLifecycleError(f"Only a draft idea can be activated; this one is {current.status}.")
            if not current.thesis:
                raise IdeaLifecycleError("Write the thesis before activating the idea.")
            return self._transition(current, "active", "Activated the idea.")

        return self.store.update(idea_id, mutate)

    def archive(self, idea_id: str) -> Idea:
        def mutate(current: Idea) -> Idea:
            if current.status not in {"draft", "active"}:
                raise IdeaLifecycleError(f"Only a draft or active idea can be archived; this one is {current.status}.")
            return self._transition(current, "archived", f"Archived the idea (was {current.status}).")

        return self.store.update(idea_id, mutate)

    def restore(self, idea_id: str) -> Idea:
        """Return an archived idea to the status it had when it was archived."""

        def mutate(current: Idea) -> Idea:
            if current.status != "archived":
                raise IdeaLifecycleError(f"Only an archived idea can be restored; this one is {current.status}.")
            previous = "draft"
            for entry in reversed(current.journal):
                if entry.kind == "status_changed" and entry.details.get("to") == "archived":
                    previous = str(entry.details.get("from") or "draft")
                    break
            if previous not in IDEA_I1_STATUSES or previous == "archived":
                previous = "draft"
            return self._transition(current, previous, f"Restored the idea from the archive to {previous}.")

        return self.store.update(idea_id, mutate)

    # -- export --------------------------------------------------------------

    def export_json(self, idea_id: str) -> dict[str, Any]:
        idea = self.store.require(idea_id)
        return {
            "format": IDEA_EXPORT_FORMAT,
            "format_version": IDEA_EXPORT_FORMAT_VERSION,
            "exported_at": self._clock().isoformat(),
            "source_provider": IDEAS_SOURCE_PROVIDER,
            "origin": "idea_service.export_json",
            "notice": "Local research record. Evidence is frozen as captured. Not advice and not an order.",
            "idea": idea.to_dict(),
        }

    def export_markdown(self, idea_id: str) -> str:
        idea = self.store.require(idea_id)
        return render_idea_markdown(idea, exported_at=self._clock())

    # -- helpers -------------------------------------------------------------

    def _transition(self, current: Idea, status: str, body: str) -> Idea:
        now = self._clock()
        updated = replace(current, status=status, updated_at=now)
        return updated.with_journal_entry(
            self._system_entry(current.idea_id, "status_changed", body, now, {"from": current.status, "to": status}),
            touched_at=now,
        )

    def _system_entry(
        self,
        idea_id: str,
        kind: str,
        body: str,
        created_at: datetime,
        details: Mapping[str, Any] | None = None,
    ) -> IdeaJournalEntry:
        return IdeaJournalEntry(
            entry_id=self._new_id(),
            idea_id=idea_id,
            kind=kind,
            author="system",
            body=body,
            created_at=created_at,
            details=dict(details or {}),
        )


# ---------------------------------------------------------------------------
# Change description and Markdown export
# ---------------------------------------------------------------------------


def _describe_changes(before: Idea, after: Idea) -> list[dict[str, Any]]:
    """List changed fields; short fields keep before/after so the journal stays honest."""
    diff: list[dict[str, Any]] = []
    for name in _EDITABLE_TEXT_FIELDS:
        old, new = getattr(before, name), getattr(after, name)
        if old != new:
            diff.append({"field": name, "before": _clip(old), "after": _clip(new)})
    if before.notes != after.notes:
        diff.append({"field": "notes", "before_length": len(before.notes), "after_length": len(after.notes)})
    if [leg.to_dict() for leg in before.legs] != [leg.to_dict() for leg in after.legs]:
        diff.append({"field": "legs", "before": _legs_text(before), "after": _legs_text(after)})
    if before.horizon != after.horizon:
        diff.append({"field": "horizon", "before": _horizon_text(before.horizon), "after": _horizon_text(after.horizon)})
    if before.tags != after.tags:
        diff.append({"field": "tags", "before": ", ".join(before.tags), "after": ", ".join(after.tags)})
    return diff


def _clip(value: str, limit: int = 300) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _legs_text(idea: Idea) -> str:
    return _clip("; ".join(_leg_text(leg) for leg in idea.legs) or "none")


def _leg_text(leg: IdeaLeg) -> str:
    weight = "" if leg.weight is None else f" {leg.weight:+g}"
    return f"{leg.entity.label}{weight}"


def _horizon_text(horizon: IdeaHorizon) -> str:
    parts = []
    if horizon.review_date:
        parts.append(f"review {horizon.review_date.isoformat()}")
    if horizon.holding_window:
        parts.append(horizon.holding_window)
    return " · ".join(parts) or "none"


def _tab_label(tab: str | None) -> str:
    if not tab:
        return ""
    return _TAB_LABELS.get(tab, tab.replace("_", " ").title())


def _source_label(evidence: IdeaEvidence) -> str:
    if evidence.reopen is None:
        return ""
    tab = _tab_label(evidence.reopen.source_tab)
    mode = evidence.reopen.source_mode
    return f"{tab} / {mode.replace('_', ' ')}" if mode else tab


def _md(value: Any) -> str:
    """Escape a value for one Markdown table cell or line."""
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def _ts(value: datetime | None) -> str:
    return f"{value.strftime('%Y-%m-%d %H:%M')} UTC" if value else "N/A"


def render_idea_markdown(idea: Idea, *, exported_at: datetime) -> str:
    stance = idea.stance.capitalize()
    lines: list[str] = [
        f"# {idea.title}",
        "",
        "> Research record exported from Gamma. Evidence is frozen as captured with its provenance; "
        "this is not advice and Gamma places no orders.",
        "",
        f"- Status: {idea.status.capitalize()}",
        f"- Stance: {stance}",
        f"- Horizon: {_horizon_text(idea.horizon)}",
        f"- Tags: {', '.join(idea.tags) if idea.tags else 'none'}",
        f"- Origin: {idea.origin.kind.replace('_', ' ')}"
        + (f" — {idea.origin.label}" if idea.origin.label else "")
        + (f" (ref `{idea.origin.source_ref}`)" if idea.origin.source_ref else ""),
        f"- Created: {_ts(idea.created_at)} · Updated: {_ts(idea.updated_at)}",
        "",
        "## Thesis",
        "",
        idea.thesis or "_No thesis written yet._",
        "",
        "## Legs",
        "",
    ]
    if idea.legs:
        lines += ["| Instrument | Type | Id | Weight |", "| --- | --- | --- | ---: |"]
        for leg in idea.legs:
            weight = "" if leg.weight is None else f"{leg.weight:+g}"
            lines.append(
                f"| {_md(leg.entity.label)} | {_md(leg.entity.entity_type)} | `{_md(leg.entity.normalized_id)}` | {weight} |"
            )
    else:
        lines.append("_No legs._")
    lines += ["", "## Notes", "", idea.notes or "_No notes._", "", "## Evidence", ""]
    counts = idea.evidence_counts()
    lines.append(
        " · ".join(f"{_STANCE_HEADINGS[stance_key]} {counts[stance_key]}" for stance_key in EVIDENCE_STANCES)
    )
    for stance_key in EVIDENCE_STANCES:
        pins = [item for item in idea.evidence if item.stance == stance_key]
        lines += ["", f"### {_STANCE_HEADINGS[stance_key]} ({len(pins)})"]
        if not pins:
            lines += ["", "_None._"]
        for pin in pins:
            lines += ["", *_evidence_markdown(pin)]
    lines += ["", "## Journal", ""]
    if idea.journal:
        lines += ["| Time | Author | Kind | Entry |", "| --- | --- | --- | --- |"]
        for entry in idea.journal:
            lines.append(
                f"| {_ts(entry.created_at)} | {entry.author} | {entry.kind.replace('_', ' ')} | {_md(entry.body)} |"
            )
    else:
        lines.append("_No entries._")
    lines += [
        "",
        "---",
        "",
        "## Export provenance",
        f"- Idea: `{idea.idea_id}` · schema v{idea.schema_version}",
        f"- Exported: {_ts(exported_at)}",
        f"- Source: {IDEAS_SOURCE_PROVIDER} (local idea store) via idea_service.export_markdown",
        "- Evidence values are the snapshot taken at capture; they were not refreshed for this export.",
        "",
    ]
    return "\n".join(lines)


def _evidence_markdown(pin: IdeaEvidence) -> list[str]:
    lines = [f"#### {pin.title}", ""]
    lines.append(f"- Kind: {pin.kind.replace('_', ' ')} · Captured: {_ts(pin.captured_at)}")
    lines += _captured_values_markdown(thaw_captured_values(pin.captured_values))
    if pin.note:
        lines.append(f"- Note: {_md(pin.note)}")
    if pin.provenance:
        source = pin.provenance
        detail = f"- Source: {source.source_provider} · retrieved {_ts(source.retrieved_at)} · origin `{source.origin}`"
        if source.transformation_note:
            detail += f" · transformation: {_md(source.transformation_note)}"
        lines.append(detail)
    else:
        lines.append("- Source: no provenance recorded at capture")
    if pin.freshness:
        warnings = f" · warnings: {'; '.join(pin.freshness.warnings)}" if pin.freshness.warnings else ""
        lines.append(f"- Freshness at capture: {pin.freshness.label.value}{warnings}")
    if pin.reopen:
        entity = pin.reopen.selected_entity
        target = _tab_label(pin.reopen.intended_target_tab)
        mode = pin.reopen.intended_target_mode
        where = f"{target} / {mode.replace('_', ' ')}" if mode else target
        on = f" on {entity.label} (`{entity.normalized_id}`)" if entity else ""
        lens = f" · lens {pin.reopen.selected_timeframe.label}" if pin.reopen.selected_timeframe else ""
        lines.append(f"- Reopen: {where}{on}{lens}")
    return lines


def _captured_values_markdown(values: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    metrics = values.get("metrics")
    if isinstance(metrics, list) and metrics:
        lines.append("- Values:")
        for metric in metrics:
            if isinstance(metric, Mapping):
                label = metric.get("label") or metric.get("name") or "Value"
                shown = metric.get("display")
                if shown is None:
                    shown = metric.get("value")
                unit = f" {metric['unit']}" if metric.get("unit") and metric.get("display") is None else ""
                lines.append(f"  - {_md(label)}: {_md('N/A' if shown is None else shown)}{unit}")
    table = values.get("table")
    if isinstance(table, Mapping) and isinstance(table.get("columns"), list) and isinstance(table.get("rows"), list):
        columns = [str(column) for column in table["columns"]]
        if columns:
            lines += ["", "| " + " | ".join(_md(column) for column in columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
            for row in table["rows"]:
                cells = row if isinstance(row, list) else [row]
                lines.append("| " + " | ".join(_md(cell) for cell in cells) + " |")
            lines.append("")
    series = values.get("series")
    if isinstance(series, Mapping) and isinstance(series.get("points"), list):
        points = series["points"]
        summary = f"- Series: {_md(series.get('label') or 'series')} · {len(points)} points"
        if points:
            summary += f" · first {_md(_point_text(points[0]))} · last {_md(_point_text(points[-1]))}"
        downsampling = series.get("downsampling")
        if isinstance(downsampling, Mapping):
            summary += (
                f" · downsampled from {downsampling.get('original_points')} points "
                f"({downsampling.get('method')})"
            )
        lines.append(summary)
    text = values.get("text")
    if isinstance(text, str) and text.strip():
        lines.append(f"- Text: {_md(text)}")
    known = {"metrics", "table", "series", "text"}
    extra = {key: value for key, value in values.items() if key not in known}
    if extra:
        lines.append(f"- Other values: `{_md(json.dumps(extra, sort_keys=True, ensure_ascii=False))}`")
    return lines


def _point_text(point: Any) -> str:
    if isinstance(point, Mapping):
        stamp = point.get("timestamp") or point.get("date") or point.get("t")
        value = point.get("value") if "value" in point else point.get("v")
        return f"{stamp}: {value}" if stamp is not None else str(value)
    if isinstance(point, list) and len(point) == 2:
        return f"{point[0]}: {point[1]}"
    return str(point)



__all__ = [
    "IDEA_EXPORT_FORMAT",
    "IDEA_SCHEMA_VERSION",
    "IdeaCreateRequest",
    "IdeaEvidenceCreateRequest",
    "IdeaListResult",
    "IdeaPatchRequest",
    "IdeaService",
    "render_idea_markdown",
]
