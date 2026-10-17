# Research Script Workspace Implementation Plan

_Living implementation and handoff document._

- Decision approved: 2026-08-29
- Last reviewed: 2026-10-15
- Implementation status: Slices 1-5 remain verified; E1/E2 have deterministic/mock acceptance; E3 complete with live Operator closure (2026-10-16); E4 bounded live Python/retention/handoff verified with weight mapping open; E5/E6 planned
- Roadmap owner: Workstream 2A in [`../roadmap.md`](../roadmap.md)
- Primary product surface: `Strategy Lab / Script`
- Natural-language entry point: Copilot Operator

## Expansion checkpoints — 2026-10-14

The user's expanded direction is an ordinary Python research workspace for tasks that are more naturally expressed in code than through Gamma's existing screens. Users may write any bounded research computation, including a simple print statement, and combine Gamma datasets with external CSV/JSON. Operator may help acquire inputs, draft code and interpret actual outputs under the existing explicit Script authorization and staged-edit contract. A predefined strategy interface or cross-tab handoff is never required to produce a useful result.

Slices 1–5 below remain the completed baseline. The following checkpoints track the expansion separately; each must record validation evidence before being marked complete.

| Checkpoint | Scope | Acceptance gate | Status |
|---|---|---|---|
| E1 — Input bundles and ordinary Python | Add multiple Gamma exports and external UTF-8 CSV/JSON/text files to one immutable bundle; preview/remove inputs; use a runnable top-level starter. | Mixed bundles preserve bytes, metadata and hashes; duplicates, invalid filenames, foreign snapshots and limits fail without losing existing inputs; retained runs remain unchanged after bundle edits; browser checks cover desktop/intermediate/narrow layouts. | Complete (2026-10-14; deterministic/mock acceptance) |
| E2 — Discoverable data and broader exports | Select Gamma objects with field/unit/coverage previews; add owning-service exports for the concrete Fundamentals, Options, Commodities, Crypto and Prediction Markets use cases. | Each export identifies source, retrieval time, units, coverage and provider degradation; no credentials or live service handles enter the runtime. | Complete (2026-10-15; deterministic/mock acceptance; live-provider acceptance not claimed) |
| E3 — Operator-assisted custom research | Allow visibly authorized Script tasks when code fits the request; acquire bundles, draft/run exact source and synthesize from actual outputs; improve reviewed revision feedback. | Evals prove scope/role separation, exact dataset/source identities, staged edits, failure truth and no silent fallback to code without Script authorization. | Complete (2026-10-16): deterministic/mock checks plus three live acquire → review → accept → isolated Python → synthesis journeys ([audit](audits/script_e3_live_closure_2026-10-16.md)) |
| E4 — Optional typed analytical results | Add an optional output helper/contract for metrics, returns, signals and weights; validate explicit handoffs into existing Strategy Lab/Risk analytics. Logs, tables, images and files remain valid standalone results. | Live structured metrics compare correctly; invalid dates/units/weights remain explicit; opening or saving a derived research object is deliberate and provenance-preserving. | In progress (2026-10-15): deterministic and bounded live Python/retention/return handoff verified; weight-handoff gate open |
| E5 — Parameters and methodology | Record parameters separately from source; provide bounded sweeps, comparisons, optional lag/cost/rebalance/alignment helpers and holdout/walk-forward checks. | Runs bind source, parameters and inputs; tests prove causal timing and stated cost/rebalance assumptions; no misleading best-in-sample certification. | Planned |
| E6 — Execution and reproducibility | Add asynchronous jobs, progress/cancellation, runtime/library metadata, optional seed recording and workload-based compute tiers. Evaluate verified libraries or bounded multi-file code only against demonstrated gaps. | Restart/cancel/timeout/expiry retain honest terminal state and unknown usage; repeatability is qualified by environment/seeds; sandbox boundaries and exact-source gates continue to pass. | Planned |

Implementation order: E1 establishes the foundation; E2 now supplies discoverable bounded datasets; select E3 research journeys next. Later checkpoints have separate acceptance gates and do not imply a new runtime/model/framework. Gamma continues to own data acquisition, permissions, storage and evidence. The official runtime review and provisional Responses/Agents SDK division are recorded in the active Copilot plan under 2026-10-14.

### E4 implementation and acceptance — 2026-10-15

**Expanded live lifecycle, 2026-10-15:** Actual yfinance-backed SPY export plus external JSON/CSV passed a three-execution Sol journey in 53.67s: 57 independently checked returns and a metric, typed signals and signed hypothetical weights, actual logs/table/image/files, server validation, temporary repeated opening, separate saving, tamper refusal, restart, later source/input changes and provenance-preserving export. Ordinary scripts without the contract and invalid optional JSON both completed with retained stdout/files. The first attempt found omitted stdout; the adapter now requests documented `code_interpreter_call.outputs`, with 130 deterministic regressions and 17 Script Operator eval checks green. Full evidence and initial failure: [live lifecycle audit](audits/script_e4_live_lifecycle_2026-10-15.md). This strengthens live E1/E2 listed-data and E4 evidence but does not certify E3's full Operator loop, cross-domain providers or weight handoff; E4 remains open for that mapping.

**Model correction, 2026-10-15:** The user explicitly selected `gpt-6.1-sol` for Script. The local live configuration and `.env.example` now use that exact ID. Official model documentation confirms Code Interpreter support; the adapter's old GPT-5-only capability allowlist now accepts exact Sol while refusing unknown GPT-6 variants. The same actual isolated-Python → retained analytical output → validated Strategy Lab handoff/restart test **passes on Sol (1 passed in 19.44s)**. Runtime/store regressions: **36 passed**. Network, model-independent limits and permissions are unchanged. This supersedes the Luna model selection in the earlier follow-up below, without closing E3 or the E4 weight gate.

**Live follow-up, 2026-10-15:** At the user's explicit request, the local `.env` now sets `GAMMA_RESEARCH_SCRIPT_RUNTIME=openai`, reusing the existing API configuration and preserving `gpt-5.6-luna`, disabled network, 1 GiB container and the 120-second limit. The configured-runtime E4 test now **passes (1 passed in 17.12s)**: actual isolated Python reads a copied supplied CSV, calculates six daily returns and a total-return metric, emits retained structured JSON, passes schema/source/input/artifact/current-run validation, opens the existing owning-service analysis and matches independent expected values within `1e-14`. Reconstructed store/service inspection is identical. This closes the earlier mock-runtime blocker for this bounded supplied-file E4 journey; it is not live market-data/provider certification or E3 Operator acceptance. Hypothetical-weight handoff remains unsupported, so E4 remains open. Earlier skipped evidence below describes the pre-switch configuration.

Delivered an optional **`gamma_analytics.json` / `gamma-script-analytics.v1`** output convention using the existing runtime file discovery/retention mechanism. No injected helper, package, Gamma import, strategy entrypoint or mandatory schema is added. Ordinary top-level Python and copied external/Gamma inputs remain supported. Exact authoring source is the immutable revision; contract/example and runtime association are inspectable in Script. Full contract, example CSV, limits, mapping matrix and implementation pointers: [Optional Script analytical results](script_analytical_results.md).

The strict schema covers named dated scalar metrics, simple/log return streams with explicit units and periods/year, dated signals and signed hypothetical NAV exposure schedules. Author-declared exact instrument namespaces/native IDs are preserved; no claim of provider identity certification is made. Nulls and limitations remain intact. Unknown versions/fields, malformed/oversized files, nonfinite numbers, date/duplicate/order failures, ambiguous units/identities and unsupported weight semantics cannot become eligible analytics.

Server inspection rereads retained bytes and checks artifact size/SHA, run/source/revision hashes, input snapshot/manifest/file hashes and completion/execution evidence. Every parsed result carries these identities plus methodology, declared instruments, sources, warnings and runtime truth. Invalid optional output leaves underlying execution status and valid logs/files untouched. Failed/incomplete/unavailable runs, association failures, missing/tampered artifacts, legacy outputs without hashes and safe previews cannot open an analysis. Preview hashes prevent stale selection or repeated actions from rebinding a different result/run/bundle. ZIP export includes raw evidence plus analytical validation.

Supported target: **complete daily simple returns declaring 252 periods/year → existing Strategy Lab return analytics**, identity fraction mapping or explicitly previewed percent/100. At least five points, bounded gaps and agreement with owning-service frequency inference are required. No filling, normalizing, resampling, benchmark fetching or calendar substitution occurs. The server calls `ResearchService.analyze_strategy_lab`; tests compare every metric and exact return values with identical owning-service inputs plus an independent compound-return calculation.

Script offers inspectable exact result/mapping/coverage/assumptions before **Open temporary Strategy Lab analysis**. Opening and repeated openings create no saved object. The existing **Save Strategy** remains a separate explicit action; its server route revalidates retained analytical content and rejects altered metrics/rows/provenance. Saved Runs restart/reopening preserves the association. Explicit **Export analysis JSON** retains analytical values and provenance. The Operator gets the optional example only within the existing authorized Script read and bounded retained validation within the existing run observation; no opening/saving tool, scope, model or orchestration expansion is added. Official documentation review and Responses/SDK decision are recorded in the active Copilot plan for 2026-10-15.

