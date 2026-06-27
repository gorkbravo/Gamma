# Gamma Usability Findings - Current State

Date: 2026-06-15  
Audience: future AI agents and contributors improving Gamma  
Context: updated from the 2026-06-12 live IBKR-connected trade-idea audit, recent handoff/provenance commits, and a 2026-06-15 targeted Fundamentals retest with live IBKR connection.

## Purpose

This note captures the current product usability state after the June usability fixes. It is not an investment recommendation. The purpose is to separate persistent workflow problems from issues that have already improved, especially around handoffs, Fundamentals, and navigation.

The original 2026-06-12 audit started from an idea discovered inside Gamma. This update keeps that workflow as the baseline, then adds a targeted retest of Fundamentals and a review of recent commits/docs to identify what is still true.

## Audit Setup

Original 2026-06-12 audit:

- Backend: FastAPI on `127.0.0.1:8000`
- Frontend: Vite on `127.0.0.1:5173`
- Session auth header: `X-Gamma-Session`
- IBKR: connected to account `U15779203`
- Market data: delayed mode
- Commodities provider: IBKR futures curves, with WTI, Brent, Henry Hub, gold, and copper enabled

2026-06-15 targeted retest:

- Temporary local app instance with live IBKR connection.
- Navigation used keyboard shortcut `Ctrl+7` into Fundamentals.
- Ticker tested: `MSFT`.
- Review inputs: recent git commits, this audit file, `docs/audits/usability/README.md`, and `docs/strategy_lab_cross_tab_handoffs.md`.

Tabs exercised across the combined audit:

- Sitrep
- Commodities
- Strategy Lab
- Risk
- Macro
- Fundamentals
- Options
- Prediction Markets
- Copilot

External sources used in the original audit were used only to cross-check a news-driven oil signal surfaced by Sitrep.

## Thesis Log

### Thesis 1: Oil de-escalation should favor airlines over energy beta

One-line thesis: Middle East / Iran de-escalation and falling crude should favor airline/transport exposure over energy beta, expressed as long `JETS` versus short `XLE`, with `DAL` as the quality airline read-through and an `XLE` put spread as a defined-risk expression.

How it started: Sitrep showed oil-deescalation headlines, WTI weakness, and a strong U.S. equity tape. The idea came from Gamma's Sitrep/news/commodity context rather than being brought in prewritten.

Steps taken:

1. **Sitrep:** Reviewed index tape, rates, FX, commodities, and headlines. The app surfaced the signal: U.S. equities were green, oil headlines were de-escalation-oriented, and WTI was weak.
2. **Commodities:** Opened WTI and energy context. At the time, the curve and header context conflicted, which weakened confidence in the oil signal. This has since been partially addressed by the commodity price-basis reconciliation work in commit `e032af9`.
3. **Strategy Lab:** Built `+0.7 JETS / -0.7 XLE`, validated, then composed. Validation worked well: usable legs, aligned observations, source diagnostics, signed normalized weights, and clear warnings. The result weakened the trade: poor historical spread behavior, low Sharpe, material drawdown, and weak 2026 behavior.
4. **Risk:** In the original run, Risk did not inherit the Strategy Lab research book and opened with unknown coverage, N/A KPIs, return history length 0, and disabled compute buttons. This specific P0 has since been fixed by commit `67972ee`, which promotes validated Strategy Lab compositions into durable research-book objects consumable by Risk.
5. **Macro:** Checked rates and dollar backdrop. Macro pushed against the thesis: CPI was hot, 2Y was well above Fed Funds, 10Y and real yields were higher, and the broad dollar was stronger.
6. **Fundamentals:** Loaded `DAL` manually because the Strategy Lab context did not carry into Fundamentals. DAL looked stronger than peers on the heatmap, but the DCF defaults produced negative equity value with suspect airline assumptions.
7. **Options:** Loaded `XLE` manually because Options did not inherit the short leg. The live delayed IBKR surface loaded, and the put-spread template built a defined-risk `57P / 54.5P` structure. This was useful, but the default front expiry was too short for a thesis trade without manual adjustment.
8. **Prediction Markets:** Searched `Iran oil`. The app found an oil-specific market, "Will Crude Oil reach a new all-time high by June 30?", at about `2.2% Yes`, with related crude-threshold markets. This was directionally relevant but did not answer the actual de-escalation question.
9. **Copilot:** Selected all loaded contexts and asked for a synthesis. In the original audit, context detection worked, but generation stayed on `GENERATING...` after the 12-second guard and only showed a planner preview. Since then, commits `99cde79` and `ccc7eb4` overhauled Copilot roles, context grounding, and the tab UI; this needs a fresh end-to-end synthesis retest.

