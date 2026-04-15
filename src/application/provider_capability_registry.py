from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from src.models.provider_capabilities import ProviderCapability
from src.utils.time import now_utc


_ACTIVE_NOTE = (
    "Static Roadmap V2 provider metadata curated from Gamma documentation and the implemented adapter inventory; "
    "this is a capability map, not a live health, entitlement, or credential check."
)
_PLANNED_NOTE = (
    "Static Roadmap V2 candidate metadata; status=planned means Gamma has no live adapter for this provider yet."
)


class ProviderCapabilityRegistry:
    def __init__(self, providers: list[ProviderCapability] | tuple[ProviderCapability, ...]) -> None:
        rows = tuple(providers)
        provider_ids = [_normalize_provider_id(row.provider_id) for row in rows]
        duplicates = sorted({provider_id for provider_id in provider_ids if provider_ids.count(provider_id) > 1})
        if duplicates:
            raise ValueError(f"Duplicate provider capability ids: {', '.join(duplicates)}")
        self._providers = {provider_id: row for provider_id, row in zip(provider_ids, rows)}
        self._order = tuple(provider_ids)

    def list_capabilities(
        self,
        *,
        status: str | None = None,
        include_planned: bool = True,
    ) -> list[ProviderCapability]:
        status_filter = _normalize_token(status)
        materialized_at = now_utc()
        rows: list[ProviderCapability] = []
        for provider_id in self._order:
            row = self._providers[provider_id]
            if not include_planned and row.status == "planned":
                continue
            if status_filter and row.status != status_filter:
                continue
            rows.append(_materialize(row, materialized_at))
        return rows

    def get_provider(self, provider_id: str) -> ProviderCapability | None:
        row = self._providers.get(_normalize_provider_id(provider_id))
        if row is None:
            return None
        return _materialize(row, now_utc())

    def providers_for_domain(
        self,
        domain: str,
        *,
        include_planned: bool = True,
    ) -> list[ProviderCapability]:
        target = _normalize_token(domain)
        return [
            row
            for row in self.list_capabilities(include_planned=include_planned)
            if target in {_normalize_token(item) for item in row.supported_domains}
        ]

    def providers_for_asset_class(
        self,
        asset_class: str,
        *,
        include_planned: bool = True,
    ) -> list[ProviderCapability]:
        target = _normalize_token(asset_class)
        return [
            row
            for row in self.list_capabilities(include_planned=include_planned)
            if target in {_normalize_token(item) for item in row.asset_classes}
        ]

    def provider_ids(self) -> list[str]:
        return list(self._order)


def build_default_provider_capability_registry() -> ProviderCapabilityRegistry:
    return ProviderCapabilityRegistry(DEFAULT_PROVIDER_CAPABILITIES)


@lru_cache(maxsize=1)
def get_default_provider_capability_registry() -> ProviderCapabilityRegistry:
    return build_default_provider_capability_registry()


def _capability(**kwargs) -> ProviderCapability:
    status = _normalize_token(kwargs.get("status"))
    kwargs["status"] = status
    kwargs.setdefault("source_provider", "gamma")
    kwargs.setdefault("origin", "provider_capability_registry.static")
    kwargs.setdefault("transformation_note", _PLANNED_NOTE if status == "planned" else _ACTIVE_NOTE)
    return ProviderCapability(**kwargs)


def _materialize(row: ProviderCapability, retrieved_at) -> ProviderCapability:
    return replace(row, retrieved_at=retrieved_at)


def _normalize_provider_id(value: str) -> str:
    return _normalize_token(value).replace("-", "_")


def _normalize_token(value: str | None) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


