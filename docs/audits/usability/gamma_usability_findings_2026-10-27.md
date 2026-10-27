# Gamma Usability Findings — 2026-10-27

Date: 2026-10-27, 13:42–14:35 and 21:05–21:15 Europe/Madrid (CET, UTC+1)<br>
Audience: future AI agents and contributors improving Gamma<br>
Mode: verify-only<br>
Data: live IBKR (TWS on 7496, account identifier not retained), market data `Auto`; US options quoted LIVE in the regular session (14:30–21:00 Madrid until 1 November)<br>
Context: live retest of every finding claimed fixed in [`gamma_usability_findings_2026-10-21.md`](./gamma_usability_findings_2026-10-21.md) ("Fix Status"), plus the Event Book ladder and `us_macro_events` fixes, on the integration branch `claude/verify-2026-10-21-audit`.

## Audit Setup

- Branch `claude/verify-2026-10-21-audit`: `claude/brave-bhabha-485286` (the 2026-10-21 fixes plus the Event Book ladder) with `claude/inspiring-yonath-627a70` (`us_macro_events`) merged at `a73e492`, no conflicts. Suites at the merge: pytest 1184 passed / 5 skipped, vitest 615 passed, `tsc --noEmit` clean.
- Backend `uvicorn src.api.main:app` on 127.0.0.1:8000 with the repo `.env` loaded and `IB_AUTO_CONNECT=true`; Vite on 127.0.0.1:5173. Gate (`check-live-ibkr.ps1`) exit 0 at 21:14:39; live IBKR was also connected for the whole 13:42–14:35 block.
- Interruptions, not product faults: Windows entered Modern Standby 14:35:07 → 15:51:03 (power-source change, Kernel-Power 506/507), TWS logged "Error 1100 connectivity lost" on wake, the machine was idle again until 21:05, and TWS was reopened and reconnected from the UI at 21:06:23. The US regular session closed at 21:00, so the after-fix re-checks ran out of session.
- Tabs exercised: SITREP, Commodities (Overview, Metals, Curves & Spreads), Strategy Lab (handoffs, Validate, Compose, Open In Risk), Risk (Scenarios), Options (Overview, Strategies on USO/BNO/SPY, closed and in session), Prediction Markets (Screener, Contract, Event Book, RELATED), Macro (Events / Regimes), Copilot (Research Agent, Research Operator, Retry), Crypto (forced render error), Settings (Provider Usage).
- Outside tools, and why:
  - EIA API v2 (`PET.RBRTE.D`, `PET.RWTC.D`, `PET.RCLC1.D`) to check the two commodity stress windows against an official series; Gamma does not expose episode anchors.
  - Direct API reads (`/system/status`, `/commodities/overview`, `/macro/events`, `/system/provider-usage`) and turn/snapshot files under `data/copilot/` for exact values and sizes.
  - A profiling script with a second IBKR client (id 9) to split the Commodities load into phases.
- Copilot: 5 live OpenAI runs (the authorised maximum), model `gpt-6.1-sol`, profile Auto → Standard.
- Fixes found necessary during the run were committed on the branch with tests (listed under each finding). Not pushed.

## Regression Delta (vs `gamma_usability_findings_2026-10-21.md`)

