# Optional Script analytical results — v1

Status: implemented with deterministic fixtures and a passed bounded actual isolated-Python supplied-file handoff (2026-10-15). E4 acceptance remains open for hypothetical-weight handoff. E3's separate live Operator gate closed on 2026-10-16 (see audits/script_e3_live_closure_2026-10-16.md).

Ordinary Python needs no strategy class, entrypoint, helper, Gamma import, network or structured output. Print/log/table/image/file outputs remain complete research outcomes. This convention is an optional interpretation layer over the existing retained-file mechanism.

## Authoring

Write UTF-8 JSON to **`gamma_analytics.json` in the sandbox working directory**, using Python's standard `json` module and `allow_nan=False`. Existing runtime output discovery downloads and retains this file. No helper is supplied or injected: the exact serialized-source logic belongs to the visible immutable source revision. Input files remain copied immutable snapshots.

In Script, open **Python output convention → Inspect exact v1 JSON schema** for both a copyable ordinary top-level Python example covering all four kinds and the complete schema. This works before a first run. The same server-owned example is supplied to the authorized Operator's existing `script_read_inputs` observation; it grants no new action. The authoritative contract and example are in [`src/models/script_analytics.py`](../src/models/script_analytics.py). `GET /research/strategy-lab/scripts/analytical-contract` exposes the exact schema, example, filename and byte ceiling.

The example expects an already supplied external file `observations.csv`:

```csv
date,return_fraction
2026-10-01,0.01
2026-10-02,-0.02
2026-10-05,0.005
2026-10-06,0.03
2026-10-07,-0.01
2026-10-08,0.02
```

Adapt its calculations, identities, names and meanings. Its score and weight series are serialization illustrations, not signals inferred by Gamma or a recommended allocation. Blank CSV values become explicit JSON `null`; they are never filled. No external file is acquired by the example.

## Contract

Root fields are `contract_version: gamma-script-analytics.v1`, `instruments`, and `results`. Unknown fields/versions, duplicate JSON keys, booleans masquerading as numbers, nonfinite values (including numeric overflow), invalid dates, unordered/duplicate observations, duplicate result/native instrument identities and references to undeclared instruments are rejected. Instrument keys are exact `instrument_id`, `namespace`, `native_id`, `label`; whitespace is not normalized. These are author-declared identities, not provider-certified identity or calculation claims.

Every result has a unique `result_id`, `name`, analytical `meaning`, `methodology`, `assumptions` and `limitations`. Text and list sizes are bounded. Dates use exact `YYYY-MM-DD`, without timezone truncation. Each series includes `instrument_id`, `frequency` (`daily`, `weekly`, `monthly`, `irregular`) and `observations` (`date`, numeric-or-null `value`). Weekly dates must use the same weekday; monthly dates cannot duplicate a month. Gaps remain gaps; declared frequency never authorizes resampling.

| Kind | Required semantics | Supported use |
| --- | --- | --- |
| `metric` | `value`, `unit` (`fraction`, `percent`, `ratio`, `count`, `currency`), `as_of`, nullable `instrument_id`; ISO currency required only for currency metrics. Counts are nonnegative integers. | Retained, validated inspection; no analytics handoff. |
| `returns` | `unit` (`fraction` or `percent`), `return_type` (`simple` or `log`), explicit positive `periods_per_year` up to 366. Simple returns cannot be below −100%. | Complete daily simple returns with 252 periods/year → existing Strategy Lab return analytics. |
| `signals` | `unit` (`score`, fractional `probability` in [0,1], or `indicator` in {−1,0,1}); meaning and methodology specify interpretation/timing. | Retained inspection. Never converted to positions, orders, returns or performance. |
| `weights` | `unit: fraction_nav`, `weight_semantics: signed_nav_exposure`, literal `hypothetical: true`. Each result carries one exact instrument's dated signed exposure schedule. | Retained inspection with signed values unchanged. No normalization or automatic composition. |

Limits: 512 KiB analytical JSON within existing runtime output limits; 32 results; 64 instruments; 5,000 observations per series; 32 assumptions and limitations each, at most 1,000 characters per note. No packages, providers, execution limits or runtime/model configuration are added or changed.

Prices, cumulative performance, implicit percentage conventions, gross-normalized weights and unknown weight semantics do not satisfy this return/weight contract. Preserve incompatible research as an ordinary file with an appropriate name; it remains a standalone outcome.

## Retained validation and eligibility