Unsupported mappings remain standalone: metrics/signals; log returns; missing observations; non-daily/other annualization calendars; unavailable targets; and hypothetical weights. **Precise weight incompatibility:** Composer gross-normalizes static signed weights, which can change NAV leverage and cannot express a dated schedule. Risk's research-book path requires computed aggregate returns and exact per-leg histories. A weight-only artifact supplies neither; E4 will not silently acquire history, normalize, discard shorts, select a live account or substitute contracts. The weight-handoff acceptance item is explicitly open.

Additional retention boundary: the provider-neutral output record now carries an additive current-run artifact association flag. Code Interpreter collection establishes it only for a new provider file identity under the exact `gamma-run-<run-id>` directory and excludes copied input filenames. Old/outside-directory citations cannot become eligible analytics. The existing wrapper, discovery, downloads, runtime/model/network configuration and limits remain unchanged. The current official Code Interpreter review is recorded in the Copilot plan.

**Deterministic verification (2026-10-15):**

| Check | Evidence |
| --- | --- |
| Combined backend | `python -m pytest tests/test_script_analytics.py tests/test_research_script.py tests/test_openai_research_script_runtime.py tests/test_script_dataset_catalog.py tests/test_script_operator_e3.py tests/test_research_script_operator.py tests/test_copilot_agents_sdk_smoke.py tests/test_api.py tests/test_research_v2.py tests/test_risk_tab_logic.py tests/test_risk_metrics.py -q` — **224 passed**. A final focused E4 run after adding oversized-artifact preservation and tightening staged-status validation — **40 passed**. |
| Numerical fidelity | Exact fractional rows and all metrics match the existing owning service. Independent `prod(1+r)-1` agrees within `1e-14`. No runtime source is executed by these fixtures. |
| Operator evals | Script eval **17 checks passed**, including optionality and non-execution truth. General Operator eval exited **0** with its existing session-persistence warnings on stderr. No live model calls were made. |
| Frontend focused | Script workspace/store, Strategy Lab view and research view-model tests — **43 passed**. |
| Frontend full | **478 passed / 2 failed**. Both failures reproduce on an untouched `git archive HEAD` frontend: `sends accepted Strategy Lab lenses through portfolio composition` and `clears stale Strategy Lab composition after failed portfolio compose` in unchanged `app.test.ts` / `app.ts`. They are existing Composer failures and remain outside E4. |
| Browser | **7 passed** against the explicit E4 fixture server and real validation/owning-analysis/save APIs. Inspected 1440/1000/390-pixel preview, temporary analysis, separate save/reopen/export, invalid-output, safe-preview and unavailable-target states, plus delayed-response/selection isolation. No page overflow; new data and controls remain readable and keyboard accessible. The disappearing-target response is deliberately injected; other validation/materialization/save responses are real fixture-server responses. |
| Static/build | TypeScript typecheck and production build pass. Only the three existing Svelte warnings in `IvView.svelte`/`Surface3D.svelte`; `git diff --check` passes. |

Every E4 owning input is pinned directly: `NoProvider` fails on any attempted acquisition, fake retained runtime artifacts are labeled deterministic fixtures, and existing suites/evals pin listed/risk history and sample providers explicitly. Browser artifacts do not prove Python execution; their runtime fixture reports execution solely to exercise eligibility/materialization. Existing E3 revision, scope, role, reviewed-input and no-retry tests remain green. Evidence screenshots: `output/playwright/script-e4/`; browser reproduction: run `tests/script_analytics_browser_server.py`, then `GAMMA_E4_BROWSER_API=http://127.0.0.1:8774 npm run test:e2e -- e2e/script-analytics.spec.ts` from `frontend`.

**Live blocker:** `$env:GAMMA_RUN_LIVE_SCRIPT_E4='true'; .venv/Scripts/python.exe -m pytest tests/test_script_analytics_live.py -q -rs` skips with `Configured runtime mock_safe_preview: available=True, executes_source=False; no runtime/model switch permitted`. No hosted Python, live market provider, model synthesis or end-to-end live handoff is certified by the fixtures. No host execution of the authored research source is used. **E4 is not complete. E3 remains open with its prior live guard/runtime limitations unchanged.** E5/E6 remain separate.

### E1 implementation notes

Implemented additive Gamma exports plus atomic multi-file UTF-8 CSV/JSON/TXT import and explicit pasted-input addition. Bundle edits derive a new immutable snapshot from retained, hash-verified input bytes, preserving timestamps and file provenance; duplicate names, invalid paths, foreign-script snapshots and aggregate/per-file/count limits fail before persistence. Removing a file also removes its filename-associated export references; legacy bundle-wide references are conservatively retained while any original files remain. Previews show up to 8 KiB of text without changing retained bytes. The latest 100 bundles are selectable and the latest bundle reloads even before a first run; historical-run inspection is separate from the next run's inputs, with explicit reuse. The starter runs top-level Python and requires no custom function contract.

Validation: 42 focused backend tests (Script service/storage/API, runtime adapter and Operator regressions), 17 frontend store/component/view tests, TypeScript typecheck and production build. An isolated mock-backend browser journey adds equity history and a Macro series plus two uploaded files, previews CSV, binds a run to four files, removes one file, reloads the unrun three-file bundle, explicitly reuses historical inputs and runs the reduced bundle. Screenshots inspected at 1440/1000/390 pixels with no page overflow or page errors; intermediate control stretching was corrected. The journey also exposed and fixed the stale export identifier label and invalid default Macro series identifier. Evidence lives in ignored `output/playwright/script-bundle/`. No live OpenAI/IBKR call, runtime/model switch, new Operator tool or authority change was made; live mixed-bundle execution remains unverified. Existing unrelated production-build warnings remain.

### E2 implementation notes — 2026-10-15

Delivered a shared server-side catalog (`script_dataset_catalog.py`) and one reusable Script dataset picker. Users search an owning-service catalog, choose an exact object/outcome, inspect fields, native units, actual observation coverage, frequency, source/retrieval times, freshness/degradation, methodology and limitations, then add copied JSON. Source/schema detail stays behind disclosure. Equity selection uses the existing curated Research universes, Macro uses its current series registry, and saved research uses its owning service; none requires typing internal IDs. Searches return at most 40 matches and disclose truncation. Fundamentals company search, token search, retained Options captures, commodity objects and Prediction Market outcomes use their current owners.

| Export slice | Owning contract / delivered payload | Unsupported or limited coverage |
|---|---|---|
| Equity history | `ResearchDataProvider.load_instrument_history_result`; exact curated instrument reference, bounded close observations, native currency, source freshness and warnings; optional last-observation weekly/monthly resampling | Not a global security master; no arbitrary nearby security substitution. 20–3650 requested calendar days, trimmed after fetch (since 2026-10-16); shorter provider coverage is labeled in `metadata.window`. |
| Macro history | `MacroService.get_series_history`; registry series, exact region and supported 1M/3M/6M/1Y window, native units/frequency | No new DB.nomics search/integration or invented observations. |
| Saved research | `ResearchService.list_saved_research/load_saved_research`; selected saved payload and provenance | Heterogeneous payload schema; sensitive fields are rejected. |
| Fundamentals | `FundamentalsService.search_companies/get_financials`; company, six annual/quarterly normalized statements, ratio views and filing/accession metadata, including native cell units and missing values | Existing SEC/company coverage only; no raw-filing bulk export, generated company summary or additional valuation integration. Valuation ratios are the existing Financials slice, not a new DCF/history product. |
| Options | Existing checksummed `IVSnapshotStore`; exact capture ID, original surface timestamp/retrieval, observed contracts/pairs, axes, grid, cell sources, model and quality metadata | Must retain a capture in Options first. No new collection, subscriptions, historical chain reconstruction, or synthetic backfill. Observed/provider/model/derived Greeks and fitted geometry remain distinct. |
| Commodities | `CommoditiesService.get_price_history/get_curve/get_workspace`; available price histories, current curves with exact contracts, spread definitions/legs/formulas/history, inventory series | Current curve only, not a historical futures dataset. Native provider/sample limitations remain; empty histories/curves cannot masquerade as observations. |
| Crypto | `CryptoService.get_workspace/get_token_detail/get_price_history/get_dex_liquidity`; exact token IDs, 30/90/365-day USD price/cap/volume observations, current token market and DEX pool liquidity | No wallet/transfer data, transaction exports, derivatives, historical pool depth or executable liquidity. Missing DEX pools are explicitly partial. |
| Prediction Markets | `PredictionMarketService.screener/get_market_detail/get_history_series`; exact venue contract and outcome/token IDs, event metadata, range/resolution/coverage and probability observations | Existing venue histories only; no inferred alternate outcome, settlement reconstruction or additional venue integration. |