| ID | Finding | Prior status | This run | Evidence |
| --- | --- | --- | --- | --- |
| GUA-20261021-1 | Add Leg duplicate-key wedge | Fixed (boundary SSR-only) | **Confirmed fixed** | Remove ×3 and Add Leg ×2 raised no error. A forced throw in CryptoView showed "This view failed to render … Retry"; Retry remounted, Macro opened normally, CryptoView rendered after the throw was reverted (no commit). |
| GUA-20261021-2 | Cracks stamped current from old history | Fixed, not live-checked | **Confirmed fixed** | 2-1-1 Crack "64.489 USD/bbl · Live 67.427 · Oct 27, 2026, 01:52 PM GMT+1 · 2026-10-20 STALE 7D OLD"; Live value from "RBX6 / HOX6 / CLZ6 from one snapshot". |
| GUA-20261021-3 | Naive UTC clocks | Fixed | **Confirmed fixed** | Commodities "TIME Oct 27, 2026, 01:51 PM GMT+1"; Options "LIVE · 14:31" local; SITREP ages correct. |
| GUA-20261021-4 | Basis date- and unit-blind | Fixed, not live-checked | **Confirmed fixed** (the `basis` state could not be seen) | Brent "FRED spot proxy 115.22 USD/bbl · 2026-10-20 · 7d · STALE". Copper 14473.06 USD/t → `converted_value` 6.5649 USD/lb, no percentage; the old "208636%" is gone. Every EIA/FRED reference was ≥7 days old, so none reached `basis`. |
| GUA-20261021-5 | EU EUR/USD inverted | Fixed (live 1.174 on 10-22) | Not retested | — |
| GUA-20261021-6 | Synthesis truncates, no Retry | Fixed, not verified live | **Confirmed fixed after one more fix** | Literal audit prompt, 5 contexts: `ready`, 2,134 output tokens (cap was 1,400), 110,730 input, 59.9 s backend; includes Brent BZZ6 114.96 / BZJ7 101.13. Retry after reload reran the identical prompt and request context. Live-session Retry was disabled for a cancelled turn → fixed in `226fa93`. Continue not triggered (no cut-off). |
| GUA-20261021-7 | Sealanes handoff dead-end | Fixed (live 10-22) | Not retested | — |
| GUA-20261021-8 | Metals delivery-month fronts, dead FRED, Zinc retries | Fixed, not live-checked | **Confirmed fixed after one more fix** | Gold GC Dec 2026 −0.11%, Silver Dec, Platinum Jan 2027, Copper Dec. One Zinc "Error 200" per backend session. The retired-FRED warning reached only the API → shown under Metals Snapshot in `19ee689` (seen live 21:08:54). |
| GUA-20261021-9 | Spot-proxy books, no stale warning, no commodity episodes | Fixed; windows from memory | **Confirmed fixed** | Legs "245 dated points to 2026-10-20 · FRED spot proxy DCOILWTICO". Validate: "ends 2026-10-20, 5 trading days before 2026-10-27 (stale above 3)". Brent–WTI-only book: no yfinance caveat (yfinance only on the SPY benchmark row). Risk replay rows "2020 oil price war … 2020-03-05 to 2020-04-21" and "2022 energy shock … 2022-02-23 to 2022-03-08". EIA Brent spot: 51.29 on 2020-03-05, low 9.12 on 2020-04-21; 99.29 on 2022-02-23, high 133.18 on 2022-03-08 — windows kept. |
| GUA-20261021-10 | 0DTE off-hours headline, nearest-expiry templates | Fixed, labels need TWS | **Confirmed fixed** | Closed (13:48–13:50): "STALE · CLOSED · LAST SESSION" on USO, BNO, SPY. Divergence warning on USO: call 116.5% vs put 73.0% at the 158 strike. In session (14:31–14:33): LIVE on all three, with headline expiries USO 11/04 (8D), BNO 11/06 (10D) and SPY 11/03 (7D). Templates landed on 11/27 (31 DTE). Net Theta: the 1D 166/167 call spread had −0.053/day and the 31D template −0.001, so the old +0.453 came from stale pre-market quotes. |
| GUA-20261021-11 | LOOKBACK not honoured | Fixed | **Confirmed fixed** | "Lookback 756 trading days · analysed 241 (2025-10-28 to 2026-10-20)" with the reason per leg. |
| GUA-20261021-12 | SITREP cold load | Fixed (TWS down) | **Confirmed fixed after one more fix** | With TWS, cold, 6 parallel requests: prediction markets 3.1 s, news 5.0 s, indices 17.1 s, equities 17.7 s, macro 32.6 s, **commodities 50.0 s**. Status polling never blocked (183/183 OK, max 225 ms). After `b21b2e8`, forced commodities 40.6 s → 10.5 s (same conditions), and 11.3 s in a 6-section forced load. |
| GUA-20261021-13 | Copilot/Operator noise | Fixed, not verified live | **Confirmed fixed after four more fixes** | JSON collapsed and tables rendered from the start. Still broken live: SEC "Plan warning" on the literal commodity prompt (`25ee22f`); 41 separate "Operator warning" steps and 842 progress rows (`382feb5`); duplicate "OPERATOR RUN" block (`226fa93`); a pipe table without separator row left raw (`34015f3`). Run 5 after the fixes: 0 SEC warnings, "Operator warning · 40" folded, one progress row, table rendered. Snapshots 2.55 MB (were 4.6–5.0 MB). |
| GUA-20261021-14 | Setup friction | Fixed (auto-connect failure path live) | **Auto-connect confirmed fixed**; Review/modal not retested | "IBKR auto-connect: trying 127.0.0.1:7496 once" → "ok in 0.3s" (13:42:13) and 0.2 s (14:34:35); without TWS "failed after 2.1s … not retrying" (21:05:58). |
| GUA-20261021-15 | RELATED misses series siblings | Fixed; Kalshi series not live | **Confirmed fixed after one more fix** | Kalshi "Fed funds rate at end of 2030": "SAME EVENT 16" + "SAME SERIES 5 \| KXFEDFUNDSYEAR". A failed series lookup was swallowed → warning in the response and panel (`11efa61`). |
| GUA-20261021-16 | Accessible names | Fixed | **Mostly fixed** | Per-leg names ("Remove Brent Crude Oil spot proxy return stream", "Weight of …"), template names ("Call Spread template, …"), "Send this options surface to Copilot", "Open Brent Crude Oil" rows. Remaining: the Options symbol input is named by its placeholder ("SPY"); Strategy Builder side/right selects have no name. |
| GUA-20260903-10 | Provider diagnostics | Fixed (live 10-22) | **Confirmed fixed after one more fix** | Rows sum to the total (207). Partial calls were also counted as failures ("us_macro_events 2 ok · 4 failed"; IBKR "3 failed and 3 returned partial data" for the same three surfaces) → `6b39648`; live after: "us_macro_events · 2 ok · 4 partial". |
| Risk copy / transient drill header | Risk copy fixed live; header tests only | **Header confirmed fixed** | SITREP "Open Brent Crude Oil": +30 ms "LOADING Brent Crude Oil", +239 ms "BZZ6 / Dec 2026", never WTI. Risk copy not retested. |
| Event Book (open on 10-21) | Cumulative ladder summed | Fixed on branch, not in UI | **Confirmed fixed** | "Putin out … by…?": "5 rungs \| date ladder · nested \| not summed · Monotonicity Holds"; Kalshi 2030 Fed funds: "21 rungs \| threshold ladder". |
| `us_macro_events` (open on 10-21) | 23/31 calendar requests failing | Fixed on branch | **Confirmed fixed after one more fix** | BEA and Fed pages load; BLS skipped with a named warning (no contact identity set, by design). The FOMC meeting of 27–28 Oct was missing on 27 Oct (dated 00:00 of day 1) → GUA-20261027-1. |