Outcome: rejected as a clean pair trade. The event idea was plausible, but Gamma's own Strategy Lab history, macro context, and commodity inconsistency did not support putting on the full long-airlines/short-energy book.

### Thesis 2: MSFT valuation sanity check through Fundamentals

One-line thesis: Test whether Fundamentals can support a direct single-name valuation workflow on a liquid mega-cap without forcing cross-tab context or sector-edge assumptions.

How it started: Follow-up concern that the prior audit may have over-weighted AI navigation friction and an airline-specific DCF edge case. The retest intentionally picked `MSFT` as a cleaner Fundamentals workflow.

Steps taken:

1. **Navigation:** Used `Ctrl+7` to open Fundamentals. This worked immediately and materially changes the navigation assessment: keyboard navigation is friendly for power users even when side-drawer automation is awkward.
2. **Fundamentals Search:** Searched `MSFT`. During refresh the UI briefly showed "No SEC matches"; after waiting, results populated. Exact `MSFT` appeared, though not at the top of the result list.
3. **Fundamentals Overview:** Loaded `MICROSOFT CORP (MSFT)`. The page displayed profile, CIK, recent filings, revenue, EBIT, FCF, price, market cap, peer heatmap, and provenance badges.
4. **Fundamentals DCF:** Opened DCF. The model loaded actuals, WACC bridge, driver bridge, scenario assumptions, working projection sheet, sensitivity, and bear/base/bull outputs. The surface was usable and analytically dense.
5. **DCF Editing:** Tried editing WACC and revenue growth cells. The values changed visually/DOM-side, but `Recalculate + Save` stayed disabled in browser automation. This may be an automation/event-dispatch issue rather than a human-blocking bug, but the cells are not clearly labeled as editable and lack descriptive labels such as "Revenue growth 2026." Updated 2026-06-23: editable DCF assumption cells and editable projection overrides now have explicit `aria-label` and `title` text, scalar assumptions are labeled by active scenario, editable cells use an accent-tinted background plus a left edit rail, and input events mark the DCF draft dirty immediately so human typing enables `Recalculate + Save` before blur.
6. **Provenance/Market Context:** Price and market cap loaded, but the wording around market data availability/provider/fallback was slightly confusing: the UI mixed IBKR context with fallback/availability language.

Outcome: confirmed that Fundamentals is one of Gamma's stronger deep-analysis tabs. The MSFT DCF workflow did not show the same reliability problem as the DAL airline case. The main Fundamentals issue is not model depth; it is editability clarity, accessibility/testability of editable cells, occasional noisy search state, and provenance wording.

## Trade Verdict

The oil de-escalation trade still does not make sense as a clean `long JETS / short XLE` pair from the workflow.

The strongest expression, if any, remains a small defined-risk bearish `XLE` put spread rather than pairing energy short exposure with airline long exposure. Sizing should be event-sized only, with premium as the known max risk. The idea needs more proof because Strategy Lab showed poor historical spread behavior and Macro showed a hostile rates/dollar setup for airline beta.

What would kill the trade:

- Oil rebounds or Iran de-escalation fails.
- Backwardation persists and energy equities hold up.
- Higher real yields and a stronger dollar keep pressuring airline beta.
- The DAL DCF issue reflects real airline capital intensity rather than a modeling normalization issue.
- The XLE options structure is too short-dated or too expensive relative to the event window.

The MSFT Fundamentals retest was not a trade recommendation. It was a workflow test, and the verdict there is that Fundamentals can support a serious single-name valuation workflow when the issuer is clean and data-rich.

## What Worked Well

### Keyboard navigation

`Ctrl+7` opened Fundamentals directly. This is important because the prior navigation criticism was partly AI-specific. A human power user can bypass much of the side-drawer friction with keybindings.

