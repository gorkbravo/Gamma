"""Copilot's Ideas domain (Workstream 12, checkpoint I5).

The context builder and three tools live here so ``copilot_service`` only
registers them:

* ``ideas`` context: the selected idea through :func:`idea_context_summary`.
* ``review_idea`` and ``explain_criterion_state``: read-only facts computed by
  Gamma (``idea_copilot``).
* ``draft_idea_from_context``: an automatic *draft change*. It validates the
  proposal against the observable registry and binds it as a pending
  ``CopilotDraftMutation`` through the existing confirmation service; nothing
  is created. ``ideas.apply_idea_draft`` (an *apply change*, confirmation
  required) creates a draft idea only after the user accepts it with the
  mutation's confirmation token.

Copilot never activates, closes or edits an idea or its criteria, and an idea
carries no order, account, wallet or execution authority.
"""

from __future__ import annotations

import re
from dataclasses import asdict, replace
from typing import Any

from src.application.idea_copilot import (
    build_idea_draft,
    draft_from_dict,
    draft_tool_schema,
    explain_criterion_facts,
    idea_context_summary,
    review_idea_facts,
)
from src.models.copilot import (
    CopilotContextBundle,
    CopilotDraftMutation,
    CopilotMutationApplyResult,
    CopilotResearchActionDefinition,
    CopilotSourceRef,
    CopilotToolExecution,
    CopilotToolTrace,
    new_copilot_id,
)
from src.models.ideas import IdeaOrigin
from src.services.idea_explanations import EXPLANATIONS
from src.utils.time import now_utc

IDEAS_DOMAIN = "ideas"
DRAFT_TOOL = "draft_idea_from_context"
REVIEW_TOOL = "review_idea"
EXPLAIN_TOOL = "explain_criterion_state"
PROPOSE_ACTION = "ideas.propose_idea_draft"
APPLY_ACTION = "ideas.apply_idea_draft"
DRAFT_SOURCE_PREFIX = "ideas.draft:"
EVIDENCE_SOURCES_MAX = 12
REVIEW_STATS_PATTERN = re.compile(r"\b(review|record|track record|closed ideas|statistics|stats|lessons?|how did|outcomes?)\b", re.IGNORECASE)


def _domain_label(bundle: CopilotContextBundle) -> str:
    return f"{bundle.domain.replace('_', ' ').title()} card"