## Thesis Log

Not applicable: verify-only mode. The Brent–WTI / Hormuz thesis of 2026-10-21 was replayed only as the vehicle for the retests (same Copilot prompts, same handoffs).

## Trade Verdict

Not applicable (verify-only). For the record, Copilot's Agent card on the same five contexts read the Dec-26 Brent–WTI spread at $13.91 and Apr-27 at $8.59 (front-loaded, not prompt-only), with Hormuz-normal-by-Dec-31 at 11%.

## Usability Report

### What worked well

- Progressive SITREP: the slow section no longer holds the others, and status polling stayed responsive throughout.
- Options session labelling is now trustworthy: CLOSED/STALE off-hours, LIVE in session, divergence called out exactly when parity broke, and 0D/1D skipped in the headline.
- Commodities freshness is explicit everywhere it matters: spread Obs dates, a same-snapshot Live value, dated and unit-converted basis references.
- The Commodities → Strategy Lab → Risk loop now states the series type and end date and warns on stale windows. It also replays the two commodity episodes, whose windows match the EIA series.
- The five-context Copilot synthesis completed and cited the Brent curve. Retry reruns the stored request, not the current selection.

### Friction points (ranked)

1. **P1 — GUA-20261027-1: the FOMC meeting disappeared from "upcoming" on its first day** (Macro › Events / Regimes, 14:01).
   - Evidence: `/macro/events?region=US` started at 2026-10-29. The FOMC of 27–28 Oct, with the decision due the next day, was missing because meetings were dated 00:00 UTC of day 1. The ECB decision day had the same midnight problem.
   - Fix: `e5f0ce2` dates FOMC at 14:00 New York on the last day and the ECB press-conference day at 14:15 Frankfurt.
   - Live after the fix: "FOMC Meeting (October 27-28) · Oct 28, 2026" first; EU Day 2 at 13:15 UTC.
   - Status: Fixed.
