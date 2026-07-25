from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Any

from src.models.copilot import (
    CopilotContextBundle,
    CopilotResearchCardRequest,
    CopilotSourceRef,
)
from src.models.copilot_context import (
    CopilotContextBudget,
    CopilotContextCompaction,
    CopilotContextFreshness,
    CopilotScopeContextContract,
)
from src.utils.time import now_utc


COPILOT_TOTAL_CONTEXT_BUDGET_BYTES = 96_000
COPILOT_SCOPE_CONTEXT_BUDGET_BYTES: dict[str, int] = {
    "portfolio": 28_000,
    "research": 32_000,
    "equity_research": 36_000,
    "strategy_lab": 32_000,
    "macro": 40_000,
    "commodities": 32_000,
    "maritime": 32_000,
    "sitrep": 44_000,
    "prediction_markets": 28_000,
    "crypto": 28_000,
    "fundamentals": 40_000,
    "risk": 36_000,
    "iv": 36_000,
    "external_context": 36_000,
    "synthesis": COPILOT_TOTAL_CONTEXT_BUDGET_BYTES,
}

_PRESERVED_SELECTOR_KEYS = (
    "workspace_mode",
    "mode",
    "active_mode",
    "region",
    "theme",
    "timeframe",
    "lookback_days",
    "lens",
    "selected_entity",
    "selected_ticker",
    "selected_symbol",
    "symbol",
    "ticker",
    "instrument_id",
    "contract_id",
    "route_id",
    "chokepoint_id",
    "market_id",
    "token_id",
    "account_scope",
    "research_book_id",
    "active_tab",
    "included_domains",
)

_HIGH_VALUE_FIELDS = (
    "workspace_mode",
    "mode",
    "active_mode",
    "region",
    "theme",
    "timeframe",
    "lens",
    "selected",
    "provider",
    "source_provider",
    "provider_state",
    "origin",
    "retrieved_at",
    "published_at",
    "freshness",
    "freshness_label",
    "coverage",
    "coverage_status",
    "status",
    "warnings",
    "caveats",
    "assumptions",
    "transformation_note",
    "source_ids",
    "included_domains",
)


def finalize_context_bundle(
    bundle: CopilotContextBundle,
    request: CopilotResearchCardRequest,
) -> CopilotContextBundle:
    """Attach the authoritative v2 context contract and enforce size guards.

    Fingerprints are computed from the un-compacted canonical context so a
    material source/selector/content change invalidates the previous context
    even when both inputs compact to the same bounded representation.
    """

    scope_budget = COPILOT_SCOPE_CONTEXT_BUDGET_BYTES.get(bundle.domain, 32_000)
    canonical_summary = _json_safe(bundle.summary_data)
    source_versions = _source_versions(bundle.sources)
    canonical_warnings = list(
        dict.fromkeys(str(item) for item in bundle.warnings if str(item).strip())
    )
    original_bytes = _json_size(
        {
            "summary": canonical_summary,
            "source_versions": source_versions,
            "warnings": canonical_warnings,
        }
    )
    fixed_overhead_bytes = _json_size(
        {
            "summary": {},
            "source_versions": source_versions,
            "warnings": canonical_warnings,
        }
    )
    compacted_summary, omitted_sections = _compact_to_budget(
        canonical_summary,
        max(256, scope_budget - fixed_overhead_bytes),
    )
    selectors = _context_selectors(bundle, request, canonical_summary)
    content_digest = _digest(
        {
            "summary": canonical_summary,
            "warnings": sorted(canonical_warnings),
        }
    )
    fingerprint = "ctxv2:" + _digest(
        {
            "scope": bundle.domain,
            "current_tab": bundle.current_tab,
            "selectors": selectors,
            "content_digest": content_digest,
            "source_versions": source_versions,
        }
    )
    freshness = _freshness_contract(
        bundle=bundle,
        canonical_summary=canonical_summary,
        supplied_fingerprint=request.context_fingerprint,
        fingerprint=fingerprint,
    )
    compacted = bool(omitted_sections)
    compacted_warnings = list(canonical_warnings)
    if compacted:
        omitted_count = sum(int(item.get("omitted_count") or 0) for item in omitted_sections)
        compacted_warnings.append(
            "Copilot context exceeded its scope budget and was compacted deterministically; "
            f"{omitted_count} repeated item(s) or text segment(s) are disclosed in the context contract."
        )
    warning_budget = max(
        512,
        scope_budget
        - _json_size(
            {
                "summary": compacted_summary,
                "source_versions": source_versions,
                "warnings": [],
            }
        ),
    )
    compacted_warnings, warning_omissions = _compact_warnings_to_budget(
        compacted_warnings,
        warning_budget,
    )
    omitted_sections.extend(warning_omissions)
    compacted = bool(omitted_sections)
    final_bytes = _json_size(
        {
            "summary": compacted_summary,
            "source_versions": source_versions,
            "warnings": compacted_warnings,
        }
    )
    compaction = CopilotContextCompaction(
        applied=compacted,
        strategy="deterministic_list_and_text_summary_v1" if compacted else "none",
        omitted_sections=omitted_sections,
        preserved_fields=list(_HIGH_VALUE_FIELDS),
        omitted_domains=_synthesis_budget_omissions(compacted_summary),
    )
    budget = CopilotContextBudget(
        scope_budget_bytes=scope_budget,
        total_budget_bytes=COPILOT_TOTAL_CONTEXT_BUDGET_BYTES,
        original_bytes=original_bytes,
        final_bytes=final_bytes,
        within_scope_budget=final_bytes <= scope_budget,
        within_total_budget=final_bytes <= COPILOT_TOTAL_CONTEXT_BUDGET_BYTES,
    )
    contract = CopilotScopeContextContract(
        scope=bundle.domain,
        current_tab=bundle.current_tab,
        context_fingerprint=fingerprint,
        selectors=selectors,
        content_digest=content_digest,
        source_versions=source_versions,
        budget=budget,
        freshness=freshness,
        compaction=compaction,
    )
    warnings = list(compacted_warnings)
    if not budget.within_scope_budget:
        warnings.append(
            "Copilot context remains above its declared scope budget after deterministic compaction; "
            "the context is degraded and the overage is recorded."
        )
    warnings.extend(freshness.stale_reasons)
    return replace(
        bundle,
        summary_data=compacted_summary,
        warnings=list(dict.fromkeys(warnings)),
        context_contract=contract,
    )