_ACTIVE_PROVIDER_CAPABILITIES: tuple[ProviderCapability, ...] = (
    _capability(
        provider_id="ibkr",
        display_name="IBKR / TWS",
        provider_class="broker",
        status="active",
        supported_domains=[
            "portfolio",
            "research",
            "risk",
            "iv",
            "macro_fx",
            "fundamentals_market_context",
            "commodities_candidate",
        ],
        asset_classes=["equities", "etfs", "options", "futures", "fx", "cash", "portfolio"],
        regions=["global_entitlement_dependent"],
        data_types=[
            "portfolio_snapshot",
            "account_summary",
            "positions",
            "snapshot_quotes",
            "historical_daily_bars",
            "fx_spot",
            "fx_history",
            "option_chain",
            "implied_volatility_surface",
        ],
        supports_live=True,
        supports_delayed=True,
        supports_historical=True,
        freshness_levels=["live", "delayed", "historical", "cached"],
        historical_depth="Entitlement, instrument, and TWS pacing dependent; not treated as a bulk history warehouse.",
        requires_user_entitlement=True,
        credential_env_vars=["IB_HOST", "IB_PORT", "IB_CLIENT_ID", "IB_ACCOUNT", "IB_MARKET_DATA_MODE"],
        configuration_notes=[
            "Requires a running Trader Workstation session for live mode.",
            "IB Gateway is not supported by Gamma yet.",
            "Market data quality depends on account subscriptions and selected live/delayed mode.",
        ],
        limitations=[
            "Session-based provider with pacing and market-data-line constraints.",
            "Historical depth varies by instrument, exchange, and entitlement.",
            "Futures and options coverage requires appropriate IBKR permissions and subscriptions.",
        ],
        provenance_notes=[
            "Existing records use source_provider='ibkr' and origins such as fundamentals.ibkr.history, fundamentals.ibkr.snapshot, ibkr.fx_history, and market-data services.",
            "Delayed snapshots should carry explicit delayed warnings when detected.",
        ],
        read_only_notes=[
            "Gamma treats IBKR/TWS as a market-data and portfolio-inspection source only.",
            "No order placement, account modification, rebalancing, or execution capability is part of this registry record.",
            "Copilot may receive IBKR-derived context only through read-only Gamma services.",
        ],
        source_provider_values=["ibkr"],
        batch_fetching="limited_by_tws_pacing",
        background_refresh_safe=False,
    ),
    _capability(
        provider_id="fred",
        display_name="FRED",
        provider_class="official",
        status="active",
        supported_domains=["macro", "risk_free_rate", "commodities_candidate"],
        asset_classes=["macro", "rates", "economic_series", "commodities"],
        regions=["US", "Global"],
        data_types=["time_series_observations", "economic_indicators", "rates_series"],
        supports_historical=True,
        freshness_levels=["official_release_lag", "historical", "cached"],
        historical_depth="Series dependent; many official macro series have multi-decade history.",
        credential_env_vars=["FRED_API_KEY"],
        configuration_notes=["FRED_API_KEY is used when configured; Gamma keeps fetched observations cached with source timestamps."],
        limitations=[
            "Series availability, frequency, and revision behavior vary by FRED series.",
            "ALFRED-style revision history is not implemented yet.",
        ],
        provenance_notes=[
            "Macro series points use source_provider='fred' and origins like fred.series.observations:<series_id>.",
            "Derived YoY, spread, and signal fields should keep FRED as source_provider and explain the transformation.",
        ],
        read_only_notes=["Official macro data only; no execution or account state."],
        source_provider_values=["fred"],
        batch_fetching="series_by_series",
        background_refresh_safe=True,
    ),
    _capability(
        provider_id="us_treasury",
        display_name="US Treasury",
        provider_class="official",
        status="active",
        supported_domains=["macro", "rates_policy"],
        asset_classes=["rates", "macro"],
        regions=["US"],
        data_types=["treasury_curve_snapshots", "nominal_curve_history", "real_yield_curve_history"],
        supports_delayed=True,
        supports_historical=True,
        freshness_levels=["official_release_lag", "historical", "cached"],
        historical_depth="Treasury XML curve history by calendar year where available from the official source.",
        limitations=[
            "Coverage is limited to Treasury-published curve fields.",
            "Intraday curve data is not provided.",
        ],
        provenance_notes=[
            "Macro curve records use source_provider='treasury' and origins tied to Treasury curve XML parsing.",
        ],
        read_only_notes=["Official rates data only; no execution or broker interaction."],
        source_provider_values=["treasury"],
        batch_fetching="yearly_curve_pages",
        background_refresh_safe=True,
    ),
    _capability(
        provider_id="official_macro_events",
        display_name="Official Macro Event Adapters",
        provider_class="official_aggregate",
        status="active",
        supported_domains=["macro", "prediction_markets_context", "copilot_context"],
        asset_classes=["macro_events", "policy", "inflation", "growth"],
        regions=["US", "EU", "Global"],
        data_types=["official_release_calendars", "policy_meetings", "event_metadata", "event_study_inputs"],
        supports_delayed=True,
        freshness_levels=["scheduled", "official_release_lag", "cached"],
        historical_depth="Current adapter focuses on upcoming official schedules rather than complete historical event databases.",
        limitations=[
            "Event-source breadth is curated and lighter outside the US lens.",
            "Some event adapters parse official HTML schedules, so source layout changes can break extraction.",
            "Global mode reuses the US macro calendar in the current implementation where cross-asset catalysts are US-centered.",
        ],
        provenance_notes=[
            "Event records use source providers such as federalreserve, bls, bea, and ecb with origins under macro.events.*.",
            "Heuristic event category and importance mappings require transformation notes.",
        ],
        read_only_notes=["Official calendar inspection only; no policy forecasting or execution path."],
        source_provider_values=["federalreserve", "bls", "bea", "ecb", "macro_calendar"],
        batch_fetching="source_calendar_pages",
        background_refresh_safe=True,
    ),
    _capability(
        provider_id="polymarket",
        display_name="Polymarket",
        provider_class="prediction_market",
        status="active",
        supported_domains=["prediction_markets", "macro_links", "copilot_context"],
        asset_classes=["prediction_markets", "event_contracts"],
        regions=["Global"],
        data_types=[
            "market_metadata",
            "probability_history",
            "volume_liquidity",
            "trades",
            "holders",
            "wallet_flow",
            "related_markets",
            "calibration_inputs",
        ],
        supports_live=True,
        supports_historical=True,
        freshness_levels=["current_public_api", "historical", "cached"],
        historical_depth="Available history depends on public Gamma, Data API, and CLOB endpoints for each market.",
        limitations=[
            "Wallet and holder data is public-chain/platform data and can be incomplete.",
            "Relatedness, freshness labels, and research rank are Gamma-defined heuristics.",
            "Endpoint availability and terms can change outside Gamma.",
        ],
        provenance_notes=[
            "Records use source_provider='polymarket' and origins such as polymarket.gamma.markets, polymarket.clob.prices_history, and polymarket.data.wallet_summary.",
            "Gamma-normalized probabilities and related-market links require transformation notes.",
        ],
        read_only_notes=["Public prediction-market research only; Gamma does not trade or route orders."],
        source_provider_values=["polymarket"],
        batch_fetching="paginated_public_endpoints",
        background_refresh_safe=True,
    ),
    _capability(
        provider_id="kalshi",
        display_name="Kalshi",
        provider_class="prediction_market",
        status="active",
        supported_domains=["prediction_markets", "macro_links", "copilot_context"],
        asset_classes=["prediction_markets", "event_contracts"],
        regions=["US", "Global"],
        data_types=[
            "market_metadata",
            "event_metadata",
            "probability_history",
            "volume_liquidity",
            "recent_trades",
            "aggregate_flow",
            "related_markets",
            "calibration_inputs",
        ],
        supports_live=True,
        supports_historical=True,
        freshness_levels=["current_public_api", "historical", "cached"],
        historical_depth="Live and historical public market endpoints where available.",
        limitations=[
            "Public endpoints do not expose wallet identities; Gamma shows aggregate taker-flow style summaries instead.",
            "Kalshi yes-side prices are normalized as binary implied probabilities.",
            "Endpoint availability and history coverage vary by market status.",
        ],
        provenance_notes=[
            "Records use source_provider='kalshi' and origins such as kalshi.markets, kalshi.event_markets, kalshi.market_candlesticks, and kalshi.market_trades.",
            "Wallet summaries for Kalshi require transformation notes because they are aggregate flow, not wallet-level data.",
        ],
        read_only_notes=["Public prediction-market research only; Gamma does not trade or route orders."],
        source_provider_values=["kalshi"],
        batch_fetching="paginated_public_endpoints",
        background_refresh_safe=True,
    ),
    _capability(
        provider_id="coingecko",
        display_name="CoinGecko",
        provider_class="crypto_market_data",
        status="active",
        supported_domains=["crypto", "copilot_context"],
        asset_classes=["crypto_tokens", "crypto_baskets", "crypto_market_data"],
        regions=["Global"],
        data_types=[
            "token_metadata",
            "spot_market_metrics",
            "price_history",
            "market_cap_history",
            "volume_history",
            "categories",
            "narrative_baskets",
        ],
        supports_live=True,
        supports_delayed=True,
        supports_historical=True,
        freshness_levels=["current_public_api", "historical", "cached", "stale_cache_fallback"],
        historical_depth="Current Gamma adapter requests up to one year of token market-chart history.",
        credential_env_vars=["COINGECKO_API_KEY"],
        configuration_notes=["COINGECKO_API_KEY is optional and sent as x-cg-demo-api-key when configured."],
        limitations=[
            "Market data is provider-normalized and can be rate-limited or stale.",
            "Narrative labels are Gamma mappings from CoinGecko categories.",
            "Coverage and token identifiers are CoinGecko-specific.",
        ],
        provenance_notes=[
            "Records use source_provider='coingecko' and origins such as coingecko.coins.markets, coingecko.coins.detail, coingecko.coins.market_chart, and coingecko.coins.categories.",
            "Turnover, FDV premium, screen score, and narrative mapping are Gamma transformations.",
        ],
        read_only_notes=["Crypto market-data research only; no wallet signing, swaps, or execution."],
        source_provider_values=["coingecko"],
        batch_fetching="token_market_pages",
        background_refresh_safe=True,
    ),
    _capability(
        provider_id="geckoterminal",
        display_name="GeckoTerminal",
        provider_class="dex_market_data",
        status="active",
        supported_domains=["crypto", "copilot_context"],
        asset_classes=["crypto_tokens", "dex_pools", "on_chain_liquidity"],
        regions=["Global"],
        data_types=["network_metadata", "pool_search", "token_pools", "reserve_liquidity", "pool_volume", "transaction_count_proxies"],
        supports_live=True,
        freshness_levels=["current_public_api", "cached", "stale_cache_fallback"],
        historical_depth="Current Gamma adapter uses current pool snapshots and does not persist full pool history.",
        limitations=[
            "Exact contract lookup depends on CoinGecko platform mappings and GeckoTerminal network coverage.",
            "Search fallback pool matching is heuristic.",
            "DEX flow metrics are pool-derived proxies, not complete wallet attribution.",
        ],
        provenance_notes=[
            "Records use source_provider='geckoterminal' and origins such as geckoterminal.token_pools, geckoterminal.search.pools, and geckoterminal.liquidity_summary.",
            "Aggregated liquidity and flow summaries require transformation notes.",
        ],
        read_only_notes=["DEX liquidity inspection only; no wallet connection, signing, swaps, or execution."],
        source_provider_values=["geckoterminal"],
        batch_fetching="network_and_pool_pages",
        background_refresh_safe=True,
    ),
    _capability(
        provider_id="sec_edgar",
        display_name="SEC EDGAR / EdgarTools",
        provider_class="filing",
        status="active",
        supported_domains=["fundamentals", "copilot_context"],
        asset_classes=["public_company_filings", "fundamentals", "equities"],
        regions=["US"],
        data_types=[
            "company_resolution",
            "ticker_reference",
            "filing_chronology",
            "company_facts",
            "financial_statement_inputs",
            "amendment_metadata",
        ],
        supports_delayed=True,
        supports_historical=True,
        freshness_levels=["official_filing_lag", "historical", "cached"],
        historical_depth="SEC filer and concept dependent; Gamma currently focuses on US SEC company facts and 10-K/10-Q filings.",
        credential_env_vars=["GAMMA_SEC_USER_NAME", "GAMMA_SEC_USER_EMAIL", "EDGAR_IDENTITY"],
        configuration_notes=[
            "EdgarTools requires an SEC identity; Gamma currently has a development fallback that should move behind user configuration.",
        ],
        limitations=[
            "Strongest for US SEC filers.",
            "Statement normalization is concept-map dependent.",
            "Broader international fundamentals are V2 future work.",
        ],
        provenance_notes=[
            "Records use source_provider='sec' for raw filing/company-facts data and source_provider='gamma' for derived quarterly or ratio values.",
            "Origins live under fundamentals.sec.* and derived rows must explain normalization or fallback logic.",
        ],
        read_only_notes=["Official filing research only; no SEC submission or account modification paths."],
        source_provider_values=["sec", "gamma"],
        batch_fetching="company_by_company",
        background_refresh_safe=True,
    ),
    _capability(
        provider_id="openai_copilot",
        display_name="OpenAI / Copilot Provider Boundary",
        provider_class="ai_model",
        status="optional",
        supported_domains=["copilot", "cross_context_synthesis"],
        asset_classes=["model_generated_research", "gamma_context"],
        regions=["Global"],
        data_types=["structured_research_cards", "grounded_synthesis", "tool_traces", "source_backed_claims"],
        freshness_levels=["model_generated", "grounded_in_gamma_context"],
        historical_depth="Model outputs are generated on demand from current Gamma context; provider response history is optional configuration.",
        requires_api_key=True,
        credential_env_vars=[
            "OPENAI_API_KEY",
            "GAMMA_COPILOT_PROVIDER",
            "GAMMA_COPILOT_MODEL",
            "GAMMA_COPILOT_REASONING_EFFORT",
            "GAMMA_COPILOT_STORE_RESPONSES",
            "GAMMA_COPILOT_API_URL",
        ],
        configuration_notes=["If OPENAI_API_KEY is absent, Gamma uses an unavailable provider boundary instead of making live calls."],
        limitations=[
            "Copilot output quality depends on supplied Gamma context and tool traces.",
            "Model-generated summaries are not source data and must distinguish source-backed claims from inference.",
        ],
        provenance_notes=[
            "Copilot results expose provider, model, source references, tool traces, warnings, and response ids where available.",
            "AI-generated claims should cite Gamma source ids or be labeled as inferred.",
        ],
        read_only_notes=[
            "Copilot is read-only and grounded in Gamma state.",
            "Copilot tools must not mutate app state, place orders, or retrieve execution authority.",
        ],
        source_provider_values=["openai_responses", "unconfigured", "mock"],
        batch_fetching="single_prompt_response",
        background_refresh_safe=False,
    ),
    _capability(
        provider_id="sample_data",
        display_name="Sample / Mock Data",
        provider_class="sample",
        status="sample",
        supported_domains=["portfolio", "research", "risk", "iv", "copilot", "tests"],
        asset_classes=["equities", "portfolio", "fx", "options", "synthetic_data"],
        regions=["demo"],
        data_types=["sample_portfolio_snapshot", "local_history_csv", "synthetic_iv_surface", "mock_copilot_cards"],
        supports_delayed=True,
        supports_historical=True,
        freshness_levels=["mocked", "local_file", "synthetic"],
        historical_depth="Limited to files and synthetic generators shipped in sample_data or test stubs.",
        limitations=[
            "Mock data is representative test data, not market truth.",
            "Synthetic IV and mock Copilot outputs are generated for offline development and smoke testing.",
        ],
        provenance_notes=[
            "Mock records should use source_provider='mock' or source_provider='gamma' with transformation notes for generated analytics.",
        ],
        read_only_notes=["Local sample data cannot trade or change external state."],
        source_provider_values=["mock", "sample_data", "gamma"],
        batch_fetching="local_files",
        background_refresh_safe=True,
    ),
)


