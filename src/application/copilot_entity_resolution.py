from __future__ import annotations

from collections.abc import Callable
import re
from typing import Any

from src.models.copilot import (
    CopilotEntityResolution,
    CopilotEntityResolutionCandidate,
    CopilotEquityEntityProposal,
)
from src.models.fundamentals import FundamentalsSearchResult


_TICKER_PATTERN = re.compile(r"\b[A-Z]{1,5}(?:\.[A-Z])?\b")
_CASHTAG_PATTERN = re.compile(r"\$([A-Z]{1,5}(?:\.[A-Z])?)\b")
_TICKER_CUE_PATTERN = re.compile(
    r"\bticker(?:\s+symbol)?\s+(?:is\s+)?([A-Z]{1,5}(?:\.[A-Z])?)\b",
    re.IGNORECASE,
)
_NON_TICKER_ACRONYMS = {
    "AI",
    "API",
    "CAGR",
    "CAPEX",
    "CEO",
    "CFO",
    "CPI",
    "DCF",
    "EBIT",
    "EBITDA",
    "EPS",
    "EV",
    "FCF",
    "FED",
    "GAAP",
    "GDP",
    "IPO",
    "IRR",
    "IV",
    "NAV",
    "NPV",
    "OIL",
    "PCE",
    "RATE",
    "RATES",
    "ROE",
    "ROIC",
    "SEC",
    "USD",
    "VAR",
    "WACC",
}
_ENTITY_TRIGGER_TERMS = (
    "about ",
    "analyze",
    "company",
    "dcf",
    "earnings",
    "equity",
    "fair value",
    "financial",
    "fundamental",
    "market cap",
    "peer",
    "price target",
    "revenue",
    "shares",
    "stock",
    "ticker",
    "valuation",
    "value of",
)
_QUERY_STOPWORDS = {
    "a",
    "about",
    "an",
    "analysis",
    "analyze",
    "and",
    "calculate",
    "company",
    "compare",
    "current",
    "dcf",
    "do",
    "earnings",
    "estimate",
    "fair",
    "financial",
    "financials",
    "for",
    "fundamental",
    "fundamentals",
    "give",
    "is",
    "me",
    "of",
    "on",
    "please",
    "research",
    "reverse",
    "run",
    "shares",
    "stock",
    "tell",
    "the",
    "to",
    "using",
    "valuation",
    "value",
    "versus",
    "vs",
    "what",
    "with",
}
_LEGAL_SUFFIXES = {
    "ag",
    "co",
    "company",
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "limited",
    "ltd",
    "nv",
    "plc",
    "sa",
    "se",
}


SearchCompanies = Callable[..., list[FundamentalsSearchResult]]


def extract_explicit_equity_tickers(prompt: str) -> list[str]:
    text = str(prompt or "")
    explicitly_marked = [
        *[match.upper() for match in _CASHTAG_PATTERN.findall(text)],
        *[match.upper() for match in _TICKER_CUE_PATTERN.findall(text)],
    ]
    plain = [
        match
        for match in _TICKER_PATTERN.findall(text)
        if match not in _NON_TICKER_ACRONYMS
    ]
    return list(dict.fromkeys([*explicitly_marked, *plain]))