def build_ideas_context(service: Any, request: Any) -> CopilotContextBundle:
    """The Ideas context contract for the selected idea (``request.context.idea_id``)."""
    if service.idea_service is None:
        raise ValueError("Ideas are not available in this runtime.")
    idea_id = str(getattr(request.context, "idea_id", None) or "").strip()
    if not idea_id:
        raise ValueError("Ideas copilot requires a selected idea. Open an idea in the Ideas tab first.")
    try:
        idea = service.idea_service.get_idea(idea_id)
    except Exception as exc:  # noqa: BLE001 - una idea borrada o ilegible se explica, no es un 500
        raise ValueError(f"The selected idea could not be read: {exc}") from exc
    warnings: list[str] = []
    tracking = None
    if idea.tracking is not None and idea.tracking.segments and service.idea_tracking is not None:
        try:
            tracking = service.idea_tracking.compute_for(idea, persist=False).to_dict()
        except Exception as exc:  # noqa: BLE001 - el titular guardado sirve de respaldo
            warnings.append(f"The tracking record could not be rebuilt ({exc.__class__.__name__}); the last stored headline is used.")
    statistics = None
    if REVIEW_STATS_PATTERN.search(str(request.prompt or "")):
        try:
            stats = service.idea_service.review_statistics()
            statistics = {key: value for key, value in asdict(stats).items() if key != "rows"}
            statistics["closed_ideas"] = len(stats.rows)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"The review statistics could not be read ({exc.__class__.__name__}).")
    summary = idea_context_summary(idea, tracking=tracking, review_statistics=statistics)
    now = now_utc()
    sources = [
        CopilotSourceRef(
            source_id="ideas.idea",
            label=f"Idea: {idea.title}",
            kind="research_record",
            provider="gamma_ideas",
            origin="idea_store",
            description="The idea's thesis, legs, criteria and journal, as stored locally.",
            retrieved_at=now,
            navigation_supported=True,
            navigation_tab="ideas",
            navigation_mode="idea",
            navigation_context={"idea_id": idea.idea_id},
        )
    ]
    if idea.tracking is not None:
        sources.append(
            CopilotSourceRef(
                source_id="ideas.tracking",
                label="Hypothetical tracking (not executed)",
                kind="timeseries",
                provider="gamma_ideas",
                origin="idea_tracking.compute",
                description="The canonical daily series rebuilt from provider closes; hypothetical, not executed.",
                retrieved_at=now,
                navigation_supported=True,
                navigation_tab="ideas",
                navigation_mode="idea",
                navigation_context={"idea_id": idea.idea_id},
            )
        )
    for pin in sorted(idea.evidence, key=lambda item: item.captured_at, reverse=True)[:EVIDENCE_SOURCES_MAX]:
        provenance = pin.provenance
        sources.append(
            CopilotSourceRef(
                source_id=f"ideas.evidence.{pin.evidence_id}",
                label=f"Pin ({pin.stance}): {pin.title}",
                kind="evidence",
                provider=provenance.source_provider if provenance else "gamma_ideas",
                origin=provenance.origin if provenance else "idea_store",
                description="Frozen at capture; it does not live-update.",
                retrieved_at=pin.captured_at,
                navigation_supported=True,
                navigation_tab="ideas",
                navigation_mode="idea",
                navigation_context={"idea_id": idea.idea_id},
            )
        )
    if len(idea.evidence) > EVIDENCE_SOURCES_MAX:
        warnings.append(f"{len(idea.evidence) - EVIDENCE_SOURCES_MAX} older pins are summarized only in the context, not listed as sources.")
    return CopilotContextBundle(
        domain=IDEAS_DOMAIN,
        current_tab=request.context.current_tab or "ideas",
        summary_data=summary,
        tool_state={"idea_id": idea.idea_id},
        sources=sources,
        warnings=warnings,
    )


def _selected_idea(service: Any, arguments: dict[str, Any], bundle: CopilotContextBundle):
    if service.idea_service is None:
        raise ValueError("Ideas are not available in this runtime.")
    idea_id = str(arguments.get("idea_id") or bundle.tool_state.get("idea_id") or "").strip()
    if not idea_id:
        raise ValueError("Name the idea, or open one in the Ideas tab.")
    return service.idea_service.get_idea(idea_id)


def tool_review_idea(service: Any, arguments: dict[str, Any], bundle: CopilotContextBundle) -> CopilotToolExecution:
    idea = _selected_idea(service, arguments, bundle)
    tracking = None
    if idea.tracking is not None and idea.tracking.segments and service.idea_tracking is not None:
        try:
            tracking = service.idea_tracking.compute_for(idea, persist=False).to_dict()
        except Exception:  # noqa: BLE001 - review_idea_facts usa el titular guardado
            tracking = None
    facts = review_idea_facts(idea, tracking)
    return CopilotToolExecution(
        output=facts,
        trace=CopilotToolTrace(
            tool_name=REVIEW_TOOL,
            summary=f"Compared the expected and realized path of “{idea.title}” and listed the evidence verdicts (read-only).",
            arguments={"idea_id": idea.idea_id},
            source_ids=["ideas.idea", *(["ideas.tracking"] if idea.tracking is not None else [])],
        ),
    )