_PLANNED_PROVIDER_CAPABILITIES: tuple[ProviderCapability, ...] = (
    _capability(
        provider_id="eia",
        display_name="EIA",
        provider_class="official",
        status="planned",
        supported_domains=["commodities", "macro"],
        asset_classes=["energy", "commodities", "macro"],
        regions=["US", "Global"],
        data_types=["inventories", "production", "storage", "demand", "energy_time_series"],
        supports_delayed=True,
        supports_historical=True,
        freshness_levels=["official_release_lag", "historical"],
        historical_depth="Candidate provider for official energy fundamentals; depth depends on EIA series.",
        requires_api_key=True,
        credential_env_vars=["EIA_API_KEY"],
        limitations=["No Gamma adapter is implemented yet.", "Should be introduced through normalized commodity series models."],
        provenance_notes=["Future EIA records should preserve source series ids, release timestamps, and inventory/production transformations."],
        read_only_notes=["Official energy data only; no trading or execution capability."],
        source_provider_values=["eia"],
        batch_fetching="planned_series_by_series",
        background_refresh_safe=True,
    ),
    _capability(
        provider_id="bls",
        display_name="BLS",
        provider_class="official",
        status="planned",
        supported_domains=["macro"],
        asset_classes=["labor", "inflation", "economic_series"],
        regions=["US"],
        data_types=["labor_statistics", "cpi", "ppi", "release_schedules"],
        supports_delayed=True,
        supports_historical=True,
        freshness_levels=["official_release_lag", "historical"],
        historical_depth="Candidate dedicated macro-series adapter; current use is limited to official event schedule parsing.",
        limitations=["Dedicated BLS series ingestion is not implemented yet."],
        provenance_notes=["Future BLS series should distinguish raw observations from Gamma transformations such as YoY change or event-window studies."],
        read_only_notes=["Official macro data only."],
        source_provider_values=["bls"],
        batch_fetching="planned_series_by_series",
        background_refresh_safe=True,
    ),
    _capability(
        provider_id="bea",
        display_name="BEA",
        provider_class="official",
        status="planned",
        supported_domains=["macro"],
        asset_classes=["growth", "national_accounts", "economic_series"],
        regions=["US"],
        data_types=["gdp", "income", "outlays", "national_accounts", "release_schedules"],
        supports_delayed=True,
        supports_historical=True,
        freshness_levels=["official_release_lag", "historical"],
        historical_depth="Candidate dedicated macro-series adapter; current use is limited to official event schedule parsing.",
        limitations=["Dedicated BEA data ingestion is not implemented yet."],
        provenance_notes=["Future BEA records should preserve official release and table identifiers."],
        read_only_notes=["Official macro data only."],
        source_provider_values=["bea"],
        batch_fetching="planned_series_by_series",
        background_refresh_safe=True,
    ),
    _capability(
        provider_id="ecb",
        display_name="ECB",
        provider_class="official",
        status="planned",
        supported_domains=["macro", "rates_policy"],
        asset_classes=["rates", "policy", "macro_events", "economic_series"],
        regions=["EU"],
        data_types=["policy_calendar", "rates_series", "eu_macro_series"],
        supports_delayed=True,
        supports_historical=True,
        freshness_levels=["official_release_lag", "historical"],
        historical_depth="Candidate dedicated EU rates and macro provider; current use is limited to ECB policy-calendar parsing.",
        limitations=["Dedicated ECB data ingestion is not implemented yet."],
        provenance_notes=["Future ECB records should identify official datasets and clearly label policy-path interpretations as Gamma-derived."],
        read_only_notes=["Official macro and policy data only."],
        source_provider_values=["ecb"],
        batch_fetching="planned_series_by_series",
        background_refresh_safe=True,
    ),
    _capability(
        provider_id="eurostat",
        display_name="Eurostat",
        provider_class="official",
        status="planned",
        supported_domains=["macro"],
        asset_classes=["economic_series", "inflation", "growth", "labor"],
        regions=["EU"],
        data_types=["eu_macro_series", "country_series", "regional_statistics"],
        supports_delayed=True,
        supports_historical=True,
        freshness_levels=["official_release_lag", "historical"],
        historical_depth="Candidate EU macro provider; depth depends on dataset.",
        limitations=["No Gamma adapter is implemented yet.", "Dataset identifiers and regional harmonization need normalized schema work."],
        provenance_notes=["Future Eurostat records should preserve dataset, frequency, unit, and country/region identifiers."],
        read_only_notes=["Official macro data only."],
        source_provider_values=["eurostat"],
        batch_fetching="planned_dataset_queries",
        background_refresh_safe=True,
    ),
    _capability(
        provider_id="databento",
        display_name="Databento",
        provider_class="specialist_market_data",
        status="planned",
        supported_domains=["commodities", "research", "iv"],
        asset_classes=["futures", "options", "equities", "market_microstructure"],
        regions=["US", "Global"],
        data_types=["futures_history", "curve_history", "tick_or_bar_data", "reference_metadata"],
        supports_live=True,
        supports_historical=True,
        freshness_levels=["provider_live_candidate", "historical"],
        historical_depth="Candidate paid provider for deeper futures and market history if IBKR/TWS is insufficient.",
        requires_api_key=True,
        requires_user_entitlement=True,
        credential_env_vars=["DATABENTO_API_KEY"],
        limitations=[
            "No Gamma adapter is implemented yet.",
            "Paid data, licensing, symbol mapping, and storage policy need evaluation before use.",
        ],
        provenance_notes=["Future records should include dataset, schema, venue, symbol mapping, and bar/tick transformation notes."],
        read_only_notes=["Market-data candidate only; no execution capability."],
        source_provider_values=["databento"],
        batch_fetching="planned_provider_dependent",
        background_refresh_safe=False,
    ),
    _capability(
        provider_id="aisstream",
        display_name="AISstream",
        provider_class="maritime",
        status="planned",
        supported_domains=["maritime_intelligence"],
        asset_classes=["ais", "vessels", "maritime"],
        regions=["Global"],
        data_types=["live_ais_positions", "vessel_static_data"],
        supports_live=True,
        freshness_levels=["streaming_candidate"],
        historical_depth="Candidate for prototype live AIS only; not a historical AIS warehouse.",
        requires_api_key=True,
        credential_env_vars=["AISSTREAM_API_KEY"],
        limitations=["No Gamma adapter is implemented yet.", "Coverage, reliability, and terms need provider evaluation."],
        provenance_notes=["Future AIS records should preserve provider timestamp, received timestamp, MMSI/IMO identifiers, and coverage warnings."],
        read_only_notes=["Maritime observation only; no vessel communication or operational control."],
        source_provider_values=["aisstream"],
        batch_fetching="streaming",
        background_refresh_safe=False,
    ),
    _capability(
        provider_id="noaa_marinecadastre",
        display_name="NOAA / MarineCadastre",
        provider_class="official_public",
        status="planned",
        supported_domains=["maritime_intelligence"],
        asset_classes=["ais", "vessels", "maritime"],
        regions=["US"],
        data_types=["historical_ais", "marine_boundaries", "ports_or_regions"],
        supports_historical=True,
        freshness_levels=["historical_dataset"],
        historical_depth="Candidate source for US historical AIS and marine geospatial reference datasets.",
        limitations=["No Gamma adapter is implemented yet.", "Coverage is US-focused and dataset size may require local storage decisions."],
        provenance_notes=["Future records should preserve dataset vintage, file/source URL, timestamp fields, and filtering transformations."],
        read_only_notes=["Historical maritime observation only."],
        source_provider_values=["noaa_marinecadastre"],
        batch_fetching="planned_bulk_files",
        background_refresh_safe=False,
    ),
    _capability(
        provider_id="global_fishing_watch",
        display_name="Global Fishing Watch",
        provider_class="public_research",
        status="planned",
        supported_domains=["maritime_intelligence"],
        asset_classes=["vessels", "fishing_activity", "maritime_events"],
        regions=["Global"],
        data_types=["vessel_activity", "event_style_activity", "geospatial_layers"],
        supports_delayed=True,
        supports_historical=True,
        freshness_levels=["provider_dependent", "historical"],
        historical_depth="Candidate source for non-commercial maritime research if terms fit Gamma's use.",
        requires_api_key=True,
        credential_env_vars=["GLOBAL_FISHING_WATCH_API_KEY"],
        limitations=["No Gamma adapter is implemented yet.", "Terms, coverage, and commercial restrictions need review before integration."],
        provenance_notes=["Future records should carry terms/coverage caveats and avoid implying complete global vessel truth."],
        read_only_notes=["Maritime research data only; no vessel communication or operational control."],
        source_provider_values=["global_fishing_watch"],
        batch_fetching="planned_provider_dependent",
        background_refresh_safe=False,
    ),
    _capability(
        provider_id="alchemy",
        display_name="Alchemy",
        provider_class="on_chain",
        status="planned",
        supported_domains=["crypto"],
        asset_classes=["wallets", "tokens", "on_chain_transfers", "nfts"],
        regions=["Global"],
        data_types=["wallet_balances", "token_transfers", "transaction_history", "contract_metadata"],
        supports_live=True,
        supports_historical=True,
        freshness_levels=["current_rpc_or_api", "historical"],
        historical_depth="Candidate provider for wallet and transfer analytics; depth depends on chain and endpoint.",
        requires_api_key=True,
        credential_env_vars=["ALCHEMY_API_KEY"],
        limitations=["No Gamma adapter is implemented yet.", "Chain coverage, rate limits, and cost need evaluation."],
        provenance_notes=["Future wallet analytics must label address-level data, aggregation windows, and Gamma-derived concentration or flow metrics."],
        read_only_notes=["Read-only chain inspection only; no wallet keys, signing, swaps, staking, or transaction submission."],
        source_provider_values=["alchemy"],
        batch_fetching="planned_provider_dependent",
        background_refresh_safe=False,
    ),
    _capability(
        provider_id="dune",
        display_name="Dune",
        provider_class="on_chain_analytics",
        status="planned",
        supported_domains=["crypto"],
        asset_classes=["wallets", "tokens", "dex_flows", "on_chain_analytics"],
        regions=["Global"],
        data_types=["query_results", "wallet_cohorts", "token_flow_summaries", "dex_activity"],
        supports_delayed=True,
        supports_historical=True,
        freshness_levels=["query_refresh_dependent", "historical"],
        historical_depth="Candidate provider for custom on-chain analytics and saved query outputs.",
        requires_api_key=True,
        credential_env_vars=["DUNE_API_KEY"],
        limitations=["No Gamma adapter is implemented yet.", "Query definitions, refresh cadence, cost, and ownership need explicit governance."],
        provenance_notes=["Future Dune records should identify query ids, refresh timestamps, query owners, and Gamma transformations from query results."],
        read_only_notes=["Read-only analytics only; no wallet keys, signing, swaps, or transaction submission."],
        source_provider_values=["dune"],
        batch_fetching="planned_query_results",
        background_refresh_safe=False,
    ),
)


DEFAULT_PROVIDER_CAPABILITIES: tuple[ProviderCapability, ...] = (
    *_ACTIVE_PROVIDER_CAPABILITIES,
    *_PLANNED_PROVIDER_CAPABILITIES,
)