Preserve:

- Direct tab keybindings.
- Predictable tab order.
- Fast keyboard path into major workflows.

Improve:

- Make shortcuts more discoverable.
- Keep accessible names distinct so keyboard users, screen readers, and agents do not collide with duplicate controls.

### Fundamentals single-name workflow

The `MSFT` retest showed Fundamentals at its best. Overview, filings, peer heatmap, DCF, WACC bridge, driver bridge, scenario assumptions, projection sheet, and sensitivity all loaded into one dense research surface.

Preserve:

- Actuals plus scenario projections in the same view.
- WACC and driver bridge explanations.
- Peer heatmap next to issuer context.
- SEC/model/market/derived provenance badges.
- Bear/base/bull valuation summary.

Improve:

- Label editable cells clearly. Updated 2026-06-23: DCF assumption/projection inputs now expose names such as `Revenue growth 2026`, `Revenue projection 2026`, `WACC (base scenario)`, and `Terminal growth (base scenario)`.
- Add descriptive input labels for row/year cells. Updated 2026-06-23: row/year inputs also include matching title text for hover inspection.
- Make dirty/recalculate state robust to both human input and automated tests. Updated 2026-06-23: the DCF view now marks dirty state on `input` as well as committing parsed values on `change`; focused frontend SSR tests cover the rendered labels and edit affordances.
- Clean up provider/fallback wording around market price context.

### Strategy Lab validation

The branch fixes here are real. The validated `JETS / XLE` book showed signed exposure, source diagnostics, alignment window, observation counts, normalized weights, provenance, and fail-closed warnings. It did not repeat the earlier stale hidden-state failure.

Preserve:

- Dedicated Validate Book action.
- Per-leg provider/source diagnostics.
- Gross/net signed exposure summary.
- Alignment diagnostics before performance interpretation.
- Warnings about yfinance and gross-normalized exposures.

### Strategy Lab to Risk handoff

This was broken in the original audit and is now materially improved. Commit `67972ee` implemented the direct handoff by turning validated Strategy Lab compositions into persisted `strategy_research_book` objects that Risk can consume.

Preserve:

- Requirement that a current valid book validation exists before composition.
- Signed normalized weights and validation provenance.
- Risk source labeling that distinguishes research books from account portfolios.
- Backend/API/frontend tests around the research-book return stream.

Still improve:

- Per-leg Risk contribution decomposition for research books.
- Broader research-thread continuity beyond the Strategy Lab to Risk path.

### Options templates

The Options strategy templates worked on a live delayed IBKR `XLE` surface. Put Spread built a bounded-risk structure with max profit/loss, breakeven, delta, gamma, vega, theta, and rho.

Preserve:

- One-click templates.
- Source strip and delayed/provider metadata.
- Strategy payoff summary.
- Data diagnostics showing chain rows, cells, lines, interpolation, and update time.

Improve:

- Template expiry selection should consider thesis horizon, not just nearest expiry.
- Missing or interpolated cells should remain visible near the strategy output, not only in diagnostics.

### Commodity basis reconciliation progress

The original audit found conflicting WTI values. Commit `e032af9` added commodity price-basis reconciliation and Copilot context support. This is exactly the right class of fix: it does not hide provider differences; it gives the user basis, contract, and context.

Retest needed:

- Confirm selected commodity header, Sitrep tile, curve nodes, and Copilot context now agree or explicitly explain their differences.

### Prediction Markets related links

The oil market's related links stayed within crude all-time-high threshold siblings. Commit `fcb7a5c` further made prediction-market related links semantically honest.

Preserve:

- Relationship labels such as adjacent threshold and conditional consistency.
- Gap display between related probabilities.
- Calibration warning when venue history is unavailable.

### Provenance visibility

Provenance and source badges remain a major strength. They helped distinguish SEC history, model-generated summaries, IBKR-delayed data, Gamma-derived analytics, and provider warnings.

## What Did Not Work

### Cross-tab context is still uneven

The most damaging 2026-06-12 failure, Strategy Lab to Risk, has been fixed. The broader problem is not fixed: research context still does not consistently move across all relevant tabs.

Observed:

- Strategy Lab to Risk is now implemented.
- `DAL` still had to be typed manually into Fundamentals in the original workflow.
- `XLE` still had to be typed manually into Options in the original workflow.
- Prediction Markets did not preserve the actual "Iran oil" event intent.
- `docs/strategy_lab_cross_tab_handoffs.md` still lists several handoff directions as planned or not started, including broader Copilot context builder coverage and some non-Strategy-Lab source participation.

Required improvement:

- Promote a current research-thread object with selected thesis, instruments, legs, market, macro shock, and validated outputs.
- Each tab should state: using current context, context available but not loaded, context unsupported, or no context.

### Copilot synthesis needs retest after recent work

In the original audit, Copilot selected contexts correctly but did not return an analytical synthesis. Since then, commits `99cde79` and `ccc7eb4` rebuilt Copilot role/context grounding and the tab UI.

Current state:

- The original failure should no longer be treated as the latest Copilot verdict.
- The remaining question is whether the new Copilot can synthesize validated objects from the same research thread the UI uses.

Required improvement:

- Retest a complete multi-context prompt after the Copilot rebuild.
- Ensure timeout/failure states produce explicit recoverable cards.
- Show which context objects were actually used, not merely detected.

### Fundamentals editable cells are under-labeled

The MSFT DCF retest did not expose a major valuation failure, but it did show an interaction clarity issue. Updated 2026-06-23: the core editability clarity issue is implemented; remaining work is browser-level workflow coverage and any additional polish found in live retest.

Observed:

- Many DCF assumptions are editable inputs, but this is not visually explicit. Updated 2026-06-23: editable cells now use an accent-tinted input surface and a left edit rail; scalar assumption inputs use the same editable tint.
- Row/year cells lack descriptive accessible names. Updated 2026-06-23: assumption and projection inputs now include descriptive accessible names and titles.
- Browser automation could change values, but `Recalculate + Save` did not become enabled. Updated 2026-06-23: typing into DCF inputs now marks the draft dirty on `input`, which enables the action immediately; parsed draft values still commit through the existing `change` path.

Required improvement:

- Add visible or structural edit affordances for editable DCF cells. Status: implemented 2026-06-23.
- Add `aria-label`/title text such as `Revenue growth 2026`, `EBIT margin 2028`, `WACC`, and `Terminal growth`. Status: implemented 2026-06-23.
- Consider marking dirty state on `input` as well as `change`, or otherwise add a regression test that proves human edits enable recalculation. Status: implemented in the component on 2026-06-23; remaining gap is a true browser-level edit/save smoke test because the current frontend test harness is SSR-focused.

### Fundamentals search state is briefly misleading

During the `MSFT` retest, search briefly showed "No SEC matches" while results were still refreshing. Exact `MSFT` also appeared below noisy large-cap matches.

Updated 2026-06-27: the search state issue is fixed. Fundamentals search now has a dedicated frontend search-state object separate from the company payload loading flag. While a search request is pending, the view shows `Searching`; if previous rows are still displayed during refresh, the header and dropdown mark them as `Stale results` / `Search Refresh` instead of clearing the list or showing `No SEC matches`. `No SEC matches` is now reserved for a completed search response with zero rows. Backend SEC search ranking now sorts exact ticker matches first, followed by exact CIK, ticker prefix, CIK prefix, and name matches; popular tickers only break ties inside a match bucket or shape the empty-query default list, so an exact `MSFT` ticker result cannot be pushed below noisy large-cap/name matches.

Required improvement:

- Distinguish loading/refreshing from no-result state. Status: implemented 2026-06-27.
- Rank exact ticker matches first. Status: implemented 2026-06-27.
- Keep stale results visibly separate from refreshed results. Status: implemented 2026-06-27.

### Fundamentals price-context wording is slightly confusing

The MSFT page showed useful market context, but the wording mixed IBKR/provider and fallback/availability language in a way that could make users question whether the price came from live IBKR, delayed IBKR, yfinance fallback, or cached close.

Required improvement:

- Show one concise price-source line: provider, timestamp, delayed/live/cached status, and fallback if used.
- Avoid simultaneous "IBKR" and "market data unavailable" signals unless the difference is explicitly explained.

### Sector-specific DCF assumptions remain a real issue