2. **P2 — GUA-20261027-2: a finished Operator run rendered twice in the live session** (Copilot). The run appeared as the thread turn and again as "OPERATOR RUN", 894 rows each. Fixed in `226fa93`. Status: Fixed.
3. **P2 — GUA-20261027-3: the Operator curve inspection reads the cached breadth curve of a non-selected instrument.**
   - Run 5 got Brent with 2 nodes "despite requesting 12" and could not inspect WTI ("per-run request limit of 1"), so 10 of 12 spreads were NA.
   - `/commodities/overview?selected_instrument_id=brent` returned 12 priced nodes at the same time.
   - Run 2 (14:09) got 12 Brent nodes only because Brent had been viewed earlier.
   - Status: Fixed (`6ebc045`), see Closure.
4. **P2 — GUA-20261027-4: crack history changes with cache state.** The 2-1-1 crack for the same observation date (2026-10-20) read 54.419 when WTI came from a cached curve (FRED spot leg) and 64.489 when WTI was freshly loaded (IBKR front-history leg). Spot and futures crude legs are mixed depending on which curve is cached. Status: Fixed (`57a8341`, `e86a99f`), see Closure.
5. **P2 — GUA-20261027-5: Options symbol edits.**
   - Typing into the filled symbol field produced "USOBNO" and a silent "LOADING…" for ~40 s, with no error.
   - After loading SPY from Strategies, switching to Overview showed "Enter an underlying symbol" until a reload.
   - Status: Fixed (`4de627b`, `4a7e872`); the Strategies → Overview loss did not reproduce with real clicks. See Closure.
6. **P2 — GUA-20261027-6: Risk "SHARE OF RESULT" explodes on a near-neutral book.** It showed −2106.9% / 2206.9% because each leg is divided by a ~0 net P&L. Status: Fixed (`5e41831`).
7. **P3 — commodity handoff caveat mismatch.** FRED-spot Brent/WTI legs carry "Cached IBKR curve snapshot with the original provider-backed quote …". Status: Fixed (`2c5d5e0`).
8. **P3 — two-digit years in RELATED.** Captions read "resolves Jan 8, 28" (asserted in a test). Status: Fixed (`ad8fa7f`).

### Gaps

Unchanged from 2026-10-21 and out of scope here: freight/Portwatch in Sealanes, inter-commodity spread curves, EU sovereigns, roll-adjusted futures streams. The `basis` reconciliation state needs a reference ≤4 days old, which EIA/FRED spot did not provide on 2026-10-27.

