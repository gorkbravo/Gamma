# Usability Audit Report Contract

Write a self-contained report. Use the structure below unless the run's shape makes a small adaptation clearer.

## Filename And Index

Default filename:

```text
docs/audits/usability/gamma_usability_findings_YYYY-MM-DD.md
```

If it already exists, use `gamma_usability_findings_YYYY-MM-DD-2.md`, then increment. Never overwrite a prior audit.

Add the newest report near the top of `docs/audits/usability/README.md` with one sentence covering mode, thesis lane, provider gate, and highest-priority result. Do not rewrite historical entries.

## Required Report Shape

```markdown
# Gamma Usability Findings — YYYY-MM-DD

Date:
Audience:
Mode: IBKR-integrated | provider-only focused | diagnostic-only blocked
IBKR state: connected live | connected delayed/frozen | connected entitlement-limited | disconnected | unverified
Runtime: existing | audit-launched frontend | desktop
Commit / branch / dirty state:
Data context:
Scope:

## Outcome

One answer-first paragraph covering the research verdict, provider-backed gate,
end-to-end completion, and most important product result.

## Environment And Provider Matrix

| Provider / subsystem | State | Freshness / mode | Used in verdict | Notes |
| --- | --- | --- | --- | --- |

## Declared Baseline Constraints

State which capabilities are outside this run's mode. A disconnected IBKR session
in an explicitly provider-only run is one baseline constraint, not a finding.

## Research Question And Provisional Thesis

- Question:
- Provisional thesis:
- Horizon:
- Initial signal:
- Expected confirmation:
- Falsifier / kill condition:
- Hypothetical expression, if any:

## Journey

| # | Surface and action | Evidence / visible provenance | Result | Classification |
| ---: | --- | --- | --- | --- |

## Coverage Mission

- Target surface:
- Why it had the highest coverage debt:
- Purpose-specific question:
- Provider-backed input:
- Meaningful action and result:
- Classification:
- Does this count as deep coverage, micro-mission coverage, or no substantive coverage?

## Thesis Verdict

- Verdict: confirmed | partially confirmed | rejected | indeterminate | unsupported
- Thesis confidence:
- Data-quality confidence:
- Supporting evidence:
- Contrary evidence:
- Falsifier status:
- Research-only expression or decision implication:

## What Worked

## Findings

### P0/P1/P2/P3 — GUA-YYYYMMDD-N: concise title

- Journey impact:
- Expected:
- Observed:
- Evidence:
- Reproduction:
- Classification: product defect | usability friction | data coverage gap | provider/entitlement constraint
- Acceptance criteria:

## Cross-Tab And State Continuity

## Copilot Evaluation

Include only when exercised. Separate grounding, tool/context scope, provider
delivery, transcript rendering, persistence, and memo/export behavior.

## Unsupported And Unverified Boundaries

Use `N/A — requires IBKR-integrated audit` for broker-dependent surfaces excluded
from a provider-only focused run. Do not convert the expected disconnect into
multiple findings or score penalties.

## Coverage Ledger Update

- Surfaces credited this run:
- Coverage depth credited:
- Surfaces still carrying the highest debt:
- Environment/provider qualification attached to the credit:

## Scorecard

| Category | Score | Rationale |
| --- | ---: | --- |
| Data breadth | /10 | |
| Data depth and drill-down | /10 | |
| Data trust and provenance | /10 | |
| Analytical tooling | /10 | |
| Cross-tab continuity | /10 | |
| Recovery and state resilience | /10 | |
| Agent drivability | /10 | |
| Speed to insight | /10 | |
| Overall | /10 | |

## Cleanup And Residual State

## Audit-Only Follow-Up

Rank findings and state their acceptance criteria. Do not modify code or mark a
finding fixed during this run.
```

Use `N/A — not exercised` rather than inventing a score. Explain why an important surface was not exercised.

## Step Classifications

Use exactly one:

- `Worked`: the visible workflow completed with trustworthy, adequately labeled output.
- `Worked with degradation`: useful output completed, but a disclosed limitation constrained it.
- `Blocked by product defect`: Gamma behavior prevented the intended step or made the output untrustworthy.
- `Blocked by provider or entitlement`: an external capability was unavailable and Gamma identified the cause honestly.
- `Unsupported by design`: Gamma clearly stated that the requested instrument, region, or workflow is outside current coverage.
- `Unverified`: the audit could not establish the behavior within safe evidence or time bounds.

## Severity Calibration

- `P0`: unsafe boundary failure, materially wrong or misleading research output, data corruption, app-wide unrecoverable failure, or a defect that invalidates the audit's central conclusion.
- `P1`: major workflow blocker, serious trust failure, or broken cross-tab/persistence behavior without a reasonable in-app workaround.
- `P2`: meaningful friction, degradation, confusing state, or coverage/presentation defect with a workable path.
- `P3`: minor polish, consistency, or efficiency issue that does not materially affect the research conclusion.

Provider absence is not a P0/P1 product defect when Gamma labels it accurately and offers the expected degraded state. A silent fallback, incorrect basis, stale value presented as current, or blank state without explanation may be.

In a provider-only focused run, IBKR disconnection itself and its direct expected consequences are baseline exclusions, not findings. Score only the capabilities actually in scope.

## Evidence Rules

- Give timestamps, units, horizons, symbols/contracts, and source/freshness labels needed to understand the claim.
- Cite local screenshots or traces with relative report links when retained.
- Redact account identifiers, credentials, session tokens, raw private holdings, and sensitive provider messages.
- State when an API probe replaced a UI step.
- Distinguish direct observation from inference.
- Compare with a prior finding only when the evidence supports regression, recurrence, narrowing, or non-reproduction.
- Do not include a remediation-status section unless the user separately requested a targeted verification-only audit of an existing fix.
