---
name: gamma-usability-check
description: Run audit-only, IBKR-integrated end-to-end usability checks of Gamma, with deliberate specialist-surface rotation and provider-only scope only when explicitly requested. Use for live dogfooding, thesis journeys, cross-tab handoffs, and Gamma usability reports; do not use to fix findings or for code-only UI reviews.
---

# Gamma Usability Check

Conduct one coherent research journey through Gamma, use the app's current provider-backed data to form and challenge a provisional investment thesis, and record which product surfaces support or obstruct the work.

Treat a rejected, indeterminate, or unsupported thesis as a valid result. The goal is to evaluate Gamma's research utility and trustworthiness, not to manufacture a trade idea.

## Read Current Gamma Context

Before launching the app:

1. Read `AGENTS.md`, `roadmap.md`, and the runtime guidance in `README.md` from the repository root.
2. Read `docs/provenance_expectations.md`.
3. Read `docs/audits/usability/README.md`, `docs/audits/usability/coverage-ledger.md` when it exists, and the most recent relevant audit. Use older reports only when needed to identify a regression or calculate coverage debt.
4. Read [references/run-contract.md](references/run-contract.md) before any runtime interaction.
5. Read [references/coverage-policy.md](references/coverage-policy.md) before selecting surfaces.
6. Read [references/thesis-routes.md](references/thesis-routes.md) when selecting the research journey.
7. Read [references/report-template.md](references/report-template.md) before writing the audit.

Use the current roadmap and live app as the source of truth for available tabs and capabilities. Do not freeze a historical tab list into the audit.

## Preserve The Audit Boundary

- This skill is audit-only. Do not edit product code, tests, product documentation, configuration, or roadmap state. Do not implement a fix or transform the run into a remediation pass.
- This is an external QA harness, not Gamma's Copilot execution architecture. It drives the UI because the UI is the object under test; it does not make UI automation authoritative for Copilot tools, permissions, analysis, or state.
- The permitted repository writes are the new audit report, its concise entry in `docs/audits/usability/README.md`, the audit coverage ledger, and narrowly selected audit evidence under `docs/audits/usability/evidence/` when that evidence materially supports a finding.
- Preserve all pre-existing working-tree changes. Record the starting commit and dirty/clean state.
- Gamma remains a read-only research environment. Never place or stage orders, rebalance an account, mutate broker/account/wallet state, expose credentials, or enable unrestricted code execution.
- Hypothetical portfolios, rebalance candidates, DCF assumptions, option structures, research scripts, Copilot sessions, and memos may be created only as clearly labeled research artifacts when they are part of the journey.
- Do not delete or overwrite user artifacts. Prefer `AUDIT <date> ...` names. Archive or remove only artifacts created by this run when the app offers a clearly safe path; otherwise record what remains.
- Do not silently change provider selection or replace unavailable provider data with sample/mock data.

If a finding deserves remediation, give it evidence, severity, and acceptance criteria in the report and stop there.

## Run The Research Journey

1. Capture a read-only preflight with `scripts/audit-preflight.ps1`. Prefer an already running Gamma instance; otherwise launch the current documented app path without inventing stale commands.
2. Apply the audit-mode gate from the run contract. A normal full audit requires Gamma to report an IBKR connection. If IBKR is disconnected, stop before thesis selection unless the user explicitly requested a provider-only focused audit. The absence of IBKR is then a baseline condition, not a usability finding.
3. Establish whether a provider-backed run is possible. At least one decisive input must be real provider data. Live, delayed, cached, stale, derived, sample, and unavailable states must remain distinct.
4. Scan an information-rich Gamma surface and select one primary research question from what the app currently shows. Record the provisional thesis before deep investigation.
5. Select one coverage target using [references/coverage-policy.md](references/coverage-policy.md). Prefer the highest-debt specialist surface that the current environment can exercise. Do not force it into the primary thesis when that would be artificial.
6. Follow an adaptive route through the relevant surfaces. When supported, exercise at least three meaningful product surfaces, one cross-tab handoff, and one terminal research artifact or synthesis step. A blocker may shorten the route, but it must be evidenced.
7. Exercise the coverage target through a bounded, purpose-specific micro-mission when the primary journey did not already cover it substantively. Opening a tab or observing its landing state does not count.
8. Use the UI for the research workflow. API probes, logs, and direct storage inspection are supporting diagnostics; if they substitute for an undrivable UI step, classify the UI step as blocked or degraded rather than passed.
9. Seek disconfirming evidence and define a falsifier or kill condition. Keep thesis confidence separate from data-quality confidence.
10. Check provider usage, provenance, freshness, warnings, state continuity, and read-only labeling throughout the journey—not only at startup.
11. Produce the report, update the coverage ledger, and perform bounded cleanup from the run contract.

The primary thesis may concern a portfolio, equity, macro regime, relative-value relationship, option structure, commodity, prediction market, crypto asset, imported return stream, or an unsupported domain. A second primary thesis is allowed only when the first is blocked before meaningful research begins. A coverage micro-mission is separate and should answer one narrow user-purpose question rather than pretending to be part of the primary thesis.

## Data And External Evidence

- Provider-backed public sources surfaced through Gamma count as live research data even when they are not streaming market data.
- Cached or delayed data may support a conclusion only when its timestamp, source, and limitation are visible and appropriate for the claim.
- Sample or mock data may be examined to evaluate fallback honesty, but it cannot satisfy the provider-backed completion gate or serve as decisive thesis evidence.
- Use an external authoritative dataset only to exercise an import workflow or to validate a suspected correctness defect. Label it as external evidence and never use it to conceal missing Gamma coverage.
- If Gamma cannot search, ingest, transform, or analyze the required data shape, report an unsupported or broken boundary rather than completing the research outside Gamma.

## Classify Every Attempted Step

Use exactly one status:

- `Worked`
- `Worked with degradation`
- `Blocked by product defect`
- `Blocked by provider or entitlement`
- `Unsupported by design`
- `Unverified`

Do not turn an honest provider limitation into a product defect. Do not turn a silent blank state, misleading value, lost context, or undrivable control into a provider limitation.

## Deliver The Audit

Only create the standard report after a research journey begins. If a normal full audit stops because IBKR is disconnected, return the concise preflight blocker required by the run contract without adding a report, index entry, or coverage credit unless the user explicitly requested those failed-preflight records.

Write `docs/audits/usability/gamma_usability_findings_YYYY-MM-DD.md`. If that filename exists, add a short numeric suffix rather than overwriting it. Add a one-line entry to `docs/audits/usability/README.md` and update `docs/audits/usability/coverage-ledger.md`. Create the ledger from the live top-level navigation if it does not exist.

The report must be useful without terminal history. Include the environment and provider matrix, provisional thesis, chronological journey, supporting and contrary evidence, final research verdict, step classifications, prioritized findings, cross-tab and Copilot assessments when exercised, scorecard, unverified boundaries, and cleanup. Follow [references/report-template.md](references/report-template.md).

In the final response, link the report, state the thesis verdict, summarize the highest-priority findings, name the coverage target and its outcome, identify the IBKR/audit mode and whether the provider-backed completion gate passed, and confirm that no product code was changed.