### Cross-tab coherence

- Carried: SITREP → Commodities (correct transient header), Commodities → Strategy Lab (dated handoffs), Strategy Lab → Risk, and Copilot context across five tabs.
- Inconsistent:
  - Operator inspection vs Commodities selection (GUA-20261027-3).
  - Crack history vintage vs cache state (GUA-20261027-4).
  - The RSS `ecb_press` feed failed with `CERTIFICATE_VERIFY_FAILED` (same Sectigo E46 root that the ECB calendar fix solved with certifi). Fixed in `1b43f49` and `a0c6c76`, see Closure.

### Copilot evaluation

| Run | Mode / contexts | Result |
| --- | --- | --- |
| 1 | Agent, SITREP + Strategy Lab + Prediction Markets + Commodities + Risk, literal 2026-10-21 prompt | `ready`, ~100 s to full render (59.9 s backend), 110,730 in / 2,134 out. Every number cited, stale inputs dated, kill criteria stated. No hallucination found. |
| 2 | Operator, same contexts, literal 2026-10-21 Operator prompt | `ready` in ~47 s; six-month table rendered; WTI Jun–Nov NA (per-run limit). SEC plan warning, 41 warning steps, 842 progress rows, duplicate render → fixed. |
| 3 | Agent, 2 contexts, stopped after ~4 s | `cancelled`; Retry disabled until reload → fixed. |
| 4 | Retry after reload | `ready`, identical prompt, scopes and request context; 27,210 / 457 tokens. |
| 5 | Operator, Commodities + Macro, literal Operator prompt, after the fixes | `ready` in ~37 s; 0 SEC warnings; grouped warnings; single render; bare pipe table → fixed and re-rendered. Brent 2 nodes (GUA-20261027-3). |

## What Could Not Be Proven This Run

- Continue after a `max_output_tokens` cut: no run was cut. Covered by tests only.
- The `basis` (dated futures-vs-spot) state: every reference was older than 4 days.
- Live-session Retry after the `226fa93` fix: no run budget left; covered by tests. Retry itself was proven after a reload.
- A failed Kalshi series lookup: the lookup worked; the warning path is covered by tests.
- In-session Options and full Sitrep timing with the fixed backend: the machine suspended at 14:35. The after-fix numbers (10.2–17.0 s forced, 11.3 s in a 6-section load) are out of session.
- GUA-20261021-5, -7, -14 (Review/modal) and the Risk copy: not retested.

## Scoring

| Category | Score | Δ vs prior | Rationale (one sentence) |
| --- | ---: | :--: | --- |
| Data breadth | 7/10 | = | Same providers; the macro calendar now carries Fed and BEA (BLS needs a contact identity). |
| Data depth / drill-down | 7/10 | +1 | Spreads, basis and handoffs now carry observation dates, units and staleness. |
| Analytical tooling (DCF, risk, scenarios, CSV) | 7/10 | +1 | Commodity episodes replay against official windows and LOOKBACK is explained; Risk share-of-result still breaks on neutral books. |
| Copilot usefulness | 7/10 | +1 | The five-context synthesis completes with Brent and Retry works; Operator curve inspection is still limited by cached breadth curves. |
| Cross-tab workflow / state continuity | 7/10 | +1 | Drill header, handoffs and Risk all carry state correctly. |
| Visual density & terminal feel | 7/10 | = | Operator traces now fold warnings and progress; raw tables are gone. |
| Speed to insight | 6/10 | +1 | No section blocks the others; commodities dropped from 50 s to ~11 s, macro is now the slowest section (19–33 s). |
| Overall (gestalt, not an average) | 7/10 | +1 | Every 2026-10-21 P0/P1 retested live now holds, after nine small follow-up fixes found only by live use. |

## Prioritized Follow-Up

**P1**
1. **GUA-20261027-1** — FOMC/ECB decision times. Status: Fixed (`e5f0ce2`).

