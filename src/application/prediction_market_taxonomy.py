from __future__ import annotations

"""Resolve a prediction-market contract to cross-domain research targets.

Prediction Markets has always consumed handoffs; this is what lets it push
context outward. A handoff is only emitted when the contract's own text maps to
an identifier the target tab can actually open - a "send to Commodities" button
that lands on an empty workspace is worse than no button, so an unresolvable
theme produces nothing rather than a guess.
"""

import re
from datetime import datetime

from src.models.handoff import CrossTabHandoffEnvelope, HandoffEntity, HandoffTimeframe
from src.models.prediction_markets import PredictionMarketRecord
from src.models.provenance import ProvenanceRecord
from src.utils.time import ensure_utc, now_utc

SOURCE_TAB = "prediction_markets"
SOURCE_MODE = "contract"

# Commodity instrument ids as registered in the Commodities workspace. Phrases
# are checked before single words so "heating oil" does not resolve as "oil".
COMMODITY_TERMS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("heating_oil", ("heating oil", "diesel", "distillate"), "Heating Oil / Diesel"),
    ("gasoline", ("gasoline", "rbob", "pump price", "gas prices"), "RBOB Gasoline"),
    ("henry_hub", ("natural gas", "nat gas", "henry hub", "lng"), "Henry Hub Natural Gas"),
    ("brent", ("brent",), "Brent Crude Oil"),
    ("wti", ("wti", "crude oil", "crude", "opec", "oil price", "oil prices", "barrel", "oil"), "WTI Crude Oil"),
    ("gold", ("gold", "bullion"), "Gold"),
    ("silver", ("silver",), "Silver"),
    ("platinum", ("platinum",), "Platinum"),
    ("copper", ("copper",), "Copper"),
    ("aluminum", ("aluminum", "aluminium"), "Aluminum"),
    ("zinc", ("zinc",), "Zinc"),
    ("nickel", ("nickel",), "Nickel"),
    ("lead", ("lead ingot",), "Lead"),
    ("tin", ("tin ingot",), "Tin"),
    ("iron_ore", ("iron ore",), "Iron Ore"),
    ("uranium", ("uranium", "enriched uranium"), "Uranium"),
)

# Chokepoint ids as registered in Sealanes.
CHOKEPOINT_TERMS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("hormuz", ("hormuz", "strait of hormuz", "persian gulf"), "Strait of Hormuz"),
    ("bab-el-mandeb", ("bab el mandeb", "bab-el-mandeb", "red sea", "houthi", "gulf of aden"), "Bab el-Mandeb"),
    ("suez", ("suez", "suez canal"), "Suez Canal"),
    ("panama", ("panama canal", "panama"), "Panama Canal"),
    ("malacca", ("malacca", "strait of malacca"), "Strait of Malacca"),
)

# Shipping language without a named chokepoint. Enough to justify opening
# Sealanes, not enough to claim a specific waterway.
MARITIME_GENERIC_TERMS: tuple[str, ...] = (
    "shipping",
    "tanker",
    "tankers",
    "vessel",
    "vessels",
    "port closure",
    "blockade",
    "naval blockade",
    "freight rate",
    "shipping lane",
    "maritime",
)

REGION_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "EU",
        (
            "ecb",
            "euro",
            "eurozone",
            "european central bank",
            "european union",
            "germany",
            "france",
            "italy",
            "spain",
            "netherlands",
        ),
    ),
    (
        "US",
        (
            "fed",
            "fomc",
            "federal reserve",
            "powell",
            "united states",
            "u s ",
            "congress",
            "senate",
            "treasury",
            "cpi",
            "nonfarm",
            "white house",
        ),
    ),
)

THEME_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("inflation", ("inflation", "cpi", "pce", "deflation", "price index")),
    ("policy", ("fed", "fomc", "ecb", "rate cut", "rate hike", "interest rate", "rates", "tariff", "sanction", "sanctions", "policy")),
    ("recession_risk", ("recession", "unemployment", "jobless", "layoffs", "contraction")),
    ("growth", ("gdp", "growth", "output", "industrial production")),
)