def tool_explain_criterion_state(service: Any, arguments: dict[str, Any], bundle: CopilotContextBundle) -> CopilotToolExecution:
    idea = _selected_idea(service, arguments, bundle)
    criterion_id = str(arguments.get("criterion_id") or "").strip()
    facts = explain_criterion_facts(idea, criterion_id, EXPLANATIONS)
    return CopilotToolExecution(
        output=facts,
        trace=CopilotToolTrace(
            tool_name=EXPLAIN_TOOL,
            summary=f"Explained why “{facts['label']}” is {facts['state']} from its own evaluation (read-only).",
            arguments={"idea_id": idea.idea_id, "criterion_id": criterion_id},
            source_ids=["ideas.idea"],
        ),
    )


def tool_draft_idea(service: Any, arguments: dict[str, Any], bundle: CopilotContextBundle) -> CopilotToolExecution:
    """Validate and bind an idea proposal; it waits for the user's acceptance and creates nothing."""
    if service.idea_service is None or service.idea_observables is None:
        raise ValueError("Ideas are not available in this runtime.")
    if service.confirmation_service is None:
        raise ValueError("Copilot confirmation service is unavailable; an idea cannot be proposed.")
    service.action_registry.authorize_draft(PROPOSE_ACTION)
    proposal = build_idea_draft(arguments, service.idea_observables, source_label=_domain_label(bundle))
    payload = {**proposal.to_dict(), "source_domain": bundle.domain, "source_tab": bundle.current_tab}
    lines = [f"New draft idea: {proposal.title}", f"Thesis: {proposal.thesis}", f"Stance: {proposal.stance}"]
    lines += [f"Leg: {leg.entity.label} ({leg.entity.entity_type}) weight {leg.weight if leg.weight is not None else 'equal'}" for leg in proposal.legs]
    lines += [f"Criterion ({item.kind}): {item.label}" for item in proposal.criteria]
    mutation = service.confirmation_service.bind(
        CopilotDraftMutation(
            mutation_id=new_copilot_id("mutation"),
            domain=IDEAS_DOMAIN,
            tool_id=PROPOSE_ACTION,
            action_type="draft_change",
            target_id="new_idea",
            target_label=proposal.title,
            status="pending",
            requires_confirmation=True,
            confirmation_token=new_copilot_id("confirm"),
            apply_tool_id=APPLY_ACTION,
            rendered_diff=lines,
            proposed_payload=payload,
            rationale=proposal.rationale or None,
            warnings=list(proposal.warnings),
            source_ids=[source.source_id for source in bundle.sources][:12],
            origin="copilot_ideas.draft_idea_from_context",
            transformation_note="Gamma validated the proposal against the observable registry; nothing is created until the user accepts it.",
        )
    )
    return CopilotToolExecution(
        output={
            "status": "awaiting_user_acceptance",
            "mutation_id": mutation.mutation_id,
            "proposal": proposal.to_dict(),
            "note": "Nothing was created. The user sees this proposal and decides; accepting creates a draft idea, never an active one.",
        },
        trace=CopilotToolTrace(
            tool_name=DRAFT_TOOL,
            summary=f"Proposed a draft idea “{proposal.title}” with {len(proposal.criteria)} criteria for the user to accept.",
            arguments={"title": proposal.title, "criteria": len(proposal.criteria)},
            source_ids=[f"{DRAFT_SOURCE_PREFIX}{mutation.mutation_id}"],
        ),
    )


