# Copilot V2 Checkpoint 3 Execution Prompt

Copy the text inside the block below into the AI agent that will implement Copilot V2 Checkpoint 3.

```text
You are the implementation owner for Copilot V2 Checkpoint 3 in:

C:\Users\User\Desktop\Gamma

Your objective is to move Copilot V2 from the verified 80% baseline to the verified 86% gate by completing all of Checkpoint 3: session lifecycle, persistence/replay, and in-tab memo/report artifacts.

This is an implementation task, not a planning-only exercise. Inspect the existing implementation, make the required backend and frontend changes, add tests, verify the running UI, and update the active documentation. Stop after Checkpoint 3 is fully verified. Do not start Checkpoint 4 or broaden Operator mutation capabilities unless a compatibility fix is strictly required for Checkpoint 3.

Do not claim 86% because code was written. Claim it only after every exit criterion below is implemented and proven.

## Read first

Read these files completely before editing:

1. `AGENTS.md`
2. `roadmap.md`, especially `Workstream 7 - Copilot V2`, the 80%-to-100% checkpoint table, sequencing rules, and product boundary
3. `docs/copilot_v2_tab_plan.md`, especially the July 2026 completion plan, Workstreams E/F, delivery order, and definition of done
4. `docs/copilot_v2_handoff_prompt.md` for the broader Copilot architecture and safety constraints
5. `docs/provenance_expectations.md`
6. `docs/design_principles.md` before changing Svelte or CSS
7. `README.md` for supported runtime and validation commands

Then inspect, at minimum:

- `src/models/copilot.py`
- `src/services/copilot_store.py`
- `src/application/copilot_service.py`
- `src/application/copilot_report_service.py`
- `src/api/schemas/copilot.py`
- `src/api/routes/copilot.py`
- `frontend/src/lib/api/types.ts`
- `frontend/src/lib/stores/app.ts`
- `frontend/src/views/CopilotView.svelte`
- `frontend/src/components/CopilotTranscriptResult.svelte`
- the focused Copilot backend and frontend tests

Use `rg` for discovery and `apply_patch` for manual edits. Inspect `git status --short --branch` and all existing uncommitted changes before editing. Preserve unrelated work. Do not commit, push, or open a pull request unless the user separately requests it.

## Verified starting point

Checkpoints 1 and 2 are complete at 80%.

The baseline already includes:

- server-owned Agent and custom-loop Operator runs with typed events, cancellation, timeout, bounded replay, and idempotent terminal persistence;
- one canonical transcript renderer for cards, plans, Operator steps/results, reports, confirmations, mutation diffs, artifacts, evidence, and typed non-success states;
- equivalent result/evidence rendering in the shelf and dedicated workspace;
- claim/source normalization before return and persistence plus defensive validation of legacy records;
- claim-level `CrossTabHandoffEnvelope` navigation that preserves supported entity, mode, timeframe, and lens context;
- local session, turn, context-snapshot, memo, report-generation, and Markdown-export foundations.

Retain the passing baseline. Do not replace the canonical transcript/evidence contract with a separate artifact-specific rendering system.

## Non-negotiable product boundary

Gamma is a read-only market, account, wallet, and execution research environment.

Checkpoint 3 may add local research-state lifecycle operations such as renaming or deleting a Copilot session and editing a memo. It must not add trading, order placement, account mutation, wallet signing, rebalancing, arbitrary code execution, or unrestricted browsing.

Do not broaden durable Operator mutation families. Keep Gamma backend services authoritative for permissions, persistence, confirmation tokens, cancellation, finalization, and mutation rules. Never expose credentials or raw sensitive provider payloads in persisted diagnostics or exports.

## Required delivery

### 1. Complete the session lifecycle

Implement and connect:

- session rename;
- restore/unarchive;
- delete, with an explicit destructive confirmation in the UI;
- archive behavior that remains distinct from deletion;
- selected-session continuity after rename, restore, archive, delete, restart, and filtered search;
- honest empty/not-found/conflict states for stale session ids.

Define deterministic API semantics and typed frontend state for every operation. Avoid optimistic state that can diverge from the store; reconcile from the authoritative response.

### 2. Version and migrate persisted Copilot data

Turn the existing schema-version field into an explicit forward-migration contract for sessions, turns, context snapshots, memos, reports, plans, events, confirmations, artifacts, usage, and trace state.

Requirements:

- declare the current schema version and the supported legacy versions in one authoritative place;
- migrate supported legacy records deterministically and idempotently;
- write migrated records back only through a safe, atomic persistence path;
- preserve unknown fields when safe or document why they are intentionally discarded;
- reject unsupported future versions without destroying them;
- recover from malformed or partially corrupted records without preventing healthy sessions from loading;
- surface a safe, actionable warning for skipped/recovered records;
- do not silently replace corrupted provider-backed records with mock/sample content;
- cover interrupted writes, malformed JSON, missing fields, legacy fields, mixed-version directories, and repeated migration.

Choose and document a recoverable corrupted-record policy, such as quarantining the unreadable file or skipping it while preserving it for inspection. Do not delete the only copy during recovery.

### 3. Persist and replay the complete turn contract

After a process restart, the selected session must faithfully reconstruct:

- role and reasoning depth/effort;
- selected scope domains;
- context fingerprints and context snapshots;
- requested and resolved provider/model metadata;
- run id, terminal status, cancellation outcome, and usage;
- research plans and Operator plans;
- Operator events, tool traces, warnings, and source registry;
- confirmation checkpoints and pending/terminal confirmation state;
- mutation/artifact identifiers and rollback/snapshot references;
- memos, reports, and their exact source-turn links.

Use typed models rather than opaque UI-only blobs where the data participates in replay or export. Reuse the finalized run/transcript contracts from Checkpoints 1 and 2. Add explicit migration/default behavior for legacy records that cannot contain newer fields.

### 4. Build the memo/report workflow inside the Copilot workspace

The dedicated Copilot tab must provide a coherent artifact workflow without requiring backend logs, manual API calls, or a separate floating surface.

Implement:

- an artifact entry point in the selected-session rail or support inspector;
- a list of the selected session's memos and reports;
- source-turn selection, with clear selected counts and unavailable-turn handling;
- template choice for at least a concise memo and a fuller research report;
- editable title and body;
- debounced autosave with visible saving/saved/error state;
- preview using the same evidence/provenance language as the transcript;
- duplicate;
- delete with explicit confirmation;
- explicit overwrite confirmation where an export or replacement would overwrite existing local research state;
- Markdown export/download as the required format;
- stable selection when artifacts are created, renamed, duplicated, deleted, or restored after restart.

Do not add PDF or DOCX unless a real repository requirement already exists. Markdown is the Checkpoint 3 gate.

Keep the UI dense, flat, keyboard-usable, and consistent with Gamma's existing rail/panel patterns. Reuse shared components and tokens. Avoid duplicating large report/card markup already owned by `CopilotTranscriptResult.svelte`.

### 5. Preserve complete artifact provenance

Every memo/report and exported Markdown snapshot must retain enough typed information to audit its origin:

- exact source session and turn ids;
- source memo ids where applicable;
- source-backed claims with inline evidence refs;
- inferred claims, assumptions, and missing-data labels;
- the source registry and relevant freshness/provider metadata;
- warnings and warning provenance;
- context snapshot/fingerprint references;
- provider/model metadata;
- tool-trace summary;
- generated/updated timestamps and transformation note.

Every persisted source-backed claim must continue to resolve through the Checkpoint 2 evidence registry. Unsupported refs must remain reclassified or explicitly unresolved; artifact editing and migration must not resurrect fake citations.

### 6. Keep backend, API, and frontend contracts aligned

Update all affected layers together:

- domain dataclasses/models;
- persistence and migration code;
- service methods;
- API request/response schemas and routes;
- frontend API types and loaders;
- selected-session and artifact state;
- UI components and interaction tests;
- active documentation.

Prefer one authoritative lifecycle and artifact contract over parallel memo/report implementations. Route filesystem work through the existing store boundary and constrain export filenames/content-disposition safely.

## Required test coverage

Add focused happy-path and failure-path coverage for:

- rename, archive, restore, delete, search, and selected-session reconciliation;
- wrong/missing/stale session or artifact ids;
- explicit delete/overwrite confirmation UI;
- schema migration from every supported legacy version;
- idempotent repeated migration;
- unsupported future schema versions;
- malformed JSON, partial records, mixed healthy/corrupt records, and interrupted-write recovery;
- restart replay of role, effort, scopes, fingerprints, plans, run status, usage, traces, confirmations, artifacts, warnings, and sources;
- memo/report create, edit, autosave success/failure/retry, preview, duplicate, delete, and Markdown export;
- source-turn selection and deleted/missing source turns;
- export preservation of claim categories, evidence refs, source metadata, warnings, provider/model metadata, and source-turn links;
- continued evidence normalization after migration, edit, duplicate, reopen, and export;
- keyboard and narrow-layout behavior for the artifact UI.

Tests must prove observable state, not just HTTP 200 responses.

## Verification gate

Run at least:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_copilot.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_copilot_agents_sdk_smoke.py tests\test_copilot_operator_eval.py -q
Set-Location frontend
npm run test
npm run typecheck
npm run build
npm run desktop:check
```