The MSFT DCF looked credible enough for workflow testing. The original DAL DCF still exposed a real limitation: capital-intensive and sector-specific models can produce implausible assumptions without enough warning.

Required improvement:

- Keep the sector-aware DCF sanity-check item open.
- Do not generalize the DAL problem to all Fundamentals workflows.

## Gaps

### Research object model

Gamma needs first-class research objects:

- signed book
- single-name focus
- commodity shock
- option structure
- macro regime or shock packet
- prediction-market event
- DCF scenario
- Copilot synthesis card

These objects should have stable IDs, provenance, timestamps, and handoff eligibility.

### Cross-tab handoff matrix

The Strategy Lab to Risk path is now real, but the product still needs an explicit handoff matrix across all research surfaces.

Needed:

- Source object type.
- Destination tab support.
- Required fields.
- Lossy transformation warnings.
- Context status in the destination tab.

### Commodity basis and contract transparency

Oil workflows need explicit distinction between:

- continuous proxy
- front futures contract
- selected futures contract month
- spot/proxy price
- Sitrep commodity tile
- EIA/FRED reference series

The recent basis reconciliation work appears directionally correct, but it should be retested across Sitrep, Commodities, Risk, and Copilot.

### Sector-aware DCF checks

Fundamentals needs model sanity checks before users trust DCF output:

- D&A plausibility by sector
- capex/revenue plausibility
- terminal value share of enterprise value
- negative FCF warnings
- implied revenue scale warnings
- "current price requires X" reverse-valuation view

### Editable-cell discoverability and accessibility

DCF editability should be clear to both humans and automation:

- visible edit affordance. Updated 2026-06-23: editable DCF cells now have an accent-tinted background and left edit rail.
- exact row/year labels. Updated 2026-06-23: yearly assumption and projection override inputs now expose row/year accessible labels and titles.
- dirty-state feedback. Updated 2026-06-23: `input` events set dirty state so `Pending recalculation` and `Recalculate + Save` appear immediately after typing.
- keyboard-friendly edit flow
- regression coverage for recalculate enablement. Remaining gap: focused SSR frontend tests cover rendered labels/affordances and the disabled initial state, but not a live browser input/click flow.

### Thesis-horizon-aware options

Options templates should ask or infer:

- event horizon
- directional view
- vol view
- max premium budget
- desired moneyness

The app can stay read-only while still preventing accidental front-expiry structures from becoming the default answer.

### Prediction-market intent search

Search should distinguish "oil all-time high" from "Iran oil de-escalation." The found market was related to crude, but not to the actual event catalyst.

Needed:

- event/entity extraction
- search result explanation
- fallback disclosure when no direct market exists
- cross-link from geopolitical markets to commodity markets

## Cross-Tab Coherence

Current state: improved on the highest-value handoff, still incomplete as a full research workflow.

Improved:

- Strategy Lab to Risk handoff is implemented.
- Strategy Lab stale handoffs were separated into Earlier Sessions.
- Copilot loaded-context discovery improved in the original audit and has since been rebuilt.
- Prediction-market related links are more semantically coherent.
- Commodity basis reconciliation has landed.

Still incomplete:

- Strategy Lab to Options.
- Thesis/instrument context to Fundamentals.
- Sitrep news/event intent to Prediction Markets.
- Commodity selection to Macro/Risk shock templates.
- Copilot synthesis over the same durable objects used by analytical tabs.

Navigation update:

- Human power users have a good path through keybindings.
- Agents and assistive technologies still suffer from duplicated accessible names, ambiguous drag handles, and controls that are hard to target.
- Future audits should use keybindings where a human user would use them, then separately log accessibility/automation friction.

Target behavior:

1. Sitrep surfaces oil de-escalation.
2. User sends the oil signal to a research thread.
3. Strategy Lab builds the signed book.
4. Risk consumes the signed book.
5. Options consumes the short energy leg and selected horizon.
6. Fundamentals consumes the airline candidate.
7. Prediction Markets searches the event catalyst.
8. Copilot synthesizes only the validated objects.

## Copilot Evaluation

Original prompt tried:

```text
Evaluate this Gamma-built trade idea: oil de-escalation should favor long JETS versus short XLE, with DAL as the quality airline read-through and an XLE put spread as the defined-risk expression. Use the loaded Commodities, Strategy Lab, Macro, Fundamentals, Options, and Prediction Markets contexts. Be explicit about what confirms it, what rejects it, and what would kill the trade.
```

