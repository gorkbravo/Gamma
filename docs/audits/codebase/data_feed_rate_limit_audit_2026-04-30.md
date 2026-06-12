# Gamma Data Feed And Rate-Limit Audit

Audit date: 2026-04-30

This maps the live data feeds Gamma can touch in the current repo and estimates load when the app is used at "full power": live mode, Research workspace/SITREP loaded, major research tabs opened, Copilot available, Commodities on IBKR, and IV surface enabled.

## Current Local Provider Configuration

From `.env`, with credentials masked:

- `MOCK_DATA=false`
- `IB_MARKET_DATA_MODE=auto`
- `AUTO_REFRESH_SECONDS=0`
- `RESEARCH_MARKET_DATA_PROVIDERS=yfinance,ibkr`
- `SITREP_MARKET_DATA_PROVIDERS=yfinance`
- `RESEARCH_OVERVIEW_CACHE_SECONDS=300`
- `SITREP_MARKET_DATA_CACHE_SECONDS=300`
- `FRED_API_KEY=SET`
- `NEWS_PROVIDER=rss,sample`
- `COMMODITIES_PROVIDER=ibkr`
- `EIA_API_KEY=SET`
- `COMMODITIES_CACHE_SECONDS=21600`
- `IBKR_COMMODITIES_ENABLED=wti,brent,henry_hub,gasoline,heating_oil,gold,silver,copper`
- `IBKR_COMMODITIES_STARTUP_ENABLED=wti`
- `IBKR_COMMODITIES_ON_DEMAND=true`
- `IBKR_COMMODITIES_CONTRACT_DEPTH=12`
- `IBKR_COMMODITIES_QUOTE_BATCH_SIZE=8`
- `OPENAI_API_KEY=SET`
- `MARITIME_PROVIDER=aisstream`
- `AISSTREAM_API_KEY=SET`
- `AISSTREAM_SAMPLE_SECONDS=6`
- `AISSTREAM_MAX_MESSAGES=500`
- `AISSTREAM_CACHE_SECONDS=30`
- IV line budgets: standard `60`, deep/front-deep `120`, max `240`

## Executive Summary

The biggest practical risk is not REST API rate limits. It is IBKR market-data-line pressure from IV plus commodities futures curves.

Approximate risk ranking:

1. **IBKR/TWS streaming lines: high risk when IV deep/max is active.** Standard IV uses up to 60 option lines plus the underlying. Commodities can add 12 futures snapshot lines for the selected root. Deep IV can use 120 lines and max can use 240, which is above the common default IBKR line capacity for many accounts before considering TWS watchlists or other API clients.
2. **CoinGecko/GeckoTerminal: medium risk during crypto refresh bursts.** The normal Crypto workspace is fine, but selected-token loading fans out into several parallel calls and currently duplicates some detail/liquidity work before caches settle. GeckoTerminal public API is only 30 calls/minute.
3. **FRED: medium risk on cold or forced Macro refresh.** Macro has 36 registered series and 21 unique FRED source series. The total per minute is usually safe, but forced snapshot/divergence/history refresh can burst faster than FRED's documented 2 requests/second guidance because Gamma does not throttle FRED calls.
4. **yfinance: medium/unknown risk.** SITREP cold start can ask yfinance for about 94 histories. yfinance is unofficial and has no stable public quota, so this is a reliability risk even when it is not a contractual limit breach.
5. **Polymarket/Kalshi: low risk.** Gamma's usage is tiny versus published limits.
6. **EIA, SEC/EdgarTools, RSS, AISstream, OpenAI: currently low to medium depending on operator use.** EIA and SEC are cache-friendly. OpenAI is account-tier dependent. AISstream is bounded by sample seconds and message cap.

## Feed Map

