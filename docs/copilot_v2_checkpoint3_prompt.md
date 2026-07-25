# Copilot V2 Checkpoint 3 Follow-up Regression Prompt

Copy the text inside the block below into the AI agent that will implement the post-Checkpoint 3 regression fixes.

````text
You are the implementation owner for the focused Copilot V2 Checkpoint 3 regression hardening pass in:

C:\Users\User\Desktop\Gamma

Copilot V2 Checkpoint 3 is verified at 86% as of 2026-07-25. The baseline implementation is commit `d48102b` (`feat: implement Copilot checkpoint 3 lifecycle and artifacts`).

Your objective is to fix the three user-visible regressions discovered during live desktop and narrow-width verification:

1. New Chat does not reliably open a new conversation when another unarchived session exists.
2. An accepted prompt remains in the composer after it is sent, especially when the provider later returns an error.
3. The orange storage-recovery warning is persistent, unclear, and can obstruct composer or artifact controls.

This is an implementation task, not a planning-only exercise. Inspect the existing behavior, implement the backend/frontend contract changes needed, add focused tests, verify desktop and narrow layouts, and update the active documentation only to record the fixes. Do not start Checkpoint 4, broaden Operator mutation capabilities, or change Gamma's read-only boundary.

## Read first

Read these files completely before editing:

1. `AGENTS.md`
2. `roadmap.md`, especially Workstream 7 and the verified 86% baseline
3. `docs/copilot_v2_tab_plan.md`
4. `docs/provenance_expectations.md`
5. `docs/design_principles.md`
6. `README.md`

Then inspect, at minimum:

- `frontend/src/views/CopilotView.svelte`
- `frontend/src/components/CopilotArtifactsPanel.svelte`
- `frontend/src/App.svelte`
- `frontend/src/lib/stores/app.ts`
- `frontend/src/lib/stores/copilot-lifecycle.test.ts`
- `frontend/src/views/CopilotView.test.ts`
- `src/models/copilot.py`
- `src/services/copilot_store.py`
- `src/application/copilot_service.py`
- `src/api/schemas/copilot.py`
- `src/api/routes/copilot.py`
- `tests/test_copilot.py`

Use `rg` for discovery and `apply_patch` for manual edits. Inspect `git status --short --branch` and preserve unrelated work. Do not commit, push, or open a pull request unless the user separately requests it.

## Verified observations and likely causes

### New Chat reconciliation bug

The current frontend path calls `startNewCopilotSession()`, assigns a client-generated session id, clears local detail, and then immediately calls `handleLoadCopilotWorkspaceState()`. `loadActiveCopilotSession()` requests the new id, receives not-found because no authoritative session record exists yet, and reconciles to the first existing session. This makes New Chat appear ineffective whenever an existing conversation is available.

Do not fix this with a UI-only timeout or by suppressing reconciliation errors. Define one authoritative new-session contract. Either create an empty session through a typed backend endpoint before selecting it or retain a clearly typed local unsaved-session state that is not treated as a stale persisted id. Prefer the server-authoritative approach if it fits the existing store boundary cleanly.

### Composer-clearing bug

`CopilotView.svelte` currently clears `promptText` only when the final result status is `ready`. A prompt that was accepted, persisted as a turn, and later ends in quota exhaustion or another typed non-success state therefore remains in the textarea even though Retry is already available from the persisted turn.

Clear the composer when submission is authoritatively accepted or a run/turn is created, not only after a successful final answer. Preserve the draft only when submission is rejected before acceptance. A quota, provider, refusal, incomplete, cancellation, or tool-availability outcome after acceptance must not repopulate the textarea. Retry must continue to use the persisted last-turn prompt and must not depend on stale composer text.

### Storage-recovery warning obstruction

The orange message:

`Copilot preserved N skipped or recovered storage records for inspection.`

is the real Checkpoint 3 non-destructive recovery warning. It must not be deleted or hidden permanently. Its current absolutely positioned bottom-right presentation is unclear and can overlap the pinned composer or the artifact inspector, particularly at narrow widths.

Move it into a non-obstructive status/diagnostics pattern. It should:

- explain briefly that the original records were preserved and healthy sessions remain usable;
- expose safe details or an inspection affordance without revealing sensitive payloads;
- be dismissible for the current UI session without deleting the recovery record or warning history;
- remain discoverable after dismissal through the Copilot support inspector or another existing diagnostics surface;
- never cover composer, artifact edit, duplicate, delete, preview, export, or confirmation controls;
- behave correctly at desktop and narrow widths;
- remain keyboard- and screen-reader-usable.

The blue robot visible in the supplied screenshots does not appear to be a Gamma repository asset. Do not add Gamma-specific layout hacks for an external desktop/testing overlay unless code inspection proves otherwise.

## Required session-state semantics

Model and present these concepts distinctly:

- `selected`: the session currently displayed in the workspace;
- `inactive`: another normal, unarchived session that can be selected or followed up;
- `running`: a session with a non-terminal server-owned run, whether selected or not;
- `archived`: a retained session excluded from the normal list unless archived sessions are requested.

Selection must not be treated as proof that a run is active. An existing selected or inactive conversation must never prevent creating a new blank session.

If the current run contract supports switching away while a run continues, allow New Chat and session switching without silently cancelling the run, retain a visible running indicator on the source session, and reconcile it through normal replay. If a genuine backend invariant prevents that behavior, show an explicit explanation and safe actions; do not silently make New Chat do nothing.

New Chat must:

- create exactly one authoritative blank session;
- select it immediately;
- show an empty transcript and clean composer;
- retain other unarchived sessions as inactive/selectable;
- survive session refresh, search filtering, and process restart;
- avoid creating duplicate empty sessions on double activation;
- produce honest error state if creation fails.

## Required test coverage

Add focused observable-state tests for:

- creating and selecting a new session while another unarchived session exists;
- creating a new session while another session is selected;
- behavior while a run is pending/streaming, including no silent cancellation;
- double-click/double-submit protection for New Chat;
- authoritative create failure and stale-id reconciliation;
- selected, inactive, running, and archived presentation;
- composer clearing after an accepted Agent or Operator submission;
- composer clearing when the accepted run ends in quota error, provider error, refusal, incomplete, cancellation, timeout, or zero-tool Operator result;
- draft preservation when submission fails before acceptance;
- Retry using the persisted turn prompt after the composer has cleared;
- storage warning details, dismissal, rediscovery, persistence semantics, and safe content;
- warning layout not covering controls at desktop and narrow widths;
- keyboard focus and screen-reader labels for New Chat and recovery diagnostics.

Retain the passing Checkpoint 3 lifecycle, migration, restart, artifact, evidence, and export tests.

## Verification

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

Inspect the running Copilot UI at desktop and narrow width. Exercise:

1. Existing selected session -> New Chat -> new empty selected session.
2. Follow-up on an inactive session and return to the new session.
3. Accepted Agent and Operator submissions ending in both ready and typed failure states.
4. Retry after the composer has cleared.
5. Storage-recovery warning details, dismissal, rediscovery, and non-overlap with the composer and artifact controls.
6. Archive/restore/delete and artifact create/edit/duplicate/delete to ensure no Checkpoint 3 regression.

Check the browser console. A real `quota_exceeded` response is an expected provider limitation when the account has no credits, but the UI must classify it honestly and remain usable. Do not claim successful live-provider output unless a provider was intentionally funded/configured and actually returned it.

## Completion criteria

This follow-up is complete only when:

- New Chat creates and selects an authoritative empty session regardless of other inactive conversations;
- selected, inactive, running, and archived states are no longer conflated;
- accepted prompts clear from the composer while pre-acceptance failures preserve the draft;
- Retry uses persisted prompt state;
- recovery warnings remain auditable but no longer obstruct work;
- desktop and narrow UI checks pass without new console errors;
- the full Checkpoint 3 automated baseline remains green;
- Gamma remains read-only and no Checkpoint 4 mutation/operator scope is added.

Report the exact changed files, tests, UI flows, known limitations, and whether any live provider was actually used. Do not change the verified 86% checkpoint or claim Checkpoint 4 progress for this regression pass.
````
