# Research Script Workspace Implementation Plan

_Living implementation and handoff document._

- Decision approved: 2026-08-29
- Last reviewed: 2026-09-04
- Implementation status: Slices 1-5 implemented and verified; Workstream 2A completion gate satisfied
- Roadmap owner: Workstream 2A in [`../roadmap.md`](../roadmap.md)
- Primary product surface: `Strategy Lab / Script`
- Natural-language entry point: Copilot Operator

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