| Feed | Used by | Current mode | Cold/full-load request shape | Cache/throttle | Rate-limit risk |
| --- | --- | --- | --- | --- | --- |
| IBKR/TWS account + portfolio | Portfolio, Risk, Research fallback, Fundamentals price context | Live | Portfolio snapshot on workspace entry; risk/performance can request one daily history per non-cash position | Historical bars cached 24h; historical queue throttles at 1 request/sec | Low to medium unless portfolio is large and repeatedly force-refreshed |
| IBKR/TWS listed-market history | Research, Risk, Fundamentals, Macro FX | Fallback for Research; direct for FX/fundamentals price | One `reqHistoricalData` per symbol/cache miss; Macro FX registry has 13 FX pairs | 24h disk cache for market data; Research overview cache 300s | Medium if yfinance fails and broad universes fall back to IBKR |
| IBKR/TWS snapshot quotes | Fundamentals, Commodities, FX spot fallback | Live/auto | Fundamentals selected ticker adds 1 snapshot; Commodities selected root adds up to 12 futures snapshots | Quote cache in memory; commodities selected curve cache 300s | Medium; snapshots still consume lines while active |
| IBKR/TWS options streaming | IV tab | Live/auto | Underlying stream plus up to standard 60, deep 120, max 240 option quote lines | Engine cancels on stop; frontend polls session every 1.5s but that poll is local backend state | **High** for deep/max presets |
| yfinance | Research overview and SITREP listed-market boards | Primary for Research/SITREP | SITREP entry loads `broad_us_market` 80 symbols + SPY benchmark, and `global_indices` 12 + SPY, about 94 yfinance calls on cold cache | Research overview and per-symbol caches 300s; no external rate limiter | Medium/unknown because yfinance is unofficial |
| FRED | Macro, Commodities spot/proxy enrichment | API key set | Macro registry: 36 series total, 21 unique FRED source series. Commodities adds 14 FRED price proxy series when enabled. | FRED cache TTL usually 24-72h for Macro, 6h for Commodities; no request-rate throttle | Medium on cold/forced refresh bursts |
| US Treasury XML | Macro rates curve | Public | US Rates & Policy loads current year and sometimes prior year XML for nominal curve | 6h cache | Low |
| Official macro calendars | Macro events | Public pages | US events fetches Fed, CPI, PPI, Employment, JOLTS, BEA pages; EU fetches ECB calendar | 12h cache | Low |
| EIA API | Commodities | API key set, under IBKR reference provider | 11 inventory/fundamental series + 2 product spot price series per cold 6h refresh | 6h cache | Low |
| Polymarket Gamma/Data/CLOB | Prediction Markets, Macro linked markets | Public | Screener: usually 1 Gamma API request. Selected market bundle can add detail, CLOB history, trades, holders, related/event, calibration, and cross-venue list; roughly 8-12 cold calls | 24h generic cache unless force-refreshed | Low versus official limits |
| Kalshi public API | Prediction Markets, Macro linked markets | Public | Screener: usually 1 market list. Selected bundle adds detail/history/trades/event/calibration; related cross-venue may list the opposite venue | 24h generic cache unless force-refreshed | Low versus Basic 20 read req/s |
| CoinGecko | Crypto | Demo/API key supported if set | Workspace: 1 markets call and 1 categories call. Selected token bundle can add detail, history, comparison/basket lookups, and benchmark/detail calls; cold parallel load can be around 5-8 calls | Markets/detail 20m, history 6h, categories 4h | Medium if using free/demo limits and force-refreshing |
| GeckoTerminal | Crypto DEX liquidity | Public | Workspace network map can paginate, then selected token liquidity does token-pools or search-pools lookup; flow duplicates liquidity through service calls | Networks 30d, pool lookups 20m | Medium because public API is 30 calls/min |
| SEC EDGAR / data.sec.gov via EdgarTools | Fundamentals | Public, identity configured in code/env | Search loads ticker reference; selected ticker loads company facts/filing data. Overview and financials reuse in-memory company cache | In-memory company cache, reference cache | Low for normal interactive use; force-refresh can become noisy |
| RSS feeds | SITREP/news | `rss,sample` | 9 curated RSS feeds per refresh | No TTL in provider; only loaded on SITREP entry/refresh | Low, but should get a short cache if SITREP is refreshed often |
| AISstream websocket | Maritime | API key set | One websocket sample per workspace load: up to 6 seconds or 500 messages | 30s in-memory cache | Low to medium; load is bounded but provider quota is plan-specific |
| OpenAI Responses API | Copilot | API key set | One request per generated card/follow-up; cross-context synthesis can use larger prompts | Store responses enabled; no app-side token/RPM limiter | Account-tier dependent |

## Full-Power Load Scenarios

### Research Workspace / SITREP Entry