MACRO_CATEGORIES = {"Economy", "Politics", "Geopolitics", "Finance"}


def build_cross_domain_handoffs(detail: PredictionMarketRecord) -> list[CrossTabHandoffEnvelope]:
    """Every cross-domain target this contract can actually open."""
    text = _normalize(
        " ".join(
            filter(
                None,
                [detail.title, detail.subtitle, detail.event_title, detail.series_title, detail.description],
            )
        )
    )
    headline = _normalize(" ".join(filter(None, [detail.title, detail.subtitle, detail.event_title])))
    envelopes: list[CrossTabHandoffEnvelope] = []

    macro = _macro_handoff(detail, text=text, headline=headline)
    if macro is not None:
        envelopes.append(macro)
    commodity = _commodity_handoff(detail, text=text, headline=headline)
    if commodity is not None:
        envelopes.append(commodity)
    maritime = _maritime_handoff(detail, text=text, headline=headline)
    if maritime is not None:
        envelopes.append(maritime)
    return envelopes


def _macro_handoff(
    detail: PredictionMarketRecord,
    *,
    text: str,
    headline: str,
) -> CrossTabHandoffEnvelope | None:
    region, region_terms = _match_first(REGION_TERMS, text)
    theme, theme_terms = _match_first(THEME_TERMS, text)
    # A canonical category is not always present: a contract opened by id comes
    # from a detail payload that can carry fewer tags than the screener's search
    # payload. Region or theme evidence in the contract's own text is enough to
    # make Macro a resolvable target on its own.
    if detail.category not in MACRO_CATEGORIES and region is None and theme is None:
        return None
    resolved_region = region or "Global"
    resolved_theme = theme or "all"
    timeframe = _macro_timeframe(detail)

    warnings: list[str] = []
    if region is None:
        warnings.append(
            "No region-specific language was found in the contract, so Macro opens on the Global region.",
        )
    if theme is None:
        warnings.append("No macro theme was identified; Macro opens with all themes shown.")
    if not _matched_headline(region_terms + theme_terms, headline):
        warnings.append(
            "The macro match comes from the contract's resolution text rather than its headline; confirm the "
            "linkage before treating the two surfaces as the same question.",
        )

    return _envelope(
        detail,
        target_tab="macro",
        target_mode="events_regimes",
        entity=HandoffEntity(
            entity_type="macro_region",
            label=f"{resolved_region} macro events",
            normalized_id=resolved_region,
            metadata={
                "region": resolved_region,
                "theme": resolved_theme,
                "timeframe": timeframe,
                "matched_terms": list(region_terms + theme_terms),
            },
        ),
        normalized_ids={
            "market_id": detail.market_id,
            "region": resolved_region,
            "theme": resolved_theme,
            "timeframe": timeframe,
        },
        warnings=warnings,
    )


def _commodity_handoff(
    detail: PredictionMarketRecord,
    *,
    text: str,
    headline: str,
) -> CrossTabHandoffEnvelope | None:
    match = _match_catalog(COMMODITY_TERMS, text)
    if match is None:
        return None
    instrument_id, label, matched = match
    warnings: list[str] = []
    if not _matched_headline(matched, headline):
        warnings.append(
            f"'{matched[0]}' appears only in the contract's resolution text, so the {label} link is indirect.",
        )
    return _envelope(
        detail,
        target_tab="commodities",
        target_mode="events_cross_domain",
        entity=HandoffEntity(
            entity_type="commodity_instrument",
            label=label,
            normalized_id=instrument_id,
            metadata={"matched_terms": list(matched)},
        ),
        normalized_ids={"market_id": detail.market_id, "commodity_id": instrument_id},
        warnings=warnings,
    )


