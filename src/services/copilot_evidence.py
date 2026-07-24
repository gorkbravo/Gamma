from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from src.models.copilot import CopilotResearchCardResult, CopilotSourceRef, ResearchClaim


def _dedupe_warnings(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def resolve_research_claims(
    claims: Iterable[ResearchClaim],
    sources: Iterable[CopilotSourceRef],
) -> tuple[list[ResearchClaim], list[str], list[str]]:
    """Resolve source-backed claims against the exact persisted source registry."""

    known_source_ids = {source.source_id for source in sources if source.source_id}
    resolved: list[ResearchClaim] = []
    reclassified: list[str] = []
    warnings: list[str] = []

    for claim in claims:
        text = str(claim.claim or "").strip()
        if not text:
            continue
        refs = list(dict.fromkeys(str(ref).strip() for ref in claim.evidence_refs if str(ref).strip()))
        valid_refs = [ref for ref in refs if ref in known_source_ids]
        unresolved_refs = [ref for ref in refs if ref not in known_source_ids]
        if valid_refs:
            resolved.append(ResearchClaim(claim=text, evidence_refs=valid_refs))
            if unresolved_refs:
                warnings.append(
                    "Removed unresolved evidence reference(s) from a source-backed claim: "
                    + ", ".join(unresolved_refs)
                    + "."
                )
            continue
        reclassified.append(text)
        detail = ", ".join(unresolved_refs) if unresolved_refs else "no evidence refs"
        warnings.append(
            "Reclassified a source-backed claim as inference because its evidence did not resolve: "
            + detail
            + "."
        )

    return resolved, list(dict.fromkeys(reclassified)), _dedupe_warnings(warnings)


def resolve_result_evidence(result: CopilotResearchCardResult) -> CopilotResearchCardResult:
    """Return a persistence-safe result whose claim refs all resolve."""

    sources_by_id: dict[str, CopilotSourceRef] = {}
    for source in result.sources:
        source_id = str(source.source_id or "").strip()
        if source_id and source_id not in sources_by_id:
            sources_by_id[source_id] = source
    sources = list(sources_by_id.values())
    if result.card is None:
        return replace(result, sources=sources)

    claims, reclassified, evidence_warnings = resolve_research_claims(
        result.card.source_backed_claims,
        sources,
    )
    card = replace(
        result.card,
        source_backed_claims=claims,
        inferred_claims=list(dict.fromkeys([*result.card.inferred_claims, *reclassified])),
    )
    return replace(
        result,
        card=card,
        sources=sources,
        warnings=_dedupe_warnings([*result.warnings, *evidence_warnings]),
    )