Also perform a real restart/replay check against a temporary Copilot data directory:

1. Create a session and turns containing plan, usage, evidence, warnings, and typed terminal state.
2. Create and edit a memo/report linked to selected turns.
3. Restart the backend/store instance.
4. Reopen the session and prove the transcript, context, plan/run metadata, evidence, confirmations/artifacts, and edited artifact state are faithful.
5. Export Markdown and inspect the actual output.
6. Exercise one corrupted legacy record alongside a healthy record and prove recovery is non-destructive.

Inspect the running Copilot UI at desktop and narrow width. Exercise rename, archive/restore, delete confirmation, source-turn selection, autosave, preview, duplicate, delete, restart reopen, and Markdown export. Check the browser console. Do not claim a live-provider result unless a provider was intentionally configured and actually used.

## Checkpoint 3 exit criteria

Checkpoint 3 reaches 86% only when all of the following are true:

- restarting Gamma faithfully reopens transcript, context snapshots, run metadata, plans, traces, confirmations, memos, reports, and artifact links;
- session rename, restore, delete, migration, and corrupted-record recovery work through typed backend/frontend contracts;
- in-tab memo/report creation, source-turn selection, template, editing, autosave, preview, duplicate, delete, explicit overwrite, and Markdown export are usable and tested;
- artifact exports preserve claim labels, inline evidence refs, source metadata, warnings, provider/model metadata, tool-trace summary, and source-turn links;
- the selected session exposes its artifacts in the rail or support inspector;
- focused and broader backend/frontend/build/desktop checks pass;
- desktop and narrow UI inspection passes without new console errors;
- the read-only product boundary and Checkpoint 2 evidence guarantees remain intact.

## Documentation and handoff

Only after the exit criteria pass:

- update `roadmap.md` from 80% to **86% verified** with the actual date and test evidence;
- update `docs/copilot_v2_tab_plan.md` to mark the session/artifact workstream complete and make Checkpoint 4 the next blocker;
- update `docs/copilot_v2_handoff_prompt.md` to use 86% as the verified baseline;
- update this prompt or move it to `docs/archive/` if it is no longer the active handoff;
- report the exact tests, UI flows, migration fixtures, restart evidence, known limitations, and changed files.

If an exit criterion is not met, leave Copilot at 80%, state exactly what remains, and do not present partial implementation as Checkpoint 3 completion.
```