Gamma reads actual retained bytes through the existing artifact store, verifies byte size and SHA-256 and rechecks the immutable revision/source and input snapshot/manifest/file hashes. Every parsed result carries run, revision, source hash, snapshot, manifest hash, retained artifact reference/hash, declared instruments, methodology, input source refs, runtime/provider and retrieval/transformation evidence. Old artifacts without hashes remain standalone and cannot become eligible by guessing metadata.

Validation is rederived from retained evidence on inspection, opening, saving and export; it is not a mutable selected-run cache. Preview hashes cover the exact provenance, result and mapping. A hash from another run or altered artifact is rejected. Later canonical edits do not change the original run. Restart uses retained execution evidence, not today's runtime selection. Runtime collection separately records whether the retained file identity was newly generated in the exact current run directory and was not a copied input. A citation to an older container file, an outside-directory file or an artifact lacking that evidence is ineligible even if the schema is valid.

Invalid optional output does **not** relabel Python execution as failed or discard valid logs/files. The UI shows execution status separately from analytical validity. A failed/incomplete/unavailable/timed-out/cancelled run cannot open an analysis. Completed safe previews remain explicitly non-executing and ineligible. Eligibility requires completed association-valid execution with both `executes_source` and runtime `executed_code` evidence. Model summaries and provider URLs are never analytical payloads.

## Deliberate mapping, opening and saving

1. **Inspect analytical output** on the selected retained run. Expand the exact result/mapping/provenance preview; inspect observations, identities, conversion, coverage, assumptions and warnings.
2. **Open temporary Strategy Lab analysis** for a supported result. The POST resubmits only run/output/result identity and preview hash; the server rereads all evidence, then calls `ResearchService.analyze_strategy_lab` with exact simple fractional rows. Percent values divide by 100 explicitly. It never resolves a nearby contract or loads a provider/account.
3. The existing Backtest screen renders the temporary analysis and warnings. **Save Strategy** is a separate deliberate action through the existing saved-research service. The server revalidates the retained analytical binding and rejects changed return rows, metrics or provenance before saving; title and notes remain user-controlled. Saved Runs reopening preserves the provenance and exact mapping. **Export analysis JSON** carries the full frozen analysis and binding, including after reopening; Script ZIP export includes raw source/inputs/outputs plus `analytical_validation.json`.

The supported target requires at least five nonmissing observations, no gaps longer than four days, and agreement with owning-service daily inference. It uses the owner's exact 252-period annualization, zero risk-free rate and existing rolling/period-return/drawdown calculations. No benchmark, costs, resampling or missing-value cleaning is silently introduced. Missing data, log returns, other frequencies/calendars or unavailable targets remain standalone with a reason. This is not an independent analytics engine.

**Weight handoff incompatibility:** Composer normalizes signed weights by gross exposure. That can alter signed NAV leverage; a dated weight schedule also cannot be represented by its static composition contract. Risk's research-book path requires an already-computed aggregate return stream and per-leg return histories, which weights alone do not provide. E4 does not authorize fetching histories, discarding shorts, normalizing exposures or selecting a live account. The hypothetical-weight handoff acceptance item remains open; the exact schedules and standalone artifacts are retained.

Operator receives bounded retained validation observations (including validity, warnings, exact artifact/run/source identity and up to 20 observations per result with explicit truncation). This grants no opening/saving/execution tool. Existing Script scope, acquisition/revision/run separation, staged acceptance/rejection, parent conflicts, reviewed-input binding, unsaved protection and failure no-rewrite/no-retry boundaries remain in force.

## Evidence — 2026-10-15

See the active [Script plan](research_script_workspace_plan.md) for current counts and commands. Backend and browser tests use explicitly pinned deterministic runtime artifacts and owning-service inputs; they do not prove Python execution. Return metrics match the owning-service calculation for identical inputs and an independent product of `(1 + fractional_return)`.

The opt-in `GAMMA_RUN_LIVE_SCRIPT_E4=true` test checks the configured runtime before running the supplied-file source. It does not select OpenAI, switch models, increase limits or use host Python to execute the research script. The first run skipped because Script was configured as `mock_safe_preview`. After the user explicitly requested live Script configuration, the local selector changed to `openai` while retaining `gpt-5.6-luna` and all limits. The test then **passed in 17.12s**, proving actual isolated Python → retained structured metric/returns → server validation/current-run association → existing Strategy Lab analytical handoff, independent numerical agreement within `1e-14`, and identical restart inspection. Inputs are supplied synthetic prices; this is no live market-data/provider certification. Hypothetical-weight handoff and E3's separate Operator gate remain open.
