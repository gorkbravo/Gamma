# Copilot Checkpoint 8 completion — 2026-09-06

Checkpoint 8 is complete for its representative workflow contract. Copilot advances to approximately 92% of the clarified end state. Checkpoint 9 owns generalized approval/resume, recovery and new durable promotion; Checkpoint 10 owns the remaining live-provider and UI release certification. In-app visual tests were explicitly excluded by the user for this pass.

## Acceptance boundary

The checkpoint requires entity-addressable Gamma analytics, exact effective inputs and temporary assumptions, retained intermediate outputs, and useful non-durable owning-tab materialization. It does not require every future analytical mode, new data vendors or new durable saved-object families.

| Representative workflow | Evidence and disposition |
| --- | --- |
| Unloaded Fundamentals and company-name acquisition | Existing 8A/8B: SEC-validated entity, reverse valuation, temporary state and Fundamentals materialization. |
| Hypothetical portfolio and loaded-book Risk | Existing 8C: exact normalized legs and typed shocks; comparison/contribution/scenario retention and Risk materialization. |
| Options comparisons and exact option sets | Existing 8D/8E: exact collection settings/legs and provider-priced results, temporary Options materialization. |
| Strategy Lab signed portfolio and Script | Existing 8F and separately completed Script workspace; source/input/run identity and temporary assumptions preserved. |
| Prediction Markets and equity baskets | Existing 8G/8H: exact requested baskets, bounded charts, full-observation statistics and owning-tab snapshots. |
| Single-name Research scope | Remaining gap closed: existing ResearchService output, complete normalized position inputs, source refs and timestamps retained; empty/partial requested scopes do not materialize as complete baskets. |
| Imported/composed Strategy Lab summaries | Remaining gap closed: active normalized analytics retained separately from raw uploaded CSV data; imported inputs are not invented or reconstructed. |
| Macro series | New strict `run_macro_series_analysis`: exact Gamma series id, requested region and 1M/3M/6M/1Y window, no loaded tab. Window statistics use all observations in that lookback; the retained recent-observation table is bounded to 12. Empty/mismatched series cannot produce a materializable result. |
| Crypto token | New strict `run_crypto_token_analysis`: exact provider token id and 1–365 day lookback, no loaded tab. Price history, liquidity and comparison degrade independently; history outside the requested window is excluded. No token substitution. |
| Commodities | Existing instrument-addressable curve/fundamentals action now retains its bounded contracts, inventories, price basis, events, provider dates and warnings. No new futures/AIS analytics or provider claims. |
| Cross-tool outputs | `read_working_analysis` reads exact active evidence in the current Operator session. It checks role, selected scopes, expiry/discard/deletion and preserves original dates. Custom Responses and SDK tests read a retained Macro result, observe a new Crypto result and synthesize their distinct windows/limitations. |

Portfolio account acquisition remains the existing read-only broker/snapshot path; Risk owns its computed analytics. SITREP is a triage/context surface. Sealanes remains paused at the existing data-limited prototype: this checkpoint adds no unvalidated maritime analytics. Existing read-only context tools and retained turn traces continue to cover these contextual surfaces.

## Implementation

- `copilot_working_evidence.py` declares the remaining supported tool/tab/mode mappings and the `copilot.retained-evidence.v1` materialization contract. It uses the existing `copilot.working-analysis.v1` store and seven-day lifecycle.
- Both Operator runners pass the server-owned request/session into retained reads. The deterministic runner uses the same registry dispatcher. Agent-mode calls and cross-session/scope reads are refused.
- Exact effective inputs and complete bounded tool outputs are retained with original source references. Reused citations are namespaced by analysis id so a fresh fetch cannot overwrite the retained source date. Chart-heavy existing snapshots are compacted only for model observations, leaving their stored outputs intact.
- Opening retained evidence bypasses live owning-tab reloads and draft mutation. The owning-tab snapshot shows domain-specific evidence sections, assumptions, expiry and provenance. Returning to the workspace restores normal loading.
- Persistence failure produces an explicit warning without a false reopen reference. Expired/discarded retries cannot resurrect the same result.
- No model, framework, key, execution authority or durable saved-object family changed. Existing 8H and unrelated working-tree edits were preserved.

## Official guidance

Reviewed the current [Agents SDK / Responses comparison](https://developers.openai.com/api/docs/guides/agents) through the OpenAI Developer Docs connector on 2026-09-06. Gamma keeps its custom Responses default and optional SDK comparison runner; Gamma remains authoritative for tool validation, permissions, persistence and approvals. The decision is recorded in the active Copilot plan.

## Validation

- Focused Copilot regression/eval/SDK suite: 168 passed at the initial implementation gate.
- Completion acceptance: 16 passed, including both runner paths, lifecycle, identity/window fidelity, partial evidence, remaining owning surfaces and persistence failure.
- Frontend: 441 tests across 61 files passed, including non-visual SSR content and typed materialization checks.
- TypeScript typecheck and production build passed. Existing build warnings remain unrelated to the checkpoint.
- Repository-wide backend verification: **733 passed, 1 skipped**, 3 warnings (513 seconds). The skip is the explicitly opt-in live OpenAI Script test.
- Final targeted follow-up after identity/retained-citation refinements: 32 checkpoint/Crypto/Script tests, 16 completion acceptance tests, and 5 Macro tests passed. Frontend tests, typecheck and production build were repeated after the frontend changes and passed.
- `git diff --check` passed.

The final completion tests use deterministic market/provider fixtures and simulated model transports. An early Crypto test unintentionally inherited the runtime's public CoinGecko adapter and encountered HTTP 429; the fixture was corrected so the retained acceptance suite makes no external calls. This is not successful live model/provider acceptance evidence. No OpenAI API spend was used for the final acceptance run. Visual/browser verification was not performed.

## Next

### Independent commit verification — 2026-10-04

The completed 8/8H slice was selectively staged over `e1e1ead` and applied to an isolated detached checkout. Checkpoint 9 recovery files, approval APIs/events/store changes, role/approval UI and unrelated website/design/configuration edits were absent. The dispatcher changes required for retained reads were included independently of recovery/retry logic.

That tree passed **177 focused backend tests**, including the completion matrix, SDK smoke and Operator evals; **449 frontend tests**, typecheck, production build and `git diff --cached --check`. Tests explicitly used `BASE_CURRENCY=USD` and `IB_MARKET_DATA_MODE=auto`: the isolated checkout has no developer `.env`, and default EUR/no benchmark FX plus delayed mode initially broke five legacy expectations. All affected cases passed when those fixture settings were explicit, followed by the complete 177-test rerun. No local configuration was copied, edited or committed. Existing IV SVG/Surface3D build warnings remain. This revalidation is deterministic/simulated-model evidence and does not certify Checkpoint 9 or live-provider release acceptance.

Checkpoint 9: persist an unfinished run and approval cursor, resume the same run after approve/reject or restart, enforce idempotency and stale-context checks, and make Agent-to-Operator authority transitions explicit. New durable working-analysis promotion must use that contract. Broader degraded replanning and live/UI certification remain part of Checkpoint 10.