`loadSitrepContext()` fires these in parallel:

- `/news/latest`: 9 RSS feed fetches.
- `/research/overview` for `broad_us_market`: 80 symbols plus `SPY` benchmark.
- `/research/overview` for `global_indices`: 12 symbols plus `SPY` benchmark.
- `/macro/snapshot`, `/macro/divergences`, `/macro/events`.
- `/commodities/workspace`.
- `/prediction-markets/screener` with limit 12.

Cold-cache impact:

- yfinance: about 94 history downloads.
- FRED: up to the active Macro series set, with 21 unique source series across the whole registry.
- IBKR commodities: with current settings only `wti` is warmed by default, so about 1 contract-details request, up to 12 futures snapshot lines, and 1 front-history request, plus EIA/FRED reference enrichment if caches are cold.
- Prediction markets: about 2 venue list calls.
- News: 9 RSS calls.

The 5-second frontend status poll only calls `/system/status`; it does not hit external market data.

### Prediction Markets Tab

Cold screener load:

- 1 Polymarket list/search/category call.
- 1 Kalshi list call.

Selecting the first visible market then loads detail, history, wallet/flow summary, related markets, and calibration in parallel. Because each backend endpoint resolves market detail independently, the same detail payload may be requested several times before the cache is populated.

Risk is still low because Polymarket's published public limits are high and Kalshi Basic read limit is 20 requests/sec, but there is avoidable duplication.

### Crypto Tab

Cold workspace:

- CoinGecko `/coins/markets`.
- CoinGecko `/coins/categories`.
- GeckoTerminal `/networks`, possibly multiple pages on a first-ever network-map build.

Selecting the first token then launches detail, history, liquidity, flow, and comparison in parallel. Service calls duplicate `get_token_detail()` and `get_dex_liquidity()` through flow/comparison paths, so a cold forced refresh can create a burst.

This is the main REST-rate-limit concern because:

- CoinGecko Demo is 30 calls/minute and 10,000 calls/month.
- GeckoTerminal public API is 30 calls/minute.

Normal cached use is fine. Repeated force refreshes or rapid token switching are the danger.

### Macro Tab

Macro registry:

- 36 total series.
- 16 raw, 5 YoY-derived, 2 spread-derived, 13 FX.
- 21 unique FRED source series across raw/YoY/spread inputs.
- US snapshot series count: 22.
- EU snapshot series count: 8.

Cold/forced refresh risk:

- `/macro/snapshot` and `/macro/divergences` are fetched in parallel and can request overlapping series.
- `prefetchMacroSeries()` then fetches chart histories after the snapshot/divergence payload.
- FRED cache TTLs are sensible, but there is no FRED-specific request throttle.

This is usually safe by count, but not always safe by burst rate. FRED's documented limit is up to 2 requests/second before 429.

### Commodities Tab

Current mode is `COMMODITIES_PROVIDER=ibkr` with EIA and FRED enrichment.

Cold EIA/FRED layer:

- 11 EIA inventory/fundamental series.
- 2 EIA product spot price series.
- 14 FRED commodity spot/proxy price series.
- Cached for 6 hours.

IBKR layer:

- Enabled roots: 8.
- Startup roots: 1 (`wti`).
- On-demand selected root: enabled.
- Contract depth: 12.
- Quote batch size: 8.

On SITREP/default overview, Gamma should warm only WTI: 1 contract discovery, 12 snapshot quote lines, 1 front-contract history. If the operator clicks through all enabled commodities with force refresh, the ceiling is roughly 8 contract discoveries, 96 futures snapshot quote lines, and 8 front-history requests.

### IV Tab

This is the line-budget ceiling:

- Standard: up to 60 option quote lines plus underlying.
- Deep/front-deep: up to 120 option quote lines plus underlying.
- Max: up to 240 option quote lines plus underlying.
- Frontend polls `/iv/session` every 1.5s while IV polling is active, but this is backend state polling, not external provider polling.

If IV and Commodities are both active:

- Standard IV + WTI curve: about 60 + 1 underlying + 12 futures snapshots = about 73 lines before TWS watchlists.
- Deep IV + WTI curve: about 133 lines before TWS watchlists.
- Max IV + WTI curve: about 253 lines before TWS watchlists.

This is where Gamma can get closest to a real market-data-line ceiling.