def aggregate_context_fingerprint(
    bundles: list[CopilotContextBundle],
    *,
    selected_domains: list[str],
) -> str | None:
    contracts = [
        bundle.context_contract
        for bundle in bundles
        if bundle.context_contract is not None
    ]
    if not contracts:
        return None
    return "ctxv2:" + _digest(
        {
            "selected_domains": list(selected_domains),
            "contexts": [
                {
                    "scope": contract.scope,
                    "fingerprint": contract.context_fingerprint,
                }
                for contract in contracts
            ],
        }
    )


def _context_selectors(
    bundle: CopilotContextBundle,
    request: CopilotResearchCardRequest,
    canonical_summary: dict[str, Any],
) -> dict[str, Any]:
    context = request.context
    selectors: dict[str, Any] = {
        "domain": bundle.domain,
        "current_tab": bundle.current_tab,
        "workspace_mode": context.workspace_mode,
        "prediction_market_id": context.prediction_market_id,
        "crypto_token_id": context.crypto_token_id,
        "fundamentals_ticker": context.fundamentals_ticker,
    }
    if context.macro is not None:
        selectors["macro"] = _json_safe(asdict(context.macro))
    for key in _PRESERVED_SELECTOR_KEYS:
        value = _find_first_key(canonical_summary, key)
        if value is not None and value not in ("", [], {}):
            selectors[key] = value
    if request.synthesis is not None:
        selectors["synthesis"] = {
            "active_tab": request.synthesis.active_tab,
            "included_domains": [
                str(scope.domain)
                for scope in request.synthesis.included_scopes
            ],
        }
    return _drop_empty(selectors)


def _freshness_contract(
    *,
    bundle: CopilotContextBundle,
    canonical_summary: dict[str, Any],
    supplied_fingerprint: str | None,
    fingerprint: str,
) -> CopilotContextFreshness:
    source_retrievals = {
        source.source_id: _datetime_text(source.retrieved_at)
        for source in sorted(bundle.sources, key=lambda item: item.source_id)
    }
    parsed_retrievals = [
        parsed
        for value in source_retrievals.values()
        if (parsed := _parse_datetime(value)) is not None
    ]
    labels = {
        str(value).strip().lower()
        for value in _find_values_for_keys(
            canonical_summary,
            {"freshness", "freshness_label", "coverage_status", "provider_state"},
        )
        if str(value or "").strip()
    }
    warning_text = " ".join(str(item).lower() for item in bundle.warnings)
    stale_reasons: list[str] = []
    status = "current"
    if labels.intersection({"unavailable", "missing", "failed"}):
        status = "unavailable"
        stale_reasons.append("Context includes explicitly unavailable provider or coverage state.")
    elif "unavailable" in warning_text and bundle.domain in {"external_context", "maritime", "commodities", "iv"}:
        status = "unavailable"
        stale_reasons.append("Context warnings report unavailable required coverage.")
    elif labels.intersection({"stale", "expired"}):
        status = "stale"
        stale_reasons.append("Context includes an explicitly stale source.")
    elif "stale" in warning_text:
        status = "stale"
        stale_reasons.append("Context warnings report stale source data.")
    elif labels.intersection({"partial", "delayed", "historical", "mocked", "sample", "unknown"}):
        status = "degraded"

    invalidated_fingerprint: str | None = None
    normalized_supplied = str(supplied_fingerprint or "").strip() or None
    if (
        normalized_supplied
        and normalized_supplied.startswith("ctxv2:")
        and normalized_supplied != fingerprint
    ):
        invalidated_fingerprint = normalized_supplied
        stale_reasons.append(
            "The supplied context fingerprint no longer matches the selected state or source versions."
        )
        status = "invalidated"

    return CopilotContextFreshness(
        status=status,
        valid=status not in {"stale", "unavailable", "invalidated"},
        latest_retrieved_at=max(parsed_retrievals) if parsed_retrievals else None,
        source_retrievals=source_retrievals,
        stale_reasons=list(dict.fromkeys(stale_reasons)),
        supplied_fingerprint=normalized_supplied,
        invalidated_fingerprint=invalidated_fingerprint,
    )