All catalog exports are UTF-8 JSON with `metadata` before `data`; the metadata uses `gamma-script-dataset.v1` and carries schema, field methodology, requested identity/range, actual coverage, units/frequency, original source/retrieval times, copy time, transformation and limitations. Mixed sources/times/units are preserved rather than collapsed into a fabricated single provider observation. Cache use is labeled when exposed by the owner; otherwise it explicitly says not reported by the owning service. Copy time is not presented as upstream retrieval time. Independent CSV/JSON/TXT imports remain available. The E1 CSV domain export without a preview was retired on 2026-10-17 (see the requested-window fix below).

Inspect acquires once into a bounded server-only preview cache (16 entries, 32 MiB total, ten-minute TTL). Add verifies the exact preview selection and appends those already-copied bytes through E1's hash-verified immutable bundle path. Preview does not create a durable bundle or become the next run's selected input. An expired/evicted/restarted/foreign preview requires inspection again; existing bundles/runs remain durable. Filenames, per-file/count/aggregate/manifest limits, duplicate rejection and failure atomicity remain E1-owned. File/source metadata and original bytes are retained when another dataset is appended. The runtime receives copied files only. Public token identifiers are explicitly allowed in these known research contracts; credential/account/order/wallet/host-path fields remain rejected. No Operator tool, authorization, model, orchestration, runtime or execution-limit change was made.

Validation: 72 focused backend tests across `test_script_dataset_catalog.py`, `test_research_script.py`, `test_research_script_operator.py`, and `test_openai_research_script_runtime.py`; 17 frontend store/component/Strategy Lab tests; TypeScript typecheck; production build (existing unrelated IV/Surface3D warnings remain). Catalog/API tests exercise every slice, exact instrument/company/contract/outcome identities, observed-versus-fitted preservation, units, schema/nulls, resampling/bounds, timestamps/provenance, sensitive/nonfinite/oversized data, empty/missing providers, preview ownership/expiry/selection changes, API auth and sanitized errors, duplicate failure and restart/run/bundle preservation. Adding a preview is tested after its provider is removed, proving no second fetch.

Browser acceptance uses the actual Script component and isolated backend with explicitly pinned mock equity history and sample commodities. It searches/inspects/adds both domains plus external JSON, verifies preview/file hashes and retained timestamps, runs the safe-preview runtime, reloads retained data/metadata and exercises empty capture discovery, changed-selection invalidation and simulated unavailable discovery without discarding inputs. Screenshots were inspected at 1440/1000/390 pixels, including the expanded source/schema view; there was no page overflow or page error in the completed journey. Evidence and reproducible CLI journey are in ignored `output/playwright/script-e2/`.

This completes E2's deterministic/mock acceptance gate, not live-provider certification. During fixture setup an initial equity request reached the configured Yahoo history path and was correctly labeled `yfinance`/`historical`; a commodities discovery attempt also used the configured provider path before the fixture was pinned. Neither constitutes cross-domain live-provider acceptance. No live IBKR/SEC/Crypto/Prediction Markets or hosted-Python acceptance is claimed for E2. Provider-specific live coverage/entitlements remain subject to each owning workspace's availability. E3–E6 remain separate.

**Requested-window fix — 2026-10-16:** E3 live closure showed `equity_history` with `lookback_days=30` returning 46 observations over 64 calendar days (2026-08-13..2026-10-16) while metadata still said 30. Cause: the owning listed-data path over-fetches (yfinance requests `max(1.8 × days, 30) + 10` calendar days, and the research history cache serves any longer cached series), and the catalog copied it untrimmed. Macro had the same pattern: `history_days` of 540+ days for every timeframe. `commodity_history` ignored any supplied window. The catalog now applies the window after acquisition, in the shared `apply_window` step:

- `lookback_days` (equity; commodity history when supplied) and the Macro (`TIMEFRAME_DAYS`, e.g. 1Y = 370) and Crypto (30/90/365) timeframes are calendar-day windows `[latest observation − N days, latest observation]`. This anchor matches the Macro service's own cutoff. Longer provider history is trimmed. Equity weekly/monthly resampling runs after trimming and now keeps each period's observed date, not a future period-end label. Equity requests without a lookback state the 756-day default.
- Prediction Markets already clip to their own window. The catalog records that window and checks coverage against it.
- Every windowed export carries `metadata.window`: basis, applied days, anchor, start/end, actual coverage and calendar span, provider coverage and observation count, the requested parameters, the lookback source and a status. Status is `trimmed_to_request`, `within_request`, `shorter_than_request` or `full_available_history`. Published `coverage_start/end` come from the exported observations. Trims are described in `transformation_note`.
- Shorter provider coverage is never backfilled. It gets `shorter_than_request` and a warning. The tolerance is the series' native spacing, with a minimum of 4 days (¼ of the window for short prediction ranges), so weekends and holidays do not trigger it.
- A window or frequency parameter a domain does not apply (for example `frequency` on commodities, or `lookback_days` on Fundamentals) is labeled with a warning instead of passing silently. The request is not rejected, so Operator inspect budgets are unchanged.

Deterministic coverage in `test_script_dataset_catalog.py` reproduces the live case: 46 provider sessions trimmed to 2026-09-16..2026-10-16 for daily, weekly and monthly. It also covers a labeled 365-day request with only 57 days of provider coverage, Macro/Crypto/commodity trimming, commodity full history, a short Prediction Markets window and labels for unapplied parameters. Validation: `test_script_dataset_catalog.py` (36), `test_script_operator_e3.py` + `test_research_script.py` (48) and `test_research_script_operator.py` + `test_script_analytics_live.py` (12 passed, 2 live skipped). Not live-certified.

**Legacy export retired — 2026-10-17:** `ResearchScriptService.export_domain_input` without a `preview_id` used to refetch `equity_history` (`load_symbol_history`), `macro_series` and `saved_research` into CSV/JSON with a `research-script-domain-export.v1` reference. It declared `lookback_days`/`timeframe` but copied the over-fetched series untrimmed. Only the direct API `POST /research/strategy-lab/scripts/{id}/inputs/export` reached it. No client depended on it: the Script picker always sends the retained preview, and the frontend store's only caller is that picker. The Operator `add_input` schema types `preview_id` as an unconstrained string, so an empty `preview_id` could also reach it and refetch without inspection. That contradicted the tool's "no refetch" contract. The path was retired rather than trimmed. The catalog already covers all three domains with the shared window step, curated identities and inspection, so a second acquisition contract would have to duplicate them. Exports now require a non-blank `preview_id`. Otherwise the service raises a validation error (HTTP `422`) that names `POST /research/strategy-lab/scripts/{script_id}/dataset-preview`, before any owning service is called and without changing bundles. Retained snapshots with the old reference stay readable and unchanged. The API request model keeps `preview_id` optional because the preview route shares it. The Operator tool schema is unchanged; the server-side check is authoritative. Tests: `test_research_script.py` now uses pandas-backed owners that over-fetch like yfinance/Macro and asserts the trimmed `metadata.window` in `dataset_ref`. It also checks refusal of `None`/empty/blank `preview_id` without owner access, plus the HTTP `422`. `test_script_operator_e3.py` covers an empty Operator `preview_id`. Validation: `test_research_script.py` (23), `test_script_dataset_catalog.py` (36), `test_script_operator_e3.py` (28); `test_research_script_operator.py` + `test_script_analytics_live.py` + `test_script_analytics.py` (52 passed, 2 live skipped); Script Operator eval passed. Deterministic only; not live-certified.

### E3 implementation and acceptance — 2026-10-15

Delivered server adapters for shared catalog discovery, acquisition/schema inspection, append from retained previews, reading immutable inputs and drafting ordinary Python against actual filenames/schema. Native analytics remain preferred when they fit; Script never becomes a silent fallback. Current-turn acquisition, draft/revision and execution scopes are independent. Handlers recheck Operator role, Script intent, operation scope, Script access (visibly attached to the current request or created by the same Copilot session; corrected 2026-10-15 after Strategy Lab-authored Scripts were wrongly refused as foreign) and forbidden authority. The unverified SDK Script path returns unavailable.

The old Operator symbol-CSV export implementation has been removed. Legacy references remain explicit unmet requirements and cannot execute as resolved inputs. New acquisition uses E2's exact selection/preview contract and E1's immutable append path. Append requires the current bundle, preserving earlier Gamma datasets and user-supplied external bytes, metadata and hashes. New retained provenance omits preview IDs. Expired/foreign/changed-selection previews fail without refetching or changing bundles. The runtime receives copied files only.

Candidates atomically persist their reviewed `input_snapshot_id` with the revision. Acceptance/rejection and expected-parent conflict checks remain store-owned. Exact execution rejects a different reviewed bundle, staged/rejected source, foreign session or unresolved reference. Restart retains input binding. Unsaved editor changes block candidate decisions; accepting a candidate selects its reviewed bundle. Review shows the change summary, canonical/candidate source and input filenames/hashes/provider labels. Operator observations additionally return a bounded unified diff. An observed failed run blocks rewriting/retrying in the same run.