def apply_idea_draft(
    service: Any,
    *,
    mutation_id: str,
    confirmation_token: str,
    session_id: str | None = None,
    context_fingerprint: str | None = None,
    proposal_hash: str | None = None,
) -> CopilotMutationApplyResult:
    """Create the draft idea the user accepted; the confirmation token and proposal hash must match."""
    if service.store is None or service.confirmation_service is None:
        raise ValueError("Accepting an idea proposal requires local Copilot persistence.")
    if service.idea_service is None:
        raise ValueError("Ideas are not available in this runtime.")
    service.action_registry.authorize_confirmed_mutation(APPLY_ACTION)
    existing = service.store.get_mutation(mutation_id)
    if existing is None:
        raise ValueError(f"Copilot mutation not found: {mutation_id}")
    if existing.domain != IDEAS_DOMAIN or existing.apply_tool_id != APPLY_ACTION:
        raise ValueError(f"Unsupported Copilot mutation: {existing.tool_id}")
    mutation = service.confirmation_service.consume(
        mutation_id=mutation_id,
        confirmation_token=confirmation_token,
        session_id=str(session_id or "").strip() or None,
        context_fingerprint=str(context_fingerprint or "").strip() or None,
        proposal_hash=str(proposal_hash or "").strip() or None,
        apply_tool_id=APPLY_ACTION,
    )
    try:
        proposal = draft_from_dict(mutation.proposed_payload)
        idea = service.idea_service.create_idea_from_draft(
            proposal,
            origin=IdeaOrigin(kind="copilot", source_ref=mutation.mutation_id, label=proposal.source_label or None),
        )
    except Exception as exc:
        failed = replace(mutation, status="failed", warnings=[*mutation.warnings, f"The idea was not created: {exc}"])
        service.store.save_mutation(failed)
        service.store.sync_mutation_resolution(failed)
        raise ValueError(f"The idea was not created: {exc}") from exc
    applied = replace(
        mutation,
        status="applied",
        tool_id=APPLY_ACTION,
        action_type="apply_change",
        target_id=idea.idea_id,
        applied_at=now_utc(),
        origin="copilot_ideas.apply_idea_draft",
        transformation_note="Gamma created a draft idea from the proposal the user accepted; it is not activated.",
    )
    service.store.save_mutation(applied)
    service.store.sync_mutation_resolution(applied)
    return CopilotMutationApplyResult(
        mutation=applied,
        artifact={"idea_id": idea.idea_id, "title": idea.title, "status": idea.status, "criteria": len(idea.criteria)},
        warnings=list(applied.warnings),
    )


def proposals_for_result(service: Any, result: Any, session_id: str | None, run_id: str | None) -> list[CopilotDraftMutation]:
    """The idea proposals this result's tools bound, now tied to the session (so only it can accept them)."""
    if service.store is None:
        return []
    proposals: list[CopilotDraftMutation] = []
    seen: set[str] = set()
    for trace in result.tool_traces:
        if trace.tool_name != DRAFT_TOOL:
            continue
        for source_id in trace.source_ids:
            if not source_id.startswith(DRAFT_SOURCE_PREFIX):
                continue
            mutation_id = source_id[len(DRAFT_SOURCE_PREFIX):]
            if mutation_id in seen:
                continue
            seen.add(mutation_id)
            existing = service.store.get_mutation(mutation_id)
            if existing is None:
                continue
            if existing.status == "pending" and existing.session_id is None and session_id:
                existing = service.store.update_mutation(
                    mutation_id, lambda item: replace(item, session_id=session_id, run_id=item.run_id or run_id)
                )
            proposals.append(existing)
    return proposals


