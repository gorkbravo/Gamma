from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from src.application.copilot_context_helpers import dedupe_warnings
from src.models.copilot import (
    CopilotMemo,
    CopilotReportWarningProvenance,
    CopilotReportToolTraceSummary,
    CopilotResearchReport,
    CopilotSession,
    CopilotSourceRef,
    CopilotTurn,
    ResearchClaim,
    new_copilot_id,
)
from src.utils.time import now_utc


class CopilotReportService:
    """Build deterministic research reports from persisted Copilot traces."""

    @classmethod
    def generate_report(
        cls,
        *,
        session: CopilotSession,
        turns: list[CopilotTurn],
        memos: list[CopilotMemo] | None = None,
        title: str | None = None,
        notes: str | None = None,
        source_turn_ids: list[str] | None = None,
        source_memo_ids: list[str] | None = None,
    ) -> CopilotResearchReport:
        selected_turns = cls._select_turns(turns, source_turn_ids)
        if not selected_turns:
            raise ValueError("No Copilot turns are available for report generation.")

        selected_memos = cls._select_memos(memos or [], source_memo_ids)
        report_title = str(title or "").strip() or f"{session.title} Research Report"
        sources = cls._dedupe_sources(
            source
            for turn in selected_turns
            for source in turn.result.sources
        )
        warnings = dedupe_warnings(
            [
                *[
                    warning
                    for turn in selected_turns
                    for warning in turn.result.warnings
                ],
                *cls._operator_event_warnings(selected_turns),
            ]
        )
        missing_data = cls._missing_data_from_warnings(warnings)

        return CopilotResearchReport(
            report_id=new_copilot_id("report"),
            session_id=session.session_id,
            title=report_title[:140],
            source_turn_ids=[turn.turn_id for turn in selected_turns],
            source_memo_ids=[memo.memo_id for memo in selected_memos],
            source_backed_claims=cls._source_backed_claims(selected_turns, sources),
            inferred_claims=cls._inferred_claims(selected_turns),
            assumptions=cls._assumptions(selected_turns, notes),
            missing_data=missing_data,
            warnings=warnings,
            warning_provenance=cls._warning_provenance(selected_turns),
            tool_trace_summary=cls._tool_trace_summary(selected_turns),
            sources=sources,
            generated_at=now_utc(),
        )

    @classmethod
    def export_markdown(cls, report: CopilotResearchReport) -> str:
        lines = [
            f"# {report.title}",
            "",
            "## Metadata",
            f"- Report: {report.report_id}",
            f"- Session: {report.session_id}",
            f"- Generated: {report.generated_at.isoformat()}",
            f"- Source turns: {', '.join(report.source_turn_ids) if report.source_turn_ids else 'none'}",
            f"- Source memos: {', '.join(report.source_memo_ids) if report.source_memo_ids else 'none'}",
            "",
            "## Source-Backed Claims",
            *cls._claim_lines(report.source_backed_claims),
            "",
            "## Inferred Claims",
            *cls._bullet_lines(report.inferred_claims),
            "",
            "## Assumptions",
            *cls._bullet_lines(report.assumptions),
            "",
            "## Missing Data",
            *cls._bullet_lines(report.missing_data),
            "",
            "## Warnings",
            *cls._bullet_lines(report.warnings),
            "",
            "## Warning Provenance",
            *cls._warning_provenance_lines(report.warning_provenance),
            "",
            "## Tool Trace Summary",
            *cls._tool_lines(report.tool_trace_summary),
            "",
            "## Sources",
            *cls._source_lines(report.sources),
            "",
            "---",
            f"Source provider: {report.source_provider}",
            f"Origin: {report.origin}",
        ]
        if report.transformation_note:
            lines.append(f"Transformation: {report.transformation_note}")
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _select_turns(turns: list[CopilotTurn], source_turn_ids: list[str] | None) -> list[CopilotTurn]:
        selected_ids = [item.strip() for item in source_turn_ids or [] if item.strip()]
        if not selected_ids:
            return list(turns)
        selected = [turn for turn in turns if turn.turn_id in selected_ids]
        missing = [turn_id for turn_id in selected_ids if turn_id not in {turn.turn_id for turn in selected}]
        if missing:
            raise ValueError(f"Unknown Copilot source turn ids: {', '.join(missing)}")
        return selected

    @staticmethod
    def _select_memos(memos: list[CopilotMemo], source_memo_ids: list[str] | None) -> list[CopilotMemo]:
        selected_ids = [item.strip() for item in source_memo_ids or [] if item.strip()]
        if not selected_ids:
            return []
        selected = [memo for memo in memos if memo.memo_id in selected_ids]
        missing = [memo_id for memo_id in selected_ids if memo_id not in {memo.memo_id for memo in selected}]
        if missing:
            raise ValueError(f"Unknown Copilot source memo ids: {', '.join(missing)}")
        return selected

    @staticmethod
    def _dedupe_sources(sources: Iterable[object]) -> list[CopilotSourceRef]:
        deduped: dict[str, CopilotSourceRef] = {}
        for source in sources:
            if isinstance(source, CopilotSourceRef) and source.source_id not in deduped:
                deduped[source.source_id] = source
        return list(deduped.values())

    @staticmethod
    def _source_backed_claims(turns: list[CopilotTurn], sources: list[CopilotSourceRef]) -> list[ResearchClaim]:
        claims: list[ResearchClaim] = []
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for turn in turns:
            card = turn.result.card
            if card is None:
                continue
            for claim in card.source_backed_claims:
                refs = tuple(claim.evidence_refs)
                key = (claim.claim, refs)
                if claim.claim and key not in seen:
                    seen.add(key)
                    claims.append(claim)
        if not claims and sources:
            claims.append(
                ResearchClaim(
                    claim="The report is grounded in persisted Gamma Copilot source references.",
                    evidence_refs=[source.source_id for source in sources[:8]],
                )
            )
        return claims

    @staticmethod
    def _inferred_claims(turns: list[CopilotTurn]) -> list[str]:
        claims: list[str] = []
        for turn in turns:
            card = turn.result.card
            if card is None:
                continue
            if card.hypothesis:
                claims.append(f"{turn.domain}: {card.hypothesis}")
            claims.extend(card.inferred_claims)
        return list(dict.fromkeys(item for item in claims if item))

    @staticmethod
    def _assumptions(turns: list[CopilotTurn], notes: str | None) -> list[str]:
        assumptions: list[str] = []
        note = str(notes or "").strip()
        if note:
            assumptions.append(f"User note: {note}")
        for turn in turns:
            card = turn.result.card
            if card is None:
                continue
            assumptions.extend(card.confounders)
            assumptions.extend(card.caveats)
        return list(dict.fromkeys(item for item in assumptions if item))

    @staticmethod
    def _missing_data_from_warnings(warnings: list[str]) -> list[str]:
        markers = ("missing", "skipped", "unavailable", "stale", "no ", "failed")
        missing = [warning for warning in warnings if any(marker in warning.lower() for marker in markers)]
        return missing or ["No explicit missing-data warnings were recorded in the selected session trace."]

    @staticmethod
    def _operator_event_warnings(turns: list[CopilotTurn]) -> list[str]:
        warnings: list[str] = []
        for turn in turns:
            for event in turn.result.operator_events:
                warnings.extend(event.warnings)
                if event.event_type == "warning" and event.message:
                    warnings.append(event.message)
        return [warning for warning in warnings if warning]

    @staticmethod
    def _warning_provenance(turns: list[CopilotTurn]) -> list[CopilotReportWarningProvenance]:
        rows: list[CopilotReportWarningProvenance] = []
        seen: set[tuple[str, str | None, str | None, str | None, tuple[str, ...]]] = set()
        seen_warning_texts: set[str] = set()

        def append_row(
            warning: str,
            *,
            source_ids: Iterable[str] = (),
            tool_name: str | None = None,
            step_id: str | None = None,
            event_type: str | None = None,
            event_id: str | None = None,
            sequence: int | None = None,
        ) -> bool:
            text = str(warning or "").strip()
            if not text:
                return False
            deduped_sources = tuple(CopilotReportService._dedupe_strings(source_ids))
            key = (text, tool_name, step_id, event_type, deduped_sources)
            if key in seen:
                return False
            seen.add(key)
            seen_warning_texts.add(text)
            rows.append(
                CopilotReportWarningProvenance(
                    warning=text,
                    source_ids=list(deduped_sources),
                    tool_name=tool_name,
                    step_id=step_id,
                    event_type=event_type,
                    event_id=event_id,
                    sequence=sequence,
                )
            )
            return True

        for turn in turns:
            final_report_events = [
                event for event in turn.result.operator_events if event.event_type == "final-report"
            ]
            for event in turn.result.operator_events:
                event_type = str(event.event_type or "")
                if event_type == "final-report":
                    continue
                source_ids = list(event.source_ids)
                tool_name = str(event.tool_id) if event.tool_id else None
                for warning in event.warnings:
                    append_row(
                        warning,
                        source_ids=source_ids,
                        tool_name=tool_name,
                        step_id=event.step_id,
                        event_type=event_type,
                        event_id=event.event_id,
                        sequence=event.sequence,
                    )
                if event_type == "warning" and event.message:
                    append_row(
                        event.message,
                        source_ids=source_ids,
                        tool_name=tool_name,
                        step_id=event.step_id,
                        event_type=event_type,
                        event_id=event.event_id,
                        sequence=event.sequence,
                    )
            for event in final_report_events:
                for warning in event.warnings:
                    if str(warning or "").strip() in seen_warning_texts:
                        continue
                    append_row(
                        warning,
                        source_ids=list(event.source_ids),
                        event_type="final-report",
                        event_id=event.event_id,
                        sequence=event.sequence,
                    )
            for warning in turn.result.warnings:
                if str(warning or "").strip() in seen_warning_texts:
                    continue
                append_row(warning, event_type="result-warning")
        return rows

    @staticmethod
    def _tool_trace_summary(turns: list[CopilotTurn]) -> list[CopilotReportToolTraceSummary]:
        rows: list[CopilotReportToolTraceSummary] = []
        seen: set[tuple[str, str | None, str | None, str]] = set()
        for turn in turns:
            tool_events = [
                event
                for event in turn.result.operator_events
                if event.event_type in {"tool-result", "confirmation-needed"}
            ]
            for trace in turn.result.tool_traces:
                event = CopilotReportService._matching_tool_event(trace.tool_name, tool_events)
                status = CopilotReportService._event_status(event) if event is not None else "recorded"
                source_ids = CopilotReportService._dedupe_strings(
                    [
                        *trace.source_ids,
                        *(event.source_ids if event is not None else []),
                    ]
                )
                output_summary = CopilotReportService._event_output_summary(event) if event is not None else {}
                event_warnings = list(event.warnings) if event is not None else []
                key = (trace.tool_name, event.step_id if event is not None else None, event.event_type if event is not None else None, trace.summary)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    CopilotReportToolTraceSummary(
                        tool_name=trace.tool_name,
                        summary=trace.summary,
                        source_ids=source_ids,
                        status=status,
                        step_id=event.step_id if event is not None else None,
                        event_type=event.event_type if event is not None else None,
                        output_summary=output_summary,
                        warnings=event_warnings,
                    )
                )
            for event in tool_events:
                tool_names = CopilotReportService._event_tool_names(event)
                for tool_name in tool_names:
                    summary = event.message or CopilotReportService._status_summary(tool_name, CopilotReportService._event_status(event))
                    key = (tool_name, event.step_id, event.event_type, summary)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(
                        CopilotReportToolTraceSummary(
                            tool_name=tool_name,
                            summary=summary,
                            source_ids=list(event.source_ids),
                            status=CopilotReportService._event_status(event),
                            step_id=event.step_id,
                            event_type=event.event_type,
                            output_summary=CopilotReportService._event_output_summary(event),
                            warnings=list(event.warnings),
                        )
                    )
        return rows

    @staticmethod
    def _matching_tool_event(tool_name: str, events: list[object]) -> Any | None:
        for event in reversed(events):
            if getattr(event, "tool_id", None) == tool_name:
                return event
            payload = getattr(event, "payload", {})
            if isinstance(payload, dict) and tool_name in list(payload.get("required_for_tool_ids") or []):
                return event
        return None

    @staticmethod
    def _event_tool_names(event: object) -> list[str]:
        tool_id = getattr(event, "tool_id", None)
        if tool_id:
            return [str(tool_id)]
        payload = getattr(event, "payload", {})
        if not isinstance(payload, dict):
            return []
        return [str(item) for item in list(payload.get("required_for_tool_ids") or []) if item]

    @staticmethod
    def _event_status(event: object | None) -> str:
        if event is None:
            return "recorded"
        payload = getattr(event, "payload", {})
        event_type = str(getattr(event, "event_type", "") or "")
        if event_type == "confirmation-needed":
            return "confirmation_required"
        if isinstance(payload, dict) and payload.get("status"):
            return str(payload["status"])
        return event_type or "recorded"

    @staticmethod
    def _event_output_summary(event: object | None) -> dict[str, Any]:
        if event is None:
            return {}
        payload = getattr(event, "payload", {})
        if isinstance(payload, dict) and isinstance(payload.get("output_summary"), dict):
            return dict(payload["output_summary"])
        return {}

    @staticmethod
    def _status_summary(tool_name: str, status: str) -> str:
        label = tool_name or "operator step"
        if status == "confirmation_required":
            return f"{label} stopped at a confirmation checkpoint."
        return f"{label} recorded operator event status `{status}`."

    @staticmethod
    def _dedupe_strings(values: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(item for item in values if item))

    @staticmethod
    def _claim_lines(claims: list[ResearchClaim]) -> list[str]:
        if not claims:
            return ["- None recorded."]
        lines: list[str] = []
        for claim in claims:
            refs = f" [{', '.join(claim.evidence_refs)}]" if claim.evidence_refs else ""
            lines.append(f"- {claim.claim}{refs}")
        return lines

    @staticmethod
    def _bullet_lines(items: list[str]) -> list[str]:
        return [f"- {item}" for item in items] if items else ["- None recorded."]

    @staticmethod
    def _warning_provenance_lines(rows: list[CopilotReportWarningProvenance]) -> list[str]:
        if not rows:
            return ["- None recorded."]
        lines: list[str] = []
        for row in rows:
            location = []
            if row.tool_name:
                location.append(f"tool `{row.tool_name}`")
            if row.step_id:
                location.append(f"step `{row.step_id}`")
            if row.event_type:
                location.append(f"event `{row.event_type}`")
            if row.sequence is not None:
                location.append(f"sequence {row.sequence}")
            refs = f" Sources: {', '.join(row.source_ids)}." if row.source_ids else ""
            prefix = f" ({'; '.join(location)})" if location else ""
            lines.append(f"- {row.warning}{prefix}.{refs}")
        return lines

    @staticmethod
    def _tool_lines(traces: list[CopilotReportToolTraceSummary]) -> list[str]:
        if not traces:
            return ["- None recorded."]
        lines: list[str] = []
        for trace in traces:
            refs = f" Sources: {', '.join(trace.source_ids)}." if trace.source_ids else ""
            status = f" Status: {trace.status}." if trace.status and trace.status != "recorded" else ""
            warnings = f" Warnings: {'; '.join(trace.warnings)}." if trace.warnings else ""
            lines.append(f"- `{trace.tool_name}`: {trace.summary}{status}{refs}{warnings}")
        return lines

    @staticmethod
    def _source_lines(sources: list[CopilotSourceRef]) -> list[str]:
        if not sources:
            return ["- None recorded."]
        lines: list[str] = []
        for source in sources:
            retrieved = ""
            if isinstance(source.retrieved_at, datetime):
                retrieved = f"; retrieved {source.retrieved_at.isoformat()}"
            lines.append(
                f"- `{source.source_id}`: {source.label} ({source.provider}; {source.kind}; {source.origin}{retrieved})"
            )
        return lines