Run observations now expose retained log/error/summary text, the first 20 table rows with truncation labels, metric values, image descriptions and file/artifact identities. Unseen artifact contents are not asserted. Terminal run failures suppress false-success synthesis; Script budget/tool failures produce incomplete status. Mock results receive a server-owned caveat that Python did not execute. Responses transport aliases preserve internal action IDs while fixing provider tool-name syntax.

**Deterministic/mock evidence:** 84 focused Script/catalog/runtime/Operator/eval/SDK-smoke tests plus eight Checkpoint 7 loop regressions pass (92 backend tests total). Both Script and general Operator evals pass; the latter reports an average score of 0.9093 across its existing variants. E3 explicitly stubs every owning dataset service; E2 supplies exact instrument/company/capture/contract/outcome fixtures. Both eval entry points explicitly pin mock listed-history/sample owners. Coverage includes mixed Gamma datasets plus external JSON, schema/filename fidelity, no refetch, preservation, expiry, unavailable/ambiguous inputs, foreign sessions, Agent/scope refusal, staged reject/re-propose/accept, conflicts, restart/bundle binding, retained run identities, actual output contents, mock truth and failed-run rewrite/retry/false-success rejection. Safe preview does **not** prove the custom calculation executed.

Frontend: 18 store/component/Strategy Lab tests, typecheck and production build pass; existing unrelated IV/Surface3D warnings remain. Browser review at 1440/1000/390 pixels covers source comparison, reviewed inputs, acceptance, safe preview and reload with retained bundle/source/run state. Corrected isolated-session checks show no overflow or page errors. An initial harness load targeted the normal backend and emitted CORS errors; it is excluded from the corrected browser evidence. Screenshots: ignored `output/playwright/script-e3/`.

**Live evidence / open gate:** existing services/models were reused without changing `.env`, runtime or execution limits. Initial Responses calls exposed dotted-name HTTP 400 rejection; corrected calls passed. A conservatively acquisition-negative prompt withheld fetch authority truthfully. A subsequent bounded request discovered exact SPY/QQQ identities and acquired one real SPY preview through the owning yfinance provider, with its unofficial-source warning. The next inspection hit the existing 12,000 ms Operator elapsed guard. The standard one-provider-call budget also limits two-dataset acquisition in one turn; preparation may need separate explicit turns. The configured runtime is `mock_safe_preview` (`executes_source=false`), so isolated Python is unavailable under unchanged configuration. No complete live multi-dataset retention, candidate review, Python execution or retained-output synthesis is claimed. Traces/runtime/usage: ignored `output/e3-live/` and `output/e3-live-*.log`; unknown usage is not zero cost.

A broader legacy Copilot regression attempt reached configured FRED through an unpinned owning Macro adapter and was stopped; it is excluded from deterministic and live acceptance. The bounded fixtures and mocked Checkpoint 7 checks are the backend evidence. E1/E2 broader provider workflows remain uncertified.

**Pending-defect fixes — 2026-10-15:** a dated review found the following E3 defects, now fixed with deterministic coverage. Decisions are recorded in the Copilot plan.

- The Operator wrongly refused Scripts created in Strategy Lab as foreign. Access is now granted to the Script visibly attached to the request or created by the same Copilot session.
- Acquisition permission no longer follows any "add"/"combine". Code edits and negated requests fail closed.
- An accepted candidate stayed locked to its reviewed bundle even for user runs. The lock now applies only to Operator exact runs.
- Large bundle and run observations lost filenames and schemas in provider compaction. They are now fitted under budget by shortening content only.
- Discovery called providers without counting. It now counts against the budget. Authorized Script acquisition may use 4 provider calls, and live Script workflows get a 180-second elapsed guard.
- Copilot context sent only the selected run's bundle. It now sends the prepared next-run bundle: after accepting a candidate, the Operator sees the reviewed inputs, and drafts no longer bind to a stale bundle.
- The staged-review boundary is unchanged, so a data-dependent build-and-run spans two turns.

**Live closure — 2026-10-16:** E3's gate is met. Three consecutive bounded journeys on the configured `openai` runtime acquired exact SPY/QQQ yfinance exports into a bundle with a supplied `external.json`, staged a reviewed candidate, accepted it as the user, ran it in isolated Python and synthesized from actual retained outputs. One used the default `auto` profile, the others `deep`. Values were independently recomputed from the retained bundle. The live investigation found and fixed five defects. The Operator model never received the attached `script_state`. A 1,600-token output ceiling truncated code drafting. A derived change summary exceeded 512 characters. A transient Windows lock in the opt-in usage audit aborted runs. Raw wrapper hashes mismatched despite normalized verification. Follow-ups: `equity_history` returned 64 calendar days for `lookback_days=30` (disclosed, not honored); runs retain input copies and a placeholder summary as outputs; a stale "Planner-only prototype" warning remains. Only the yfinance listed-data path is live-certified. Evidence: [`audits/script_e3_live_closure_2026-10-16.md`](audits/script_e3_live_closure_2026-10-16.md).

Original gate, kept for history: E3 stays open until an allowed bounded Operator journey and a configured isolated runtime retain a useful standalone calculation and synthesize actual outputs. New acquisition may require staged source review before execution. External files must already be supplied through Script; no host-file discovery, invented uploads, arbitrary URL fetch, packages or network/account/trading authority is added. E4-E6 typed interfaces, sweeps, async execution and compute expansion remain separate.

## Start Here

Read these active documents before changing the implementation:

1. [`../roadmap.md`](../roadmap.md), especially Guiding Product Principle 5 and Workstream 2A.
2. [`copilot_v2_tab_plan.md`](./copilot_v2_tab_plan.md) for the Operator authority, run-state, tool-registry, and materialization contracts.
3. [`design_principles.md`](./design_principles.md), especially `Tab Architecture and Modes`.
4. [`provenance_expectations.md`](./provenance_expectations.md) for source, retrieval, origin, and transformation metadata.
5. [`strategy_lab_cross_tab_handoffs.md`](./strategy_lab_cross_tab_handoffs.md) before changing Strategy Lab inbound state.

This document is the detailed implementation source for the Script workspace. Update its status checklist and decision log as slices land. Do not create a competing script-workspace plan.

## Decision Summary

Gamma may add an optional, transparent Python research workflow without becoming a trading platform or a general-purpose local IDE.

The approved user experience is:

```text
User describes a strategy in natural language
  -> Copilot Operator acquires authorized read-only inputs
  -> Operator creates a temporary Python draft and input manifest
  -> Gamma opens Strategy Lab / Script
  -> user inspects or edits the canonical source
  -> Run executes that visible revision in an isolated ephemeral runtime
  -> Gamma renders logs, tables, metrics, images, files, warnings, and provenance
  -> saving, exporting, duplicating, or requesting an Operator revision is explicit
```

The permission boundary is:

**Isolated research computation is allowed. Unrestricted code authority is not.**

The runtime must not have access to Gamma's process, host filesystem, local APIs, environment, credentials, TWS/IBKR, accounts, wallets, order routing, or outbound network in the first version.

## Product Classification

This is a **mode**, not a new top-level tab.

- Tab: `Strategy Lab`
- Mode: `Script`
- Shared context: selected strategy/research objects, input datasets, benchmark, timeframe, session, and provenance
- Primary column: code editor followed by typed run outputs
- Support column: run controls, source revision, input manifest, runtime status, limits, warnings, and provenance
- Copilot relationship: Operator drafts/materializes; Script mode owns canonical editing and run inspection

The existing Strategy Lab modes remain data-first and must continue to work without loading or invoking the script runtime:

- `Composer`
- `Backtest / Analyze`
- `Regime / Stress`
- `Imports`
- `Saved Runs`

`Script` is additive. It does not replace imported return streams or Gamma-owned analytics.

## Historical Repository Starting Point

The following records the repository state when this plan was approved, before Slices 1-5 shipped. The current implementation and verification state is recorded in the delivery sections below.

### Strategy Lab UI and state

- `frontend/src/views/StrategyLabView.svelte`
  - owns the visible mode bar and the existing primary/support `workspace-grid` layout;
  - currently registers `composer`, `backtest_analyze`, `regime_stress`, `imports`, and `saved_runs`;
  - already handles inbound handoffs, saved runs, result state, and Risk opening.
- `frontend/src/lib/api/types.ts`
  - owns the `StrategyLabMode` union.
- `frontend/src/lib/stores/app.ts`
  - owns shared application and Strategy Lab state.
- `frontend/src/lib/view-models/research.ts`
  - owns Strategy Lab view-model helpers and should remain the home for non-trivial frontend transformations.

### Strategy Lab backend

- `src/models/research_lab.py`
  - owns imported-stream, composition, portfolio-leg, handoff, and validation models.