Original useful behavior:

- Detected `JETS`, `XLE`, `DAL`, and oil.
- Selected seven loaded contexts.
- Displayed context fingerprints and warnings.
- Built a planner view with relevant domains.

Original failed behavior:

- Did not return an analytical synthesis.
- Stayed on `GENERATING...` after the guard.
- The visible result was planner-only and stated it did not execute tools or fetch provider data.

Current interpretation:

- Do not treat the original Copilot failure as current-state proof after commits `99cde79` and `ccc7eb4`.
- Do keep the acceptance bar: Copilot must synthesize durable, validated context objects and expose timeout/error states clearly.

Retest prompt:

```text
Using the current research thread, evaluate the oil de-escalation trade: long JETS versus short XLE, DAL as the airline read-through, and an XLE put spread as the defined-risk expression. Use only the loaded validated objects. Separate what confirms the trade, what rejects it, what is missing, and what would kill it.
```

## Scoring

| Category | Score | Rationale |
| --- | ---: | --- |
| Data breadth | 8/10 | Gamma covers macro, commodities, options, fundamentals, prediction markets, portfolio, Strategy Lab, Sitrep, and news in one workspace. |
| Data depth / drill-down | 7/10 | Fundamentals and Strategy Lab are deep enough for real analysis, and commodity basis work improved trust; sector DCF checks and event search still need depth. |
| Analytical tooling | 8/10 | Strategy Lab validation, Risk research-book handoff, Options templates, and Fundamentals DCF are strong; cross-tab object coverage and sector-specific model checks remain limiting. |
| Copilot usefulness | 5/10 | Original context discovery was useful and recent commits improved the surface, but full synthesis over validated objects still needs a fresh proof. |
| Cross-tab workflow / state continuity | 5/10 | Strategy Lab to Risk moved from broken to implemented, but the broader research-thread contract is still incomplete. |
| Visual density and terminal feel | 8/10 | The app remains dense, data-rich, and provenance-heavy; DCF edit affordances and accessibility names need cleanup. |
| Speed to insight | 6/10 | Keybindings and strong tab surfaces are fast, but manual re-entry, search refresh ambiguity, and incomplete handoffs slow full workflows. |
| Overall | 7/10 | The recent fixes are real and materially improve the product; the remaining work is less about adding tabs and more about making validated research context durable across the whole app. |

## Prioritized Follow-Up

### P0: Complete research-thread context contract

Create a shared current research-thread object across tabs.

Acceptance criteria:

- Tabs declare context status.
- Instruments, books, option structures, DCF scenarios, commodity shocks, and prediction markets can attach to one research thread.
- Copilot uses the same validated context records the UI uses.
- Destination tabs show whether context was loaded exactly, transformed, partially supported, or unavailable.

Status: Open.

### P0: Retest Copilot synthesis after rebuild

Make the dedicated Copilot workspace return a ready card or explicit recoverable failure using the rebuilt chatbot UI.

Acceptance criteria:

- A timeout guard never leaves the UI indefinitely on `GENERATING...`.
- The user sees whether the issue was planner-only, provider timeout, route timeout, or model error.
- The prompt and selected contexts remain recoverable.
- The answer cites the validated context objects used.

Status: Needs current retest.

### P1: Fundamentals editable-cell clarity

Make DCF editable cells obvious, labeled, and testable.

Acceptance criteria:

- Editable assumption/projection cells have descriptive labels. Status: implemented 2026-06-23.
- Visual treatment distinguishes editable cells from read-only outputs. Status: implemented 2026-06-23.
- Editing a cell enables `Recalculate + Save` in a human/browser regression test. Status: component behavior implemented 2026-06-23 via `input` dirty-state handling; browser-level regression coverage remains open.
- Dirty state is visible and recoverable. Status: implemented for typed edits and existing save/reset flow.

Status: Implemented in part on 2026-06-23; needs live/browser retest.

### P1: Fundamentals DCF sanity checks

Add sector-aware DCF validation and reverse-valuation tools.

Acceptance criteria:

- Implausible D&A, capex, growth, and terminal-value assumptions are flagged before the valuation summary.
- DAL-like airline cases explain why defaults produce negative value.
- User can compare current price to implied growth/margin/capex assumptions.

Status: Open.

### P1: Commodity value reconciliation retest

Verify the recent commodity basis reconciliation across tabs.

Acceptance criteria:

- WTI header shows contract month, timestamp, provider, and basis.
- If Sitrep and Commodities use different instruments, the UI states that clearly.
- Copilot context includes the basis note.
- Risk/scenario shock templates use the selected or declared commodity basis.

Status: Implemented in part by `e032af9`; needs workflow retest.

### P2: Thesis-horizon-aware options

Improve options template defaults for actual thesis work.

Acceptance criteria:

- User can set or infer event horizon before template construction.
- Template default expiry/moneyness reflects the selected horizon.
- Missing/interpolated cells stay visible near the strategy output.

Status: Open.

### P2: Prediction-market intent search

Improve event-sensitive search for geopolitical/commodity catalysts.

Acceptance criteria:

- `Iran oil` returns direct geopolitical/oil markets when available.
- If no direct market exists, Gamma says so and offers adjacent crude, Iran, or Middle East contracts separately.
- Related-market rows explain event, topic, entity, threshold, or weak-match basis.

Status: Partially improved for related-link honesty by `fcb7a5c`; search intent remains open.

### P2: Navigation/accessibility cleanup

Separate human keyboard workflow from accessibility/automation friction.

Acceptance criteria:

- Major tab keybindings remain reliable and discoverable.
- `getByRole('button', { name: 'COPILOT' })` resolves predictably in the intended scope.
- Drag handles include distinct labels that do not collide with tab names.
- Offscreen nav controls are not exposed as active duplicates when the drawer is closed.

Status: Reframed. This is not a primary human power-user blocker, but it remains an accessibility and agent-workflow issue.

## Recently Resolved Or Improved

### Strategy Lab to Risk handoff

Status: Complete as of 2026-06-14.

Implemented by commit `67972ee`:

- Strategy Lab portfolio composition now requires a current valid book validation before creating the composed signed book.
- A successful validated composition is promoted into a persisted `strategy_research_book` object with signed normalized weights, validation provenance, aligned return points, and a Risk-ready synthetic snapshot.
- Risk accepts `source_scope = research_book` with explicit source label/object/origin fields and computes core risk metrics from the supplied Strategy Lab aggregate return stream instead of reloading provider histories.
- Risk shows the Strategy Lab book as a selectable source and labels the active source as `Strategy Lab book: ...`, separate from account portfolio and research-scope snapshots.
- Focused backend/API/frontend tests cover the direct return-stream compute path, API contract, durable book object construction, and Risk source labeling.

Remaining follow-up:

- Per-leg contribution decomposition for research books.
- Full research-thread context beyond this one handoff.

### Commodity price-basis reconciliation

Status: Implemented in part by commit `e032af9`.

The original audit's WTI inconsistency led to the right class of fix. The remaining need is a cross-tab workflow retest rather than another generic complaint that commodities lack basis transparency.

### Prediction-market related-link honesty

Status: Improved by commit `fcb7a5c`.

The remaining issue is search intent and event matching, not generic related-link quality.

### Copilot surface and grounding

Status: Improved by commits `99cde79` and `ccc7eb4`.

The original `GENERATING...` failure should be retested against the rebuilt Copilot tab before being repeated as current truth.

## Guidance For Future Agents

Use keyboard navigation in audits where a human power user would use it. Log side-drawer and duplicate accessible-name issues as accessibility/automation friction, not necessarily as core human usability blockers.

Do not add another research tab to solve these findings. The app already has enough surfaces. The next improvement should make the existing research path trustworthy:

1. Make research-thread context durable across tabs.
2. Make Copilot consume the same validated objects the UI uses.
3. Make editable DCF cells obvious, labeled, and testable.
4. Retest commodity basis reconciliation across Sitrep, Commodities, Risk, and Copilot.
5. Add sector/model sanity checks before showing valuation conclusions.

The product bar is not "more data." The bar is that a user can understand exactly which data Gamma used, how it transformed it, and whether the workflow remained coherent across tabs.