## Verified External Limits

These are provider-published limits as of this audit date:

- Polymarket docs: Gamma `/markets` 300 requests/10s, `/public-search` 350 requests/10s; Data `/trades` 200 requests/10s; CLOB `/prices-history` 1,000 requests/10s.
- Kalshi docs: Basic read 20 requests/sec, Advanced 30/sec, Premier 100/sec, Prime 400/sec.
- CoinGecko public/demo material: Demo plan 30 calls/minute and 10,000 calls/month.
- GeckoTerminal FAQ: Public API 30 calls/minute.
- FRED docs: 429 above up to 2 requests/second.
- EIA docs: main documented constraint found here is 5,000 rows returned per request for JSON, not an app-threatening request-rate cap for Gamma's current small series set.
- IBKR docs: real-time top-of-book subscriptions consume market-data lines across TWS and API. The actual user line allowance is account/subscription dependent, so Gamma should treat its own budgets as guardrails rather than proof of available capacity.

Sources:

- Polymarket: https://docs.polymarket.com/quickstart/introduction/rate-limits
- Kalshi: https://docs.kalshi.com/getting_started/rate_limits
- CoinGecko: https://www.coingecko.com/en/api
- GeckoTerminal: https://apiguide.geckoterminal.com/faq
- FRED: https://fred.stlouisfed.org/docs/api/fred/v2/errors.html
- EIA: https://www.eia.gov/opendata/documentation.php
- IBKR: https://interactivebrokers.github.io/tws-api/market_data.html

## Gaps In The Current Implementation

- No unified provider request ledger. Gamma exposes provider capability metadata, but it does not count outbound requests by provider/endpoint/window.
- No app-side REST rate limiter for CoinGecko, GeckoTerminal, FRED, Polymarket, Kalshi, EIA, RSS, or SEC. Only IBKR historical requests have a simple throttle queue.
- Crypto selected-token loading duplicates detail/liquidity work across parallel detail/history/liquidity/flow/comparison calls.
- Prediction selected-market loading duplicates detail resolution across parallel detail/history/wallet/related/calibration calls.
- Macro snapshot/divergence/history prefetches can duplicate series loads during forced refresh.
- IV budgets are static and do not account for open TWS watchlist lines, commodities snapshots, or another API client.
- yfinance is treated as a primary listed-market source for SITREP and Research, but it has no contractual SLA or stable official quota.

## Recommendations

1. Add a provider usage ledger in `src/services/cache.py` or a new `src/services/provider_usage.py`.
   Track provider, endpoint family, timestamp, cache hit/miss, force refresh, status, and estimated line usage.

2. Add a `/system/provider-usage` endpoint and a small diagnostics panel section.
   Show 1-minute, 10-minute, 1-hour, and daily counters, plus current IBKR line estimates.

3. Add provider-specific limiters:
   - FRED: 2 requests/sec.
   - CoinGecko Demo: 30/min unless API plan says otherwise.
   - GeckoTerminal public: 30/min.
   - RSS: add a short cache, probably 5 minutes.

4. Deduplicate cold in-flight requests per cache key.
   This matters most for Crypto selected-token bundles and Prediction selected-market bundles.

5. Put an IV + commodities line guard in the backend.
   Before starting IV, estimate requested option lines plus active commodities lines and warn/block if it exceeds a configurable `IBKR_TOTAL_MARKET_DATA_LINE_BUDGET`.

6. Reduce default "full power" IBKR exposure:
   Keep standard IV as the default, keep commodities startup to one root, and require explicit confirmation or warning for IV max preset.

7. Consider replacing broad yfinance cold loads with a batched public market-data provider or a persistent cache refresh job.
   Current yfinance cold SITREP load is the least controlled public-market path.

## Bottom Line

Under normal cached use, Gamma is not close to REST rate limits on Polymarket, Kalshi, EIA, Treasury, SEC, or RSS. It can get close to CoinGecko/GeckoTerminal if the Crypto tab is force-refreshed or token-switched rapidly. It can burst FRED too fast on cold/forced Macro refresh.

The real "full power" constraint is IBKR: standard IV plus one commodities curve is probably manageable on a typical setup, but deep/max IV can exceed practical line capacity quickly, especially with TWS watchlists open.