def should_attempt_equity_resolution(prompt: str) -> bool:
    text = str(prompt or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if any(term in lowered for term in _ENTITY_TRIGGER_TERMS):
        return True
    words = re.findall(r"\b[A-Z][A-Za-z0-9&'-]{2,}\b", text)
    return any(word.upper() not in _NON_TICKER_ACRONYMS for word in words[1:] or words)


def resolve_equity_entity(
    *,
    prompt: str,
    context_ticker: str | None,
    search_companies: SearchCompanies,
    proposal: CopilotEquityEntityProposal | None = None,
    extra_warnings: list[str] | None = None,
) -> CopilotEntityResolution | None:
    warnings = list(extra_warnings or [])
    selected_ticker = str(context_ticker or "").strip().upper()
    if selected_ticker:
        exact = _exact_ticker_matches(_safe_search(search_companies, selected_ticker, warnings), selected_ticker)
        candidate = _candidate_from_row(exact[0], 1.0, "active_context") if exact else CopilotEntityResolutionCandidate(
            kind="ticker",
            id=selected_ticker,
            label=selected_ticker,
            source_provider="gamma_context",
            origin="copilot.request_context.fundamentals_ticker",
            confidence=1.0,
            match_reason="active_context",
        )
        return CopilotEntityResolution(
            status="resolved",
            query=selected_ticker,
            resolved=candidate,
            candidates=[candidate],
            method="active_context",
            warnings=warnings,
        )

    explicit_tickers = extract_explicit_equity_tickers(prompt)
    if explicit_tickers:
        exact_candidates: list[CopilotEntityResolutionCandidate] = []
        for ticker in explicit_tickers:
            matches = _exact_ticker_matches(_safe_search(search_companies, ticker, warnings), ticker)
            if matches:
                exact_candidates.append(_candidate_from_row(matches[0], 1.0, "explicit_ticker"))
        if len(exact_candidates) == 1:
            candidate = exact_candidates[0]
            return CopilotEntityResolution(
                status="resolved",
                query=candidate.id,
                resolved=candidate,
                candidates=[candidate],
                method="explicit_ticker",
                warnings=warnings,
            )
        if len(exact_candidates) > 1:
            return CopilotEntityResolution(
                status="ambiguous",
                query=" / ".join(explicit_tickers),
                candidates=_dedupe_candidates(exact_candidates),
                method="explicit_ticker",
                warnings=[
                    *warnings,
                    "This Operator flow needs one primary company; specify which ticker should anchor the run.",
                ],
            )
        # An explicit symbol remains a canonical user target even when the
        # reference lookup is temporarily unavailable. The downstream
        # Fundamentals adapter still validates that symbol before returning data.
        candidate = CopilotEntityResolutionCandidate(
            kind="ticker",
            id=explicit_tickers[0],
            label=explicit_tickers[0],
            source_provider="user",
            origin="copilot.prompt.explicit_ticker",
            confidence=0.9,
            match_reason="explicit_ticker_unverified",
        )
        return CopilotEntityResolution(
            status="resolved",
            query=explicit_tickers[0],
            resolved=candidate,
            candidates=[candidate],
            method="explicit_ticker",
            warnings=warnings,
        )

    if proposal is None and not should_attempt_equity_resolution(prompt):
        return None
    if proposal is not None and not any(
        str(value or "").strip()
        for value in (proposal.mention, proposal.ticker, proposal.issuer_name)
    ):
        return None

    proposal_ticker = str(proposal.ticker or "").strip().upper() if proposal else ""
    proposal_queries = [
        str(value or "").strip()
        for value in (
            proposal.issuer_name if proposal else None,
            proposal.mention if proposal else None,
        )
        if str(value or "").strip()
    ]
    deterministic_queries = _company_queries(prompt)
    query_candidates = list(dict.fromkeys([*proposal_queries, *deterministic_queries]))
    searched: list[tuple[str, FundamentalsSearchResult]] = []

    primary_row: FundamentalsSearchResult | None = None
    if proposal_ticker:
        proposal_rows = _safe_search(search_companies, proposal_ticker, warnings)
        exact = _exact_ticker_matches(proposal_rows, proposal_ticker)
        primary_row = exact[0] if exact else None
        searched.extend((proposal_ticker, row) for row in proposal_rows)
    for query in query_candidates[:8]:
        searched.extend((query, row) for row in _safe_search(search_companies, query, warnings))

    matched_rows: list[tuple[FundamentalsSearchResult, int, str]] = []
    if primary_row is not None:
        matched_rows.append((primary_row, 0, "model_proposed_ticker"))
        for query, row in searched:
            if row.cik == primary_row.cik and _company_match_score(query, row) is not None:
                matched_rows.append((row, 1, "same_sec_issuer"))
    else:
        for query, row in searched:
            score = _company_match_score(query, row)
            if score is not None:
                matched_rows.append((row, score, "sec_company_name"))
        if matched_rows:
            best_score = min(score for _row, score, _reason in matched_rows)
            matched_rows = [item for item in matched_rows if item[1] == best_score]

    candidates = _dedupe_candidates(
        [
            _candidate_from_row(
                row,
                _candidate_confidence(score, proposal),
                reason,
            )
            for row, score, reason in matched_rows
        ]
    )
    method = "model_proposal_sec_validation" if proposal is not None else "sec_name_search"
    query = (
        str(proposal.mention or proposal.issuer_name or proposal.ticker or "").strip()
        if proposal is not None
        else (query_candidates[0] if query_candidates else None)
    ) or None
    proposal_kwargs: dict[str, Any] = {
        "model_proposal": proposal_ticker or None,
        "proposal_provider": proposal.provider if proposal else None,
        "proposal_model": proposal.model if proposal else None,
        "proposal_confidence": proposal.confidence if proposal else None,
    }
    if len(candidates) == 1:
        return CopilotEntityResolution(
            status="resolved",
            query=query,
            resolved=candidates[0],
            candidates=candidates,
            method=method,
            warnings=warnings,
            **proposal_kwargs,
        )
    if len(candidates) > 1:
        return CopilotEntityResolution(
            status="ambiguous",
            query=query,
            candidates=candidates,
            method=method,
            warnings=[
                *warnings,
                "Gamma found multiple SEC-listed matches. Specify one ticker so the Operator does not guess.",
            ],
            **proposal_kwargs,
        )
    if proposal is None and warnings:
        return CopilotEntityResolution(
            status="unavailable",
            query=query,
            method="sec_name_search",
            warnings=warnings,
        )
    if proposal is None:
        return None
    return CopilotEntityResolution(
        status="not_found",
        query=query,
        method=method,
        warnings=[
            *warnings,
            "Gamma could not validate a unique SEC-listed company. Specify the ticker explicitly.",
        ],
        **proposal_kwargs,
    )


def _safe_search(
    search_companies: SearchCompanies,
    query: str,
    warnings: list[str],
) -> list[FundamentalsSearchResult]:
    try:
        return list(search_companies(query, limit=12))
    except Exception:
        warning = "SEC company identity lookup was unavailable during Copilot entity resolution."
        if warning not in warnings:
            warnings.append(warning)
        return []


def _exact_ticker_matches(
    rows: list[FundamentalsSearchResult],
    ticker: str,
) -> list[FundamentalsSearchResult]:
    normalized = ticker.strip().upper()
    return [row for row in rows if row.ticker.strip().upper() == normalized]


def _company_queries(prompt: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9&'-]+", str(prompt or ""))
    groups: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        lowered = token.lower()
        if lowered in _QUERY_STOPWORDS or token.upper() in _NON_TICKER_ACRONYMS:
            if current:
                groups.append(current)
                current = []
            continue
        current.append(token)
    if current:
        groups.append(current)
    queries: list[str] = []
    for group in groups:
        for width in range(min(4, len(group)), 0, -1):
            for start in range(0, len(group) - width + 1):
                query = " ".join(group[start : start + width]).strip()
                if len(query) >= 2:
                    queries.append(query)
    return list(dict.fromkeys(queries))[:8]


def _normalize_company_text(value: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", str(value or "").lower())
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _company_match_score(query: str, row: FundamentalsSearchResult) -> int | None:
    query_text = _normalize_company_text(query)
    ticker = row.ticker.strip().lower()
    name = _normalize_company_text(row.name)
    if not query_text:
        return None
    if query_text == ticker:
        return 0
    if query_text == name:
        return 1
    query_tokens = query_text.split()
    name_tokens = name.split()
    if query_tokens and name_tokens[: len(query_tokens)] == query_tokens:
        return 2
    if len(query_tokens) >= 2 and all(token in name_tokens for token in query_tokens):
        return 3
    return None


def _candidate_from_row(
    row: FundamentalsSearchResult,
    confidence: float,
    reason: str,
) -> CopilotEntityResolutionCandidate:
    return CopilotEntityResolutionCandidate(
        kind="ticker",
        id=row.ticker.strip().upper(),
        label=row.name,
        provider_id=row.cik,
        exchange=row.exchange,
        source_provider=row.source_provider or "sec",
        origin=row.origin or "fundamentals.sec.reference_tickers",
        confidence=max(0.0, min(1.0, confidence)),
        match_reason=reason,
    )


def _candidate_confidence(
    score: int,
    proposal: CopilotEquityEntityProposal | None,
) -> float:
    base = {0: 0.98, 1: 0.96, 2: 0.9, 3: 0.82}.get(score, 0.75)
    if proposal is None or proposal.confidence is None:
        return base
    return min(base, max(0.0, float(proposal.confidence)))


def _dedupe_candidates(
    candidates: list[CopilotEntityResolutionCandidate],
) -> list[CopilotEntityResolutionCandidate]:
    deduped: dict[str, CopilotEntityResolutionCandidate] = {}
    for candidate in candidates:
        existing = deduped.get(candidate.id)
        if existing is None or (candidate.confidence or 0.0) > (existing.confidence or 0.0):
            deduped[candidate.id] = candidate
    return sorted(deduped.values(), key=lambda item: (-(item.confidence or 0.0), item.id))