- `src/application/research_service.py`
  - owns existing Strategy Lab analysis, composition, portfolio validation, and handoff resolution.
- `src/api/schemas/research.py`
  - owns Pydantic request/response models for current Research and Strategy Lab routes.
- `src/api/routes/research.py`
  - exposes the existing `/research/strategy-lab/*` surface.
- `src/services/saved_research_store.py`
  - is a relevant persistence pattern, but script revisions/runs need their own versioned contract rather than being hidden inside generic saved-research payloads.

### Copilot Operator

- `src/application/copilot_service.py`
  - owns `_CopilotToolDefinition`, the action definitions, custom Responses Operator loop, execution, traces, and working-analysis decoration;
  - already exposes `run_strategy_lab_backtest`, but that action summarizes loaded normalized results and must not be repurposed to execute scripts.
- `src/application/research_action_registry.py`
  - remains authoritative for tool existence, schema validation, permission policy, and action classification.
- `src/models/copilot.py`
  - owns `CopilotWorkingAnalysis`, run events, traces, sources, warnings, and persistence-facing contracts.
- `src/services/copilot_store.py`
  - already persists sessions, turns, artifacts, mutations, and working analyses.
- `src/api/routes/copilot.py`
  - already streams Operator work through `/copilot/operator-plan/execute/stream` and exposes working-analysis materialization.
- `evals/copilot_operator_eval.py`
  - is the existing regression harness for tool selection, argument fidelity, observation use, stopping, and final synthesis.

### Runtime and API composition

- `src/application/runtime.py`
  - constructs stores and application services and exposes them through the shared runtime object.
- `src/api/main.py`
  - registers the current routers.
- `src/application/request_limits.py`
  - owns local memory/CPU/request safety bounds and should own or import Script limits.
- `src/models/provenance.py`
  - owns shared provenance and freshness primitives.

## Non-Goals For The First Version

Do not build:

- a top-level IDE tab;
- a local terminal or `xterm.js` surface;
- arbitrary shell access;
- a local Python subprocess runner;
- Docker as an end-user prerequisite;
- a file tree or multi-file project system;
- a package manager or arbitrary dependency installation;
- a language server, debugger, breakpoint system, Git integration, or notebook-cell graph;
- runtime access to Gamma's API, localhost, TWS/IBKR, accounts, wallets, credentials, or host files;
- direct outbound network access from user code;
- automatic execution from Research Agent mode;
- silent Operator overwrites of user-edited source;
- any interpretation of a backtest as a live or executable trading strategy.

## User and Operator Authority Contract

The intended meaning of “user editable” is:

1. Operator may create the initial script draft when the user explicitly invokes a Script workflow.
2. Materialization creates a visible, session-ephemeral draft; it does not silently create a durable saved strategy.
3. After materialization, the editor contents are the canonical source.
4. Canonical source changes are made through an explicit user edit/save-revision request.
5. If the user asks Operator to change the code, Operator creates a staged candidate revision or diff.
6. The candidate does not replace the canonical source until the user accepts it.
7. `Run` always binds to a specific immutable source revision and input snapshot.
8. A run may be initiated directly by the user's `Run` action or by Operator only when the current user request explicitly asked to run the Script workflow.
9. Retrying a failed provider call may replay the same immutable revision; it may not substitute new code.

Research Agent cannot draft, modify, or run scripts. It may inspect a Script result only when that result is attached as context.

## Proposed Domain Contracts

Create a dedicated module, suggested as `src/models/research_script.py`. Keep the contracts independent of OpenAI response objects.

### `ResearchScript`

Required fields:

- `script_id`
- `session_id`
- `title`
- `language` — `python` only in v1
- `status` — `draft`, `active`, `archived`, or `discarded`
- `canonical_revision_id`
- `created_by` — `operator` or `user`
- `created_at`
- `updated_at`
- `source_provider`
- `origin`
- `transformation_note`
- `contract_version` — start with `research-script.v1`

### `ResearchScriptRevision`

Required fields:

- `revision_id`
- `script_id`
- `revision_number`
- `source`
- `source_sha256`
- `created_by`
- `created_at`
- `parent_revision_id`
- `status` — `canonical`, `staged`, `superseded`, or `rejected`
- `change_summary`
- `operator_run_id` when model-generated
- `expected_parent_sha256` for optimistic concurrency

Never mutate a revision in place. Editing creates a new canonical revision after the expected-parent check. Operator revisions remain staged until accepted.

### `ResearchScriptInputSnapshot`

Required fields:

- `snapshot_id`
- `script_id`
- `created_at`
- `files`
- `dataset_refs`
- `source_refs`
- `warnings`
- `manifest_sha256`
- `total_bytes`
- `source_provider`
- `origin`
- `transformation_note`
- `contract_version` — start with `research-script-input.v1`

Each file entry should carry:

- logical filename;
- media type;
- byte size;
- content hash;
- Gamma object/provider identity;
- source timestamp and retrieval timestamp;
- transformation note;
- whether it came from Gamma state, a configured provider, or an explicit user upload.

### `ResearchScriptRun`

Required fields:

- `run_id`
- `script_id`
- `revision_id`
- `source_sha256`
- `input_snapshot_id`
- `input_manifest_sha256`
- `runtime_provider`
- `runtime_kind`
- `provider_container_id` — diagnostic only; never the persistence key
- `provider_response_id`
- `status` — `queued`, `running`, `completed`, `failed`, `cancelled`, `timed_out`, `expired`, `unavailable`, or `incomplete`
- `started_at`
- `completed_at`
- `outputs`
- `source_refs`
- `warnings`
- `usage`
- `limits`
- `source_provider`
- `origin`
- `transformation_note`
- `contract_version` — start with `research-script-run.v1`

### `ResearchScriptOutput`

Normalize provider output into these v1 kinds:

- `log` — stdout-style text;
- `error` — traceback or runtime failure;
- `metric` — named scalar with optional unit;
- `table` — bounded inline rows plus optional persisted CSV/JSON file;
- `image` — persisted image metadata and local artifact reference;
- `file` — persisted downloadable artifact;
- `summary` — model-generated run summary, clearly labeled as inferred/generated;
- `warning` — limit, provider, expiry, parsing, or provenance warning.

Every output should carry an `output_id`, kind, sequence, media type, byte size where relevant, created time, persisted location/reference, provider-native reference when available, and transformation/provenance metadata.

## Proposed Persistence Contract

Add a dedicated `ResearchScriptStore`, suggested at `src/services/research_script_store.py`.

Use the same safety properties as the hardened local stores:

- schema-versioned JSON metadata;
- atomic same-directory replacement;
- expected-parent/expected-update conflict detection;
- safe identifier normalization;
- deterministic ordering;
- quarantine or typed recovery for malformed metadata;
- no provider-container state as the authoritative copy;
- immutable revisions and run records;
- output bytes stored separately from metadata;
- bounded cleanup for temporary files;
- explicit archive/discard instead of implicit deletion where practical.

Suggested layout under the configured Gamma data directory:

```text
research_scripts/
  scripts/<script_id>.json
  revisions/<script_id>/<revision_id>.json
  inputs/<snapshot_id>/manifest.json
  inputs/<snapshot_id>/files/*
  runs/<script_id>/<run_id>.json
  outputs/<run_id>/*
  quarantine/*
```

Do not store generated output blobs inside the Copilot session JSON. Copilot working analyses should reference the Script record and run ids.

## Proposed API Surface

Keep the user-facing route family under Strategy Lab:

```text
POST   /research/strategy-lab/scripts
GET    /research/strategy-lab/scripts
GET    /research/strategy-lab/scripts/{script_id}
POST   /research/strategy-lab/scripts/{script_id}/revisions
POST   /research/strategy-lab/scripts/{script_id}/revisions/{revision_id}/accept
POST   /research/strategy-lab/scripts/{script_id}/revisions/{revision_id}/reject
POST   /research/strategy-lab/scripts/{script_id}/runs
GET    /research/strategy-lab/scripts/{script_id}/runs
GET    /research/strategy-lab/script-runs/{run_id}
POST   /research/strategy-lab/script-runs/{run_id}/cancel
GET    /research/strategy-lab/script-runs/{run_id}/outputs/{output_id}
POST   /research/strategy-lab/scripts/{script_id}/archive
```

Slice 1 may implement only create/list/get/revise/run/list-runs/get-run against the mock runtime. Cancellation, staged Operator revisions, output download, and archive can follow as their contracts stabilize.

Use typed Pydantic schemas in `src/api/schemas/research.py` initially unless the file becomes materially harder to navigate; then split into `src/api/schemas/research_script.py` while preserving the public route family.

Prefer extending `src/api/routes/research.py` for the first slice so the feature does not add router-registration work before the contract is proven. Split later only if the route file becomes unwieldy.

## Application Service Boundary

Add `ResearchScriptService`, suggested at `src/application/research_script_service.py`.

It owns:

- script/revision validation;
- source hashing;
- optimistic concurrency;
- input snapshot creation;
- runtime selection;
- run lifecycle and terminal-state idempotency;
- output normalization and persistence;
- provider-container expiry recovery;
- access to persisted run history;
- materialization payload creation;
- permission-independent domain logic.

Routes remain thin. Copilot actions call this service through the registry. The frontend never talks directly to OpenAI.

## Runtime Adapter Boundary

Define a provider-neutral protocol, suggested in `src/services/research_script_runtime.py`:

```python
class ResearchScriptRuntime(Protocol):
    def capabilities(self) -> ResearchScriptRuntimeCapabilities: ...
    def start_run(self, request: ResearchScriptRuntimeRequest) -> ResearchScriptRuntimeResult: ...
    def cancel_run(self, provider_run_id: str) -> ResearchScriptRuntimeCancelResult: ...
    def collect_outputs(self, result: ResearchScriptRuntimeResult) -> list[ResearchScriptRuntimeOutput]: ...
```

The exact sync/async shape should follow Gamma's current FastAPI/runtime patterns. Do not leak OpenAI SDK classes into the domain models.

Required implementations:

1. `MockResearchScriptRuntime`
   - deterministic;
   - executes no code;
   - returns fixture logs, one table, one image/file reference, and controllable failed/timeout/unavailable states;
   - used for Slice 1, offline tests, and demos.
2. `OpenAICodeInterpreterRuntime`
   - added only after the mock contract and persistence tests are stable;
   - creates or reuses an explicit ephemeral container where appropriate;
   - supplies source and input files;
   - requests Python-tool execution;
   - records provider call items, executed code where returned, container id, response id, usage, and warnings;
   - downloads generated files immediately into Gamma-owned storage;
   - never enables network access in v1;
   - treats an expired container as recoverable by creating a new container and replaying the immutable revision plus input snapshot.

Do not use hosted shell in v1. If future requirements need it, that is a separate security review and runtime adapter. It must not silently replace Code Interpreter.

## Exact-Source Run Requirement

The visible source must be auditable against the code actually executed.

For every run:

1. Gamma computes `source_sha256` before provider submission.
2. Gamma persists the immutable revision before starting the provider call.
3. Gamma supplies that revision as a file or otherwise immutable provider input.
4. The runtime request instructs the Python tool to execute that supplied revision, not to rewrite it.
5. Gamma records any provider-returned executed-code item.
6. Gamma accepts the run as `completed` only when the runtime adapter can associate the execution with the expected source hash.
7. If exact-source association cannot be established, the result is `incomplete` with a prominent warning; it must not be presented as the output of the visible revision.

The initial provider spike must prove this association. If the current Code Interpreter API cannot support it reliably, keep the UI/domain contracts and replace only the runtime adapter with a dedicated managed sandbox. Do not weaken the audit requirement to preserve the provider choice.

## Data Bundle Contract

User code receives files, not live Gamma service handles.

First supported input sources:

- explicit user-uploaded CSV/JSON files already accepted by the current workflow;
- current or saved Strategy Lab normalized return streams;
- selected Equity Research scope histories;
- hypothetical portfolio legs/weights from Copilot working state;
- later, bounded tab-owned exports from Macro, Fundamentals, Options, Commodities, Prediction Markets, and Crypto.

External data policy:

- use configured Gamma provider adapters first;
- fetch external data before sandbox execution;
- normalize, cache, and attach provenance in Gamma;
- pass a copied snapshot to the runtime;
- do not pass provider credentials;
- do not let scripts call arbitrary URLs in v1.

Each bundle must include `manifest.json` describing files, fields, time coverage, provider identity, retrieval time, transformation notes, warnings, and hashes.

## Copilot Operator Integration

Add new action ids without changing `run_strategy_lab_backtest`:

### `strategy_lab.draft_research_script`

- Action type: `draft_change`
- Permission: automatic only from an explicit Operator Script request
- Input: strict schema containing title, intent, language, requested input refs, and source
- Output: temporary script reference, staged/canonical initial revision, input requirements, warnings, sources, and materialization target
- Mutation: creates session-ephemeral Script state; does not create a durable saved strategy

### `strategy_lab.run_research_script`

- Action type: `run_analysis`
- Permission: automatic only when the same user turn explicitly requests execution, or when triggered directly by the user's `Run` control
- Input: strict schema containing `script_id`, `revision_id`, `input_snapshot_id`, and expected hashes
- Output: run reference, status, typed output summaries, warnings, sources, usage, and materialization target
- Mutation: persists an immutable run record and retained output artifacts; does not modify portfolios, accounts, strategies, or broker state

Both schemas must use strict function calling with `additionalProperties: false` and all properties required, using nullable types where necessary.

Extend `copilot.working-analysis.v1` with a Script family whose materialization target is:

```text
target_tab: strategy_lab
target_mode: script
payload_contract: copilot.strategy-lab-script-working-analysis.v1
durable: false
```

Operator events should reuse the existing run envelope. At minimum retain:

- plan;
- script draft created;
- input snapshot created;
- run started;
- provider progress;
- output/artifact created;
- warning;
- run completed/failed/cancelled/timed out/incomplete;
- final synthesis.

## Frontend Plan

### Slice 1 editor choice

Use a plain monospace `<textarea>` or a tiny local editor component for the mock vertical slice if that avoids adding a dependency before the contracts stabilize. Upgrade to CodeMirror 6 when the real runtime slice begins. Do not add Monaco for v1.

### Strategy Lab mode

Add `script` to `StrategyLabMode` and the visible mode bar.

Recommended layout:

```text
section.view
  existing Strategy Lab header and mode bar
  script status / temporary-state strip
  div.workspace-grid
    primary-column
      source editor panel
      run output panel
    support-column
      run controls and limits
      revision / staged diff status
      input manifest
      runtime / provider status
      warnings and provenance
      run history
```

Required first-slice behaviors:

- create a draft;
- load a script by id;
- edit and create a new canonical revision;
- reject stale `expected_parent_sha256` updates visibly;
- run the selected revision against the mock runtime;
- render mock logs, a compact table, an image/file placeholder, warnings, and run status;
- retain editor and selected run state when switching Strategy Lab modes;
- render empty, loading, ready, failed, unavailable, and stale-revision states;
- collapse to one column with the primary editor/output path first.

Do not render raw provider payloads or internal file paths in the primary UI.

## Initial Limits

Create named constants and tests. These are proposed first-slice defaults and may be tuned after the provider spike:

- Python source: 64 KiB
- Input files: 20
- Individual input file: 20 MiB
- Total input bundle: 64 MiB
- Run wall time: 120 seconds
- Inline text output retained in metadata: 1 MiB
- Output artifacts: 32
- Total retained output bytes: 64 MiB
- Inline table preview: 500 rows and 50 columns
- Concurrent runs per script: 1
- Retry count for a provider-transport failure: 1, only for the same immutable revision and input snapshot

Oversized requests should fail before provider submission with typed `422` or domain validation errors. Truncation must be explicit and preserve downloadable full output only when within the retained-artifact cap.

## Security Invariants

The following must be true by construction and covered by tests before enabling the real runtime:

1. No OpenAI or provider secret is included in model-visible input, script files, manifests, logs, or returned artifacts.
2. No Gamma environment variables are copied into the container.
3. No Gamma data directory, repository path, home directory, or local filesystem path is mounted.
4. No TWS/IBKR session, port, account id, adapter, credential, or order-capable function is exposed.
5. No wallet connection, signing method, cookie, token, or transaction endpoint is exposed.
6. No localhost/Gamma API endpoint is exposed.
7. Network access remains disabled in the first real runtime.
8. Input bundles are copies with bounded size and explicit provenance.
9. Output filenames are normalized before persistence and cannot escape the run output directory.
10. Archive/discard/delete operations resolve exact ids and cannot target broad directories.
11. Runtime/provider ids are diagnostic metadata, not authorization tokens.
12. A provider retry cannot change the source revision, input snapshot, or limits.
13. Agent mode cannot call Script actions.
14. Existing Operator tools cannot accept a hidden source-code argument.
15. No trade, rebalance, order, account, wallet, or host-execution action exists in the registry.

## Test and Acceptance Matrix

### Backend unit and API tests

- model round trips and schema versions;
- source and manifest hashing;
- immutable revisions;
- optimistic concurrency conflict;
- staged Operator revision accept/reject;
- store atomicity, quarantine, and recovery;
- create/list/get/revise routes;
- mock run success;
- syntax/runtime failure fixtures;
- timeout, cancellation, unavailable, incomplete, and expired states;
- oversized source/input/output rejection;
- output filename/path traversal rejection;
- terminal-state idempotency;
- provider retry preserves hashes;
- provenance and warnings survive persistence;
- no secret, host, broker, wallet, or network fields in serialized runtime requests.

### Frontend tests