def _maritime_handoff(
    detail: PredictionMarketRecord,
    *,
    text: str,
    headline: str,
) -> CrossTabHandoffEnvelope | None:
    match = _match_catalog(CHOKEPOINT_TERMS, text)
    if match is not None:
        chokepoint_id, label, matched = match
        warnings: list[str] = []
        if not _matched_headline(matched, headline):
            warnings.append(
                f"'{matched[0]}' appears only in the contract's resolution text, so the {label} link is indirect.",
            )
        return _envelope(
            detail,
            target_tab="maritime",
            target_mode="chokepoints",
            entity=HandoffEntity(
                entity_type="maritime_chokepoint",
                label=label,
                normalized_id=chokepoint_id,
                metadata={"matched_terms": list(matched)},
            ),
            normalized_ids={"market_id": detail.market_id, "chokepoint_id": chokepoint_id},
            warnings=warnings,
        )

    generic = [term for term in MARITIME_GENERIC_TERMS if _contains(text, term)]
    if not generic:
        return None
    return _envelope(
        detail,
        target_tab="maritime",
        target_mode="live_map",
        entity=HandoffEntity(
            entity_type="maritime_theme",
            label="Shipping disruption context",
            normalized_id="shipping",
            metadata={"matched_terms": generic},
        ),
        normalized_ids={"market_id": detail.market_id},
        warnings=[
            "The contract uses shipping language but names no chokepoint Gamma tracks, so Sealanes opens on the "
            "live map rather than a specific waterway.",
        ],
    )


def _envelope(
    detail: PredictionMarketRecord,
    *,
    target_tab: str,
    target_mode: str,
    entity: HandoffEntity,
    normalized_ids: dict[str, str],
    warnings: list[str],
) -> CrossTabHandoffEnvelope:
    return CrossTabHandoffEnvelope(
        source_tab=SOURCE_TAB,
        source_mode=SOURCE_MODE,
        intended_target_tab=target_tab,
        intended_target_mode=target_mode,
        selected_entity=entity,
        selected_timeframe=_contract_window(detail),
        provider=detail.venue,
        source=ProvenanceRecord(
            source_provider=detail.source_provider or detail.venue,
            retrieved_at=ensure_utc(detail.retrieved_at) or ensure_utc(now_utc()),
            origin=detail.origin or "prediction_market_service.cross_domain_handoff",
            transformation_note=(
                "Target resolved from the contract's own text against Gamma's registered commodity, chokepoint, "
                "and macro vocabularies. No price or probability is carried across."
            ),
        ),
        warnings=warnings,
        normalized_ids=normalized_ids,
    )


def _contract_window(detail: PredictionMarketRecord) -> HandoffTimeframe:
    """The contract's own event window, which is the lens the target should adopt."""
    return HandoffTimeframe(
        label=f"{detail.title[:60]} event window" if detail.title else "Contract event window",
        start=ensure_utc(detail.open_time),
        end=ensure_utc(detail.close_time or detail.end_time),
    )


def _macro_timeframe(detail: PredictionMarketRecord) -> str:
    end_time = ensure_utc(detail.end_time)
    reference = ensure_utc(detail.retrieved_at) or ensure_utc(now_utc())
    if end_time is None or reference is None:
        return "3M"
    days = (end_time - reference).total_seconds() / 86400.0
    if days <= 35:
        return "1M"
    if days <= 100:
        return "3M"
    if days <= 200:
        return "6M"
    return "1Y"


def _match_first(catalog: tuple[tuple[str, tuple[str, ...]], ...], text: str) -> tuple[str | None, tuple[str, ...]]:
    for key, terms in catalog:
        matched = tuple(term for term in terms if _contains(text, term))
        if matched:
            return key, matched
    return None, ()


def _match_catalog(
    catalog: tuple[tuple[str, tuple[str, ...], str], ...],
    text: str,
) -> tuple[str, str, tuple[str, ...]] | None:
    for key, terms, label in catalog:
        matched = tuple(term for term in terms if _contains(text, term))
        if matched:
            return key, label, matched
    return None


def _matched_headline(terms: tuple[str, ...], headline: str) -> bool:
    return any(_contains(headline, term) for term in terms)


def _contains(text: str, term: str) -> bool:
    normalized_term = _normalize(term)
    if not text or not normalized_term:
        return False
    return f" {normalized_term} " in f" {text} "


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


__all__ = [
    "CHOKEPOINT_TERMS",
    "COMMODITY_TERMS",
    "build_cross_domain_handoffs",
]