def _source_versions(sources: list[CopilotSourceRef]) -> list[dict[str, Any]]:
    return [
        _drop_empty(
            {
                "source_id": source.source_id,
                "provider": source.provider,
                "provider_native_id": source.provider_native_id,
                "origin": source.origin,
                "retrieved_at": _datetime_text(source.retrieved_at),
            }
        )
        for source in sorted(sources, key=lambda item: item.source_id)
    ]


def _compact_to_budget(
    value: dict[str, Any],
    budget_bytes: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if _json_size(value) <= budget_bytes:
        return value, []
    stages = (
        (32, 4_000),
        (16, 2_400),
        (8, 1_600),
        (4, 1_000),
        (2, 640),
        (1, 320),
    )
    last_value: dict[str, Any] = value
    last_omitted: list[dict[str, Any]] = []
    for list_limit, string_limit in stages:
        omitted: list[dict[str, Any]] = []
        candidate = _compact_value(
            value,
            path="$",
            list_limit=list_limit,
            string_limit=string_limit,
            omitted=omitted,
        )
        if not isinstance(candidate, dict):
            candidate = {"summary": candidate}
        last_value, last_omitted = candidate, omitted
        if _json_size(candidate) <= budget_bytes:
            return candidate, omitted

    # Pathological payloads can still contain many wide mapping keys. Replace
    # the largest non-critical top-level sections with an explicit digest.
    candidate = dict(last_value)
    omitted = list(last_omitted)
    replaceable = sorted(
        (
            (_json_size(section), key)
            for key, section in candidate.items()
            if not _is_high_value_key(key)
        ),
        reverse=True,
    )
    for size, key in replaceable:
        if _json_size(candidate) <= budget_bytes:
            break
        original = candidate[key]
        candidate[key] = {
            "compacted": True,
            "original_type": type(original).__name__,
            "content_digest": _digest(original),
        }
        omitted.append(
            {
                "path": f"$.{key}",
                "reason": "scope_budget",
                "omitted_count": _value_count(original),
                "original_bytes": size,
            }
        )
    if _json_size(candidate) > budget_bytes:
        protected_complex = sorted(
            (
                (_json_size(section), key)
                for key, section in candidate.items()
                if isinstance(section, (dict, list))
                and key not in _PRESERVED_SELECTOR_KEYS
            ),
            reverse=True,
        )
        for size, key in protected_complex:
            if _json_size(candidate) <= budget_bytes:
                break
            original = candidate[key]
            candidate[key] = {
                "compacted": True,
                "original_type": type(original).__name__,
                "content_digest": _digest(original),
                "preserved_facts": _bounded_high_value_facts(original),
            }
            omitted.append(
                {
                    "path": f"$.{key}",
                    "reason": "scope_budget",
                    "omitted_count": _value_count(original),
                    "original_bytes": size,
                    "high_value_summary_preserved": True,
                }
            )
    return candidate, _dedupe_omissions(omitted)


def _compact_value(
    value: Any,
    *,
    path: str,
    list_limit: int,
    string_limit: int,
    omitted: list[dict[str, Any]],
) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _compact_value(
                child,
                path=f"{path}.{key}",
                list_limit=list_limit,
                string_limit=string_limit,
                omitted=omitted,
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        retained = value[:list_limit]
        if len(value) > list_limit:
            omitted.append(
                {
                    "path": path,
                    "reason": "scope_budget",
                    "omitted_count": len(value) - list_limit,
                    "original_count": len(value),
                    "retained_count": list_limit,
                }
            )
        return [
            _compact_value(
                child,
                path=f"{path}[{index}]",
                list_limit=list_limit,
                string_limit=string_limit,
                omitted=omitted,
            )
            for index, child in enumerate(retained)
        ]
    if isinstance(value, str) and len(value) > string_limit:
        omitted.append(
            {
                "path": path,
                "reason": "scope_budget",
                "omitted_count": len(value) - string_limit,
                "original_characters": len(value),
                "retained_characters": string_limit,
            }
        )
        return value[:string_limit] + " … [context compacted]"
    return value


def _compact_warnings_to_budget(
    warnings: list[str],
    budget_bytes: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    if _json_size(warnings) <= budget_bytes:
        return warnings, []
    stages = ((32, 800), (16, 480), (8, 320), (4, 200), (2, 120))
    for item_limit, character_limit in stages:
        selected = [
            (
                warning
                if len(warning) <= character_limit
                else warning[:character_limit] + " … [warning compacted]"
            )
            for warning in warnings[:item_limit]
        ]
        omitted_count = max(0, len(warnings) - item_limit)
        truncated_count = sum(len(item) > character_limit for item in warnings[:item_limit])
        if omitted_count:
            selected.append(
                f"{omitted_count} additional warning(s) compacted; "
                f"content_digest={_digest(warnings[item_limit:])}."
            )
        if _json_size(selected) <= budget_bytes:
            return selected, [
                {
                    "path": "$.warnings",
                    "reason": "scope_budget",
                    "omitted_count": omitted_count + truncated_count,
                    "original_count": len(warnings),
                    "retained_count": min(len(warnings), item_limit),
                    "content_digest": _digest(warnings),
                }
            ]
    return [
        f"{len(warnings)} warning(s) compacted; content_digest={_digest(warnings)}."
    ], [
        {
            "path": "$.warnings",
            "reason": "scope_budget",
            "omitted_count": len(warnings),
            "original_count": len(warnings),
            "retained_count": 0,
            "content_digest": _digest(warnings),
        }
    ]


def _synthesis_budget_omissions(summary: dict[str, Any]) -> list[dict[str, str]]:
    omitted: list[dict[str, str]] = []
    for item in summary.get("omitted_domains", []) if isinstance(summary, dict) else []:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or "").strip()
        if domain:
            omitted.append(
                {
                    "domain": domain,
                    "reason": str(item.get("reason") or "budget_omission"),
                }
            )
    return omitted


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {
            str(key): _json_safe(child)
            for key, child in value.items()
            if not _looks_sensitive(str(key))
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(child) for child in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _looks_sensitive(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return normalized in {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "credentials",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
    } or normalized.endswith(("_api_key", "_secret", "_password", "_token"))


def _find_first_key(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = _find_first_key(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value[:8]:
            found = _find_first_key(child, key)
            if found is not None:
                return found
    return None


def _find_values_for_keys(value: Any, keys: set[str]) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in keys and not isinstance(child, (dict, list)):
                found.append(child)
            found.extend(_find_values_for_keys(child, keys))
    elif isinstance(value, list):
        for child in value:
            found.extend(_find_values_for_keys(child, keys))
    return found


def _drop_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: child
        for key, child in value.items()
        if child is not None and child != "" and child != [] and child != {}
    }


def _datetime_text(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value or "").strip()
    return text or None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _json_size(value: Any) -> int:
    return len(_canonical_json(value).encode("utf-8"))


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _is_high_value_key(key: str) -> bool:
    lowered = str(key).lower()
    return any(marker in lowered for marker in _HIGH_VALUE_FIELDS)


def _value_count(value: Any) -> int:
    if isinstance(value, (dict, list)):
        return len(value)
    if isinstance(value, str):
        return len(value)
    return 1


def _bounded_high_value_facts(value: Any, *, limit: int = 12) -> dict[str, Any]:
    facts: dict[str, Any] = {}

    def visit(item: Any, path: str) -> None:
        if len(facts) >= limit:
            return
        if isinstance(item, dict):
            for key in sorted(item):
                child = item[key]
                child_path = f"{path}.{key}" if path else str(key)
                if (
                    _is_high_value_key(str(key))
                    and not isinstance(child, (dict, list))
                    and child not in (None, "")
                ):
                    facts[child_path] = (
                        child[:240] + " … [fact compacted]"
                        if isinstance(child, str) and len(child) > 240
                        else child
                    )
                visit(child, child_path)
                if len(facts) >= limit:
                    return
        elif isinstance(item, list):
            for index, child in enumerate(item[:limit]):
                visit(child, f"{path}[{index}]")
                if len(facts) >= limit:
                    return

    visit(value, "")
    return facts


def _dedupe_omissions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        key = (str(item.get("path") or ""), str(item.get("reason") or ""))
        by_key[key] = item
    return [by_key[key] for key in sorted(by_key)]