- `script` mode registration and switching;
- editor draft load and revision save;
- stale revision conflict UI;
- run/stop button states;
- typed log/table/image/file/warning rendering;
- empty, loading, failed, unavailable, timed-out, cancelled, expired, and incomplete states;
- mode switching preserves draft and selected run;
- narrow layout ordering;
- keyboard/focus behavior;
- no terminal, package-manager, or trading controls.

### Operator evals

- natural-language strategy request selects draft action;
- explicit “run it” selects run action with exact ids/hashes;
- Agent role refuses/redirects to visible Operator transition;
- Operator does not run when the user asked only for a draft;
- staged revision does not overwrite user source;
- degraded input acquisition stops or continues with explicit warnings;
- run outputs are returned as observations before final synthesis;
- final answer cites run/source ids and preserves warnings;
- prompts requesting orders, broker access, secrets, localhost, wallet actions, or network escape are refused or structurally impossible.

### First real-runtime acceptance case

Use one deterministic, non-trading example:

> Build and run a monthly moving-average crossover research script for SPY using a Gamma-provided historical-price snapshot. Show the code, cumulative-return table, one chart, drawdown, and warnings. Do not save a strategy or connect to a broker.

Acceptance requires:

- visible source before/after execution;
- matching source hash;
- manifest with provider and time coverage;
- one persisted table and image;
- explicit generated/derived labels;
- outputs survive container expiry and app restart;
- no network, host, credential, broker, account, wallet, or order capability.

## Delivery Slices and Status

### Slice 0 - Boundary and documentation

- [x] Approve the isolated research-computation exception.
- [x] Add roadmap Workstream 2A.
- [x] Create this implementation/handoff plan.
- [x] Reconcile active README and Copilot authority language.
- [x] Re-review current official OpenAI tool/container guidance on 2026-08-29.

### Slice 1 - Backend contracts, persistence, and mock runtime

- [x] Add `research_script` domain models and schema versions.
- [x] Add named Script request/compute/output limits.
- [x] Add `ResearchScriptStore` with immutable revisions and run records.
- [x] Add `ResearchScriptRuntime` protocol and deterministic mock runtime.
- [x] Add `ResearchScriptService`.
- [x] Add create/list/get/revise/run/list-runs/get-run routes.
- [x] Register the service/store/runtime in `src/application/runtime.py`.
- [x] Add backend tests for contracts, conflicts, store safety, routes, and mock terminal states.

Status (2026-08-29): complete. Verification from the repository root:

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_research_script.py tests/test_api.py` — `34 passed in 9.17s`.

Exit criterion: a mock script can be created, revised, run, persisted, reopened, and rendered through typed API responses without executing code or calling OpenAI.

### Slice 2 - Strategy Lab Script UI

- [x] Add `script` to `StrategyLabMode` and mode navigation.
- [x] Add a focused Script workspace component or well-bounded Strategy Lab section.
- [x] Add editor, revision state, run controls, input manifest, runtime status, warnings, provenance, output list, and run history.
- [x] Preserve draft/selected-run state across mode changes.
- [x] Add typed frontend API helpers and view-models.
- [x] Add frontend tests and production build/typecheck coverage.

Status (2026-08-29): complete. Verification from `frontend/`:

- `npm run test -- src/components/StrategyScriptWorkspace.test.ts src/lib/stores/research-script.test.ts src/views/StrategyLabView.test.ts src/lib/navigation.test.ts` — `4` files and `16` tests passed in `2.97s`.
- `npm run typecheck` — passed with no TypeScript errors.
- `npm run build` — passed in `14.23s`; Vite reported three pre-existing Svelte warnings in `IvView.svelte` and `Surface3D.svelte`, with no Script-workspace warnings.
- Repository-root `git diff --check` — no whitespace errors; Git reported only existing CRLF conversion notices.

Exit criterion: the complete mock workflow is usable in Strategy Lab with honest states and no runtime dependency.

### Slice 3 - OpenAI Code Interpreter runtime spike and adapter

- [x] Verify configured SDK support and feature availability without changing the default model solely because a newer model exists.
- [x] Prove exact-source association with an immutable source file and SHA-256.
- [x] Upload the input bundle and create/reuse an explicit container.
- [x] Parse code-interpreter call items, logs, messages, annotations, usage, and generated files.
- [x] Download outputs immediately into Gamma-owned storage.
- [x] Handle cancellation, timeout, provider errors, container expiry, and replay on a new container.
- [x] Keep network disabled.
- [x] Add provider capability and usage diagnostics.
- [x] Add contract tests plus one opt-in live smoke.

Status (2026-08-29): complete. `OpenAICodeInterpreterRuntime` is isolated behind the provider-neutral runtime protocol; Gamma keeps the mock default and fails closed when the configured provider/model lacks Code Interpreter or when the returned execution wrapper cannot prove exact-source association. The synchronous v1 adapter reports provider cancellation as unsupported, applies a local terminal cancellation boundary, and ignores late results after a local terminal state.

Verification from the repository root:

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_research_script.py tests/test_openai_research_script_runtime.py tests/test_research_script_openai_live.py tests/test_research_script_operator.py tests/test_api.py` — `55 passed, 1 skipped in 12.42s`; the live test is skipped by default.
- `$env:GAMMA_RUN_LIVE_RESEARCH_SCRIPT_SMOKE='true'; .\.venv\Scripts\python.exe -m pytest -q tests/test_research_script_openai_live.py -s` — `1 passed in 14.46s` using the existing authorized provider configuration.
- The live deterministic SPY monthly moving-average case verified visible source and matching SHA-256, provider/time-covered immutable input manifest, one retained cumulative-return CSV table, one retained SVG chart, drawdown and warning output, generated/derived labels, and retained artifact recovery after reconstructing the Gamma service/store. Fake-client coverage proves expired-container replay with identical source and input bytes.
- `npm run typecheck` — passed.
- `npm run build` — passed in `15.23s`; only the three pre-existing Svelte warnings in `IvView.svelte` and `Surface3D.svelte` were emitted.

Exit criterion: the deterministic SPY example runs in the hosted sandbox and retained outputs survive expiry/restart with matching hashes.

### Slice 4 - Copilot Operator drafting and materialization

- [x] Add strict draft/run action definitions.
- [x] Extend working-analysis persistence and materialization for Strategy Lab / Script.
- [x] Stage Operator revisions instead of overwriting canonical source.
- [x] Reuse the shared Operator run-event and trace contracts.
- [x] Add role, permission, argument-fidelity, observation, warning, and synthesis evals.
- [x] Verify shelf/full-workspace continuity.

Status (2026-08-29): complete. The custom Responses Operator exposes `strategy_lab.draft_research_script` and `strategy_lab.run_research_script` only for an explicit current-turn Script workflow. Draft-only and negated-run prompts cannot execute. The app-native v1 input bridge can copy bounded symbol history into the immutable snapshot; unsupported or unavailable acquisition remains explicit as a warning. Direct user edits remain canonical, Operator follow-up changes are staged, and accept/reject revalidates the visible parent hash. Research Agent receives no Script actions, but may summarize an attached completed result with no Script tool authority.

Verification from the repository root unless noted:

- The combined Script/API suite above — `55 passed, 1 skipped` — includes 12 Script Operator tests for strict schemas, action selection, argument fidelity, app-native input copying and degraded warnings, exact ids/hashes, staged accept/reject/stale-parent behavior, API decision routes, Research Agent isolation/read-only inspection, provider-disabled behavior, observation-before-synthesis, and timeout false-success prevention.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_research_script_operator.py` — `12 passed in 2.37s` in the final focused rerun.
- Selected existing Copilot action/permission/store/custom-loop regressions — `14 passed, 3 third-party deprecation warnings in 19.43s`.
- `.\.venv\Scripts\python.exe evals/research_script_operator_eval.py` — passed all 12 deterministic Script Operator checks.
- `.\.venv\Scripts\python.exe evals/copilot_operator_eval.py` — passed all 31 retained deterministic outcomes; average score `0.9092741935483871`; default routing remained `gamma_custom_loop`. The harness now forces mock/sample providers unless an explicit live flag is supplied.
- From `frontend/`, `npm test` — 54 files and `384` tests passed in `8.13s`.
- From `frontend/`, `npm run typecheck` — passed with no TypeScript errors.
- From `frontend/`, `npm run build` — passed in `15.23s` with only the three pre-existing warnings noted above.
- `.\.venv\Scripts\python.exe -m py_compile src/services/openai_research_script_runtime.py src/application/research_script_service.py src/application/copilot_service.py src/application/runtime.py` — passed. The repository has no configured Python or frontend formatter/linter command, so TypeScript typecheck, production build, Python compilation, tests, and `git diff --check` are the available changed-file static gates.
- `git diff --check` — no whitespace errors; only repository line-ending conversion notices.

Broader non-gating evidence: `.\.venv\Scripts\python.exe -m pytest -q tests/test_copilot.py` reached `132 passed, 7 failed`. Re-running those seven tests produced the same `7 failed, 3 warnings in 7.74s`: three existing hypothetical-portfolio/entity-disambiguation expectations, one existing imported-strategy intent expectation, one existing temporary-portfolio elapsed-budget expectation, one existing external-news execution expectation, and one existing CPI/Fed domain-selection expectation. None exercises a Research Script action, runtime, permission, store, or materialization contract; the focused existing Copilot regressions and every new Script Operator test pass. These unrelated working-tree failures were preserved rather than widened into this implementation.

Exit criterion: an explicit Operator request can draft, acquire inputs, materialize, run, observe outputs, and synthesize without preloading Strategy Lab or gaining any additional authority.

### Slice 5 - Data bridge, hardening, and beta gate

- [x] Add bounded exports from selected Gamma domains.
- [x] Add richer table/image/file renderers and downloads.
- [x] Add run comparison, duplicate, archive, explicit save/export, and recovery UX.
- [x] Add security/escape tests and retained-output cleanup.
- [x] Add accessibility, responsive, disabled-provider, cost/usage, first-run, and diagnostics coverage.
- [x] Run representative live/mock/provider-disabled acceptance cases.

Status (2026-08-31): complete. The data bridge now creates immutable, provenance-bearing snapshots from bounded equity history, macro history, and saved-research exports. The workspace renders retained tables and authenticated images/files, exports an auditable ZIP containing source/input/run/output evidence, compares retained runs, and supports duplicate, archive/restore, recovery, and safe orphan cleanup. Storage diagnostics report scripts, archived scripts, runs, snapshots, outputs, retained bytes, and missing/orphaned files. Source validation rejects network, shell, environment, dynamic-execution, dunder, absolute-path, and parent-traversal escape attempts before dispatch. Provider paths and transient `sandbox:` links are sanitized, and provider-reported Python failures map to a typed `failed` terminal state rather than a false success.

Verification evidence:

- `tests/test_research_script.py`, `tests/test_openai_research_script_runtime.py`, and `tests/test_copilot_agents_sdk_smoke.py` — 30 tests passed after the final failure-state/provenance patch.
- Focused Luna model-policy and incompatible-model checks — 4 tests passed.
- Opt-in real-provider smoke — 1 test passed in `22.37s`, proving exact source/input association, network-disabled Code Interpreter execution, retained table/image outputs, and restart replay.
- Browser acceptance against the live app completed a `gpt-5.6-luna` run in `13.43s` over a 939-row bounded SPY snapshot. The UI displayed source SHA `b14cfbcb012b`, input SHA `90329c4cec51`, OpenAI/Code Interpreter provenance, a retained CSV and SVG, authenticated blob rendering, no raw provider paths, `2,467` input / `567` output tokens, a `$0.001174` token-cost estimate, and clean `0 / 0` missing/orphan diagnostics.
- Mock success/failure/timeout/unavailable/cancel paths, provider-disabled behavior, stale revisions, expired-container replay, oversized outputs, failed downloads, archive/run conflicts, cleanup, and authority-escape cases are covered by deterministic tests.
- Frontend: 54 files and 386 tests passed; TypeScript typecheck and the production build passed. The build retained only three pre-existing warnings in `IvView.svelte` and `Surface3D.svelte`.
- Repository-root `git diff --check` passed. A broad backend fail-fast still reaches the known, unrelated current-date commodities fixture whose August futures contract is now expired; the Script-focused and model-policy gates are green.

Exit criterion: all Workstream 2A completion gates in the roadmap are satisfied.

## Official OpenAI Guidance Review — 2026-08-31

Reviewed official OpenAI documentation:

- [GPT-5.6 Luna model](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
- [Latest model guidance](https://developers.openai.com/api/docs/guides/latest-model)

Resulting decisions:

- At the user's direction, make exact model id `gpt-5.6-luna` the active default for Copilot, the Copilot Operator/Agents comparison default, Research Script Code Interpreter, and Fundamentals summary generation. Preserve existing Gamma profile reasoning efforts and record the resolved model on each run.
- Luna's documented Responses, function-calling, structured-output, and Code Interpreter support fits the existing adapters; no framework expansion or provider-type leak is required.
- Keep Gamma's custom Responses loop as the default control plane and the Agents SDK as a feature-flagged comparison path. The model change does not move tool exposure, permissions, validation, persistence, approvals, terminal truth, or audit ownership out of Gamma's server.
- Keep Code Interpreter network disabled, continue immediate Gamma-owned artifact retention, and keep strict exact-wrapper/source/input hash verification.
- Apply Luna pricing only as a clearly scoped text-token estimate; hosted-tool charges and unavailable usage fields remain excluded rather than guessed.
- The 2026-08-29 `gpt-5.4` no-switch decision below is historical and is superseded by this explicit, tested Luna migration.

## Official OpenAI Guidance Review — 2026-08-29

Reviewed official OpenAI documentation:

- [Code Interpreter](https://developers.openai.com/api/docs/guides/tools-code-interpreter)
- [Function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [Responses create](https://developers.openai.com/api/reference/resources/responses/methods/create)

Installed SDK reviewed: `openai==2.38.0`. The installed interfaces used by the adapter are `responses.create`, `responses.cancel`, `containers.create`, `containers.files.create`, `containers.files.list`, and `containers.files.content.retrieve`. The installed container interface supports an explicit disabled network policy and expiry configuration. The create-response types expose Code Interpreter tool configuration and response items/citations needed by the provider adapter. No OpenAI SDK type crosses the adapter boundary.

Resulting decisions:

- Code Interpreter is the preferred first real runtime because the official guide describes sandboxed Python execution and generated files/images.
- Treat every provider container as ephemeral. Gamma persists source, manifests, metadata, and generated artifacts independently and can replay an immutable revision/input snapshot into a new container.
- Hosted shell is not part of v1 and is never used as a fallback.
- Network stays disabled. External data is acquired through Gamma provider adapters and passed as copied files.
- Operator draft/run actions use strict schemas with `additionalProperties: false` and all properties required, using nullable types for optional values.
- No framework or default-model switch is justified by this feature. Gamma's current custom Responses Operator remains the control plane, and the Agents SDK remains a feature-flagged comparison path.
- The configured `gpt-5.4` model supports Code Interpreter and remained unchanged. Capability detection rejects unsupported configured models (including models whose published capability page omits Code Interpreter) and retains the mock runtime instead of silently switching models.
- Code Interpreter execution through Responses is model-mediated. Gamma therefore sends a minimal stable wrapper, requires one returned wrapper to match exactly, verifies uploaded source and manifest hashes inside the container, and withholds outputs if exact-source association is not established.
- Gamma's store, action registry, permissions, limits, run lifecycle, artifact retention, and audit state remain authoritative; provider response/container state is transport state only.

## Open Decisions

| Decision | Current stance | Resolution gate |
|---|---|---|
| Editor | CodeMirror 6 with the Python language extension | Implemented as a narrow accessible single-file editor; Monaco and IDE surfaces remain excluded. |
| Runtime | Provider-neutral contract with a verified OpenAI Code Interpreter path and mock fallback | Exact-source/hash, network-disabled execution, and retained-output gates passed; unsupported configurations remain unavailable without silently changing the configured model. |
| Shell | Excluded from v1 | Separate security review and explicit roadmap update required. |
| Network | Disabled | Separate threat model, allowlist design, provider/data-governance review, and user need required. |
| Persistence | Dedicated Script store | Do not overload Copilot artifact JSON or generic saved research. |
| Operator edit authority | Staged revisions only after materialization | Acceptance tests must prove no silent overwrite. |
| Direct user Run | Allowed and bounded | Must bind immutable revision and input hashes. |
| Operator Run | Allowed only on explicit current-turn request | Permission and eval coverage required. |
| Package installation | Excluded | Revisit only after real workflows show a blocking dependency gap. |
| Multiple files | Excluded | Revisit after single-file v1 is stable. |

## Agent Handoff Rules

When continuing this work:

1. Read the current roadmap, this entire document, the Copilot plan, provenance expectations, and Strategy Lab UI/state code before editing.
2. Re-check official OpenAI guidance before changing the real runtime, container lifecycle, tool schemas, model routing, approvals, or storage policy; record the date, URLs, and decision here and in the Copilot plan.
3. Treat Slices 1-5 as completed baseline. Extend the provider-neutral contracts and deterministic mock coverage before broadening any live-runtime behavior.
4. Keep source revisions immutable and runs hash-bound from the first slice.
5. Keep routes thin and provider-neutral; no OpenAI SDK types in public/domain contracts.
6. Preserve existing Strategy Lab modes and unrelated worktree changes.
7. Use app-native tools and provider adapters for data acquisition; never expose Gamma services or credentials to scripts.
8. Stop if an implementation choice requires host access, local shell, network egress, broker/account/wallet authority, or a broader permission boundary. That requires a new explicit decision.
9. Update the status checklist and add concrete test evidence after each completed slice.
10. Do not call the feature complete until the roadmap completion gate is satisfied.