**P2**
2. **GUA-20261027-3** — the Operator curve inspection should request the instrument's full depth (or allow one inspection per instrument) instead of reusing the breadth cache. Acceptance: Brent and WTI 12-node curves in one Operator run without prior viewing. Status: Fixed (`6ebc045`); tool-level live check passed, no Copilot run left to replay end to end.
3. **GUA-20261027-4** — compute crack history from one consistent crude basis (spot with spot, futures with futures) regardless of cache state. Acceptance: identical values for the same observation date across selections. Status: Fixed (`57a8341`, `e86a99f`).
4. **GUA-20261027-5** — the Options symbol field replaces rather than appends, an unknown symbol fails visibly, and mode switches keep the loaded surface. Status: Fixed (`4de627b`, `4a7e872`).
5. **GUA-20261027-6** — Risk share-of-result is bounded or replaced by gross-share for near-zero net P&L. Status: Fixed (`5e41831`).
6. **GUA-20261027-2** — duplicate Operator render. Status: Fixed (`226fa93`).
7. **GUA-20261021-16** — name the Options symbol input and the Strategy Builder selects. Status: Fixed (`4a7e872`).
8. RSS `ecb_press` certificate chain (reuse the certifi context of the ECB calendar). Status: Fixed (`1b43f49`, `a0c6c76`).

**P3**
9. Handoff caveat text for spot-proxy legs; four-digit years in RELATED captions. Status: Fixed (`2c5d5e0`, `ad8fa7f`).

Visual observations belong to `gamma-ui`; no chart internals were assessed.

## Closure (2026-10-27, 21:30–21:50)

Every finding left open above was fixed on `claude/verify-2026-10-21-audit`, one commit per area, with tests. Re-checked live with TWS connected after the US close (no OpenAI run left):

| ID | Fix | Live check |
| --- | --- | --- |
| GUA-20261027-3 | `6ebc045`: a breadth-only curve (≤2 nodes) of a non-selected instrument is read from the read-only CommoditiesService, with a note; the tool may run twice per run. | Workspace with Gold selected held Brent with 2 nodes; the tool returned 12 with "held 2 breadth node(s) for brent; Gamma read 12 node(s)". WTI 12 nodes; `request_limit` 2. |
| GUA-20261027-4 | `57a8341`, `e86a99f`: the provider keeps the spot reference it replaces. Spread history uses each leg's spot reference when every leg has one, otherwise one shared basis, otherwise a warning. | 2-1-1 54.419 (2026-10-20) with forced fresh IBKR histories and with cached spot histories; Live 65.803. Before: 54.419 / 64.489 / 68.981. |
| GUA-20261027-5 | `4de627b`: the IV service stops waiting when the engine thread ends and skips depth retries for unknown underlyings, naming the cause. `4a7e872`: entering the symbol field selects its text. | "ZZQXW" failed in 3.6 s with "Unable to qualify underlying contract for ZZQXW". Click + type over it gave "SPY". Strategies → Overview kept the SPY surface (7D headline). |
| GUA-20261027-6 | `5e41831`: offsetting legs share the gross leg move; the column reads "Share of gross P&L". | Unit-tested on the BNO/USO case; not replayed in the UI. |
| GUA-20261021-16 | `4a7e872`: "Options underlying symbol", "Strategy leg side", "Strategy leg option type", "Expiry". | Accessibility tree shows "textbox Options underlying symbol". |
| RSS `ecb_press` | `1b43f49`: shared certifi context, RSS retry on certificate failure. `a0c6c76`: the recording opener trusts certifi, so ECB calls verify on the first, recorded attempt (the ECB calendar no longer bypasses the recorder). | Provider Usage: "http:www.ecb.europa.eu via news.latest success" and "… via macro.load_events success". |
| P3 caveat / years | `2c5d5e0`, `ad8fa7f`. | Prediction Markets shows "RESOLVES Jan 1, 2027". |