def tool_definitions(service: Any, definition_type: Any, all_domains: tuple[str, ...]) -> list[Any]:
    """The three Ideas tools for the Research Agent registry."""
    idea_and_criterion = {
        "type": "object",
        "properties": {
            "idea_id": {"type": ["string", "null"], "description": "Null for the selected idea."},
            "criterion_id": {"type": "string"},
        },
        "required": ["idea_id", "criterion_id"],
        "additionalProperties": False,
    }
    idea_only = {
        "type": "object",
        "properties": {"idea_id": {"type": ["string", "null"], "description": "Null for the selected idea."}},
        "required": ["idea_id"],
        "additionalProperties": False,
    }
    return [
        definition_type(
            name=REVIEW_TOOL,
            description=(
                "Read-only. Compare an idea's expected path (its thesis or review expectation) with the realized hypothetical "
                "tracking, and list the evidence that held or failed and the criteria that fired. Gamma computes every figure."
            ),
            domains=(IDEAS_DOMAIN,),
            parameters_schema=idea_only,
            handler=lambda arguments, bundle: tool_review_idea(service, arguments, bundle),
            failure_modes=("No idea is selected.", "The idea was deleted."),
            provenance_behavior="Returns facts from the local idea record and the rebuilt hypothetical tracking series.",
            test_coverage_owner="tests/test_copilot_ideas.py",
        ),
        definition_type(
            name=EXPLAIN_TOOL,
            description=(
                "Read-only. Explain why one criterion of an idea is pending, holding, triggered, unavailable or stale, from its own "
                "latest or triggering evaluation, its arming rule and Gamma's explanation registry."
            ),
            domains=(IDEAS_DOMAIN,),
            parameters_schema=idea_and_criterion,
            handler=lambda arguments, bundle: tool_explain_criterion_state(service, arguments, bundle),
            failure_modes=("The criterion is not on the idea.",),
            provenance_behavior="Returns the criterion's stored evaluation with its provenance and the registry texts.",
            test_coverage_owner="tests/test_copilot_ideas.py",
        ),
        definition_type(
            name=DRAFT_TOOL,
            description=(
                "Draft change, only when the user asks to draft, create or save an idea. Propose a title, a falsifiable thesis, "
                "a stance, equity/ETF/crypto legs and two to four criteria stated in advance (include an invalidation rule), "
                "grounded in the current context. Gamma validates the proposal and shows it to the user, who accepts or rejects it; "
                "nothing is created by this call, and an accepted proposal becomes a draft idea, never an active one."
            ),
            domains=all_domains,
            parameters_schema=draft_tool_schema(),
            handler=lambda arguments, bundle: tool_draft_idea(service, arguments, bundle),
            action_type="draft_change",
            read_only=False,
            mutates_local_state=False,
            requires_confirmation=False,
            permission_policy="automatic_draft",
            failure_modes=(
                "A criterion uses an observable, condition or parameter the registry refuses.",
                "Fewer than two or more than four criteria.",
            ),
            provenance_behavior="Returns the validated proposal and the pending mutation id; nothing is written to the idea store.",
            retry_policy="retry_safe_until_applied",
            test_coverage_owner="tests/test_copilot_ideas.py",
        ),
    ]


def apply_action_definition() -> CopilotResearchActionDefinition:
    return CopilotResearchActionDefinition(
        tool_id=APPLY_ACTION,
        domains=[IDEAS_DOMAIN],
        action_type="apply_change",
        description="Create a draft idea from a Copilot proposal after the user accepts it with its confirmation token.",
        input_schema={
            "type": "object",
            "properties": {"mutation_id": {"type": "string"}, "confirmation_token": {"type": "string"}},
            "required": ["mutation_id", "confirmation_token"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        read_only=False,
        mutates_local_state=True,
        requires_confirmation=True,
        request_limit=1,
        failure_modes=[
            "Confirmation token is missing or does not match.",
            "The proposal was already accepted, rejected or expired.",
            "The observable registry refuses a criterion at acceptance.",
        ],
        permission_policy="confirmation_required",
        provenance_behavior="Creates a draft idea with origin copilot and the mutation id as its source reference; journaled.",
        retry_policy="not_retry_safe_after_success",
        test_coverage_owner="tests/test_copilot_ideas.py",
    )


def propose_action_definition() -> CopilotResearchActionDefinition:
    return CopilotResearchActionDefinition(
        tool_id=PROPOSE_ACTION,
        domains=[IDEAS_DOMAIN],
        action_type="draft_change",
        description="Validate an idea proposal and bind it for the user's acceptance; no idea is created.",
        input_schema=draft_tool_schema(),
        output_schema={"type": "object"},
        read_only=False,
        mutates_local_state=False,
        requires_confirmation=False,
        request_limit=1,
        failure_modes=["The observable registry refuses a criterion."],
        permission_policy="automatic_draft",
        provenance_behavior="Returns the validated proposal and a confirmation token without writing to the idea store.",
        retry_policy="retry_safe_until_applied",
        test_coverage_owner="tests/test_copilot_ideas.py",
    )
